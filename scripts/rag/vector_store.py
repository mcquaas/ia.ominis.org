"""
Vector Store for Ominis Health LLM
Stores and retrieves document embeddings using FAISS
"""

import os
import json
import pickle
import numpy as np
from typing import List, Dict, Any, Tuple, Optional
import logging
import boto3

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class FAISSVectorStore:
    """Vector store using FAISS for similarity search"""
    
    def __init__(self, embedding_dim: int = 384):
        """
        Initialize FAISS vector store
        
        Args:
            embedding_dim: Dimension of embeddings
        """
        import faiss
        
        self.embedding_dim = embedding_dim
        self.index = faiss.IndexFlatIP(embedding_dim)  # Inner product (cosine with normalized vectors)
        self.chunks: List[Dict[str, Any]] = []
        self.id_to_idx: Dict[str, int] = {}
    
    def add_chunks(self, chunks: List[Dict[str, Any]]):
        """
        Add chunks with embeddings to the store
        
        Args:
            chunks: List of chunks with 'id', 'content', 'embedding', 'metadata'
        """
        if not chunks:
            return
        
        # Extract embeddings
        embeddings = np.array([chunk['embedding'] for chunk in chunks], dtype=np.float32)
        
        # Normalize for cosine similarity
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        embeddings = embeddings / norms
        
        # Add to FAISS index
        start_idx = len(self.chunks)
        self.index.add(embeddings)
        
        # Store chunks and mapping
        for i, chunk in enumerate(chunks):
            self.id_to_idx[chunk['id']] = start_idx + i
            # Store chunk without embedding (save memory)
            chunk_copy = {k: v for k, v in chunk.items() if k != 'embedding'}
            self.chunks.append(chunk_copy)
        
        logger.info(f"Added {len(chunks)} chunks. Total: {len(self.chunks)}")
    
    def search(
        self,
        query_embedding: np.ndarray,
        k: int = 5,
        threshold: float = 0.0
    ) -> List[Tuple[Dict[str, Any], float]]:
        """
        Search for similar chunks
        
        Args:
            query_embedding: Query embedding vector
            k: Number of results to return
            threshold: Minimum similarity threshold
            
        Returns:
            List of (chunk, score) tuples
        """
        if len(self.chunks) == 0:
            return []
        
        # Normalize query
        query = np.array([query_embedding], dtype=np.float32)
        query = query / np.linalg.norm(query)
        
        # Search
        scores, indices = self.index.search(query, min(k, len(self.chunks)))
        
        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx >= 0 and score >= threshold:
                results.append((self.chunks[idx], float(score)))
        
        return results
    
    def save(self, path: str):
        """
        Save vector store to disk
        
        Args:
            path: Directory path to save to
        """
        import faiss
        
        os.makedirs(path, exist_ok=True)
        
        # Save FAISS index
        faiss.write_index(self.index, os.path.join(path, 'index.faiss'))
        
        # Save chunks and metadata
        with open(os.path.join(path, 'chunks.json'), 'w') as f:
            json.dump(self.chunks, f, ensure_ascii=False)
        
        with open(os.path.join(path, 'metadata.json'), 'w') as f:
            json.dump({
                'embedding_dim': self.embedding_dim,
                'num_chunks': len(self.chunks),
                'id_to_idx': self.id_to_idx
            }, f)
        
        logger.info(f"Saved vector store to {path}")
    
    @classmethod
    def load(cls, path: str) -> 'FAISSVectorStore':
        """
        Load vector store from disk
        
        Args:
            path: Directory path to load from
            
        Returns:
            Loaded FAISSVectorStore instance
        """
        import faiss
        
        # Load metadata
        with open(os.path.join(path, 'metadata.json'), 'r') as f:
            metadata = json.load(f)
        
        # Create instance
        store = cls(embedding_dim=metadata['embedding_dim'])
        
        # Load FAISS index
        store.index = faiss.read_index(os.path.join(path, 'index.faiss'))
        
        # Load chunks
        with open(os.path.join(path, 'chunks.json'), 'r') as f:
            store.chunks = json.load(f)
        
        store.id_to_idx = metadata['id_to_idx']
        
        logger.info(f"Loaded vector store from {path} ({len(store.chunks)} chunks)")
        return store
    
    def save_to_s3(self, bucket: str, prefix: str, region: str = 'us-east-2'):
        """
        Save vector store to S3
        
        Args:
            bucket: S3 bucket name
            prefix: S3 key prefix
            region: AWS region
        """
        import tempfile
        
        s3 = boto3.client('s3', region_name=region)
        
        # Save to temp directory first
        with tempfile.TemporaryDirectory() as tmpdir:
            self.save(tmpdir)
            
            # Upload files
            for filename in ['index.faiss', 'chunks.json', 'metadata.json']:
                local_path = os.path.join(tmpdir, filename)
                s3_key = f"{prefix}/{filename}"
                
                s3.upload_file(local_path, bucket, s3_key)
                logger.info(f"Uploaded {s3_key}")
        
        logger.info(f"Vector store saved to s3://{bucket}/{prefix}/")
    
    @classmethod
    def load_from_s3(cls, bucket: str, prefix: str, region: str = 'us-east-2') -> 'FAISSVectorStore':
        """
        Load vector store from S3
        
        Args:
            bucket: S3 bucket name
            prefix: S3 key prefix
            region: AWS region
            
        Returns:
            Loaded FAISSVectorStore instance
        """
        import tempfile
        
        s3 = boto3.client('s3', region_name=region)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Download files
            for filename in ['index.faiss', 'chunks.json', 'metadata.json']:
                s3_key = f"{prefix}/{filename}"
                local_path = os.path.join(tmpdir, filename)
                
                s3.download_file(bucket, s3_key, local_path)
                logger.info(f"Downloaded {s3_key}")
            
            return cls.load(tmpdir)


