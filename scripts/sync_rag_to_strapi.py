#!/usr/bin/env python3
"""
Sync RAG Sources to Strapi
Reads all RAG source data and creates entries in Strapi
"""

import os
import sys
import json
import glob
import requests
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
import logging
import argparse
import re

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Strapi configuration
STRAPI_URL = os.getenv('STRAPI_URL', 'https://admin.ominis.org')
STRAPI_ADMIN_EMAIL = os.getenv('STRAPI_ADMIN_EMAIL', 'admin@ominis.org')
STRAPI_ADMIN_PASSWORD = os.getenv('STRAPI_ADMIN_PASSWORD', 'OminisDevAdmin2024!')
STRAPI_API_TOKEN = os.getenv('STRAPI_API_TOKEN', '')


class StrapiClient:
    """Client for Strapi API"""
    
    def __init__(self, base_url: str, api_token: str = None):
        self.base_url = base_url.rstrip('/')
        self.api_url = f"{self.base_url}/api"
        self.session = requests.Session()
        self.jwt_token = None
        self.api_token = api_token
        
        # If API token provided, use it directly
        if api_token:
            self.session.headers.update({
                'Authorization': f'Bearer {api_token}',
                'Content-Type': 'application/json'
            })
            logger.info("Using API token authentication")
    
    def login(self, email: str, password: str) -> bool:
        """Login and get JWT token (not needed if using API token)"""
        if self.api_token:
            logger.info("Already authenticated via API token")
            return True
            
        try:
            response = self.session.post(
                f"{self.api_url}/auth/local",
                json={"identifier": email, "password": password}
            )
            
            if response.status_code == 200:
                data = response.json()
                self.jwt_token = data.get('jwt')
                self.session.headers.update({
                    'Authorization': f'Bearer {self.jwt_token}'
                })
                logger.info(f"Logged in as {email}")
                return True
            else:
                logger.error(f"Login failed: {response.text}")
                return False
        except Exception as e:
            logger.error(f"Login error: {e}")
            return False
    
    def is_authenticated(self) -> bool:
        """Check if client has authentication"""
        return bool(self.api_token or self.jwt_token)
    
    def get_existing_sources(self) -> Dict[str, int]:
        """Get existing RAG sources by externalId"""
        existing = {}
        page = 1
        page_size = 100
        
        while True:
            response = self.session.get(
                f"{self.api_url}/rag-sources",
                params={
                    'pagination[page]': page,
                    'pagination[pageSize]': page_size,
                    'fields': ['id', 'externalId', 'title']
                }
            )
            
            if response.status_code != 200:
                logger.error(f"Failed to get sources: {response.text}")
                break
            
            data = response.json()
            sources = data.get('data', [])
            
            for source in sources:
                ext_id = source.get('attributes', {}).get('externalId')
                if ext_id:
                    existing[ext_id] = source.get('id')
            
            meta = data.get('meta', {}).get('pagination', {})
            if page >= meta.get('pageCount', 1):
                break
            page += 1
        
        logger.info(f"Found {len(existing)} existing sources in Strapi")
        return existing
    
    def create_source(self, source_data: Dict[str, Any]) -> Optional[int]:
        """Create a new RAG source"""
        response = self.session.post(
            f"{self.api_url}/rag-sources",
            json={"data": source_data}
        )
        
        if response.status_code in [200, 201]:
            data = response.json()
            source_id = data.get('data', {}).get('id')
            logger.info(f"Created source: {source_data.get('title', 'Unknown')[:50]}... (ID: {source_id})")
            return source_id
        else:
            logger.error(f"Failed to create source: {response.status_code} - {response.text[:200]}")
            return None
    
    def update_source(self, source_id: int, source_data: Dict[str, Any]) -> bool:
        """Update an existing RAG source"""
        response = self.session.put(
            f"{self.api_url}/rag-sources/{source_id}",
            json={"data": source_data}
        )
        
        if response.status_code == 200:
            logger.debug(f"Updated source ID {source_id}")
            return True
        else:
            logger.error(f"Failed to update source {source_id}: {response.text[:200]}")
            return False


