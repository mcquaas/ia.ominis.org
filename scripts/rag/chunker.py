"""
Document Chunking for Ominis Health LLM
Splits documents into smaller chunks for embedding
"""

import re
from typing import List, Dict, Any
from dataclasses import dataclass
import hashlib


@dataclass
class Chunk:
    """Represents a document chunk"""
    id: str
    document_id: str
    content: str
    metadata: Dict[str, Any]
    chunk_index: int
    total_chunks: int
    

class DocumentChunker:
    """Split documents into chunks for embedding"""
    
    def __init__(
        self,
        chunk_size: int = 512,
        chunk_overlap: int = 50,
        min_chunk_size: int = 100
    ):
        """
        Initialize chunker
        
        Args:
            chunk_size: Target size of each chunk in characters
            chunk_overlap: Overlap between consecutive chunks
            min_chunk_size: Minimum chunk size (smaller chunks are merged)
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.min_chunk_size = min_chunk_size
    
    def chunk_document(self, document: Dict[str, Any]) -> List[Chunk]:
        """
        Split a document into chunks
        
        Args:
            document: Document dictionary with 'id', 'title', 'content'
            
        Returns:
            List of Chunk objects
        """
        doc_id = document.get('id', 'unknown')
        title = document.get('title', '')
        content = document.get('content', '')
        
        # Combine title and content
        full_text = f"# {title}\n\n{content}" if title else content
        
        # Split into chunks
        text_chunks = self._split_text(full_text)
        
        # Create Chunk objects
        chunks = []
        for i, text in enumerate(text_chunks):
            chunk_id = self._generate_chunk_id(doc_id, i)
            
            chunk = Chunk(
                id=chunk_id,
                document_id=doc_id,
                content=text,
                metadata={
                    'title': title,
                    'url': document.get('url', ''),
                    'categories': document.get('categories', []),
                    'tags': document.get('tags', []),
                    'date_published': document.get('date_published', ''),
                    'source': document.get('source', 'unknown')
                },
                chunk_index=i,
                total_chunks=len(text_chunks)
            )
            chunks.append(chunk)
        
        return chunks
    
    def _split_text(self, text: str) -> List[str]:
        """
        Split text into chunks using semantic boundaries
        
        Args:
            text: Text to split
            
        Returns:
            List of text chunks
        """
        # First, try to split by paragraphs
        paragraphs = self._split_by_paragraphs(text)
        
        # Then ensure each chunk is within size limits
        chunks = []
        current_chunk = ""
        
        for para in paragraphs:
            # If paragraph alone is too large, split it further
            if len(para) > self.chunk_size:
                # Save current chunk if not empty
                if current_chunk.strip():
                    chunks.append(current_chunk.strip())
                    current_chunk = ""
                
                # Split large paragraph by sentences
                sentences = self._split_by_sentences(para)
                for sentence in sentences:
                    if len(current_chunk) + len(sentence) <= self.chunk_size:
                        current_chunk += sentence + " "
                    else:
                        if current_chunk.strip():
                            chunks.append(current_chunk.strip())
                        current_chunk = sentence + " "
            
            # Normal case: add paragraph to current chunk
            elif len(current_chunk) + len(para) <= self.chunk_size:
                current_chunk += para + "\n\n"
            else:
                # Save current chunk and start new one
                if current_chunk.strip():
                    chunks.append(current_chunk.strip())
                current_chunk = para + "\n\n"
        
        # Don't forget the last chunk
        if current_chunk.strip():
            chunks.append(current_chunk.strip())
        
        # Apply overlap
        if self.chunk_overlap > 0 and len(chunks) > 1:
            chunks = self._apply_overlap(chunks)
        
        # Filter out tiny chunks
        chunks = [c for c in chunks if len(c) >= self.min_chunk_size]
        
        return chunks
    
    def _split_by_paragraphs(self, text: str) -> List[str]:
        """Split text by paragraph boundaries"""
        # Split by double newlines or multiple newlines
        paragraphs = re.split(r'\n\s*\n', text)
        return [p.strip() for p in paragraphs if p.strip()]
    
    def _split_by_sentences(self, text: str) -> List[str]:
        """Split text into sentences"""
        # Simple sentence splitter
        sentences = re.split(r'(?<=[.!?])\s+', text)
        return [s.strip() for s in sentences if s.strip()]
    
    def _apply_overlap(self, chunks: List[str]) -> List[str]:
        """Apply overlap between consecutive chunks"""
        overlapped = [chunks[0]]
        
        for i in range(1, len(chunks)):
            prev_chunk = chunks[i - 1]
            curr_chunk = chunks[i]
            
            # Get overlap from end of previous chunk
            overlap_text = prev_chunk[-self.chunk_overlap:] if len(prev_chunk) > self.chunk_overlap else prev_chunk
            
            # Find a good break point (word boundary)
            space_idx = overlap_text.find(' ')
            if space_idx > 0:
                overlap_text = overlap_text[space_idx + 1:]
            
            # Prepend overlap to current chunk
            overlapped.append(f"{overlap_text} {curr_chunk}")
        
        return overlapped
    
    def _generate_chunk_id(self, doc_id: str, chunk_index: int) -> str:
        """Generate unique chunk ID"""
        raw = f"{doc_id}_{chunk_index}"
        return hashlib.md5(raw.encode()).hexdigest()[:16]
    
    def chunk_to_dict(self, chunk: Chunk) -> Dict[str, Any]:
        """Convert Chunk to dictionary"""
        return {
            'id': chunk.id,
            'document_id': chunk.document_id,
            'content': chunk.content,
            'metadata': chunk.metadata,
            'chunk_index': chunk.chunk_index,
            'total_chunks': chunk.total_chunks
        }


def process_documents(
    documents: List[Dict[str, Any]],
    chunk_size: int = 512,
    chunk_overlap: int = 50
) -> List[Dict[str, Any]]:
    """
    Process multiple documents into chunks
    
    Args:
        documents: List of document dictionaries
        chunk_size: Target chunk size
        chunk_overlap: Overlap between chunks
        
    Returns:
        List of chunk dictionaries
    """
    chunker = DocumentChunker(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    
    all_chunks = []
    for doc in documents:
        chunks = chunker.chunk_document(doc)
        all_chunks.extend([chunker.chunk_to_dict(c) for c in chunks])
    
    return all_chunks


if __name__ == '__main__':
    # Test chunking
    sample_doc = {
        'id': 'test-1',
        'title': 'Sample Medical Article',
        'content': """
        This is a sample medical article about diabetes management.
        
        Diabetes is a chronic condition that affects millions of people worldwide.
        Managing blood sugar levels is crucial for preventing complications.
        
        There are several key strategies for diabetes management:
        
        1. Regular blood glucose monitoring
        2. Healthy diet and nutrition
        3. Regular physical activity
        4. Medication adherence
        5. Regular check-ups with healthcare providers
        
        Diet plays a crucial role in managing diabetes. Patients should focus on
        consuming complex carbohydrates, lean proteins, and healthy fats while
        limiting simple sugars and processed foods.
        """,
        'url': 'https://example.com/diabetes',
        'categories': ['Endocrinology', 'Diabetes'],
        'date_published': '2024-01-15'
    }
    
    chunker = DocumentChunker(chunk_size=300, chunk_overlap=30)
    chunks = chunker.chunk_document(sample_doc)
    
    print(f"Created {len(chunks)} chunks from document")
    for i, chunk in enumerate(chunks):
        print(f"\nChunk {i + 1}:")
        print(f"  ID: {chunk.id}")
        print(f"  Length: {len(chunk.content)} chars")
        print(f"  Content preview: {chunk.content[:100]}...")
