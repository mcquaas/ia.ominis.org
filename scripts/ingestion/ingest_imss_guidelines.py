#!/usr/bin/env python3
"""
IMSS Clinical Practice Guidelines Ingestion Script for Ominis Health LLM
Fetches all guidelines from IMSS website and prepares them for RAG
"""

import os
import sys
import json
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from urllib.parse import urljoin
import logging
import time
import re

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

BASE_URL = "https://www.imss.gob.mx"
GUIDELINES_URL = f"{BASE_URL}/guias_practicaclinica"


def fetch_page(url: str, retries: int = 3) -> Optional[BeautifulSoup]:
    """Fetch a page and return BeautifulSoup object"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'es-MX,es;q=0.9,en;q=0.8',
    }
    
    for attempt in range(retries):
        try:
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            return BeautifulSoup(response.text, 'html.parser')
        except requests.RequestException as e:
            logger.warning(f"Attempt {attempt + 1} failed for {url}: {e}")
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
    return None


def extract_pdf_content(pdf_url: str) -> str:
    """
    Download and extract text from PDF
    For now, we'll store the URL and metadata - PDF parsing can be added later
    """
    # PDF extraction can be added with PyPDF2 or pdfplumber
    return f"[PDF document available at: {pdf_url}]"


def parse_guideline_item(item_element) -> Dict[str, Any]:
    """Parse a single guideline item from the page"""
    guideline = {}
    
    # Extract title from h2
    h2 = item_element.find('h2')
    if h2:
        guideline['title'] = h2.get_text(strip=True)
        # Try to extract code from title (e.g., "IMSS-081-08" or "GPC-IMSS-635-19")
        code_match = re.search(r'((?:GPC-)?IMSS-\d+(?:-\d+)?)', guideline['title'])
        if code_match:
            guideline['code'] = code_match.group(1)
    
    # Extract category
    category_text = item_element.get_text()
    category_match = re.search(r'Categoría:\s*([^\n]+)', category_text)
    if category_match:
        guideline['category'] = category_match.group(1).strip()
    
    # Extract PDF links
    pdf_links = []
    for link in item_element.find_all('a', href=True):
        href = link['href']
        if '.pdf' in href.lower():
            pdf_info = {
                'url': urljoin(BASE_URL, href),
                'type': 'GER' if 'GER' in link.get_text() else 'GRR' if 'GRR' in link.get_text() else 'PDF',
                'label': link.get_text(strip=True)
            }
            pdf_links.append(pdf_info)
    
    guideline['pdf_links'] = pdf_links
    
    return guideline


def get_all_guidelines() -> List[Dict[str, Any]]:
    """Fetch all guidelines from all pages"""
    all_guidelines = []
    seen_titles = set()  # Track unique guidelines
    
    # First, determine max pages by checking the pager on page 0
    first_url = f"{GUIDELINES_URL}?field_categoria_gs_value=All"
    first_soup = fetch_page(first_url)
    
    max_page = 0
    if first_soup:
        # Find all page links to determine total pages
        pager_items = first_soup.find_all('a', href=lambda x: x and 'page=' in x)
        for pi in pager_items:
            href = pi.get('href', '')
            page_match = re.search(r'page=(\d+)', href)
            if page_match:
                max_page = max(max_page, int(page_match.group(1)))
        
        # Also check for "última" (last) link
        last_link = first_soup.find('a', string=lambda x: x and 'última' in str(x).lower())
        if last_link and last_link.get('href'):
            page_match = re.search(r'page=(\d+)', last_link.get('href', ''))
            if page_match:
                max_page = max(max_page, int(page_match.group(1)))
    
    logger.info(f"Detected {max_page + 1} total pages to fetch")
    
    # Fetch all pages from 0 to max_page
    for page in range(max_page + 1):
        if page == 0:
            url = f"{GUIDELINES_URL}?field_categoria_gs_value=All"
        else:
            url = f"{GUIDELINES_URL}?field_categoria_gs_value=All&page={page}"
        
        logger.info(f"Fetching page {page + 1}/{max_page + 1}: {url}")
        
        # Add cache-busting parameter
        cache_bust_url = f"{url}&_={int(time.time())}"
        soup = fetch_page(cache_bust_url)
        if not soup:
            # Retry without cache buster
            soup = fetch_page(url)
        
        if not soup:
            logger.error(f"Failed to fetch page {page}")
            continue
        
        # Parse guidelines from page
        page_guidelines = []
        
        # Method 1: Find all h2 tags that contain guideline codes
        all_h2 = soup.find_all('h2')
        for h2 in all_h2:
            text = h2.get_text(strip=True)
            if 'IMSS' in text or 'GPC' in text or 'Síndrome' in text:
                # Get the parent container
                parent = h2.find_parent(['li', 'article', 'div'])
                if parent:
                    guideline = parse_guideline_item(parent)
                    title = guideline.get('title', '')
                    if title and title not in seen_titles:
                        seen_titles.add(title)
                        page_guidelines.append(guideline)
        
        # Method 2: Look for list items with guideline patterns
        if not page_guidelines:
            items = soup.find_all('li')
            for item in items:
                h2 = item.find('h2')
                if h2:
                    text = h2.get_text(strip=True)
                    if 'IMSS' in text or 'GPC' in text:
                        guideline = parse_guideline_item(item)
                        title = guideline.get('title', '')
                        if title and title not in seen_titles:
                            seen_titles.add(title)
                            page_guidelines.append(guideline)
        
        all_guidelines.extend(page_guidelines)
        logger.info(f"Found {len(page_guidelines)} new guidelines on page {page + 1} (total: {len(all_guidelines)})")
        
        # Be polite to the server
        time.sleep(0.5)
    
    return all_guidelines


def convert_to_rag_format(guidelines: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Convert guidelines to RAG document format"""
    documents = []
    
    for i, g in enumerate(guidelines):
        doc_id = g.get('code', f"imss-guideline-{i+1}")
        
        # Build content from available information
        content_parts = [
            f"# {g.get('title', 'Sin título')}",
            "",
            f"**Categoría:** {g.get('category', 'No especificada')}",
            "",
            "## Documentos disponibles:",
        ]
        
        for pdf in g.get('pdf_links', []):
            content_parts.append(f"- [{pdf.get('label', 'PDF')}]({pdf.get('url', '')})")
        
        document = {
            'id': doc_id,
            'title': g.get('title', 'Sin título'),
            'content': '\n'.join(content_parts),
            'source': 'IMSS - Guías de Práctica Clínica',
            'url': f"{GUIDELINES_URL}",
            'category': g.get('category', 'No especificada'),
            'pdf_links': g.get('pdf_links', []),
            'ingested_at': datetime.now(timezone.utc).isoformat(),
            'metadata': {
                'source_type': 'clinical_guideline',
                'institution': 'IMSS',
                'institution_full': 'Instituto Mexicano del Seguro Social',
                'country': 'Mexico',
                'language': 'es'
            }
        }
        
        documents.append(document)
    
    return documents


