#!/usr/bin/env python3
"""
RAG Index Builder for Ominis Health LLM
Downloads documents from S3, chunks them, generates embeddings, and builds vector index
"""

import os
import sys
import json
import boto3
import argparse
from typing import List, Dict, Any
from datetime import datetime
import logging

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from chunker import DocumentChunker
from embedder import EmbeddingGenerator, create_embedder
from vector_store import FAISSVectorStore

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class RAGIndexBuilder:
    """Build RAG index from S3 documents"""
    
    def __init__(
        self,
        raw_bucket: str = 'ominis-health-raw-data-mx',
        processed_bucket: str = 'ominis-health-processed-data-mx',
        embeddings_bucket: str = 'ominis-health-embeddings-mx',
        region: str = 'mx-central-1',
        use_bedrock: bool = False
    ):
        self.raw_bucket = raw_bucket
        self.processed_bucket = processed_bucket
        self.embeddings_bucket = embeddings_bucket
        self.region = region
        
        self.s3 = boto3.client('s3', region_name=region)
        self.chunker = DocumentChunker(chunk_size=512, chunk_overlap=50)
        self.embedder = create_embedder(use_bedrock=use_bedrock)
        self.vector_store = None
    
    def load_documents_from_s3(self, prefix: str = 'wordpress/posts') -> List[Dict[str, Any]]:
        """
        Load documents from S3
        
        Args:
            prefix: S3 prefix to load from
            
        Returns:
            List of document dictionaries
        """
        documents = []
        
        # List objects
        paginator = self.s3.get_paginator('list_objects_v2')
        
        for page in paginator.paginate(Bucket=self.raw_bucket, Prefix=prefix):
            for obj in page.get('Contents', []):
                key = obj['Key']
                if key.endswith('.json') and not key.endswith('manifest.json'):
                    try:
                        response = self.s3.get_object(Bucket=self.raw_bucket, Key=key)
                        doc = json.loads(response['Body'].read().decode('utf-8'))
                        documents.append(doc)
                    except Exception as e:
                        logger.error(f"Error loading {key}: {e}")
        
        logger.info(f"Loaded {len(documents)} documents from s3://{self.raw_bucket}/{prefix}")
        return documents
    
    def chunk_documents(self, documents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Chunk all documents
        
        Args:
            documents: List of documents
            
        Returns:
            List of chunk dictionaries
        """
        all_chunks = []
        
        for doc in documents:
            chunks = self.chunker.chunk_document(doc)
            for chunk in chunks:
                all_chunks.append(self.chunker.chunk_to_dict(chunk))
        
        logger.info(f"Created {len(all_chunks)} chunks from {len(documents)} documents")
        return all_chunks
    
    def save_chunks_to_s3(self, chunks: List[Dict[str, Any]]):
        """
        Save processed chunks to S3
        
        Args:
            chunks: List of chunk dictionaries
        """
        # Save all chunks as a single file
        key = 'chunks/all_chunks.json'
        self.s3.put_object(
            Bucket=self.processed_bucket,
            Key=key,
            Body=json.dumps(chunks, ensure_ascii=False),
            ContentType='application/json'
        )
        logger.info(f"Saved chunks to s3://{self.processed_bucket}/{key}")
    
    def generate_embeddings(self, chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Generate embeddings for all chunks
        
        Args:
            chunks: List of chunk dictionaries
            
        Returns:
            Chunks with embeddings added
        """
        return self.embedder.embed_chunks(chunks)
    
    def build_vector_store(self, chunks_with_embeddings: List[Dict[str, Any]]) -> FAISSVectorStore:
        """
        Build FAISS vector store from chunks
        
        Args:
            chunks_with_embeddings: Chunks with embedding field
            
        Returns:
            Built vector store
        """
        embedding_dim = len(chunks_with_embeddings[0]['embedding'])
        self.vector_store = FAISSVectorStore(embedding_dim=embedding_dim)
        self.vector_store.add_chunks(chunks_with_embeddings)
        return self.vector_store
    
    def save_vector_store(self, prefix: str = 'vectors'):
        """Save vector store to S3"""
        if self.vector_store:
            self.vector_store.save_to_s3(self.embeddings_bucket, prefix, self.region)
    
    def run_pipeline(self, prefixes: List[str] = None) -> Dict[str, Any]:
        """
        Run the full indexing pipeline
        
        Args:
            prefixes: List of S3 prefixes to process
            
        Returns:
            Pipeline summary
        """
        if prefixes is None:
            prefixes = ['tainacan/collection_97']  # Default to Tainacan health sources
        
        summary = {
            'started_at': datetime.utcnow().isoformat(),
            'prefixes': prefixes
        }
        
        # Load all documents
        all_documents = []
        for prefix in prefixes:
            docs = self.load_documents_from_s3(prefix)
            all_documents.extend(docs)
        
        summary['total_documents'] = len(all_documents)
        
        if not all_documents:
            logger.warning("No documents found!")
            return summary
        
        # Chunk documents
        chunks = self.chunk_documents(all_documents)
        summary['total_chunks'] = len(chunks)
        
        # Save chunks
        self.save_chunks_to_s3(chunks)
        
        # Generate embeddings
        logger.info("Generating embeddings...")
        chunks_with_embeddings = self.generate_embeddings(chunks)
        summary['embedding_dim'] = len(chunks_with_embeddings[0]['embedding'])
        
        # Build vector store
        logger.info("Building vector store...")
        self.build_vector_store(chunks_with_embeddings)
        
        # Save vector store
        logger.info("Saving vector store to S3...")
        self.save_vector_store()
        
        summary['completed_at'] = datetime.utcnow().isoformat()
        
        # Save summary
        self.s3.put_object(
            Bucket=self.embeddings_bucket,
            Key='vectors/build_summary.json',
            Body=json.dumps(summary, ensure_ascii=False, indent=2),
            ContentType='application/json'
        )
        
        logger.info("Pipeline complete!")
        return summary


def main():
    parser = argparse.ArgumentParser(description='Build RAG index from S3 documents')
    parser.add_argument('--raw-bucket', default='ominis-health-raw-data-mx',
                        help='S3 bucket with raw documents')
    parser.add_argument('--processed-bucket', default='ominis-health-processed-data-mx',
                        help='S3 bucket for processed data')
    parser.add_argument('--embeddings-bucket', default='ominis-health-embeddings-mx',
                        help='S3 bucket for embeddings')
    parser.add_argument('--prefixes', nargs='+', 
                        default=['tainacan/collection_97'],
                        help='S3 prefixes to process')
    parser.add_argument('--use-bedrock', action='store_true',
                        help='Use AWS Bedrock for embeddings')
    
    args = parser.parse_args()
    
    builder = RAGIndexBuilder(
        raw_bucket=args.raw_bucket,
        processed_bucket=args.processed_bucket,
        embeddings_bucket=args.embeddings_bucket,
        use_bedrock=args.use_bedrock
    )
    
    summary = builder.run_pipeline(prefixes=args.prefixes)
    
    print("\n" + "=" * 60)
    print("INDEX BUILD SUMMARY")
    print("=" * 60)
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
