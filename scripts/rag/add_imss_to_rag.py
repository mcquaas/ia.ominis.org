#!/usr/bin/env python3
"""
Add Medical Guidelines to RAG Index
Loads local guidelines (IMSS, ISSSTE, etc.) and adds them to the vector store
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


def clean_category(category: str) -> str:
    """Clean category string by removing 'Archivos:' and PDF references"""
    if not category:
        return "General"
    
    # Split at 'Archivos:' and take first part
    if 'Archivos:' in category:
        category = category.split('Archivos:')[0].strip()
    
    return category if category else "General"


def load_guidelines_from_dir(data_dir: str, institution: str = None) -> List[Dict[str, Any]]:
    """
    Load guidelines from local JSON files
    
    Args:
        data_dir: Directory containing the JSON files
        institution: Override institution name (IMSS, ISSSTE, etc.)
        
    Returns:
        List of document dictionaries
    """
    documents = []
    
    pattern = os.path.join(data_dir, '*.json')
    files = glob.glob(pattern)
    
    for filepath in files:
        if 'manifest.json' in filepath:
            continue
            
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                doc = json.load(f)
            
            # Detect institution from metadata or override
            doc_institution = institution or doc.get('metadata', {}).get('institution', 'Unknown')
            
            # Clean up the category
            doc['category'] = clean_category(doc.get('category', ''))
            
            # Add categories list for compatibility with chunker
            doc['categories'] = [doc['category']]
            
            # Extract clean title
            title = doc.get('title', '')
            
            # Build richer content based on institution
            if doc_institution == 'IMSS':
                content_parts = [
                    f"Guía de Práctica Clínica del IMSS (Instituto Mexicano del Seguro Social): {title}",
                    "",
                    f"Institución: IMSS - Instituto Mexicano del Seguro Social",
                    f"Categoría médica: {doc['category']}",
                    "",
                    "Esta guía de práctica clínica del Instituto Mexicano del Seguro Social (IMSS) "
                    "proporciona recomendaciones basadas en evidencia para el diagnóstico, "
                    "tratamiento y manejo de pacientes.",
                    ""
                ]
            elif doc_institution == 'ISSSTE':
                content_parts = [
                    f"Guía Operativa del ISSSTE (Instituto de Seguridad y Servicios Sociales de los Trabajadores del Estado): {title}",
                    "",
                    f"Institución: ISSSTE - Instituto de Seguridad y Servicios Sociales de los Trabajadores del Estado",
                    f"Categoría: {doc['category']}",
                    "",
                    "Esta guía operativa del ISSSTE proporciona lineamientos y recomendaciones "
                    "para los profesionales de la salud en el manejo de situaciones clínicas y operativas.",
                    ""
                ]
            else:
                content_parts = [
                    f"Guía de Salud: {title}",
                    "",
                    f"Institución: {doc_institution}",
                    f"Categoría: {doc['category']}",
                    ""
                ]
            
            # Add PDF links as searchable content
            pdf_links = doc.get('pdf_links', [])
            if pdf_links:
                content_parts.append("Documentos de referencia disponibles:")
                for pdf in pdf_links:
                    pdf_type = pdf.get('type', 'PDF')
                    if pdf_type == 'GER':
                        content_parts.append(f"- Guía de Evidencias y Recomendaciones (GER): documento completo")
                    elif pdf_type == 'GRR':
                        content_parts.append(f"- Guía de Referencia Rápida (GRR): resumen para consulta rápida")
                    else:
                        content_parts.append(f"- {pdf.get('label', 'Documento PDF')}")
            
            doc['content'] = '\n'.join(content_parts)
            
            # Ensure metadata has institution
            if 'metadata' not in doc:
                doc['metadata'] = {}
            doc['metadata']['institution'] = doc_institution
            
            documents.append(doc)
            
        except Exception as e:
            logger.error(f"Error loading {filepath}: {e}")
    
    logger.info(f"Loaded {len(documents)} guidelines from {data_dir}")
    return documents


def load_imss_guidelines(data_dir: str) -> List[Dict[str, Any]]:
    """Load IMSS guidelines - wrapper for backward compatibility"""
    return load_guidelines_from_dir(data_dir, institution='IMSS')


def load_issste_guidelines(data_dir: str) -> List[Dict[str, Any]]:
    """Load ISSSTE guidelines"""
    return load_guidelines_from_dir(data_dir, institution='ISSSTE')


def add_to_rag(
    documents: List[Dict[str, Any]],
    output_dir: str = None,
    chunk_size: int = 512,
    chunk_overlap: int = 50
) -> Dict[str, Any]:
    """
    Add documents to RAG system (local mode)
    
    Args:
        documents: List of document dictionaries
        output_dir: Directory to save the index
        chunk_size: Chunk size for splitting
        chunk_overlap: Overlap between chunks
        
    Returns:
        Summary dictionary
    """
    if output_dir is None:
        output_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            'data', 'embeddings', 'imss_guidelines'
        )
    
    os.makedirs(output_dir, exist_ok=True)
    
    summary = {
        'started_at': datetime.now(timezone.utc).isoformat(),
        'document_count': len(documents)
    }
    
    # Initialize components
    chunker = DocumentChunker(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    embedder = create_embedder(use_bedrock=False)  # Use local embeddings
    
    # Chunk documents
    logger.info("Chunking documents...")
    all_chunks = []
    for doc in documents:
        chunks = chunker.chunk_document(doc)
        all_chunks.extend([chunker.chunk_to_dict(c) for c in chunks])
    
    summary['chunk_count'] = len(all_chunks)
    logger.info(f"Created {len(all_chunks)} chunks from {len(documents)} documents")
    
    # Generate embeddings
    logger.info("Generating embeddings (this may take a few minutes)...")
    chunks_with_embeddings = embedder.embed_chunks(all_chunks)
    summary['embedding_dim'] = len(chunks_with_embeddings[0]['embedding'])
    
    # Build vector store
    logger.info("Building vector store...")
    vector_store = FAISSVectorStore(embedding_dim=summary['embedding_dim'])
    vector_store.add_chunks(chunks_with_embeddings)
    
    # Save locally
    logger.info(f"Saving to {output_dir}...")
    vector_store.save(output_dir)
    
    # Also save chunks for reference
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
    parser = argparse.ArgumentParser(description='Add medical guidelines to RAG')
    parser.add_argument('--source', choices=['imss', 'issste', 'all'], default='all',
                        help='Which source to process: imss, issste, or all')
    parser.add_argument('--output-dir', 
                        help='Output directory for embeddings (default: data/embeddings/medical_guidelines)')
    parser.add_argument('--chunk-size', type=int, default=512,
                        help='Chunk size in characters')
    parser.add_argument('--chunk-overlap', type=int, default=50,
                        help='Overlap between chunks')
    
    args = parser.parse_args()
    
    base_data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'data')
    
    # Load documents from selected sources
    documents = []
    sources_processed = []
    
    if args.source in ['imss', 'all']:
        imss_dir = os.path.join(base_data_dir, 'imss_guidelines')
        if os.path.exists(imss_dir):
            imss_docs = load_imss_guidelines(imss_dir)
            documents.extend(imss_docs)
            sources_processed.append(f"IMSS: {len(imss_docs)} documents")
            logger.info(f"Loaded {len(imss_docs)} IMSS guidelines")
        else:
            logger.warning(f"IMSS directory not found: {imss_dir}")
    
    if args.source in ['issste', 'all']:
        issste_dir = os.path.join(base_data_dir, 'issste_guidelines')
        if os.path.exists(issste_dir):
            issste_docs = load_issste_guidelines(issste_dir)
            documents.extend(issste_docs)
            sources_processed.append(f"ISSSTE: {len(issste_docs)} documents")
            logger.info(f"Loaded {len(issste_docs)} ISSSTE guidelines")
        else:
            logger.warning(f"ISSSTE directory not found: {issste_dir}")
    
    if not documents:
        logger.error("No documents found!")
        sys.exit(1)
    
    # Set output directory
    if args.output_dir:
        output_dir = args.output_dir
    else:
        output_dir = os.path.join(base_data_dir, 'embeddings', 'medical_guidelines')
    
    # Add to RAG
    summary = add_to_rag(
        documents,
        output_dir=output_dir,
        chunk_size=args.chunk_size,
        chunk_overlap=args.chunk_overlap
    )
    
    # Count by institution
    institution_counts = {}
    for doc in documents:
        inst = doc.get('metadata', {}).get('institution', 'Unknown')
        institution_counts[inst] = institution_counts.get(inst, 0) + 1
    
    print("\n" + "=" * 60)
    print("MEDICAL GUIDELINES RAG INDEXING COMPLETE")
    print("=" * 60)
    print(f"\nSources processed:")
    for source in sources_processed:
        print(f"  - {source}")
    print(f"\nBy institution:")
    for inst, count in institution_counts.items():
        print(f"  - {inst}: {count} documents")
    print(f"\nTotal documents: {summary['document_count']}")
    print(f"Chunks created: {summary['chunk_count']}")
    print(f"Embedding dimension: {summary['embedding_dim']}")
    print(f"Output directory: {summary['output_dir']}")


if __name__ == '__main__':
    main()
