#!/usr/bin/env python3
"""
Enhanced Tainacan Ingestion Pipeline for Ominis Health LLM
Fetches items from Tainacan, downloads PDFs, extracts content, and prepares for RAG
"""

import os
import sys
import json
import requests
import re
import tempfile
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple
from urllib.parse import urljoin, unquote
import logging
import argparse
import hashlib
import time

# PDF extraction
try:
    import fitz  # PyMuPDF
    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False
    print("Warning: PyMuPDF not installed. PDF extraction will be disabled.")

from bs4 import BeautifulSoup
import html2text

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class PDFExtractor:
    """Extract text from PDF files"""
    
    def __init__(self, cache_dir: str = None):
        self.cache_dir = cache_dir or os.path.join(tempfile.gettempdir(), 'ominis_pdf_cache')
        os.makedirs(self.cache_dir, exist_ok=True)
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Ominis-Health-Bot/1.0'
        })
    
    def download_pdf(self, url: str) -> Optional[str]:
        """Download PDF to cache and return local path"""
        # Create cache filename from URL hash
        url_hash = hashlib.md5(url.encode()).hexdigest()
        cache_path = os.path.join(self.cache_dir, f"{url_hash}.pdf")
        
        # Check cache
        if os.path.exists(cache_path):
            logger.debug(f"Using cached PDF: {cache_path}")
            return cache_path
        
        try:
            logger.info(f"Downloading PDF: {url[:80]}...")
            response = self.session.get(url, timeout=60, stream=True)
            response.raise_for_status()
            
            with open(cache_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            return cache_path
        except Exception as e:
            logger.error(f"Failed to download PDF: {e}")
            return None
    
    def extract_text(self, pdf_path: str, max_pages: int = 100) -> str:
        """Extract text from PDF file"""
        if not HAS_PYMUPDF:
            return ""
        
        try:
            doc = fitz.open(pdf_path)
            text_parts = []
            
            for page_num in range(min(len(doc), max_pages)):
                page = doc[page_num]
                text = page.get_text()
                if text.strip():
                    text_parts.append(f"--- Página {page_num + 1} ---\n{text}")
            
            doc.close()
            return '\n\n'.join(text_parts)
        except Exception as e:
            logger.error(f"Failed to extract text from PDF: {e}")
            return ""
    
    def extract_from_url(self, url: str, max_pages: int = 100) -> Tuple[str, str]:
        """Download PDF and extract text. Returns (text, local_path)"""
        pdf_path = self.download_pdf(url)
        if not pdf_path:
            return "", ""
        
        text = self.extract_text(pdf_path, max_pages)
        return text, pdf_path


class TainacanLocalIngestion:
    """Enhanced Tainacan ingestion with PDF extraction"""
    
    def __init__(self, base_url: str, output_dir: str = None):
        self.base_url = base_url.rstrip('/')
        self.api_url = f"{self.base_url}/wp-json/tainacan/v2"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Ominis-Health-Ingestion/2.0'
        })
        
        self.output_dir = output_dir or os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            'data', 'tainacan_sources'
        )
        os.makedirs(self.output_dir, exist_ok=True)
        
        self.pdf_extractor = PDFExtractor()
        
        # HTML to text converter
        self.h2t = html2text.HTML2Text()
        self.h2t.ignore_links = False
        self.h2t.ignore_images = True
        self.h2t.body_width = 0
    
    def test_connection(self) -> bool:
        """Test API connection"""
        try:
            response = self.session.get(f"{self.api_url}/collections")
            response.raise_for_status()
            return True
        except Exception as e:
            logger.error(f"Connection failed: {e}")
            return False
    
    def get_collections(self) -> List[Dict[str, Any]]:
        """Get all collections"""
        try:
            response = self.session.get(f"{self.api_url}/collections")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error fetching collections: {e}")
            return []
    
    def get_all_items(self, collection_id: int, max_items: int = None) -> List[Dict[str, Any]]:
        """Fetch all items from a collection"""
        all_items = []
        page = 1
        per_page = 20  # Smaller page size to avoid server errors
        max_retries = 3
        
        while True:
            retries = 0
            success = False
            
            while retries < max_retries and not success:
                try:
                    response = self.session.get(
                        f"{self.api_url}/collection/{collection_id}/items",
                        params={'perpage': per_page, 'paged': page, 'status': 'publish'},
                        timeout=30
                    )
                    response.raise_for_status()
                    
                    data = response.json()
                    items = data if isinstance(data, list) else data.get('items', data)
                    
                    if not items:
                        return all_items
                    
                    all_items.extend(items)
                    
                    total_pages = int(response.headers.get('X-WP-TotalPages', 1))
                    if page % 10 == 0 or page == 1:
                        logger.info(f"  Fetched page {page}/{total_pages} ({len(all_items)} items)")
                    
                    success = True
                    
                except Exception as e:
                    retries += 1
                    logger.warning(f"Retry {retries}/{max_retries} for page {page}: {e}")
                    time.sleep(2 ** retries)  # Exponential backoff
            
            if not success:
                logger.error(f"Failed to fetch page {page} after {max_retries} retries")
                break
            
            if max_items and len(all_items) >= max_items:
                all_items = all_items[:max_items]
                break
            
            if page >= total_pages:
                break
            
            page += 1
            time.sleep(0.5)  # Be polite to server
        
        return all_items
    
    def extract_pdf_url(self, item: Dict[str, Any]) -> Optional[str]:
        """Extract PDF URL from item data"""
        # Method 1: From document_as_html iframe
        doc_html = item.get('document_as_html', '')
        if doc_html and 'file=' in doc_html:
            match = re.search(r'file=([^\'\"&\s]+\.pdf)', doc_html, re.IGNORECASE)
            if match:
                url = match.group(1)
                # URL decode
                url = unquote(url)
                return url
        
        # Method 2: From dc-source metadata (if it's a PDF)
        metadata = item.get('metadata', {})
        for key in ['dc-source', 'public_url']:
            if key in metadata:
                meta = metadata[key]
                value = meta.get('value', '') if isinstance(meta, dict) else ''
                if value and '.pdf' in value.lower():
                    return value
        
        # Method 3: Construct from attachment ID
        document_id = item.get('document', '')
        if document_id and item.get('document_mimetype') == 'application/pdf':
            # Try to get attachment URL from WordPress API
            try:
                resp = self.session.get(f"{self.base_url}/wp-json/wp/v2/media/{document_id}")
                if resp.status_code == 200:
                    media = resp.json()
                    return media.get('source_url', '')
            except:
                pass
        
        return None
    
    def extract_item_content(self, item: Dict[str, Any], extract_pdf: bool = True) -> Dict[str, Any]:
        """Extract content from item, including PDF if available"""
        item_id = str(item.get('id', 'unknown'))
        
        # Title
        title_raw = item.get('title', '')
        if isinstance(title_raw, dict):
            title = title_raw.get('rendered', str(title_raw))
        else:
            title = str(title_raw)
        title = BeautifulSoup(title, 'html.parser').get_text().strip()
        
        # Description
        description_raw = item.get('description', '')
        if isinstance(description_raw, dict):
            description = description_raw.get('rendered', str(description_raw))
        else:
            description = str(description_raw)
        description = self.h2t.handle(description).strip() if description else ''
        
        # URL
        url = item.get('url', f"{self.base_url}/?p={item_id}")
        
        # Extract metadata
        metadata_values = {}
        raw_metadata = item.get('metadata', {})
        
        if isinstance(raw_metadata, dict):
            for key, meta in raw_metadata.items():
                if isinstance(meta, dict):
                    field_name = meta.get('name', key)
                    value = meta.get('value', '')
                    if isinstance(value, list):
                        value = ', '.join(
                            str(v.get('name', v) if isinstance(v, dict) else v) 
                            for v in value
                        )
                    if value:
                        metadata_values[field_name] = str(value)
        
        # Extract PDF URL and content
        pdf_url = self.extract_pdf_url(item)
        pdf_content = ""
        
        if pdf_url and extract_pdf:
            logger.info(f"  Extracting PDF: {pdf_url[:60]}...")
            pdf_content, _ = self.pdf_extractor.extract_from_url(pdf_url)
            if pdf_content:
                logger.info(f"    Extracted {len(pdf_content)} characters from PDF")
        
        # Build full content
        content_parts = [description]
        
        # Add key metadata
        for name, value in metadata_values.items():
            if value and name not in ['Nombre de la fuente', 'Descripción']:
                content_parts.append(f"{name}: {value}")
        
        # Add PDF content if available
        if pdf_content:
            content_parts.append("\n--- CONTENIDO DEL DOCUMENTO ---\n")
            content_parts.append(pdf_content)
        
        full_content = '\n\n'.join(filter(None, content_parts))
        
        # Determine source type based on document type
        doc_type = item.get('document_type', '')
        doc_mimetype = item.get('document_mimetype', '')
        
        if doc_mimetype == 'application/pdf':
            source_type = 'pdf_document'
        elif doc_type == 'url':
            source_type = 'external_url'
        else:
            source_type = 'tainacan_item'
        
        # Build structured document
        document = {
            'id': f"tainacan-{item_id}",
            'title': title,
            'content': full_content,
            'description': description,
            'url': url,
            'pdf_url': pdf_url,
            'has_pdf_content': bool(pdf_content),
            'date_published': item.get('creation_date', ''),
            'date_modified': item.get('modification_date', ''),
            'source': 'Ominis - Tainacan',
            'collection_id': str(item.get('collection_id', '')),
            'category': metadata_values.get('Taxonomía', metadata_values.get('taxonomia', '')),
            'metadata': {
                'source_type': source_type,
                'institution': metadata_values.get('Organismo', 'Ominis'),
                'country': 'Mexico',
                'language': metadata_values.get('Idioma', 'es'),
                'document_type': doc_type,
                'document_mimetype': doc_mimetype,
                **{k: v for k, v in metadata_values.items() if k not in ['Taxonomía', 'taxonomia', 'Organismo', 'Idioma']}
            },
            'ingested_at': datetime.now(timezone.utc).isoformat()
        }
        
        return document
    
    def ingest_collection(
        self, 
        collection_id: int, 
        collection_name: str = "",
        max_items: int = None,
        extract_pdf: bool = True
    ) -> List[Dict[str, Any]]:
        """Ingest all items from a collection"""
        logger.info(f"\nIngesting collection: {collection_name} (ID: {collection_id})")
        
        items = self.get_all_items(collection_id, max_items)
        logger.info(f"Fetched {len(items)} items")
        
        documents = []
        for i, item in enumerate(items):
            try:
                logger.info(f"Processing item {i+1}/{len(items)}: {item.get('id')}")
                doc = self.extract_item_content(item, extract_pdf=extract_pdf)
                doc['collection_name'] = collection_name
                documents.append(doc)
                
                # Save individual document
                doc_path = os.path.join(self.output_dir, f"{doc['id']}.json")
                with open(doc_path, 'w', encoding='utf-8') as f:
                    json.dump(doc, ensure_ascii=False, indent=2, fp=f)
                
            except Exception as e:
                logger.error(f"Error processing item {item.get('id')}: {e}")
        
        return documents
    
    def ingest_all(
        self, 
        collection_ids: List[int] = None,
        max_items_per_collection: int = None,
        extract_pdf: bool = True
    ) -> Dict[str, Any]:
        """Ingest from all or specified collections"""
        collections = self.get_collections()
        
        if collection_ids:
            collections = [c for c in collections if c.get('id') in collection_ids]
        
        summary = {
            'started_at': datetime.now(timezone.utc).isoformat(),
            'base_url': self.base_url,
            'output_dir': self.output_dir,
            'collections': {},
            'total_documents': 0,
            'total_with_pdf': 0
        }
        
        all_documents = []
        
        for col in collections:
            col_id = col.get('id')
            col_name = col.get('name', f'Collection {col_id}')
            
            try:
                docs = self.ingest_collection(
                    col_id, 
                    col_name, 
                    max_items=max_items_per_collection,
                    extract_pdf=extract_pdf
                )
                
                all_documents.extend(docs)
                pdf_count = sum(1 for d in docs if d.get('has_pdf_content'))
                
                summary['collections'][col_name] = {
                    'id': col_id,
                    'documents': len(docs),
                    'with_pdf_content': pdf_count
                }
                
            except Exception as e:
                logger.error(f"Error processing collection {col_name}: {e}")
                summary['collections'][col_name] = {'error': str(e)}
        
        summary['completed_at'] = datetime.now(timezone.utc).isoformat()
        summary['total_documents'] = len(all_documents)
        summary['total_with_pdf'] = sum(1 for d in all_documents if d.get('has_pdf_content'))
        
        # Save manifest
        manifest = {
            'created_at': datetime.now(timezone.utc).isoformat(),
            'document_count': len(all_documents),
            'source': 'Ominis - Tainacan',
            'documents': [
                {
                    'id': doc['id'],
                    'title': doc['title'],
                    'has_pdf_content': doc.get('has_pdf_content', False),
                    'pdf_url': doc.get('pdf_url', '')
                }
                for doc in all_documents
            ]
        }
        
        manifest_path = os.path.join(self.output_dir, 'manifest.json')
        with open(manifest_path, 'w', encoding='utf-8') as f:
            json.dump(manifest, ensure_ascii=False, indent=2, fp=f)
        
        # Save summary
        summary_path = os.path.join(self.output_dir, 'ingestion_summary.json')
        with open(summary_path, 'w', encoding='utf-8') as f:
            json.dump(summary, ensure_ascii=False, indent=2, fp=f)
        
        return summary


