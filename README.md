# Ominis Health LLM

A Retrieval-Augmented Generation (RAG) health Q&A system with **100% data residency in Mexico**.

Released by [Fundación Mexicana para la Salud A.C.](https://funsalud.org.mx/) through [ai.ominis.org](https://ai.ominis.org)

## Table of Contents

- [Overview](#overview)
- [Key Features](#key-features)
- [Architecture](#architecture)
- [Technology Stack](#technology-stack)
- [Quick Start](#quick-start)
- [Project Structure](#project-structure)
- [Data Privacy & Residency](#data-privacy--residency)
- [API Reference](#api-reference)
- [Documentation](#documentation)
- [License](#license)
- [Support](#support)

## Overview

Ominis Health LLM is an AI-powered health information assistant that provides accurate, sourced answers to health-related questions in Spanish. The system ingests health content from WordPress/Tainacan, creates semantic embeddings, and uses Retrieval-Augmented Generation to answer user queries with citations.

**All data processing and storage remains 100% within Mexico.**

### Purpose

- Provide reliable health information to Spanish-speaking users
- Ensure all answers are grounded in verified medical sources
- Maintain **100% data residency compliance in Mexico**
- Support FUNSALUD's mission of health education

## Key Features

- **RAG-based Q&A**: Answers are grounded in retrieved source documents
- **Source Citations**: Every response includes references to source materials
- **Multi-source Ingestion**: Supports WordPress posts, pages, and Tainacan collections
- **100% Mexico Data Residency**: All data storage and processing in AWS mx-central-1
- **Self-hosted LLM**: Uses Ominis-2.0 model on Ollama in Mexico - no external AI API calls
- **Local Embeddings**: Sentence-transformers run locally - no data leaves Mexico
- **Serverless API**: Cost-effective Lambda + API Gateway deployment
- **Modern Frontend**: Responsive chat interface in Spanish

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Control Plane (Local)                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐               │
│  │   AWS CLI    │  │   Scripts    │  │    Config    │               │
│  └──────────────┘  └──────────────┘  └──────────────┘               │
└─────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│              Execution Plane (AWS mx-central-1 - Mexico)             │
│                     100% DATA RESIDENCY IN MEXICO                    │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                     S3 Storage (Mexico)                       │   │
│  │  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐ │   │
│  │  │  raw-data  │ │ processed  │ │ embeddings │ │   models   │ │   │
│  │  └────────────┘ └────────────┘ └────────────┘ └────────────┘ │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  ┌────────────────┐    ┌────────────────┐    ┌────────────────┐     │
│  │  WordPress/    │───▶│  Lambda Query  │───▶│   Ominis-2.0   │     │
│  │  Tainacan      │    │   Function     │    │   (EC2 Mexico) │     │
│  └────────────────┘    └────────────────┘    └────────────────┘     │
│                                │                                     │
│                                ▼                                     │
│                        ┌────────────────┐                           │
│                        │  API Gateway   │                           │
│                        │  /query        │                           │
│                        └────────────────┘                           │
└─────────────────────────────────────────────────────────────────────┘
```

For detailed architecture documentation, see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Technology Stack

### Backend
| Component | Technology | Purpose |
|-----------|------------|---------|
| Language | Python 3.11+ | Core application logic |
| Vector Store | FAISS | Similarity search |
| Embeddings | Sentence-Transformers (local) | Text vectorization |
| LLM | Ominis-2.0 via Ollama (Mexico) | Response generation |
| Compute | AWS Lambda | Serverless query processing |
| API | AWS API Gateway | RESTful endpoint |
| Storage | AWS S3 (mx-central-1) | Data persistence |

### Data Pipeline
| Component | Technology | Purpose |
|-----------|------------|---------|
| Ingestion | Custom Python clients | WordPress/Tainacan API |
| Chunking | LangChain | Document segmentation |
| Indexing | FAISS | Vector index creation |

### Frontend
| Component | Technology | Purpose |
|-----------|------------|---------|
| UI | HTML5/CSS3/JavaScript | Chat interface |
| Styling | CSS Gradients | Modern appearance |
| Storage | localStorage | API endpoint persistence |

### Infrastructure
| Component | Technology | Purpose |
|-----------|------------|---------|
| IaC | Bash scripts | AWS resource provisioning |
| LLM Server | Ominis-2.0 on Ollama | Self-hosted inference |
| IAM | AWS IAM | Access control |
| Logging | CloudWatch | Monitoring |

## Quick Start

### Prerequisites

- AWS CLI configured with appropriate credentials
- Python 3.11+
- pip

### 1. Set Up Infrastructure

```bash
# Run all infrastructure setup (S3, IAM)
./infrastructure/setup-all.sh
```

### 2. Create Virtual Environment

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Configure Data Source

Edit `config/settings.sh`:

```bash
export WORDPRESS_API_URL="https://your-wordpress-site.com"
export WORDPRESS_API_KEY="your-api-key"  # If required
export OLLAMA_URL="http://your-ollama-ec2:11434"
```

### 4. Ingest Content

```bash
# Ingest from WordPress
python scripts/ingestion/ingest_wordpress.py \
    --url https://your-site.com \
    --bucket ominis-health-raw-data-mx

# Or from Tainacan
python scripts/ingestion/ingest_tainacan.py \
    --url https://your-site.com \
    --collection-id 97
```

### 5. Build RAG Index

```bash
python scripts/rag/build_index.py
```

### 6. Deploy API

```bash
# Deploy Lambda function
./infrastructure/07-deploy-lambda.sh

# Deploy API Gateway
./infrastructure/08-deploy-api-gateway.sh
```

### 7. Test

```bash
curl -X POST 'YOUR_API_ENDPOINT/query' \
     -H 'Content-Type: application/json' \
     -d '{"question": "¿Qué es la diabetes?"}'
```

## Project Structure

```
ia.ominis.org/
├── config/
│   └── settings.sh              # Environment configuration
├── docs/
│   ├── ARCHITECTURE.md          # Detailed architecture docs
│   ├── DATA_PRIVACY.md          # Data handling & privacy policy
│   └── DEVELOPMENT.md           # Development guide
├── frontend/
│   └── index.html               # Chat interface
├── infrastructure/
│   ├── iam-policies/            # IAM policy documents
│   ├── 01-setup-s3.sh           # Create S3 buckets
│   ├── 02-setup-iam.sh          # Create IAM roles
│   ├── 03-verify-setup.sh       # Verify infrastructure
│   ├── 07-deploy-lambda.sh      # Deploy Lambda function
│   ├── 08-deploy-api-gateway.sh # Deploy API Gateway
│   └── setup-all.sh             # Run all setup
├── lambda/
│   └── query/
│       ├── handler.py           # Lambda handler
│       └── requirements.txt     # Lambda dependencies
├── scripts/
│   ├── ingestion/
│   │   ├── wordpress_client.py  # WordPress API client
│   │   ├── tainacan_client.py   # Tainacan API client
│   │   ├── ingest_wordpress.py  # WordPress ingestion
│   │   └── ingest_tainacan.py   # Tainacan ingestion
│   └── rag/
│       ├── chunker.py           # Document chunking
│       ├── embedder.py          # Embedding generation
│       ├── vector_store.py      # FAISS vector store
│       ├── build_index.py       # Index building pipeline
│       └── query_engine.py      # RAG query engine
├── requirements.txt             # Python dependencies
├── LICENSE                      # Apache 2.0 License
├── NOTICE                       # Attribution notices
└── README.md                    # This file
```

## Data Privacy & Residency

### 100% Mexico Data Residency

**All data storage and processing occurs within Mexico (AWS mx-central-1).**

| Data Type | Storage Location | Transferred Outside Mexico |
|-----------|------------------|---------------------------|
| Raw content | S3 mx-central-1 | **No** |
| Processed chunks | S3 mx-central-1 | **No** |
| Vector embeddings | S3 mx-central-1 | **No** |
| LLM inference | EC2 mx-central-1 | **No** |
| User queries | Not stored | **No** |

### No External AI API Calls

| Component | Location | External Calls |
|-----------|----------|----------------|
| Embeddings | Local (sentence-transformers) | **None** |
| LLM | Ominis-2.0 on EC2 (Mexico) | **None** |
| Vector Search | Lambda (Mexico) | **None** |

### User Data Handling

- **User queries are NOT stored** - processed transiently only
- **No user accounts** - anonymous usage
- **No tracking** - no cookies or identifiers
- **No external analytics** - all logs stay in Mexico

For complete data privacy documentation, see [docs/DATA_PRIVACY.md](docs/DATA_PRIVACY.md).

## API Reference

### POST /query

Query the health knowledge base.

**Request:**
```json
{
  "question": "¿Cuáles son los síntomas de la diabetes?",
  "num_sources": 5
}
```

**Response:**
```json
{
  "answer": "Los síntomas principales de la diabetes incluyen...",
  "sources": [
    {
      "title": "Diabetes: Guía Completa",
      "url": "https://...",
      "score": 0.85
    }
  ],
  "query": "¿Cuáles son los síntomas de la diabetes?"
}
```

**Parameters:**
- `question` (required): Health question in Spanish
- `num_sources` (optional): Number of sources to retrieve (default: 5, max: 10)

**Error Responses:**
- `400`: Missing question
- `500`: Internal server error

## Ominis-2.0 Model

The system is powered by **Ominis-2.0**, a medical-focused language model running 100% in Mexico.

### Model Specifications

| Specification | Value |
|---------------|-------|
| Parameters | **7 billion** |
| Context Window | **32,768 tokens** |
| Architecture | Transformer (decoder-only) |
| Attention | Grouped-Query Attention (GQA) |
| Training Data | ~3 million PubMed Central articles |
| Medical Domains | 10+ specialties |
| Languages | Spanish, English |

### Training Sources

| Source | Documents |
|--------|-----------|
| PubMed Central (Open Access) | ~3,000,000 |
| Medical Abstracts | ~30,000,000 |
| Clinical Guidelines | ~50,000 |

For complete model documentation, see [docs/MODEL.md](docs/MODEL.md).

## Documentation

| Document | Description |
|----------|-------------|
| [MODEL.md](docs/MODEL.md) | Ominis-2.0 model specifications and training data |
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | Detailed system architecture and component design |
| [DATA_PRIVACY.md](docs/DATA_PRIVACY.md) | Data handling, privacy policy, and compliance |
| [DEVELOPMENT.md](docs/DEVELOPMENT.md) | Development setup and contribution guidelines |

## License

Copyright 2026 Fundación Mexicana para la Salud A.C.

Licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE) for details.

### Third-Party Licenses

This project uses open-source libraries. See [NOTICE](NOTICE) for attributions.

| Library | License | Purpose |
|---------|---------|---------|
| FAISS | MIT | Vector similarity search |
| Sentence-Transformers | Apache 2.0 | Text embeddings |
| LangChain | MIT | Document processing |
| boto3 | Apache 2.0 | AWS SDK |
| Ollama | MIT | LLM inference |
| NumPy | BSD-3-Clause | Numerical computing |

## Cost Optimization

- **Lambda**: Pay only for execution time
- **EC2 (Ominis-2.0)**: Right-size instance for inference workload
- **S3**: Minimal storage costs
- **No external AI APIs**: No per-token costs

## Roadmap

1. Add clinical evaluation framework
2. Implement model versioning
3. Add multi-user support and scaling
4. Implement medical governance and auditing
5. Enhanced semantic search with hybrid retrieval

## Support

For questions about this implementation, contact the Ominis Health team.

- Website: [ai.ominis.org](https://ai.ominis.org)
- Organization: [Fundación Mexicana para la Salud A.C.](https://funsalud.org.mx/)

---

**Disclaimer**: This is an information system, not a substitute for professional medical advice. Always consult a healthcare professional for medical decisions.
