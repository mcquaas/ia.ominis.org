#!/usr/bin/env python3
"""
Cleanup duplicate RAG sources in Strapi
Keeps the first source for each externalId and deletes duplicates
"""

import os
import sys
import requests
from collections import defaultdict
import logging
import argparse

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

STRAPI_URL = os.getenv('STRAPI_URL', 'https://admin.ominis.org')
STRAPI_API_TOKEN = os.getenv('STRAPI_API_TOKEN', '')


def get_all_sources(session, api_url):
    """Fetch all sources with pagination"""
    sources = []
    page = 1
    page_size = 100
    
    while True:
        response = session.get(
            f"{api_url}/rag-sources",
            params={
                'pagination[page]': page,
                'pagination[pageSize]': page_size,
                'fields': ['id', 'documentId', 'externalId', 'title', 'createdAt'],
                'sort': 'createdAt:asc'  # Oldest first, so we keep the first created
            }
        )
        
        if response.status_code != 200:
            logger.error(f"Failed to get sources: {response.text}")
            break
        
        data = response.json()
        batch = data.get('data', [])
        sources.extend(batch)
        
        meta = data.get('meta', {}).get('pagination', {})
        logger.info(f"Fetched page {page}/{meta.get('pageCount', '?')} ({len(sources)} total)")
        
        if page >= meta.get('pageCount', 1):
            break
        page += 1
    
    return sources


def find_duplicates(sources):
    """Group sources by externalId and find duplicates"""
    by_external_id = defaultdict(list)
    
    for source in sources:
        ext_id = source.get('externalId') or source.get('attributes', {}).get('externalId')
        if ext_id:
            by_external_id[ext_id].append(source)
    
    duplicates_to_delete = []
    
    for ext_id, group in by_external_id.items():
        if len(group) > 1:
            # Keep the first (oldest), delete the rest
            to_delete = group[1:]
            duplicates_to_delete.extend(to_delete)
            logger.debug(f"ExternalId {ext_id}: keeping ID {group[0].get('id')}, deleting {[s.get('id') for s in to_delete]}")
    
    return duplicates_to_delete


def delete_sources(session, api_url, sources_to_delete, dry_run=False):
    """Delete duplicate sources"""
    deleted = 0
    failed = 0
    
    for source in sources_to_delete:
        # Strapi V5 uses documentId for deletion, not numeric id
        doc_id = source.get('documentId')
        source_id = source.get('id')
        title = source.get('title') or source.get('attributes', {}).get('title', 'Unknown')
        
        if dry_run:
            logger.info(f"Would delete ID {source_id}: {title[:50]}...")
            deleted += 1
        else:
            # Use documentId for deletion in Strapi V5
            delete_id = doc_id if doc_id else source_id
            response = session.delete(f"{api_url}/rag-sources/{delete_id}")
            if response.status_code in [200, 204]:
                deleted += 1
                if deleted % 100 == 0:
                    logger.info(f"Deleted {deleted} duplicates...")
            else:
                logger.error(f"Failed to delete {delete_id}: {response.text[:100]}")
                failed += 1
    
    return deleted, failed


def main():
    parser = argparse.ArgumentParser(description='Cleanup duplicate RAG sources')
    parser.add_argument('--strapi-url', default=STRAPI_URL, help='Strapi API URL')
    parser.add_argument('--api-token', default=STRAPI_API_TOKEN, help='Strapi API token')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be deleted')
    
    args = parser.parse_args()
    
    if not args.api_token:
        logger.error("API token required. Set STRAPI_API_TOKEN or use --api-token")
        sys.exit(1)
    
    api_url = f"{args.strapi_url.rstrip('/')}/api"
    
    session = requests.Session()
    session.headers.update({
        'Authorization': f'Bearer {args.api_token}',
        'Content-Type': 'application/json'
    })
    
    logger.info(f"Connecting to {args.strapi_url}")
    
    # Get all sources
    logger.info("Fetching all RAG sources...")
    sources = get_all_sources(session, api_url)
    logger.info(f"Total sources: {len(sources)}")
    
    # Find duplicates
    logger.info("Finding duplicates...")
    duplicates = find_duplicates(sources)
    logger.info(f"Found {len(duplicates)} duplicates to delete")
    
    if not duplicates:
        logger.info("No duplicates found!")
        return
    
    # Delete duplicates
    mode = "DRY RUN - " if args.dry_run else ""
    logger.info(f"{mode}Deleting duplicates...")
    deleted, failed = delete_sources(session, api_url, duplicates, dry_run=args.dry_run)
    
    print("\n" + "=" * 60)
    print("CLEANUP COMPLETE")
    print("=" * 60)
    print(f"Total sources before: {len(sources)}")
    print(f"Duplicates found: {len(duplicates)}")
    print(f"Deleted: {deleted}")
    print(f"Failed: {failed}")
    print(f"Remaining sources: {len(sources) - deleted}")


if __name__ == '__main__':
    main()