class VectorStoreManager:
    """Manage vector store operations with S3 integration"""
    
    def __init__(
        self,
        s3_bucket: str = 'ominis-health-embeddings',
        prefix: str = 'vectors',
        region: str = 'us-east-2'
    ):
        self.s3_bucket = s3_bucket
        self.prefix = prefix
        self.region = region
        self.store: Optional[FAISSVectorStore] = None
    
    def create_store(self, embedding_dim: int = 384) -> FAISSVectorStore:
        """Create a new vector store"""
        self.store = FAISSVectorStore(embedding_dim=embedding_dim)
        return self.store
    
    def load_store(self) -> FAISSVectorStore:
        """Load store from S3"""
        self.store = FAISSVectorStore.load_from_s3(
            self.s3_bucket, self.prefix, self.region
        )
        return self.store
    
    def save_store(self):
        """Save current store to S3"""
        if self.store:
            self.store.save_to_s3(self.s3_bucket, self.prefix, self.region)
    
    def get_store(self) -> Optional[FAISSVectorStore]:
        """Get current store"""
        return self.store


if __name__ == '__main__':
    # Test vector store
    import numpy as np
    
    # Create store
    store = FAISSVectorStore(embedding_dim=384)
    
    # Add some test chunks
    test_chunks = [
        {
            'id': 'chunk-1',
            'content': 'Diabetes management requires regular monitoring.',
            'embedding': np.random.randn(384).tolist(),
            'metadata': {'source': 'test'}
        },
        {
            'id': 'chunk-2',
            'content': 'Hypertension is a common cardiovascular condition.',
            'embedding': np.random.randn(384).tolist(),
            'metadata': {'source': 'test'}
        }
    ]
    
    store.add_chunks(test_chunks)
    
    # Test search
    query_embedding = np.random.randn(384)
    results = store.search(query_embedding, k=2)
    
    print(f"Search results:")
    for chunk, score in results:
        print(f"  Score: {score:.4f} - {chunk['content'][:50]}...")
    
    # Test save/load
    store.save('/tmp/test_vector_store')
    loaded_store = FAISSVectorStore.load('/tmp/test_vector_store')
    print(f"\nLoaded store with {len(loaded_store.chunks)} chunks")
