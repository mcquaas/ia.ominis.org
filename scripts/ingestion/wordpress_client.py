"""
WordPress API Client for Ominis Health LLM
Fetches content from WordPress REST API
"""

import os
import json
import requests
from typing import List, Dict, Any, Optional
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class WordPressClient:
    """Client to interact with WordPress REST API"""
    
    def __init__(self, base_url: str, api_key: Optional[str] = None):
        """
        Initialize WordPress client
        
        Args:
            base_url: WordPress site URL (e.g., https://example.com)
            api_key: Optional API key for authentication
        """
        self.base_url = base_url.rstrip('/')
        self.api_url = f"{self.base_url}/wp-json/wp/v2"
        self.session = requests.Session()
        
        if api_key:
            self.session.headers.update({
                'Authorization': f'Bearer {api_key}'
            })
        
        self.session.headers.update({
            'User-Agent': 'Ominis-Health-Ingestion/1.0'
        })
    
    def get_posts(self, 
                  per_page: int = 100, 
                  page: int = 1,
                  post_type: str = 'posts',
                  status: str = 'publish') -> List[Dict[str, Any]]:
        """
        Fetch posts from WordPress
        
        Args:
            per_page: Number of posts per page (max 100)
            page: Page number
            post_type: Type of content (posts, pages, etc.)
            status: Post status filter
            
        Returns:
            List of post dictionaries
        """
        endpoint = f"{self.api_url}/{post_type}"
        params = {
            'per_page': min(per_page, 100),
            'page': page,
            'status': status,
            '_embed': True  # Include embedded data (author, featured image, etc.)
        }
        
        try:
            response = self.session.get(endpoint, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching {post_type} page {page}: {e}")
            return []
    
    def get_all_posts(self, 
                      post_type: str = 'posts',
                      max_posts: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Fetch all posts of a given type
        
        Args:
            post_type: Type of content to fetch
            max_posts: Maximum number of posts to fetch (None = all)
            
        Returns:
            List of all posts
        """
        all_posts = []
        page = 1
        per_page = 100
        
        while True:
            logger.info(f"Fetching {post_type} page {page}...")
            posts = self.get_posts(per_page=per_page, page=page, post_type=post_type)
            
            if not posts:
                break
            
            all_posts.extend(posts)
            
            if max_posts and len(all_posts) >= max_posts:
                all_posts = all_posts[:max_posts]
                break
            
            if len(posts) < per_page:
                break
            
            page += 1
        
        logger.info(f"Fetched {len(all_posts)} {post_type}")
        return all_posts
    
    def get_categories(self) -> List[Dict[str, Any]]:
        """Fetch all categories"""
        return self._get_taxonomy('categories')
    
    def get_tags(self) -> List[Dict[str, Any]]:
        """Fetch all tags"""
        return self._get_taxonomy('tags')
    
    def _get_taxonomy(self, taxonomy: str) -> List[Dict[str, Any]]:
        """Fetch all items from a taxonomy"""
        endpoint = f"{self.api_url}/{taxonomy}"
        params = {'per_page': 100}
        
        all_items = []
        page = 1
        
        while True:
            params['page'] = page
            try:
                response = self.session.get(endpoint, params=params)
                response.raise_for_status()
                items = response.json()
                
                if not items:
                    break
                
                all_items.extend(items)
                
                if len(items) < 100:
                    break
                
                page += 1
            except requests.exceptions.RequestException as e:
                logger.error(f"Error fetching {taxonomy}: {e}")
                break
        
        return all_items
    
    def test_connection(self) -> bool:
        """Test if the WordPress API is accessible"""
        try:
            response = self.session.get(f"{self.base_url}/wp-json")
            response.raise_for_status()
            info = response.json()
            logger.info(f"Connected to: {info.get('name', 'Unknown')}")
            return True
        except Exception as e:
            logger.error(f"Connection failed: {e}")
            return False


def extract_content(post: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract relevant content from a WordPress post
    
    Args:
        post: Raw WordPress post data
        
    Returns:
        Cleaned and structured document
    """
    from bs4 import BeautifulSoup
    import html2text
    
    # HTML to text converter
    h2t = html2text.HTML2Text()
    h2t.ignore_links = False
    h2t.ignore_images = True
    h2t.body_width = 0
    
    # Extract raw HTML content
    title_html = post.get('title', {}).get('rendered', '')
    content_html = post.get('content', {}).get('rendered', '')
    excerpt_html = post.get('excerpt', {}).get('rendered', '')
    
    # Clean HTML
    title = BeautifulSoup(title_html, 'html.parser').get_text().strip()
    content = h2t.handle(content_html).strip()
    excerpt = BeautifulSoup(excerpt_html, 'html.parser').get_text().strip()
    
    # Extract categories and tags
    categories = []
    tags = []
    
    if '_embedded' in post:
        embedded = post['_embedded']
        if 'wp:term' in embedded:
            for term_group in embedded['wp:term']:
                for term in term_group:
                    if term.get('taxonomy') == 'category':
                        categories.append(term.get('name'))
                    elif term.get('taxonomy') == 'post_tag':
                        tags.append(term.get('name'))
    
    # Build structured document
    document = {
        'id': str(post.get('id')),
        'title': title,
        'content': content,
        'excerpt': excerpt,
        'url': post.get('link', ''),
        'date_published': post.get('date', ''),
        'date_modified': post.get('modified', ''),
        'categories': categories,
        'tags': tags,
        'author': extract_author(post),
        'source': 'wordpress',
        'ingested_at': datetime.utcnow().isoformat()
    }
    
    return document


def extract_author(post: Dict[str, Any]) -> str:
    """Extract author name from post"""
    if '_embedded' in post and 'author' in post['_embedded']:
        authors = post['_embedded']['author']
        if authors:
            return authors[0].get('name', 'Unknown')
    return 'Unknown'


if __name__ == '__main__':
    # Test with a sample WordPress site
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python wordpress_client.py <wordpress_url>")
        sys.exit(1)
    
    url = sys.argv[1]
    client = WordPressClient(url)
    
    if client.test_connection():
        print("Connection successful!")
        posts = client.get_posts(per_page=5)
        print(f"Found {len(posts)} posts")
        
        if posts:
            doc = extract_content(posts[0])
            print(f"\nSample document:")
            print(f"  Title: {doc['title']}")
            print(f"  Categories: {doc['categories']}")
            print(f"  Content preview: {doc['content'][:200]}...")