def save_guidelines_local(documents: List[Dict[str, Any]], output_dir: str = None):
    """Save guidelines to local JSON files"""
    if output_dir is None:
        output_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'imss_guidelines')
    
    os.makedirs(output_dir, exist_ok=True)
    
    # Save individual documents
    for doc in documents:
        filename = f"{doc['id']}.json"
        filepath = os.path.join(output_dir, filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(doc, ensure_ascii=False, indent=2, fp=f)
    
    # Save manifest
    manifest = {
        'created_at': datetime.now(timezone.utc).isoformat(),
        'document_count': len(documents),
        'source': 'IMSS Guías de Práctica Clínica',
        'documents': [
            {
                'id': doc['id'],
                'title': doc['title'],
                'category': doc['category']
            }
            for doc in documents
        ]
    }
    
    manifest_path = os.path.join(output_dir, 'manifest.json')
    with open(manifest_path, 'w', encoding='utf-8') as f:
        json.dump(manifest, ensure_ascii=False, indent=2, fp=f)
    
    logger.info(f"Saved {len(documents)} documents to {output_dir}")
    return output_dir


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Ingest IMSS Clinical Practice Guidelines')
    parser.add_argument('--output-dir', help='Output directory for JSON files')
    parser.add_argument('--dry-run', action='store_true', help='Only fetch and display, do not save')
    
    args = parser.parse_args()
    
    logger.info("Starting IMSS Guidelines ingestion...")
    logger.info(f"Source: {GUIDELINES_URL}")
    
    # Fetch all guidelines
    guidelines = get_all_guidelines()
    logger.info(f"Total guidelines found: {len(guidelines)}")
    
    if not guidelines:
        logger.error("No guidelines found!")
        sys.exit(1)
    
    # Convert to RAG format
    documents = convert_to_rag_format(guidelines)
    
    if args.dry_run:
        print("\n" + "=" * 60)
        print("DRY RUN - Guidelines found:")
        print("=" * 60)
        for doc in documents:
            print(f"\n[{doc['id']}] {doc['title']}")
            print(f"  Category: {doc['category']}")
            print(f"  PDFs: {len(doc.get('pdf_links', []))}")
        return
    
    # Save locally
    output_dir = save_guidelines_local(documents, args.output_dir)
    
    print("\n" + "=" * 60)
    print("INGESTION COMPLETE")
    print("=" * 60)
    print(f"Total guidelines: {len(documents)}")
    print(f"Output directory: {output_dir}")
    print("\nTo add to RAG, run:")
    print(f"  python scripts/rag/build_index.py --prefixes imss_guidelines")


if __name__ == '__main__':
    main()
