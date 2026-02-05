#!/usr/bin/env python3
"""
WordPress to S3 Ingestion Pipeline for Ominis Health LLM
Fetches content from WordPress and stores in S3
"""

import os
import sys
import json
import boto3
from datetime import datetime
from typing import List, Dict, Any
import logging
import argparse

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from wordpress_client import WordPressClient, extract_content

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
    
    def upload_document(self, document: Dict[str, Any], prefix: str = 'wordpress') -> str:
        """
        Upload a single document to S3
        
        Args:
            document: Document dictionary
            prefix: S3 key prefix
            
        Returns:
            S3 key of uploaded document
        """
        doc_id = document.get('id', 'unknown')
        key = f"{prefix}/{doc_id}.json"
        
        self.s3.put_object(
            Bucket=self.bucket_name,
            Key=key,
            Body=json.dumps(document, ensure_ascii=False, indent=2),
            ContentType='application/json'
        )
        
        return key
    
    def upload_batch(self, documents: List[Dict[str, Any]], prefix: str = 'wordpress') -> Dict[str, Any]:
        """
        Upload multiple documents to S3
        
        Args:
            documents: List of document dictionaries
            prefix: S3 key prefix
            
        Returns:
            Summary of upload operation
        """
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
    
    def upload_manifest(self, documents: List[Dict[str, Any]], prefix: str = 'wordpress') -> str:
        """
        Create and upload a manifest file with document metadata
        
        Args:
            documents: List of documents
            prefix: S3 key prefix
            
        Returns:
            S3 key of manifest
        """
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
    wordpress_url: str,
    s3_bucket: str,
    api_key: str = None,
    max_posts: int = None,
    post_types: List[str] = None
) -> Dict[str, Any]:
    """
    Run the full ingestion pipeline
    
    Args:
        wordpress_url: WordPress site URL
        s3_bucket: S3 bucket for raw data
        api_key: Optional WordPress API key
        max_posts: Maximum posts to fetch per type
        post_types: List of post types to fetch
        
    Returns:
        Summary of ingestion
    """
    if post_types is None:
        post_types = ['posts', 'pages']
    
    logger.info(f"Starting ingestion from {wordpress_url}")
    
    # Initialize clients
    wp_client = WordPressClient(wordpress_url, api_key)
    s3_store = S3DataStore(s3_bucket)
    
    # Test connection
    if not wp_client.test_connection():
        raise ConnectionError(f"Cannot connect to WordPress at {wordpress_url}")
    
    all_documents = []
    summary = {
        'wordpress_url': wordpress_url,
        's3_bucket': s3_bucket,
        'started_at': datetime.utcnow().isoformat(),
        'post_types': {}
    }
    
    # Fetch and process each post type
    for post_type in post_types:
        logger.info(f"Processing {post_type}...")
        
        try:
            posts = wp_client.get_all_posts(post_type=post_type, max_posts=max_posts)
            
            # Extract content from posts
            documents = []
            for post in posts:
                try:
                    doc = extract_content(post)
                    doc['post_type'] = post_type
                    documents.append(doc)
                except Exception as e:
                    logger.error(f"Error processing post {post.get('id')}: {e}")
            
            # Upload to S3
            upload_result = s3_store.upload_batch(documents, prefix=f"wordpress/{post_type}")
            
            all_documents.extend(documents)
            summary['post_types'][post_type] = {
                'fetched': len(posts),
                'processed': len(documents),
                **upload_result
            }
            
        except Exception as e:
            logger.error(f"Error processing {post_type}: {e}")
            summary['post_types'][post_type] = {'error': str(e)}
    
    # Upload manifest
    if all_documents:
        manifest_key = s3_store.upload_manifest(all_documents, prefix='wordpress')
        summary['manifest_key'] = manifest_key
    
    summary['completed_at'] = datetime.utcnow().isoformat()
    summary['total_documents'] = len(all_documents)
    
    # Upload summary
    s3_store.s3.put_object(
        Bucket=s3_bucket,
        Key='wordpress/ingestion_summary.json',
        Body=json.dumps(summary, ensure_ascii=False, indent=2),
        ContentType='application/json'
    )
    
    logger.info(f"Ingestion complete. Total documents: {len(all_documents)}")
    return summary


def main():
    parser = argparse.ArgumentParser(description='Ingest WordPress content to S3')
    parser.add_argument('--url', required=True, help='WordPress site URL')
    parser.add_argument('--bucket', default='ominis-health-raw-data', help='S3 bucket name')
    parser.add_argument('--api-key', help='WordPress API key (optional)')
    parser.add_argument('--max-posts', type=int, help='Max posts per type')
    parser.add_argument('--post-types', nargs='+', default=['posts', 'pages'],
                        help='Post types to fetch')
    
    args = parser.parse_args()
    
    try:
        summary = run_ingestion(
            wordpress_url=args.url,
            s3_bucket=args.bucket,
            api_key=args.api_key,
            max_posts=args.max_posts,
            post_types=args.post_types
        )
        
        print("\n" + "=" * 60)
        print("INGESTION SUMMARY")
        print("=" * 60)
        print(json.dumps(summary, indent=2))
        
    except Exception as e:
        logger.error(f"Ingestion failed: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
