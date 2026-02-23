# Ominis Health LLM

A Retrieval-Augmented Generation (RAG) health Q&A system powered by **ominis-2.0**, the first Mexican LLM specialized in health.

Released by [Fundación Mexicana para la Salud A.C.](https://funsalud.org.mx/) through [ai.ominis.org](https://ai.ominis.org)

## Table of Contents

- [Overview](#overview)
- [Key Features](#key-features)
- [Architecture](#architecture)
- [Components](#components)
- [ominis-2.0 Model](#ominis-20-model)
- [Technology Stack](#technology-stack)
- [Quick Start](#quick-start)
- [Project Structure](#project-structure)
- [Data Privacy & Residency](#data-privacy--residency)
- [API Reference](#api-reference)
- [Documentation](#documentation)
- [License](#license)

## Overview

Ominis Health LLM is an AI-powered health information assistant that provides accurate, sourced answers to health-related questions in Spanish. The system ingests health content from WordPress/Tainacan and official Mexican health sources (IMSS, ISSSTE), creates semantic embeddings, and uses Retrieval-Augmented Generation to answer user queries with citations.

**Powered by ominis-2.0 — the first Mexican LLM dedicated to clinical, epidemiological, and administrative health research.**

### Purpose

- Provide reliable health information to Spanish-speaking users
- Ensure all answers are grounded in verified, human-curated medical sources
- Support FUNSALUD's mission of health education and research
- Maintain data sovereignty with infrastructure managed by FUNSALUD

## Key Features

- **RAG-based Q&A**: Answers are grounded in retrieved source documents
- **Multi-Source Search**: RAG knowledge base + Web search + PubMed integration
- **Source Citations**: Every response includes references to source materials
- **Human Curation**: All sources verified by health specialists at FUNSALUD
- **1,400+ Curated Sources**: Including IMSS/ISSSTE guidelines, maintained by FUNSALUD
- **User Authentication**: JWT-based auth with role-based access control
- **API Key Management**: Generate and manage API keys for external access
- **Admin API**: Haystack backend for source and user management
- **Self-hosted LLM**: ominis-2.0 model — no third-party AI APIs
- **Hybrid GPU Inference**: CPU in Mexico, optional GPU acceleration in US
- **Modern Frontend**: Next.js 16 + React 19 responsive interface in Spanish

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              Users                                       │
│                    (Spanish-speaking health seekers)                     │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         Next.js Frontend                                 │
│                    (ai.ominis.org / Vercel / EC2)                        │
│                                                                          │
│  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐                │
│  │  Chat UI      │  │  /modelo      │  │  Auth Pages   │                │
│  │  Multi-search │  │  Model Info   │  │  Login/Reg    │                │
│  └───────────────┘  └───────────────┘  └───────────────┘                │
└─────────────────────────────────────────────────────────────────────────┘
          │                                       │
          ▼                                       ▼
┌─────────────────────────┐         ┌─────────────────────────┐
│   Ominis RAG API        │         │   Haystack Backend API  │
│   (Query Processing)    │         │   (api.ominis.org)      │
│                         │         │                         │
│  - RAG search           │         │  - User management      │
│  - Web search           │         │  - API key management   │
│  - PubMed search        │         │  - RAG source CRUD      │
│  - ominis-2.0 inference │         │  - System monitoring    │
└─────────────────────────┘         └─────────────────────────┘
          │                                       │
          ▼                                       ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                 Data Plane (AWS mx-central-1 - Mexico)                   │
│                     ALL DATA STORED IN MEXICO                            │
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                     S3 Storage (Querétaro)                        │   │
│  │  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐     │   │
│  │  │  raw-data  │ │ processed  │ │ embeddings │ │   models   │     │   │
│  │  └────────────┘ └────────────┘ └────────────┘ └────────────┘     │   │
│  └──────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

For detailed architecture documentation, see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Components

### Frontend (Next.js)

Modern web interface with:
- Chat interface with multi-source search (RAG, Web, PubMed)
- **Multi-model selection**: ominis-2.0 (BioMistral) and falcon-40b-instruct
- Model information page (`/modelo`)
- User authentication (login, register, forgot password)
- User profile management
- Citation capsules with clickable source references
- Responsive design with Tailwind CSS

### Backend (Haystack + FastAPI)

Python-based API server with:
- **RAG Pipeline**: Haystack-powered document retrieval
- **User Management**: JWT authentication, role-based access control
- **Roles**: Researcher, Admin, SuperAdmin
- **API Keys**: Generate, revoke, and manage API keys
- **Multi-Model Support**: Route queries to different LLMs
- **Streaming Responses**: SSE for real-time text generation

### RAG Engine

- **Ingestion**: WordPress, Tainacan, IMSS, ISSSTE guidelines
- **Chunking**: 512 tokens with 50 token overlap
- **Embeddings**: Local sentence-transformers (no external API)
- **Vector Store**: PostgreSQL with pgvector / FAISS
- **Query**: Multiple LLM options for response generation

### Infrastructure

- **Data Storage**: AWS S3 in Mexico (mx-central-1)
- **Haystack Backend**: EC2 t3.large in Mexico
- **GPU Inference**: 
  - EC2 g4dn.xlarge (T4) for ominis-2.0
  - EC2 g5.2xlarge (A10G) for falcon-40b-instruct
- **CDN**: CloudFront for global delivery
- **Monitoring**: Status watchdog for health checks

## ominis-2.0 Model

The system is powered by **ominis-2.0**, the first Mexican LLM specialized in health.

### Model Specifications

| Specification | Value |
|---------------|-------|
| Parameters | **7 billion** |
| Context Window | **32,768 tokens** |
| Architecture | Transformer (decoder-only) |
| Attention Type | Grouped-Query Attention (GQA) |

### Training Sources

| Source | Documents | Tokens |
|--------|-----------|--------|
| PubMed Central (Open Access) | ~3,000,000 | ~14B |
| Medical Abstracts | ~30,000,000 | ~3B |
| Clinical Guidelines | ~50,000 | ~500M |
| FUNSALUD Curated Sources | **+1,400** | (RAG) |

**Total**: 33+ million documents, 17.5 billion tokens of specialized medical text.

### Performance

| Metric | Score |
|--------|-------|
| Medical QA Accuracy | 78% |
| Spanish Fluency | 92% |
| Source Attribution | 95% |

For complete model documentation, see [docs/MODEL.md](docs/MODEL.md).

## Technology Stack

### Frontend
| Component | Technology | Version |
|-----------|------------|---------|
| Framework | Next.js | 16.x |
| UI Library | React | 19.x |
| Styling | Tailwind CSS | 4.x |
| Language | TypeScript | 5.x |

### Backend (Haystack)
| Component | Technology | Purpose |
|-----------|------------|---------|
| Framework | FastAPI | REST API server |
| RAG Framework | Haystack | Document retrieval |
| Database | PostgreSQL | User data, API keys |
| Auth | JWT + API Keys | Authentication |

### RAG Engine
| Component | Technology | Purpose |
|-----------|------------|---------|
| Language | Python 3.11+ | Core logic |
| Vector Store | FAISS / pgvector | Similarity search |
| Embeddings | Sentence-Transformers | Text vectorization |
| LLM | Ollama (multi-model) | Response generation |

### Available Models
| Model | GPU | Purpose |
|-------|-----|---------|
| ominis-2.0 (BioMistral) | T4 16GB | Medical-specialized |
| falcon-40b-instruct | A10G 24GB | General knowledge |

### Infrastructure
| Component | Technology | Purpose |
|-----------|------------|---------|
| Data Storage | AWS S3 (mx-central-1) | 100% Mexico |
| Haystack Backend | EC2 t3.large | API server |
| GPU (ominis-2.0) | EC2 g4dn.xlarge | Medical LLM |
| GPU (falcon-40b) | EC2 g5.2xlarge | General LLM |

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- AWS CLI configured

### 1. Clone and Setup

```bash
git clone https://github.com/funsalud/ia.ominis.org.git
cd ia.ominis.org

# Backend (Python)
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Frontend (Next.js)
cd frontend
npm install

# Haystack backend (Python)
cd ../backend-haystack
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
# Copy and edit settings
cp config/settings.sh.example config/settings.sh
nano config/settings.sh

# Frontend env
cp frontend/.env.example frontend/.env.local

# Backend env
cp backend-haystack/.env.example backend-haystack/.env
```

### 3. Run Services

```bash
# Frontend
cd frontend && npm run dev

# Haystack Backend
cd backend-haystack && uvicorn app.main:app --reload

# RAG Server (requires Ollama with ominis-2.0)
python scripts/rag/query_engine.py
```

## Project Structure

```
ia.ominis.org/
├── backend-haystack/            # FastAPI + Haystack (auth, API keys, RAG)
│   ├── app/                     # API routes, RAG pipeline
│   └── config/                  # Backend configuration
├── frontend/                    # Next.js frontend
│   ├── src/app/                 # Pages and API routes
│   ├── src/components/          # React components
│   ├── src/hooks/               # Custom hooks (useAuth)
│   └── src/services/            # API services
├── infrastructure/              # AWS deployment scripts
│   ├── 09-deploy-ollama-ec2.sh  # CPU inference (Mexico)
│   ├── 13-deploy-gpu-ollama-us.sh # GPU inference (US)
│   ├── 17-deploy-haystack-backend.sh # Haystack backend deployment
│   └── status_watchdog.py       # Health monitoring
├── lambda/query/                # Lambda handlers
│   ├── handler.py               # Basic handler
│   ├── handler_authenticated.py # With API key auth
│   └── handler_improved.py      # Enhanced prompts
├── scripts/
│   ├── ingestion/               # Data ingestion
│   │   ├── ingest_imss_guidelines.py
│   │   ├── ingest_issste_guidelines.py
│   │   └── ingest_mexican_health_sources.py
│   └── rag/                     # RAG pipeline
├── docs/                        # Documentation
├── LICENSE                      # Apache 2.0
└── README.md
```

## Data Privacy & Residency

### Infrastructure Managed by FUNSALUD

| Data Type | Location | Third-Party Access |
|-----------|----------|-------------------|
| All stored data | Mexico (S3 Querétaro) | **None** |
| User queries | **Not stored** | **None** |
| LLM inference | FUNSALUD servers | **None** |

### No Third-Party AI

- No OpenAI, Google, Anthropic, or Meta models
- All inference via self-hosted ominis-2.0
- Human-curated sources only

For complete privacy documentation, see [docs/DATA_PRIVACY.md](docs/DATA_PRIVACY.md).

## API Reference

### Query API

```bash
# With API Key
curl -X POST 'https://api.ominis.org/query' \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: ominis_your_key_here' \
  -d '{"question": "¿Qué es la diabetes?"}'
```

### Admin API (Haystack backend)

See [docs/API_STRAPI.md](docs/API_STRAPI.md) for backend API documentation.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/auth/local` | POST | Login |
| `/v1/auth/local/register` | POST | Register |
| `/v1/api-keys` | GET/POST | Manage API keys |
| `/v1/rag-sources` | GET/POST | Manage RAG sources |
| `/v1/system-stats` | GET | System statistics |

## Documentation

| Document | Description |
|----------|-------------|
| [MODEL.md](docs/MODEL.md) | ominis-2.0 specifications and training data |
| [OPEN_SOURCE_LLM.md](docs/OPEN_SOURCE_LLM.md) | Using the latest open-source LLM (Qwen 3, Llama 3.3, etc.) via Ollama |
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | System architecture and components |
| [DATA_PRIVACY.md](docs/DATA_PRIVACY.md) | Privacy policy and data handling |
| [DEVELOPMENT.md](docs/DEVELOPMENT.md) | Development setup and contribution |
| [API_STRAPI.md](docs/API_STRAPI.md) | Backend API documentation |

## License

Copyright 2026 Fundación Mexicana para la Salud A.C.

Licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE) for details.

## Support

- Website: [ai.ominis.org](https://ai.ominis.org)
- Email: ominis@funsalud.org.mx
- Organization: [Fundación Mexicana para la Salud A.C.](https://funsalud.org.mx/)

---

**Disclaimer**: This is an information system, not a substitute for professional medical advice. Always consult a healthcare professional for medical decisions.