def main():
    parser = argparse.ArgumentParser(description='Ingest Tainacan content with PDF extraction')
    parser.add_argument('--url', default='https://ominis.org', 
                        help='WordPress/Tainacan site URL')
    parser.add_argument('--output-dir', 
                        help='Output directory for documents')
    parser.add_argument('--collection-ids', type=int, nargs='+',
                        help='Specific collection IDs to ingest')
    parser.add_argument('--max-items', type=int, 
                        help='Max items per collection')
    parser.add_argument('--no-pdf', action='store_true',
                        help='Skip PDF extraction')
    parser.add_argument('--discover', action='store_true',
                        help='Only discover collections')
    
    args = parser.parse_args()
    
    ingestion = TainacanLocalIngestion(args.url, args.output_dir)
    
    if not ingestion.test_connection():
        print("Failed to connect!")
        sys.exit(1)
    
    if args.discover:
        collections = ingestion.get_collections()
        print(f"\nFound {len(collections)} collections:\n")
        for col in collections:
            total = col.get('total_items', {})
            if isinstance(total, dict):
                item_count = total.get('publish', 0)
            else:
                item_count = total
            print(f"  ID: {col.get('id'):5} | Items: {str(item_count):>6} | {col.get('name')}")
        return
    
    logger.info(f"Starting Tainacan ingestion from {args.url}")
    
    summary = ingestion.ingest_all(
        collection_ids=args.collection_ids,
        max_items_per_collection=args.max_items,
        extract_pdf=not args.no_pdf
    )
    
    print("\n" + "=" * 60)
    print("INGESTION COMPLETE")
    print("=" * 60)
    print(f"Total documents: {summary['total_documents']}")
    print(f"Documents with PDF content: {summary['total_with_pdf']}")
    print(f"Output directory: {summary['output_dir']}")
    print("\nBy collection:")
    for name, info in summary['collections'].items():
        if 'error' in info:
            print(f"  - {name}: ERROR - {info['error']}")
        else:
            print(f"  - {name}: {info['documents']} docs ({info['with_pdf_content']} with PDF)")


if __name__ == '__main__':
    main()
