#!/usr/bin/env python3
"""
Add Mexican Health Sources to RAG Index
Loads local Mexican health documents and adds them to the vector store
"""

import os
import sys
import json
import glob
from typing import List, Dict, Any
from datetime import datetime, timezone
import logging
import argparse

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from chunker import DocumentChunker
from embedder import create_embedder
from vector_store import FAISSVectorStore

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_mexican_health_sources(data_dir: str) -> List[Dict[str, Any]]:
    """
    Load Mexican health sources from local JSON files
    """
    documents = []
    
    pattern = os.path.join(data_dir, '*.json')
    files = glob.glob(pattern)
    
    with_pdf = 0
    by_source = {}
    
    for filepath in files:
        basename = os.path.basename(filepath)
        if basename in ['manifest.json', 'ingestion_summary.json']:
            continue
            
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                doc = json.load(f)
            
            if not doc.get('content'):
                continue
            
            # Add categories for chunker compatibility
            doc['categories'] = [doc.get('category', 'General')]
            
            # Track stats
            source = doc.get('source', 'Unknown')
            by_source[source] = by_source.get(source, 0) + 1
            
            if doc.get('has_pdf_content'):
                with_pdf += 1
            
            documents.append(doc)
            
        except Exception as e:
            logger.error(f"Error loading {filepath}: {e}")
    
    logger.info(f"Loaded {len(documents)} Mexican health sources from {data_dir}")
    logger.info(f"  - With PDF content: {with_pdf}")
    logger.info(f"  - By source: {by_source}")
    
    return documents


def add_to_rag(
    documents: List[Dict[str, Any]],
    output_dir: str = None,
    chunk_size: int = 512,
    chunk_overlap: int = 50
) -> Dict[str, Any]:
    """
    Add documents to RAG system
    """
    if output_dir is None:
        output_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            'data', 'embeddings', 'mexican_health_sources'
        )
    
    os.makedirs(output_dir, exist_ok=True)
    
    summary = {
        'started_at': datetime.now(timezone.utc).isoformat(),
        'document_count': len(documents),
        'documents_with_pdf': sum(1 for d in documents if d.get('has_pdf_content'))
    }
    
    # Initialize components
    chunker = DocumentChunker(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    embedder = create_embedder(use_bedrock=False)
    
    # Chunk documents
    logger.info("Chunking documents...")
    all_chunks = []
    for doc in documents:
        chunks = chunker.chunk_document(doc)
        all_chunks.extend([chunker.chunk_to_dict(c) for c in chunks])
    
    summary['chunk_count'] = len(all_chunks)
    logger.info(f"Created {len(all_chunks)} chunks from {len(documents)} documents")
    
    # Generate embeddings
    logger.info("Generating embeddings...")
    chunks_with_embeddings = embedder.embed_chunks(all_chunks)
    summary['embedding_dim'] = len(chunks_with_embeddings[0]['embedding'])
    
    # Build vector store
    logger.info("Building vector store...")
    vector_store = FAISSVectorStore(embedding_dim=summary['embedding_dim'])
    vector_store.add_chunks(chunks_with_embeddings)
    
    # Save
    logger.info(f"Saving to {output_dir}...")
    vector_store.save(output_dir)
    
    # Save chunks without embeddings
    chunks_file = os.path.join(output_dir, 'chunks.json')
    chunks_for_save = [{k: v for k, v in c.items() if k != 'embedding'} for c in chunks_with_embeddings]
    with open(chunks_file, 'w', encoding='utf-8') as f:
        json.dump(chunks_for_save, ensure_ascii=False, indent=2, fp=f)
    
    summary['completed_at'] = datetime.now(timezone.utc).isoformat()
    summary['output_dir'] = output_dir
    
    # Save summary
    summary_file = os.path.join(output_dir, 'build_summary.json')
    with open(summary_file, 'w', encoding='utf-8') as f:
        json.dump(summary, ensure_ascii=False, indent=2, fp=f)
    
    logger.info("RAG indexing complete!")
    return summary


def main():
    parser = argparse.ArgumentParser(description='Add Mexican health sources to RAG')
    parser.add_argument('--data-dir', 
                        default=os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 
                                            'data', 'mexican_health_sources'),
                        help='Directory with source JSON files')
    parser.add_argument('--output-dir', help='Output directory for embeddings')
    parser.add_argument('--chunk-size', type=int, default=512)
    parser.add_argument('--chunk-overlap', type=int, default=50)
    
    args = parser.parse_args()
    
    documents = load_mexican_health_sources(args.data_dir)
    
    if not documents:
        logger.error("No documents found!")
        sys.exit(1)
    
    summary = add_to_rag(
        documents,
        output_dir=args.output_dir,
        chunk_size=args.chunk_size,
        chunk_overlap=args.chunk_overlap
    )
    
    print("\n" + "=" * 60)
    print("MEXICAN HEALTH SOURCES RAG INDEXING COMPLETE")
    print("=" * 60)
    print(f"Documents processed: {summary['document_count']}")
    print(f"Documents with PDF: {summary['documents_with_pdf']}")
    print(f"Chunks created: {summary['chunk_count']}")
    print(f"Embedding dimension: {summary['embedding_dim']}")
    print(f"Output directory: {summary['output_dir']}")


if __name__ == '__main__':
    main()
