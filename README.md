# Ominis Health LLM

A Retrieval-Augmented Generation (RAG) health Q&A system powered by **ominis-2.0**, an LLM specialized in health.

Released by [Fundación Mexicana para la Salud A.C.](https://funsalud.org.mx/) through [ai.ominis.org](https://ai.ominis.org)

## Table of Contents

- [Overview](#overview)
- [Key Features](#key-features)
- [Architecture](#architecture)
- [Components](#components)
- [Model equivalents](#model-equivalents)
- [Infrastructure & LLM endpoints](#infrastructure--llm-endpoints)
- [ominis-2.0 Model](#ominis-20-model)
- [Technology Stack](#technology-stack)
- [Frontends and chat.ominis.org](#frontends-and-chatominisorg-librechat)
- [Pipeline and DataStores](#pipeline-and-datastores)
- [Live Avatar and Lambdas](#live-avatar-and-lambdas)
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
- **Multi-model selection**: Ominis 2.0, Ominis 2.0 Med, Modo Investigación (OpenScholar), optional Power/Open
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

### Model equivalents

| Chat option | Backend model_id | Underlying model | Notes |
|-------------|------------------|------------------|--------|
| **Ominis 2.0** | `ominis-2.0` | **Qwen 2.5 14B** (Ollama) | General health Q&A. Default `OLLAMA_MODEL=qwen2.5:14b`. |
| **Ominis 2.0 Med** | `ominis-2.0-med` | **Med42-v2** (M42 Health, via Ollama) | Clinical/medical focus. `OLLAMA_MED_MODEL=med42` (or med42-v2-8b). |
| **Ominis 2.0 Research** (Modo investigación 8K) | `ominis-2.0-research` | **OpenScholar** (Llama-3.1_OpenScholar-8B, vLLM) | Academic synthesis, 8K context. |
| **Ominis 2.0 Research 128K** | `ominis-2.0-research-128k` | **OpenScholar 128K** (vLLM, long context) | Deep research, long reports. |
| Ominis 2.0 Clinic | `ominis-2.0-clinic` | **BioMistral 7B** (Ollama) | Legacy medical; often same server as Ominis 2.0. |
| Ominis 2.0 Open | `ominis-2.0-open` | e.g. **Qwen 3** / **Llama 3.3** (Ollama) | Optional; only if `OLLAMA_OPEN_MODEL` is set. |
| Ominis 2.0 Power | (admin-only) | **gpt-oss** (vLLM, 20B) | Optional; when `POWER_API_URL` is set. |

See [docs/LLM_ROUTING.md](docs/LLM_ROUTING.md) for routing and env vars.

### Infrastructure & LLM endpoints

The **Haystack backend** (api.ominis.org) calls LLM services over HTTP. Infrastructure can be **EC2** (fixed instances) or **Vast.ai** (on-demand GPUs).

| Purpose | Env / config | Typical host | Protocol |
|--------|----------------|--------------|----------|
| **Ominis 2.0** (Qwen) | `OLLAMA_URL`, `OLLAMA_MODEL` | EC2 g4dn.xlarge (T4) or Vast | Ollama `:11434` |
| **Ominis 2.0 Med** (Med42) | `OLLAMA_MED_URL`, `OLLAMA_MED_MODEL` | Same as above or **Vast.ai** | Ollama |
| **Vision** (images) | `OLLAMA_URL`, vision model | Same Ollama server | Ollama |
| **Modo Investigación 8K** | `OPENSCHOLAR_API_URL` | EC2 g5.2xlarge (A10G) | vLLM OpenAI-compatible `:8000` |
| **Modo Investigación 128K** | `OPENSCHOLAR_128K_API_URL` | EC2 g5.2xlarge or **Vast.ai** | vLLM OpenAI-compatible |
| **Ominis 2.0 Power** (optional) | `POWER_API_URL` | EC2 or **Vast.ai** vLLM | OpenAI-compatible |
| Clinical translator (research) | `MED42_API_URL` | Optional A100 / Vast | OpenAI-compatible |

- **Data & API**: Backend and RAG (PostgreSQL, S3) in **AWS mx-central-1** (Mexico). GPU inference often in **us-east-1** or **Vast.ai**.
- **Config files**: `config/ollama_gpu_server.txt`, `config/ollama_med_server.txt`, `config/openscholar_server.txt`, `config/openscholar_128k_server.txt`. See [docs/INFRASTRUCTURE.md](docs/INFRASTRUCTURE.md) and [docs/VAST_AI_POWER.md](docs/VAST_AI_POWER.md) for Vast.ai setup.

## Frontends and chat.ominis.org (LibreChat)

The project has **two chat frontends**, both using the **same backend** (api.ominis.org):

| Frontend | URL | Stack | Purpose |
|----------|-----|--------|---------|
| **Next.js** | ia.ominis.org / ai.ominis.org | `frontend/` (Next.js 16, React 19) | Main chat UI: RAG, PubMed, OpenScholar, model selector, dashboard. |
| **LibreChat** | chat.ominis.org | `frontend-librechat/` (submodule) | Alternative chat UI (LibreChat), same models and RAG; OIDC so users share the same account as ia.ominis.org. |

**Interactions:**

- **Auth:** Both can use the same identity. LibreChat is configured with OIDC against api.ominis.org, so login is unified (no separate LibreChat registration).
- **Completions:** Both send requests to **api.ominis.org** (e.g. `POST /v1/chat/completions`). Same LLMs, same RAG, same API keys.
- **Conversation history:** Next.js frontend relies on the backend/session; LibreChat stores **conversation history** (chats, messages) in **MongoDB** on its own EC2 (chat server). The “brain” and user identity stay on api.ominis.org.

**LibreChat layout:** `frontend-librechat/client/` (React/Vite UI), `frontend-librechat/api/` (Node API used by the Docker image; we proxy completions to api.ominis.org). Build and overrides: `infrastructure/librechat-ominis-build/` (CSS, logo, footer). See [docs/CHAT_OMINIS.md](docs/CHAT_OMINIS.md) and [docs/FRONTEND_LIBRECHAT.md](docs/FRONTEND_LIBRECHAT.md).

## Pipeline and DataStores

**Pipeline** (`pipeline/`): Ingests health content, chunks, embeds, and indexes it for retrieval.

- **Ingest:** PubMed, URL lists, ZIPs, crawl (`pipeline/ingest/`). Output: raw docs → normalized docs.
- **Chunk:** Semantic chunker (`pipeline/chunk/`).
- **Embed:** Sentence-transformers or external service (`pipeline/embed/`).
- **Index:** Writes to FAISS (S3), OpenSearch, and PostgreSQL (`pipeline/index/`). Can run as a **nightly job** on a worker (EC2 or CPU Vast) or be driven by **Lambdas** (see below).

**DataStores (two kinds):**

| Store | Purpose | Used by |
|--------|---------|--------|
| **Admin RAG (PostgreSQL + pgvector)** | Documents and chunks added via the backend admin (RAG sources, uploads, Tainacan). | Chat when the user turns **“Ominis / bases de datos”** on. Queried by the Haystack RAG pipeline in the backend. |
| **Health Datastore** | Built by the **nightly pipeline**: PubMed + Mexican health URLs → FAISS (S3) + OpenSearch + PostgreSQL. | All models using `/v1/rag/query-stream` when `HEALTH_DATASTORE_ENABLED=true`; retrieval runs in parallel with admin RAG, web, PubMed. |

So: **admin RAG** = curated sources via UI; **health datastore** = bulk health corpus from the pipeline. See [docs/HEALTH_DATASTORE_NIGHTLY.md](docs/HEALTH_DATASTORE_NIGHTLY.md) and [docs/RAG_AGREGAR_DOCUMENTOS.md](docs/RAG_AGREGAR_DOCUMENTOS.md).

## Live Avatar and Lambdas

**Live Avatar** (`liveavatar-demo/`): Real-time voice avatar using **HeyGen Live Avatar** + **Ominis 2.0 Med** (BioMistral).

- **Where:** `liveavatar-demo/` — Pipecat agent that connects HeyGen to the backend proxy `POST /v1/liveavatar/chat/completions` (streaming). Deployed to **Pipecat Cloud**; frontend `/live` (ia.ominis.org) creates a session and opens the avatar.
- **Modes:** FULL (HeyGen’s LLM) or **CUSTOM** (Pipecat + Ominis Med via api.ominis.org). Backend needs `PIPECAT_AGENT_NAME` + `PIPECAT_API_TOKEN` for CUSTOM, or `HEYGEN_LIVE_AVATAR_API_KEY` for FULL.
- **Deploy:** `./infrastructure/23a-deploy-liveavatar-production.sh` (after changes in `liveavatar-demo/`). See [docs/LIVEAVATAR.md](docs/LIVEAVATAR.md).

**Lambdas:**

| Location | Purpose |
|----------|---------|
| **`lambda/query/`** | **Query Lambda** (optional/legacy): RAG query using Ollama + S3 embeddings; can run in AWS (e.g. mx-central-1) for serverless inference. Handlers: `handler.py` (basic), `handler_authenticated.py` (API key auth), `handler_improved.py` (enhanced prompts). |
| **`lambda/pipeline/`** | **Pipeline Lambdas** for scalable ingest/embed: `ingest/` (trigger by source list, writes raw docs to S3), `embed_batch/` (batch embeddings for pipeline). Used when running the health pipeline on Lambda instead of a single worker. See [docs/PIPELINE_LAMBDA.md](docs/PIPELINE_LAMBDA.md). |

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
├── backend-haystack/            # FastAPI + Haystack (auth, API keys, RAG, LiveAvatar proxy)
│   ├── app/                     # API routes, RAG pipeline, health datastore retriever
│   └── config/                  # Backend configuration
├── frontend/                    # Next.js frontend (ia.ominis.org / ai.ominis.org)
│   ├── src/app/                 # Pages, API routes, /live (Live Avatar)
│   ├── src/components/          # React components
│   ├── src/hooks/               # Custom hooks (useAuth)
│   └── src/services/            # API services
├── frontend-librechat/          # LibreChat submodule (chat.ominis.org); same backend, MongoDB for history
│   ├── client/                  # React/Vite chat UI
│   └── api/                     # Node API (completions → api.ominis.org)
├── pipeline/                    # Nightly health pipeline: ingest → chunk → embed → index (FAISS, OpenSearch, PG)
│   ├── ingest/                  # PubMed, URL, ZIP, crawl connectors
│   ├── chunk/                  # Semantic chunker
│   ├── embed/                  # Embedder (sentence-transformers)
│   ├── index/                  # Indexer (FAISS, OpenSearch, PostgreSQL)
│   └── nightly_pipeline.py      # Full pipeline entrypoint
├── lambda/
│   ├── query/                  # Query Lambda (optional RAG via Ollama + S3)
│   │   ├── handler.py           # Basic handler
│   │   ├── handler_authenticated.py  # With API key auth
│   │   └── handler_improved.py  # Enhanced prompts
│   └── pipeline/               # Pipeline Lambdas (scalable ingest/embed)
│       ├── ingest/             # Ingest by source (writes S3)
│       └── embed_batch/        # Batch embedding Lambda
├── liveavatar-demo/            # Pipecat agent: HeyGen Live Avatar + Ominis 2.0 Med (BioMistral)
│   ├── main.py                 # Agent entry; calls api.ominis.org/v1/liveavatar/chat/completions
│   └── pcc-deploy.toml         # Pipecat Cloud deploy config
├── infrastructure/             # AWS/Vast deployment scripts, LibreChat build
│   ├── librechat-chat/         # Docker Compose, .env for chat.ominis.org
│   ├── librechat-ominis-build/ # CSS/logo overrides and from-source Dockerfile
│   ├── 20-sync-backend.sh      # Deploy backend-haystack
│   ├── 23a-deploy-liveavatar-production.sh  # Deploy Live Avatar to Pipecat Cloud
│   └── ...                     # Ollama, OpenScholar, RDS, pipeline worker, etc.
├── scripts/
│   ├── ingestion/              # Legacy/extra data ingestion (IMSS, ISSSTE, Mexican sources)
│   └── rag/                    # Legacy RAG scripts (query_engine, etc.)
├── docs/                       # Documentation
├── config/                     # Server IPs, env snippets (ollama_gpu_server.txt, etc.)
├── LICENSE                     # Apache 2.0
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

Backend API (Haystack): [api.ominis.org/docs](https://api.ominis.org/docs) when deployed, or run `backend-haystack` and open `http://localhost:8000/docs`.

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
| Backend API | Haystack FastAPI — see `/docs` when backend is running |

## License

Copyright 2026 Fundación Mexicana para la Salud A.C.

Licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE) for details.

## Support

- Website: [ai.ominis.org](https://ai.ominis.org)
- Email: ominis@funsalud.org.mx
- Organization: [Fundación Mexicana para la Salud A.C.](https://funsalud.org.mx/)

---

**Disclaimer**: This is an information system, not a substitute for professional medical advice. Always consult a healthcare professional for medical decisions.
