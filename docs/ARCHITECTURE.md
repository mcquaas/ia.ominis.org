# Architecture Documentation

This document provides a comprehensive overview of the Ominis Health LLM system architecture.

## Table of Contents

- [High-Level Overview](#high-level-overview)
- [System Components](#system-components)
- [Frontend Architecture](#frontend-architecture)
- [Backend Architecture (Haystack)](#backend-architecture-haystack)
- [RAG Engine](#rag-engine)
- [Hybrid Inference](#hybrid-inference)
- [Data Flow](#data-flow)
- [AWS Resources](#aws-resources)
- [Security](#security)
- [Scalability](#scalability)

## High-Level Overview

The Ominis Health LLM is a multi-component system with:

- **Frontend**: Next.js 16 web application
- **Admin Backend**: Haystack (FastAPI) for user and content management
- **RAG Engine**: Python-based retrieval and generation
- **Inference**: Self-hosted ominis-2.0 (CPU/GPU)
- **Data Storage**: 100% in Mexico (AWS mx-central-1)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              Users                                       │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
        ┌───────────────────────────┴───────────────────────────┐
        ▼                           ▼
┌───────────────┐         ┌───────────────────────────────────────┐
│  ai.ominis.org│         │ api.ominis.org (Haystack backend)       │
│  (Frontend)   │         │  - Auth, API Keys, RAG sources          │
│  - Chat UI    │         │  - Query, inference, health             │
│  - /modelo    │         └───────────────────────────────────────┘
│  - Login/Reg  │
└───────────────┘
        │                           │
        └───────────────────────────┘
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     Data Layer (AWS mx-central-1)                        │
│                                                                          │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐        │
│  │  S3 Raw    │  │ S3 Chunks  │  │ S3 Vectors │  │ PostgreSQL │        │
│  │  (sources) │  │            │  │  (FAISS)   │  │ (Haystack) │        │
│  └────────────┘  └────────────┘  └────────────┘  └────────────┘        │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     Inference Layer                                      │
│                                                                          │
│  ┌─────────────────────────────┐  ┌─────────────────────────────┐       │
│  │   CPU (mx-central-1)        │  │   GPU (us-east-1) Optional  │       │
│  │   c6i.4xlarge               │  │   g4dn.xlarge (T4)          │       │
│  │   ~5-10s response           │  │   ~2-3s response            │       │
│  └─────────────────────────────┘  └─────────────────────────────┘       │
└─────────────────────────────────────────────────────────────────────────┘
```

## System Components

### 1. Frontend (Next.js)

Modern web application built with Next.js 16 and React 19.

**Features:**
- Chat interface with multi-source search
- **Multi-model selection**: ominis-2.0 and falcon-40b-instruct
- Model information page (`/modelo`)
- User authentication (login, register, password reset)
- User profile management
- Citation capsules with clickable references
- Streaming responses with SSE
- Responsive design with Tailwind CSS 4

**Tech Stack:**
| Technology | Version | Purpose |
|------------|---------|---------|
| Next.js | 16.x | React framework |
| React | 19.x | UI library |
| Tailwind CSS | 4.x | Styling |
| TypeScript | 5.x | Type safety |

**Key Files:**
```
frontend/src/
├── app/
│   ├── page.tsx              # Main chat interface
│   ├── modelo/page.tsx       # Model specifications
│   ├── login/page.tsx        # Login page
│   ├── register/page.tsx     # Registration page
│   ├── profile/page.tsx      # User profile
│   ├── forgot-password/      # Password reset
│   └── api/
│       ├── query/route.ts    # CPU inference proxy
│       ├── query-gpu/route.ts # GPU inference proxy
│       └── query-stream/route.ts # Streaming proxy
├── components/
│   ├── MainLayout.tsx        # Chat UI component
│   ├── Header.tsx            # Site header
│   ├── Footer.tsx            # Site footer
│   └── auth/                 # Auth components
├── hooks/
│   └── useAuth.tsx           # Authentication hook
├── services/
│   └── auth.ts               # Auth API service
└── types/
    └── auth.ts               # TypeScript types
```

### 2. Backend (Haystack + FastAPI)

Python-based API server with Haystack for RAG.

**Features:**
- User authentication with JWT
- Role-based access control (Researcher, Admin, SuperAdmin)
- API key generation and management
- RAG pipeline with Haystack
- Multi-model routing (ominis-2.0, falcon-40b)
- Streaming responses via SSE
- Rate limiting per API key

**Roles:**
| Role | Capabilities |
|------|-------------|
| Researcher | Use API, manage own API keys |
| Admin | + View stats, manage RAG sources |
| SuperAdmin | + Manage users and roles |

**API Endpoints:**
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/auth/login` | POST | Login |
| `/v1/auth/register` | POST | Register |
| `/v1/auth/me` | GET | Get current user |
| `/v1/api-keys` | GET/POST | Manage API keys |
| `/v1/query` | POST | Non-streaming query |
| `/v1/query-stream` | POST | Streaming query (SSE) |
| `/v1/health` | GET | Health check |

**Key Files:**
```
backend/src/
├── api/
│   ├── api-key/              # API key management
│   ├── rag-source/           # RAG source management
│   ├── system-stat/          # System statistics
│   └── query-log/            # Query logging
├── middlewares/
│   ├── api-key-auth.js       # API key validation
│   └── rate-limit.js         # Rate limiting
├── policies/
│   ├── is-admin.js           # Admin check
│   ├── is-owner-or-admin.js  # Ownership check
│   └── is-super-admin.js     # SuperAdmin check
└── index.js                  # Bootstrap
```

### 3. RAG Engine (Python)

Retrieval-Augmented Generation pipeline.

**Components:**

#### Ingestion
- WordPress/Tainacan content
- IMSS clinical guidelines
- ISSSTE guidelines
- Mexican health sources

#### Processing
```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│   Raw Data   │───▶│   Chunker    │───▶│   Embedder   │───▶│   FAISS      │
│   (JSON)     │    │  (512 tok)   │    │  (local)     │    │   Index      │
└──────────────┘    └──────────────┘    └──────────────┘    └──────────────┘
```

**Key Files:**
```
scripts/
├── ingestion/
│   ├── ingest_tainacan.py
│   ├── ingest_wordpress.py
│   ├── ingest_imss_guidelines.py
│   ├── ingest_issste_guidelines.py
│   └── ingest_mexican_health_sources.py
├── rag/
│   ├── chunker.py            # 512 tokens, 50 overlap
│   ├── embedder.py           # sentence-transformers
│   ├── vector_store.py       # FAISS operations
│   ├── build_index.py        # Pipeline orchestration
│   └── query_engine.py       # Query processing
└── (RAG sync to backend)     # Sources managed via Haystack API
```

### 4. Lambda Functions

Serverless query handlers.

| Handler | Description |
|---------|-------------|
| `handler.py` | Basic query processing |
| `handler_authenticated.py` | With API key validation |
| `handler_improved.py` | Enhanced prompts and responses |

## Frontend Architecture

### Chat Interface

The main chat interface supports:

- **Multi-source search**: RAG, Web, PubMed
- **Toggle controls**: Enable/disable search sources
- **Image upload**: Attach images to queries
- **Message editing**: Edit and regenerate responses
- **Citation formatting**: Automatic source references
- **Streaming responses**: Real-time text generation

```tsx
// MainLayout.tsx - Key state
const [ragSearchEnabled, setRagSearchEnabled] = useState(true);
const [webSearchEnabled, setWebSearchEnabled] = useState(true);
const [pubmedSearchEnabled, setPubmedSearchEnabled] = useState(true);
const [uploadedImages, setUploadedImages] = useState([]);
```

### Authentication Flow

```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│   Login      │───▶│ Haystack API │───▶│   JWT Token  │
│   Form       │    │   Auth API   │    │   Storage    │
└──────────────┘    └──────────────┘    └──────────────┘
                           │
                           ▼
                    ┌──────────────┐
                    │   useAuth    │
                    │   Hook       │
                    └──────────────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
        ┌──────────┐ ┌──────────┐ ┌──────────┐
        │  user    │ │  isAdmin │ │  logout  │
        └──────────┘ └──────────┘ └──────────┘
```

### API Routes

Next.js API routes proxy requests to backend services:

| Route | Target |
|-------|--------|
| `/api/query` | Mexico RAG server (CPU) |
| `/api/query-gpu` | US GPU server (faster) |
| `/api/query-stream` | Streaming endpoint |

## Backend Architecture (Haystack)

### Content Types

```
┌──────────────────────────────────────────────────────────────────┐
│                       Backend API (auth, API keys, RAG sources)   │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐          │
│  │  api-key    │    │  rag-source │    │ system-stat │          │
│  │             │    │             │    │             │          │
│  │ - name      │    │ - title     │    │ - total*    │          │
│  │ - keyHash   │    │ - slug      │    │ - model*    │          │
│  │ - owner     │    │ - sourceType│    │ - avgTime*  │          │
│  │ - status    │    │ - status    │    │ - errors    │          │
│  │ - perms     │    │ - content   │    │             │          │
│  │ - rateLimit │    │ - chunks    │    │             │          │
│  └─────────────┘    └─────────────┘    └─────────────┘          │
│                                                                   │
│  ┌─────────────┐                                                 │
│  │ query-log   │                                                 │
│  │             │                                                 │
│  │ - query     │                                                 │
│  │ - response  │                                                 │
│  │ - timing    │                                                 │
│  │ - apiKey    │                                                 │
│  └─────────────┘                                                 │
└──────────────────────────────────────────────────────────────────┘
```

### Middleware

**API Key Authentication:**
```javascript
// middlewares/api-key-auth.js
module.exports = async (ctx, next) => {
  const apiKey = ctx.request.header['x-api-key'];
  if (!apiKey) return ctx.unauthorized('API key required');
  
  const valid = await validateApiKey(apiKey);
  if (!valid) return ctx.unauthorized('Invalid API key');
  
  await next();
};
```

**Rate Limiting:**
```javascript
// middlewares/rate-limit.js
module.exports = async (ctx, next) => {
  const key = ctx.state.apiKey;
  const limit = key.rateLimit || 100;
  // ... rate limit logic
};
```

## RAG Engine

### Ingestion Pipeline

```
┌─────────────────────────────────────────────────────────────────┐
│                     Ingestion Sources                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │
│  │  Tainacan    │  │  WordPress   │  │  IMSS        │           │
│  │  Collections │  │  Posts/Pages │  │  Guidelines  │           │
│  └──────────────┘  └──────────────┘  └──────────────┘           │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐                             │
│  │  ISSSTE      │  │  Manual      │                             │
│  │  Guidelines  │  │  Uploads     │                             │
│  └──────────────┘  └──────────────┘                             │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌──────────────────┐
                    │   S3 Raw Data    │
                    │   (mx-central-1) │
                    └──────────────────┘
```

### Processing Pipeline

```python
# build_index.py - Pipeline flow
documents = load_documents_from_s3(prefix)  # 1. Load
chunks = chunker.chunk_document(doc)        # 2. Chunk (512 tokens)
embeddings = embedder.embed_texts(texts)    # 3. Embed (local)
vector_store.add_chunks(chunks)             # 4. Index (FAISS)
vector_store.save_to_s3(bucket, prefix)     # 5. Persist
```

### Query Pipeline

```
User Query
    │
    ▼
┌──────────────────┐
│  Keyword Search  │  (fast pre-filter)
└──────────────────┘
    │
    ▼
┌──────────────────┐
│  Vector Search   │  (FAISS similarity)
└──────────────────┘
    │
    ▼
┌──────────────────┐
│  Context Format  │  (top-k chunks)
└──────────────────┘
    │
    ▼
┌──────────────────┐
│  ominis-2.0      │  (generate answer)
└──────────────────┘
    │
    ▼
┌──────────────────┐
│  Response +      │
│  Citations       │
└──────────────────┘
```

## Hybrid Inference

### Deployment Options

| Option | Location | Hardware | Response Time | Cost |
|--------|----------|----------|---------------|------|
| CPU | Mexico (mx-central-1) | c6i.4xlarge | 5-10s | $0.17/hr |
| GPU | US (us-east-1) | g4dn.xlarge (T4) | 2-3s | $0.52/hr |

### Data Flow (GPU)

When GPU inference is used:
1. Query arrives at frontend
2. Frontend routes to GPU API
3. GPU server fetches vectors from Mexico S3
4. Inference runs on ominis-2.0
5. Response returns to user

**Only query text travels to US. All data remains in Mexico.**

## Data Flow

### Complete Request Flow

```
┌──────────────────────────────────────────────────────────────────┐
│  1. User submits question via chat UI                            │
└──────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│  2. Frontend calls /api/query or /api/query-gpu                  │
└──────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│  3. API validates request (optional API key)                     │
└──────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│  4. RAG pipeline:                                                 │
│     a. Keyword search (stop word removal)                        │
│     b. Vector similarity (FAISS)                                 │
│     c. Top-k chunk retrieval                                     │
└──────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│  5. ominis-2.0 generates response with citations                 │
└──────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│  6. Response + sources returned to frontend                      │
└──────────────────────────────────────────────────────────────────┘
```

## AWS Resources

### Mexico Region (mx-central-1)

| Resource | Name | Purpose |
|----------|------|---------|
| S3 | ominis-health-raw-data-mx | Raw sources |
| S3 | ominis-health-processed-data-mx | Chunks |
| S3 | ominis-health-embeddings-mx | FAISS index |
| EC2 | ominis-ollama | CPU inference |
| EC2 | ominis-frontend | Next.js |
| EC2 | ominis-haystack-backend | Haystack backend |
| RDS / local | PostgreSQL | Backend database |

### US Region (us-east-1) - Optional

| Resource | Name | Purpose |
|----------|------|---------|
| EC2 | ominis-ollama-gpu | GPU inference |
| EIP | ominis-ollama-gpu-eip | Static IP |

## Security

### Authentication

- **Frontend**: JWT tokens stored in localStorage
- **API Keys**: Hashed with bcrypt, shown once on creation
- **Haystack backend**: JWT auth, users-permissions, API keys

### Authorization

- **Role-based**: Researcher < Admin < SuperAdmin
- **Resource-based**: Owner or admin access
- **API Keys**: Per-key permissions (query, queryGpu, sources)

### Data Protection

- **In Transit**: TLS 1.2+
- **At Rest**: S3 default encryption (AES-256)
- **Secrets**: AWS Secrets Manager / env vars

## Scalability

### Horizontal Scaling

| Component | Strategy |
|-----------|----------|
| Frontend | Vercel / EC2 Auto Scaling |
| Haystack backend | Containerize with load balancer |
| RAG API | Lambda concurrency / EC2 ASG |
| FAISS | Read replicas from S3 |

### Performance

| Optimization | Implementation |
|--------------|----------------|
| Caching | Lambda warm starts, FAISS in memory |
| CDN | CloudFront for static assets |
| GPU | Optional T4 for 10-30x speed |
| Streaming | SSE for real-time responses |

---

For development guide, see [DEVELOPMENT.md](DEVELOPMENT.md).
For API documentation, run the Haystack backend and open `/docs`.