def map_source_type(doc: Dict[str, Any]) -> str:
    """Map document metadata to Strapi sourceType enum
    
    Valid values: tainacan, wordpress, imss_guideline, issste_guideline, pubmed, manual_upload, other
    """
    source = doc.get('source', '').lower()
    metadata = doc.get('metadata', {})
    source_type = metadata.get('source_type', '').lower()
    institution = metadata.get('institution', '').lower()
    
    if 'imss' in source or 'imss' in institution:
        return 'imss_guideline'
    elif 'issste' in source or 'issste' in institution:
        return 'issste_guideline'
    elif 'tainacan' in source or 'tainacan' in source_type:
        return 'tainacan'
    elif 'wordpress' in source or 'wordpress' in source_type:
        return 'wordpress'
    elif 'pubmed' in source or 'pubmed' in source_type:
        return 'pubmed'
    elif doc.get('has_pdf_content') or 'pdf' in source_type:
        return 'manual_upload'  # Map PDF documents to manual_upload
    else:
        return 'other'


def map_category(doc: Dict[str, Any]) -> str:
    """Map document to Strapi category enum
    
    Valid values: general_health, nutrition, mental_health, chronic_diseases, 
                  maternal_health, pediatrics, geriatrics, emergency, prevention, medications, other
    """
    category = doc.get('category', '').lower()
    source = doc.get('source', '').lower()
    title = doc.get('title', '').lower()
    
    # Category mapping - only use valid production enum values
    if any(x in category for x in ['nutri', 'aliment', 'dieta']):
        return 'nutrition'
    elif any(x in category for x in ['mental', 'psiq', 'psico']):
        return 'mental_health'
    elif any(x in category for x in ['diabetes', 'cronic', 'hipertens', 'cardiolog', 'cardio', 'coronar', 'oncolog', 'cancer']):
        return 'chronic_diseases'
    elif any(x in category for x in ['maternal', 'embarazo', 'obstet', 'gineco']):
        return 'maternal_health'
    elif any(x in category for x in ['pediatr', 'niño', 'infantil']):
        return 'pediatrics'
    elif any(x in category for x in ['geriatr', 'adulto mayor', 'anciano']):
        return 'geriatrics'
    elif any(x in category for x in ['urgencia', 'emergencia']):
        return 'emergency'
    elif any(x in category for x in ['preven', 'vacuna', 'inmun']):
        return 'prevention'
    elif any(x in category for x in ['medicament', 'farmac', 'drug']):
        return 'medications'
    elif any(x in category for x in ['norma', 'protocolo', 'lineamiento', 'acuerdo', 'epidemiolog', 'datos']):
        return 'other'
    else:
        return 'general_health'


def generate_slug(title: str, doc_id: str = '') -> str:
    """Generate URL-friendly slug from title with optional doc_id for uniqueness"""
    # Remove special characters and convert to lowercase
    slug = title.lower()
    slug = re.sub(r'[áàäâ]', 'a', slug)
    slug = re.sub(r'[éèëê]', 'e', slug)
    slug = re.sub(r'[íìïî]', 'i', slug)
    slug = re.sub(r'[óòöô]', 'o', slug)
    slug = re.sub(r'[úùüû]', 'u', slug)
    slug = re.sub(r'[ñ]', 'n', slug)
    slug = re.sub(r'[^a-z0-9\s-]', '', slug)
    slug = re.sub(r'[\s]+', '-', slug)
    slug = re.sub(r'-+', '-', slug)
    slug = slug.strip('-')
    
    # Add doc_id suffix for uniqueness
    if doc_id:
        # Create a short hash from doc_id
        id_suffix = re.sub(r'[^a-z0-9-]', '', doc_id.lower())[:30]
        slug = f"{slug[:160]}-{id_suffix}"
    
    return slug[:200]  # Max 200 chars


