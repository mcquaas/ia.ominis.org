#!/usr/bin/env python3
"""
Export embeddings to a separate JSON file for Lambda
"""

import os
import sys
import json
import boto3

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from embedder import EmbeddingGenerator

BUCKET = os.environ.get('EMBEDDINGS_BUCKET', 'ominis-health-embeddings-mx')
PREFIX = os.environ.get('VECTOR_PREFIX', 'vectors')
REGION = os.environ.get('AWS_REGION', 'mx-central-1')


def main():
    s3 = boto3.client('s3', region_name=REGION)
    
    # Load chunks
    print(f"Loading chunks from s3://{BUCKET}/{PREFIX}/chunks.json")
    response = s3.get_object(Bucket=BUCKET, Key=f"{PREFIX}/chunks.json")
    chunks = json.loads(response['Body'].read().decode('utf-8'))
    
    print(f"Loaded {len(chunks)} chunks")
    
    # Generate embeddings
    print("Generating embeddings...")
    embedder = EmbeddingGenerator()
    
    texts = [chunk.get('content', '') for chunk in chunks]
    embeddings = embedder.embed_texts(texts)
    
    # Convert to list format
    embeddings_list = [emb.tolist() for emb in embeddings]
    
    # Upload
    print(f"Uploading embeddings to s3://{BUCKET}/{PREFIX}/embeddings.json")
    s3.put_object(
        Bucket=BUCKET,
        Key=f"{PREFIX}/embeddings.json",
        Body=json.dumps(embeddings_list),
        ContentType='application/json'
    )
    
    print("Done!")


if __name__ == '__main__':
    main()
