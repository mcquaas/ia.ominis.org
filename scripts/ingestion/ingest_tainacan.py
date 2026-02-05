#!/usr/bin/env python3
"""
Tainacan to S3 Ingestion Pipeline for Ominis Health LLM
Fetches items from Tainacan collections and stores in S3
"""

import os
import sys
import json
import boto3
from datetime import datetime
from typing import List, Dict, Any, Optional
import logging
import argparse

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tainacan_client import TainacanClient

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class S3DataStore:
    """Store documents in S3"""
    
    def __init__(self, bucket_name: str, region: str = 'us-east-2'):
        self.bucket_name = bucket_name
        self.s3 = boto3.client('s3', region_name=region)
    
    def upload_document(self, document: Dict[str, Any], prefix: str = 'tainacan') -> str:
        """Upload a single document to S3"""
        doc_id = document.get('id', 'unknown')
        key = f"{prefix}/{doc_id}.json"
        
        self.s3.put_object(
            Bucket=self.bucket_name,
            Key=key,
            Body=json.dumps(document, ensure_ascii=False, indent=2),
            ContentType='application/json'
        )
        
        return key
    
    def upload_batch(self, documents: List[Dict[str, Any]], prefix: str = 'tainacan') -> Dict[str, Any]:
        """Upload multiple documents to S3"""
        uploaded = []
        failed = []
        
        for doc in documents:
            try:
                key = self.upload_document(doc, prefix)
                uploaded.append(key)
            except Exception as e:
                logger.error(f"Failed to upload document {doc.get('id')}: {e}")
                failed.append(doc.get('id'))
        
        return {
            'uploaded_count': len(uploaded),
            'failed_count': len(failed),
            'failed_ids': failed
        }
    
    def upload_manifest(self, documents: List[Dict[str, Any]], prefix: str = 'tainacan') -> str:
        """Create and upload a manifest file"""
        manifest = {
            'created_at': datetime.utcnow().isoformat(),
            'document_count': len(documents),
            'documents': [
                {
                    'id': doc.get('id'),
                    'title': doc.get('title'),
                    'url': doc.get('url'),
                    's3_key': f"{prefix}/{doc.get('id')}.json"
                }
                for doc in documents
            ]
        }
        
        key = f"{prefix}/manifest.json"
        self.s3.put_object(
            Bucket=self.bucket_name,
            Key=key,
            Body=json.dumps(manifest, ensure_ascii=False, indent=2),
            ContentType='application/json'
        )
        
        return key


def run_ingestion(
    base_url: str,
    s3_bucket: str,
    api_key: str = None,
    collection_ids: List[int] = None,
    max_items: int = None
) -> Dict[str, Any]:
    """
    Run the full Tainacan ingestion pipeline
    
    Args:
        base_url: WordPress/Tainacan site URL
        s3_bucket: S3 bucket for raw data
        api_key: Optional API key
        collection_ids: Specific collection IDs to ingest (None = all)
        max_items: Maximum items to fetch per collection
        
    Returns:
        Summary of ingestion
    """
    logger.info(f"Starting Tainacan ingestion from {base_url}")
    
    # Initialize clients
    tainacan = TainacanClient(base_url, api_key)
    s3_store = S3DataStore(s3_bucket)
    
    # Test connection
    if not tainacan.test_connection():
        raise ConnectionError(f"Cannot connect to Tainacan at {base_url}")
    
    # Get collections
    collections = tainacan.get_collections()
    
    if collection_ids:
        collections = [c for c in collections if c.get('id') in collection_ids]
    
    if not collections:
        raise ValueError("No collections found!")
    
    summary = {
        'base_url': base_url,
        's3_bucket': s3_bucket,
        'started_at': datetime.utcnow().isoformat(),
        'collections': {}
    }
    
    all_documents = []
    
    # Process each collection
    for collection in collections:
        col_id = collection.get('id')
        col_name = collection.get('name', f'Collection {col_id}')
        
        logger.info(f"\n{'='*60}")
        logger.info(f"Processing collection: {col_name} (ID: {col_id})")
        logger.info(f"{'='*60}")
        
        try:
            # Fetch all items
            items = tainacan.get_all_items(col_id, max_items=max_items)
            
            # Extract content
            documents = []
            for item in items:
                try:
                    doc = tainacan.extract_item_content(item)
                    doc['collection_name'] = col_name
                    documents.append(doc)
                except Exception as e:
                    logger.error(f"Error processing item {item.get('id')}: {e}")
            
            # Upload to S3
            prefix = f"tainacan/collection_{col_id}"
            upload_result = s3_store.upload_batch(documents, prefix=prefix)
            
            all_documents.extend(documents)
            
            summary['collections'][col_name] = {
                'collection_id': col_id,
                'items_fetched': len(items),
                'documents_processed': len(documents),
                **upload_result
            }
            
            logger.info(f"Processed {len(documents)} documents from {col_name}")
            
        except Exception as e:
            logger.error(f"Error processing collection {col_name}: {e}")
            summary['collections'][col_name] = {'error': str(e)}
    
    # Upload combined manifest
    if all_documents:
        manifest_key = s3_store.upload_manifest(all_documents, prefix='tainacan')
        summary['manifest_key'] = manifest_key
    
    summary['completed_at'] = datetime.utcnow().isoformat()
    summary['total_documents'] = len(all_documents)
    
    # Upload summary
    s3_store.s3.put_object(
        Bucket=s3_bucket,
        Key='tainacan/ingestion_summary.json',
        Body=json.dumps(summary, ensure_ascii=False, indent=2),
        ContentType='application/json'
    )
    
    logger.info(f"\n{'='*60}")
    logger.info(f"INGESTION COMPLETE")
    logger.info(f"Total documents: {len(all_documents)}")
    logger.info(f"{'='*60}")
    
    return summary


def main():
    parser = argparse.ArgumentParser(description='Ingest Tainacan content to S3')
    parser.add_argument('--url', default='https://ominis.org', 
                        help='WordPress/Tainacan site URL')
    parser.add_argument('--bucket', default='ominis-health-raw-data', 
                        help='S3 bucket name')
    parser.add_argument('--api-key', help='API key (optional)')
    parser.add_argument('--collection-ids', type=int, nargs='+',
                        help='Specific collection IDs to ingest')
    parser.add_argument('--max-items', type=int, 
                        help='Max items per collection')
    parser.add_argument('--discover', action='store_true',
                        help='Only discover collections, do not ingest')
    
    args = parser.parse_args()
    
    if args.discover:
        # Just discover and show collections
        tainacan = TainacanClient(args.url, args.api_key)
        if not tainacan.test_connection():
            print("Failed to connect!")
            sys.exit(1)
        
        collections = tainacan.get_collections()
        print(f"\nFound {len(collections)} collections:\n")
        for col in collections:
            total = col.get('total_items', {})
            if isinstance(total, dict):
                item_count = total.get('publish', 0)
            else:
                item_count = total
            print(f"  ID: {col.get('id'):5} | Items: {str(item_count):>6} | {col.get('name')}")
        return
    
    try:
        summary = run_ingestion(
            base_url=args.url,
            s3_bucket=args.bucket,
            api_key=args.api_key,
            collection_ids=args.collection_ids,
            max_items=args.max_items
        )
        
        print("\n" + "=" * 60)
        print("INGESTION SUMMARY")
        print("=" * 60)
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        
    except Exception as e:
        logger.error(f"Ingestion failed: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