def load_rag_sources(data_dir: str) -> List[Dict[str, Any]]:
    """Load all RAG source documents from embeddings directories"""
    documents = []
    
    # Load from each embeddings directory
    embeddings_dirs = [
        'data/embeddings/medical_guidelines',
        'data/embeddings/tainacan_sources', 
        'data/embeddings/mexican_health_sources'
    ]
    
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__))) if '__file__' in dir() else data_dir
    
    for rel_dir in embeddings_dirs:
        dir_path = os.path.join(base_dir, rel_dir)
        chunks_file = os.path.join(dir_path, 'chunks.json')
        
        if os.path.exists(chunks_file):
            logger.info(f"Loading from {chunks_file}")
            with open(chunks_file, 'r', encoding='utf-8') as f:
                chunks = json.load(f)
            
            # Group chunks by document_id
            docs_map = {}
            for chunk in chunks:
                doc_id = chunk.get('document_id', '')
                if doc_id not in docs_map:
                    docs_map[doc_id] = {
                        'id': doc_id,
                        'title': chunk.get('metadata', {}).get('title', doc_id),
                        'source': chunk.get('metadata', {}).get('source', ''),
                        'url': chunk.get('metadata', {}).get('url', ''),
                        'category': chunk.get('metadata', {}).get('categories', [''])[0] if chunk.get('metadata', {}).get('categories') else '',
                        'metadata': chunk.get('metadata', {}),
                        'chunks_count': 0,
                        'has_pdf_content': chunk.get('metadata', {}).get('source_type', '') == 'pdf_document'
                    }
                docs_map[doc_id]['chunks_count'] += 1
            
            documents.extend(docs_map.values())
            logger.info(f"  Found {len(docs_map)} unique documents")
    
    # Also load from raw data directories for more metadata
    raw_dirs = [
        ('data/imss_guidelines', 'imss_guideline'),
        ('data/issste_guidelines', 'issste_guideline'),
        ('data/tainacan_sources', 'tainacan'),
        ('data/mexican_health_sources', 'other')
    ]
    
    existing_ids = {d['id'] for d in documents}
    
    for rel_dir, default_type in raw_dirs:
        dir_path = os.path.join(base_dir, rel_dir)
        if os.path.exists(dir_path):
            pattern = os.path.join(dir_path, '*.json')
            for filepath in glob.glob(pattern):
                if 'manifest' in filepath or 'summary' in filepath:
                    continue
                
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        doc = json.load(f)
                    
                    doc_id = doc.get('id', '')
                    if doc_id and doc_id not in existing_ids:
                        documents.append({
                            'id': doc_id,
                            'title': doc.get('title', ''),
                            'source': doc.get('source', ''),
                            'url': doc.get('url', ''),
                            'pdf_url': doc.get('pdf_url', ''),
                            'category': doc.get('category', ''),
                            'metadata': doc.get('metadata', {}),
                            'chunks_count': 0,
                            'has_pdf_content': doc.get('has_pdf_content', False),
                            'content_preview': doc.get('content', '')[:500] if doc.get('content') else ''
                        })
                        existing_ids.add(doc_id)
                except Exception as e:
                    logger.error(f"Error loading {filepath}: {e}")
    
    logger.info(f"Total unique documents: {len(documents)}")
    return documents


def sync_to_strapi(
    strapi: StrapiClient,
    documents: List[Dict[str, Any]],
    dry_run: bool = False,
    update_existing: bool = False
) -> Dict[str, int]:
    """Sync documents to Strapi"""
    stats = {'created': 0, 'updated': 0, 'skipped': 0, 'failed': 0}
    
    # Get existing sources
    existing = strapi.get_existing_sources()
    
    for doc in documents:
        doc_id = doc.get('id', '')
        if not doc_id:
            continue
        
        # Check if already exists
        if doc_id in existing:
            if update_existing:
                # Update existing
                source_data = build_source_data(doc)
                if not dry_run:
                    if strapi.update_source(existing[doc_id], source_data):
                        stats['updated'] += 1
                    else:
                        stats['failed'] += 1
                else:
                    logger.info(f"Would update: {doc.get('title', '')[:50]}...")
                    stats['updated'] += 1
            else:
                stats['skipped'] += 1
            continue
        
        # Create new source
        source_data = build_source_data(doc)
        
        if dry_run:
            logger.info(f"Would create: {source_data.get('title', '')[:50]}...")
            stats['created'] += 1
        else:
            if strapi.create_source(source_data):
                stats['created'] += 1
            else:
                stats['failed'] += 1
    
    return stats


