"""
Embedding Generator for Ominis Health LLM
Generates vector embeddings for document chunks
"""

import os
import json
import numpy as np
from typing import List, Dict, Any, Optional
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class EmbeddingGenerator:
    """Generate embeddings for text using sentence-transformers"""
    
    def __init__(self, model_name: str = 'sentence-transformers/all-MiniLM-L6-v2'):
        """
        Initialize embedding generator
        
        Args:
            model_name: HuggingFace model name for embeddings
        """
        self.model_name = model_name
        self.model = None
        self.embedding_dim = None
    
    def _load_model(self):
        """Lazy load the embedding model"""
        if self.model is None:
            logger.info(f"Loading embedding model: {self.model_name}")
            from sentence_transformers import SentenceTransformer
            self.model = SentenceTransformer(self.model_name)
            # Get embedding dimension from a test embedding
            test_embedding = self.model.encode(['test'])
            self.embedding_dim = test_embedding.shape[1]
            logger.info(f"Model loaded. Embedding dimension: {self.embedding_dim}")
    
    def embed_texts(self, texts: List[str], batch_size: int = 32) -> np.ndarray:
        """
        Generate embeddings for a list of texts
        
        Args:
            texts: List of text strings
            batch_size: Batch size for encoding
            
        Returns:
            numpy array of embeddings (n_texts x embedding_dim)
        """
        self._load_model()
        
        logger.info(f"Generating embeddings for {len(texts)} texts...")
        embeddings = self.model.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=True,
            convert_to_numpy=True
        )
        
        return embeddings
    
    def embed_chunks(self, chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Add embeddings to chunk dictionaries
        
        Args:
            chunks: List of chunk dictionaries with 'content' field
            
        Returns:
            Chunks with added 'embedding' field
        """
        texts = [chunk['content'] for chunk in chunks]
        embeddings = self.embed_texts(texts)
        
        for chunk, embedding in zip(chunks, embeddings):
            chunk['embedding'] = embedding.tolist()
        
        return chunks
    
    def get_embedding_dim(self) -> int:
        """Get the dimension of embeddings"""
        self._load_model()
        return self.embedding_dim


class BedrockEmbeddingGenerator:
    """Generate embeddings using AWS Bedrock (for production)"""
    
    def __init__(self, model_id: str = 'amazon.titan-embed-text-v1', region: str = 'us-east-2'):
        """
        Initialize Bedrock embedding generator
        
        Args:
            model_id: Bedrock model ID for embeddings
            region: AWS region
        """
        import boto3
        self.model_id = model_id
        self.bedrock = boto3.client('bedrock-runtime', region_name=region)
        self.embedding_dim = 1536  # Titan embed dimension
    
    def embed_texts(self, texts: List[str], batch_size: int = 10) -> np.ndarray:
        """
        Generate embeddings using Bedrock
        
        Args:
            texts: List of texts
            batch_size: Batch size (Bedrock has limits)
            
        Returns:
            numpy array of embeddings
        """
        embeddings = []
        
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            
            for text in batch:
                body = json.dumps({'inputText': text[:8000]})  # Titan has 8k limit
                
                response = self.bedrock.invoke_model(
                    modelId=self.model_id,
                    body=body,
                    contentType='application/json',
                    accept='application/json'
                )
                
                result = json.loads(response['body'].read())
                embeddings.append(result['embedding'])
        
        return np.array(embeddings)
    
    def embed_chunks(self, chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Add embeddings to chunks using Bedrock"""
        texts = [chunk['content'] for chunk in chunks]
        embeddings = self.embed_texts(texts)
        
        for chunk, embedding in zip(chunks, embeddings):
            chunk['embedding'] = embedding.tolist()
        
        return chunks
    
    def get_embedding_dim(self) -> int:
        return self.embedding_dim


def create_embedder(use_bedrock: bool = False, **kwargs) -> Any:
    """
    Factory function to create appropriate embedder
    
    Args:
        use_bedrock: If True, use AWS Bedrock; otherwise use local model
        **kwargs: Additional arguments for embedder
        
    Returns:
        Embedder instance
    """
    if use_bedrock:
        return BedrockEmbeddingGenerator(**kwargs)
    return EmbeddingGenerator(**kwargs)


if __name__ == '__main__':
    # Test embedding generation
    embedder = EmbeddingGenerator()
    
    test_texts = [
        "Diabetes is a chronic metabolic disease.",
        "Hypertension requires regular blood pressure monitoring.",
        "Vaccination is important for preventing infectious diseases."
    ]
    
    embeddings = embedder.embed_texts(test_texts)
    
    print(f"Generated {len(embeddings)} embeddings")
    print(f"Embedding dimension: {embeddings.shape[1]}")
    print(f"First embedding (preview): {embeddings[0][:5]}...")
    
    # Test similarity
    from numpy.linalg import norm
    
    def cosine_similarity(a, b):
        return np.dot(a, b) / (norm(a) * norm(b))
    
    print(f"\nSimilarity between text 0 and 1: {cosine_similarity(embeddings[0], embeddings[1]):.4f}")
    print(f"Similarity between text 0 and 2: {cosine_similarity(embeddings[0], embeddings[2]):.4f}")
