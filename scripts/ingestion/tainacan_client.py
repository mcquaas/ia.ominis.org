"""
Tainacan API Client for Ominis Health LLM
Fetches items from Tainacan collections on WordPress
"""

import os
import json
import requests
from typing import List, Dict, Any, Optional
from datetime import datetime
import logging
from bs4 import BeautifulSoup
import html2text

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TainacanClient:
    """Client to interact with Tainacan REST API"""
    
    def __init__(self, base_url: str, api_key: Optional[str] = None):
        """
        Initialize Tainacan client
        
        Args:
            base_url: WordPress site URL (e.g., https://ominis.org)
            api_key: Optional API key for authentication
        """
        self.base_url = base_url.rstrip('/')
        self.api_url = f"{self.base_url}/wp-json/tainacan/v2"
        self.wp_api_url = f"{self.base_url}/wp-json/wp/v2"
        self.session = requests.Session()
        
        if api_key:
            self.session.headers.update({
                'Authorization': f'Bearer {api_key}'
            })
        
        self.session.headers.update({
            'User-Agent': 'Ominis-Health-Ingestion/1.0'
        })
        
        # HTML to text converter
        self.h2t = html2text.HTML2Text()
        self.h2t.ignore_links = False
        self.h2t.ignore_images = True
        self.h2t.body_width = 0
    
    def test_connection(self) -> bool:
        """Test if the Tainacan API is accessible"""
        try:
            response = self.session.get(f"{self.api_url}/collections")
            response.raise_for_status()
            collections = response.json()
            logger.info(f"Connected! Found {len(collections)} collections")
            return True
        except Exception as e:
            logger.error(f"Connection failed: {e}")
            return False
    
    def get_collections(self) -> List[Dict[str, Any]]:
        """
        Fetch all Tainacan collections
        
        Returns:
            List of collection dictionaries
        """
        try:
            response = self.session.get(f"{self.api_url}/collections")
            response.raise_for_status()
            collections = response.json()
            
            for col in collections:
                logger.info(f"  Collection: {col.get('name')} (ID: {col.get('id')}, Items: {col.get('total_items', 'N/A')})")
            
            return collections
        except Exception as e:
            logger.error(f"Error fetching collections: {e}")
            return []
    
    def get_collection_metadata(self, collection_id: int) -> List[Dict[str, Any]]:
        """
        Get metadata fields for a collection
        
        Args:
            collection_id: Tainacan collection ID
            
        Returns:
            List of metadata field definitions
        """
        try:
            response = self.session.get(f"{self.api_url}/collection/{collection_id}/metadata")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error fetching metadata for collection {collection_id}: {e}")
            return []
    
    def get_items(
        self,
        collection_id: int,
        per_page: int = 96,
        page: int = 1,
        status: str = 'publish'
    ) -> Dict[str, Any]:
        """
        Fetch items from a collection
        
        Args:
            collection_id: Tainacan collection ID
            per_page: Number of items per page
            page: Page number
            status: Item status filter
            
        Returns:
            Dictionary with items and pagination info
        """
        endpoint = f"{self.api_url}/collection/{collection_id}/items"
        params = {
            'perpage': per_page,
            'paged': page,
            'status': status,
            'fetch_only': 'title,description,document,metadata,url'
        }
        
        try:
            response = self.session.get(endpoint, params=params)
            response.raise_for_status()
            
            # Tainacan returns items in a specific structure
            data = response.json()
            
            # Get total from headers
            total_items = int(response.headers.get('X-WP-Total', 0))
            total_pages = int(response.headers.get('X-WP-TotalPages', 0))
            
            return {
                'items': data.get('items', data) if isinstance(data, dict) else data,
                'total_items': total_items,
                'total_pages': total_pages,
                'page': page
            }
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching items page {page}: {e}")
            return {'items': [], 'total_items': 0, 'total_pages': 0, 'page': page}
    
    def get_all_items(
        self,
        collection_id: int,
        max_items: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Fetch all items from a collection
        
        Args:
            collection_id: Tainacan collection ID
            max_items: Maximum items to fetch (None = all)
            
        Returns:
            List of all items
        """
        all_items = []
        page = 1
        per_page = 100  # Request 100, but API may limit to less
        
        while True:
            logger.info(f"Fetching items page {page}...")
            result = self.get_items(collection_id, per_page=per_page, page=page)
            items = result['items']
            
            if not items:
                break
            
            all_items.extend(items)
            total_pages = result['total_pages']
            logger.info(f"  Fetched {len(items)} items. Total: {len(all_items)}/{result['total_items']} (page {page}/{total_pages})")
            
            if max_items and len(all_items) >= max_items:
                all_items = all_items[:max_items]
                break
            
            # Stop if we've processed all pages
            if page >= total_pages:
                break
            
            page += 1
        
        logger.info(f"Total items fetched: {len(all_items)}")
        return all_items
    
    def extract_item_content(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract relevant content from a Tainacan item
        
        Args:
            item: Raw Tainacan item data
            
        Returns:
            Cleaned and structured document
        """
        # Get basic fields
        item_id = str(item.get('id', 'unknown'))
        
        # Title
        title_raw = item.get('title', '')
        if isinstance(title_raw, dict):
            title = title_raw.get('rendered', str(title_raw))
        else:
            title = str(title_raw)
        title = BeautifulSoup(title, 'html.parser').get_text().strip()
        
        # Description/Content
        description_raw = item.get('description', '')
        if isinstance(description_raw, dict):
            description = description_raw.get('rendered', str(description_raw))
        else:
            description = str(description_raw)
        
        content = self.h2t.handle(description).strip() if description else ''
        
        # URL
        url = item.get('url', item.get('permalink', ''))
        if not url:
            url = f"{self.base_url}/?p={item_id}"
        
        # Extract metadata
        metadata_values = {}
        raw_metadata = item.get('metadata', {})
        
        if isinstance(raw_metadata, dict):
            for key, meta in raw_metadata.items():
                if isinstance(meta, dict):
                    value = meta.get('value', '')
                    if isinstance(value, list):
                        value = ', '.join(str(v.get('name', v) if isinstance(v, dict) else v) for v in value)
                    metadata_values[key] = str(value) if value else ''
        
        # Document (attached file info)
        document = item.get('document', '')
        document_type = item.get('document_type', '')
        
        # Build full text content
        full_content_parts = [content]
        
        # Add metadata to content for better retrieval
        for key, value in metadata_values.items():
            if value and key not in ['_thumbnail_id']:
                full_content_parts.append(f"{key}: {value}")
        
        if document and document_type:
            full_content_parts.append(f"Documento: {document}")
        
        full_content = '\n\n'.join(filter(None, full_content_parts))
        
        # Build structured document
        document = {
            'id': item_id,
            'title': title,
            'content': full_content,
            'description': content,
            'url': url,
            'date_published': item.get('date', ''),
            'date_modified': item.get('modified', ''),
            'metadata': metadata_values,
            'document_type': document_type,
            'collection_id': str(item.get('collection_id', '')),
            'source': 'tainacan',
            'source_type': 'ominis',
            'ingested_at': datetime.utcnow().isoformat()
        }
        
        return document


def discover_collections(base_url: str) -> List[Dict[str, Any]]:
    """
    Discover available Tainacan collections
    
    Args:
        base_url: WordPress site URL
        
    Returns:
        List of collections with their info
    """
    client = TainacanClient(base_url)
    
    if not client.test_connection():
        logger.error("Cannot connect to Tainacan API")
        return []
    
    return client.get_collections()


if __name__ == '__main__':
    import sys
    
    base_url = sys.argv[1] if len(sys.argv) > 1 else "https://ominis.org"
    
    print(f"\n=== Discovering Tainacan Collections at {base_url} ===\n")
    
    client = TainacanClient(base_url)
    
    if not client.test_connection():
        print("Failed to connect!")
        sys.exit(1)
    
    collections = client.get_collections()
    
    print(f"\nFound {len(collections)} collections:")
    for col in collections:
        print(f"\n  ID: {col.get('id')}")
        print(f"  Name: {col.get('name')}")
        print(f"  Description: {col.get('description', 'N/A')[:100]}...")
        print(f"  Total Items: {col.get('total_items', 'N/A')}")
    
    # Test fetching items from first collection
    if collections:
        col_id = collections[0]['id']
        print(f"\n=== Testing item fetch from collection {col_id} ===")
        
        result = client.get_items(col_id, per_page=3)
        items = result['items']
        
        print(f"Fetched {len(items)} sample items")
        
        if items:
            print("\nSample item extraction:")
            doc = client.extract_item_content(items[0])
            print(f"  Title: {doc['title']}")
            print(f"  URL: {doc['url']}")
            print(f"  Content preview: {doc['content'][:200]}..." if doc['content'] else "  (No content)")
