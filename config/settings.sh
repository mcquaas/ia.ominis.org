#!/bin/bash
# Ominis Health LLM - Configuration Settings
# 100% Data Residency in Mexico - No cross-region services

# Project
export PROJECT_NAME="ominis-health"
export ENVIRONMENT="dev"

# AWS - 100% Mexico (mx-central-1)
export AWS_REGION="mx-central-1"
export AWS_ACCOUNT_ID="945284793685"

# S3 Buckets (all in mx-central-1 for 100% data residency in Mexico)
export S3_BUCKET_RAW="ominis-health-raw-data-mx"
export S3_BUCKET_PROCESSED="ominis-health-processed-data-mx"
export S3_BUCKET_EMBEDDINGS="ominis-health-embeddings-mx"
export S3_BUCKET_MODELS="ominis-health-models-mx"

# WordPress/Tainacan API
export WORDPRESS_API_URL="https://ominis.org"
export WORDPRESS_API_KEY=""  # Optional: add if authentication required

# Tainacan Configuration
export TAINACAN_COLLECTION_ID=""  # Will be auto-detected

# Lambda
export LAMBDA_ROLE_NAME="ominis-lambda-role"
export LAMBDA_FUNCTION_INGESTION="ominis-ingestion"
export LAMBDA_FUNCTION_QUERY="ominis-query"

# API Gateway
export API_NAME="ominis-health-api"

# Ollama Configuration (self-hosted LLM on EC2 in Mexico)
export OLLAMA_URL="http://localhost:11434"
export OLLAMA_MODEL="ominis-2.0"  # Ominis Health medical LLM

# Embedding Configuration (local, no external API calls)
export EMBEDDING_MODEL="sentence-transformers/all-MiniLM-L6-v2"
