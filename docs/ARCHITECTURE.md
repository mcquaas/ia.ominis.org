# Ominis Health LLM - Architecture Documentation

This document provides a detailed technical overview of the Ominis Health LLM system architecture.

**All components run 100% within Mexico (AWS mx-central-1) with no external AI API calls.**

## Table of Contents

- [System Overview](#system-overview)
- [Component Architecture](#component-architecture)
- [Data Flow](#data-flow)
- [AWS Resources](#aws-resources)
- [Security Architecture](#security-architecture)
- [Scalability Considerations](#scalability-considerations)

## System Overview

Ominis Health LLM is a Retrieval-Augmented Generation (RAG) system designed to provide accurate health information in Spanish. The system follows a serverless architecture pattern with self-hosted LLM inference, ensuring **100% data residency in Mexico**.

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              USER LAYER                                  │
│  ┌─────────────────────────────────────────────────────────────────────┐│
│  │                      Frontend (index.html)                          ││
│  │  - Chat interface                                                   ││
│  │  - Source display                                                   ││
│  │  - API endpoint configuration                                       ││
│  └─────────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ HTTPS
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    API LAYER (mx-central-1 - Mexico)                     │
│  ┌─────────────────────────────────────────────────────────────────────┐│
│  │                    AWS API Gateway                                  ││
│  │  - REST API endpoint                                                ││
│  │  - CORS configuration                                               ││
│  │  - Request validation                                               ││
│  └─────────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ AWS Internal
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    COMPUTE LAYER (mx-central-1 - Mexico)                 │
│  ┌─────────────────────────────────────────────────────────────────────┐│
│  │                    AWS Lambda (ominis-query)                        ││
│  │  1. Parse request                                                   ││
│  │  2. Load cached chunks from S3                                      ││
│  │  3. Search for relevant content (keyword + semantic)                ││
│  │  4. Build context from results                                      ││
│  │  5. Call Ominis-2.0 LLM (EC2 in Mexico)                             ││
│  │  6. Return formatted response                                       ││
│  └─────────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┴───────────────┐
                    │                               │
                    ▼                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    SERVICE LAYER (mx-central-1 - Mexico)                 │
│  ┌───────────────────────────┐  ┌───────────────────────────────────┐  │
│  │ S3 Storage (mx-central-1) │  │ Ominis-2.0 on EC2 (mx-central-1)  │  │
│  │                           │  │                                    │  │
│  │ - Vector index            │  │ - Self-hosted LLM inference       │  │
│  │ - Document chunks         │  │ - Medical-focused model           │  │
│  │ - Metadata                │  │ - No external API calls           │  │
│  │ - Raw content             │  │ - 100% Mexico data residency      │  │
│  └───────────────────────────┘  └───────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
```

### Key Design Principles

1. **100% Mexico Data Residency**: All data storage and processing in mx-central-1
2. **Self-hosted LLM**: Ominis-2.0 on EC2 eliminates external AI API dependencies
3. **Local Embeddings**: Sentence-transformers run locally during indexing
4. **No External Calls**: Query processing makes no calls outside Mexico
5. **Serverless API**: Lambda + API Gateway for cost efficiency

## Component Architecture

### 1. Data Ingestion Pipeline

The ingestion pipeline fetches content from WordPress/Tainacan and prepares it for the RAG system.

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  WordPress/  │────▶│   Content    │────▶│   Document   │────▶│   S3 Raw     │
│  Tainacan    │     │   Extraction │     │   Formatting │     │   (Mexico)   │
│  API         │     │              │     │              │     │              │
└──────────────┘     └──────────────┘     └──────────────┘     └──────────────┘
```

**Components:**
- `wordpress_client.py`: WordPress REST API client
- `tainacan_client.py`: Tainacan collection API client
- `ingest_wordpress.py`: WordPress ingestion orchestrator
- `ingest_tainacan.py`: Tainacan ingestion orchestrator

**Data Extracted:**
- Post/page content (HTML → Markdown)
- Titles and URLs
- Metadata (categories, tags, dates)
- Tainacan custom fields

### 2. RAG Index Building Pipeline

Transforms raw documents into a searchable vector index. **All processing runs locally - no external API calls.**

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   S3 Raw     │────▶│   Document   │────▶│   Embedding  │────▶│   FAISS      │
│   Documents  │     │   Chunking   │     │   Generation │     │   Index      │
│   (Mexico)   │     │              │     │   (LOCAL)    │     │   (Mexico)   │
└──────────────┘     └──────────────┘     └──────────────┘     └──────────────┘
                            │                    │
                            ▼                    ▼
                     512 tokens/chunk      sentence-transformers
                     50 token overlap      (runs locally)
```

**Components:**
- `chunker.py`: Document segmentation (512 tokens, 50 overlap)
- `embedder.py`: Text → vector using local sentence-transformers
- `vector_store.py`: FAISS index management
- `build_index.py`: Pipeline orchestrator

**Embedding Generation:**
- Model: `sentence-transformers/all-MiniLM-L6-v2`
- Dimension: 384
- Runs locally on build machine - no external API calls
- Index uploaded to S3 in Mexico

### 3. Query Processing Pipeline

Real-time query handling in AWS Lambda with self-hosted LLM.

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   User       │────▶│   Keyword    │────▶│   Content    │────▶│   Context    │
│   Question   │     │   Matching   │     │   Retrieval  │     │   Building   │
└──────────────┘     └──────────────┘     └──────────────┘     └──────────────┘
                                                                      │
┌──────────────┐     ┌──────────────┐     ┌──────────────┐           │
│   Response   │◀────│   Answer     │◀────│   Ollama     │◀──────────┘
│   + Sources  │     │   Formatting │     │   (EC2 MX)   │
└──────────────┘     └──────────────┘     └──────────────┘
```

**Processing Steps:**
1. **Parse Request**: Extract question from API call
2. **Load Chunks**: Get cached document chunks from S3
3. **Keyword Search**: Find relevant chunks using semantic keyword matching
4. **Context Building**: Format retrieved chunks with metadata
5. **LLM Generation**: Generate answer via Ominis-2.0 on EC2 in Mexico
6. **Response Formatting**: Structure answer with source citations

**Search Algorithm:**
The Lambda uses a lightweight semantic search without external embeddings:
- Word overlap scoring with stop word filtering
- Phrase match boosting
- Title match boosting
- All computation stays in Mexico

### 4. LLM Inference (Ominis-2.0)

Self-hosted LLM inference ensures no data leaves Mexico.

```
┌─────────────────────────────────────────────────────────────────┐
│              Ominis-2.0 Server (EC2 mx-central-1)                │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                     Ominis-2.0 Model                       │  │
│  │  - Optimized for health information                       │  │
│  │  - Spanish language support                               │  │
│  │  - Runs entirely within Mexico                            │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                     Ollama API                             │  │
│  │  - POST /api/generate                                     │  │
│  │  - Temperature: 0.3 (factual responses)                   │  │
│  │  - Max tokens: 1024                                       │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

**Configuration:**
- Endpoint: `http://ollama-ec2:11434/api/generate`
- Model: Ominis-2.0 (7B parameters, 32K context)
- No external API calls - 100% self-hosted

**Model Specifications:**
| Spec | Value |
|------|-------|
| Parameters | 7 billion |
| Context | 32,768 tokens |
| Training | ~3M PubMed articles |
| Architecture | Transformer + GQA |

For complete model documentation, see [MODEL.md](MODEL.md).

### 5. Vector Store Architecture

FAISS-based similarity search with S3 persistence.

```
┌─────────────────────────────────────────────────────────────────┐
│                       S3 Persistence (Mexico)                    │
│  vectors/                                                        │
│  ├── chunks.json      # Chunk content + metadata                │
│  ├── embeddings.json  # Pre-computed embeddings (optional)      │
│  └── metadata.json    # Index configuration                     │
└─────────────────────────────────────────────────────────────────┘
```

## Data Flow

### Ingestion Flow

```
1. Content Source (WordPress/Tainacan)
   └─▶ API Request (GET posts/items)
       └─▶ HTML Content
           └─▶ Markdown Conversion (html2text)
               └─▶ Structured Document
                   └─▶ S3 Upload (mx-central-1)
                       └─▶ Manifest Generation
```

### Index Building Flow

```
1. S3 Raw Documents (Mexico)
   └─▶ Document Loading
       └─▶ Text Chunking (512 tokens)
           └─▶ Local Embedding Generation
               └─▶ sentence-transformers (no external API)
                   └─▶ FAISS Index Creation
                       └─▶ S3 Upload (mx-central-1)
```

### Query Flow (100% Mexico)

```
1. User Question (Spanish)
   └─▶ API Gateway (mx-central-1)
       └─▶ Lambda Handler (mx-central-1)
           └─▶ Load Chunks from S3 (mx-central-1)
               └─▶ Keyword Semantic Search (in-memory)
                   └─▶ Build Context String
                       └─▶ Ollama API Call (EC2 mx-central-1)
                           └─▶ Response + Sources
                               └─▶ API Response (JSON)
```

**No external calls at any step.**

## AWS Resources

### Resource Inventory

| Resource Type | Name | Region | Purpose |
|---------------|------|--------|---------|
| S3 Bucket | ominis-health-raw-data-mx | mx-central-1 | Raw ingested content |
| S3 Bucket | ominis-health-processed-data-mx | mx-central-1 | Processed chunks |
| S3 Bucket | ominis-health-embeddings-mx | mx-central-1 | Vector index storage |
| S3 Bucket | ominis-health-models-mx | mx-central-1 | Model artifacts |
| EC2 Instance | ominis-2.0-server | mx-central-1 | Ominis-2.0 LLM inference |
| IAM Role | ominis-lambda-role | Global | Lambda execution |
| Lambda Function | ominis-query | mx-central-1 | Query processing |
| API Gateway | ominis-health-api | mx-central-1 | REST API |

### IAM Permissions

**Lambda Execution Role:**
```json
{
  "s3:GetObject": "ominis-health-* buckets",
  "s3:ListBucket": "ominis-health-* buckets",
  "logs:*": "CloudWatch Logs"
}
```

Note: No Bedrock or SageMaker permissions needed - LLM runs on self-hosted EC2.

## Security Architecture

### Network Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     Security Boundaries                          │
│                                                                  │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────┐       │
│  │   Public    │────▶│ API Gateway │────▶│   Lambda    │       │
│  │   Internet  │     │  (CORS)     │     │             │       │
│  └─────────────┘     └─────────────┘     └─────────────┘       │
│                                                 │                │
│                                    ┌────────────┘                │
│                                    ▼                             │
│                           ┌─────────────┐                       │
│                           │ EC2 Ollama  │                       │
│                           │ (VPC only)  │                       │
│                           └─────────────┘                       │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Data Protection

- **At Rest**: S3 server-side encryption (SSE-S3)
- **In Transit**: TLS 1.2+ for all API calls
- **Access Control**: IAM policies with least privilege
- **LLM Security**: Ollama runs in private VPC subnet

## Scalability Considerations

### Current Limitations

| Component | Limit | Mitigation |
|-----------|-------|------------|
| Lambda Memory | 10GB max | Sufficient for chunk search |
| Lambda Timeout | 15 min | Queries complete in <30s |
| Ominis-2.0 Throughput | EC2 instance size | Scale vertically or add replicas |
| Cold Start | ~5-10s | Provisioned concurrency option |

### Scaling Strategy

1. **Query Scaling**: Lambda auto-scales to demand
2. **LLM Scaling**: Add Ominis-2.0 replicas behind load balancer
3. **Storage Scaling**: S3 scales automatically
4. **Cost Scaling**: Pay-per-use model optimal for variable load

### Performance Optimization

- **Lambda Warm Starts**: Chunks cached in global scope
- **Keyword Search**: Fast in-memory search without external API calls
- **Model Caching**: Ominis-2.0 stays loaded in memory
- **Connection Reuse**: Keep-alive connections to LLM server

---

For implementation details, see [DEVELOPMENT.md](DEVELOPMENT.md).
For data privacy information, see [DATA_PRIVACY.md](DATA_PRIVACY.md).