def map_language(doc: Dict[str, Any]) -> str:
    """Map document language to valid Strapi enum
    
    Valid values: es, en, es-mx
    """
    lang = doc.get('metadata', {}).get('language', 'es')
    if not lang:
        return 'es'
    lang = lang.lower().strip()
    if lang in ['es', 'en', 'es-mx']:
        return lang
    elif lang.startswith('es'):
        return 'es'
    elif lang.startswith('en'):
        return 'en'
    else:
        return 'es'  # Default to Spanish


def build_source_data(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Build Strapi source data from document"""
    title = doc.get('title', 'Untitled')[:500]
    doc_id = doc.get('id', '')
    
    source_data = {
        'title': title,
        'slug': generate_slug(title, doc_id),
        'externalId': doc_id,
        'sourceType': map_source_type(doc),
        'status': 'indexed',
        'sourceUrl': doc.get('url', '') or doc.get('pdf_url', ''),
        'category': map_category(doc),
        'language': map_language(doc),
        'chunksCount': doc.get('chunks_count', 0),
        'lastIndexedAt': datetime.now(timezone.utc).isoformat(),
        'metadata': {
            'institution': doc.get('metadata', {}).get('institution', ''),
            'source': doc.get('source', ''),
            'has_pdf_content': doc.get('has_pdf_content', False),
            'original_category': doc.get('category', '')
        },
        'notes': f"Auto-imported from RAG system. Source: {doc.get('source', 'Unknown')}"
    }
    
    return source_data


def main():
    parser = argparse.ArgumentParser(description='Sync RAG sources to Strapi')
    parser.add_argument('--strapi-url', default=STRAPI_URL, help='Strapi API URL')
    parser.add_argument('--api-token', default=STRAPI_API_TOKEN, help='Strapi API token')
    parser.add_argument('--email', default=STRAPI_ADMIN_EMAIL, help='Admin email')
    parser.add_argument('--password', default=STRAPI_ADMIN_PASSWORD, help='Admin password')
    parser.add_argument('--dry-run', action='store_true', help='Do not actually create/update')
    parser.add_argument('--update-existing', action='store_true', help='Update existing sources')
    parser.add_argument('--data-dir', default='.', help='Base data directory')
    
    args = parser.parse_args()
    
    logger.info(f"Syncing RAG sources to Strapi at {args.strapi_url}")
    
    # Initialize Strapi client with API token if provided
    strapi = StrapiClient(args.strapi_url, api_token=args.api_token)
    
    # Login (only needed if no API token)
    if not args.dry_run:
        if not strapi.is_authenticated():
            if not strapi.login(args.email, args.password):
                logger.error("Failed to login to Strapi")
                sys.exit(1)
    else:
        logger.info("Dry run - skipping login")
    
    # Load documents
    documents = load_rag_sources(args.data_dir)
    
    if not documents:
        logger.error("No documents found!")
        sys.exit(1)
    
    # Sync to Strapi
    stats = sync_to_strapi(
        strapi,
        documents,
        dry_run=args.dry_run,
        update_existing=args.update_existing
    )
    
    print("\n" + "=" * 60)
    print("SYNC COMPLETE")
    print("=" * 60)
    print(f"Created: {stats['created']}")
    print(f"Updated: {stats['updated']}")
    print(f"Skipped: {stats['skipped']}")
    print(f"Failed: {stats['failed']}")


if __name__ == '__main__':
    main()
