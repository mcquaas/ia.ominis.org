# Ominis Health LLM - Development Guide

This guide covers setting up a development environment and contributing to the project.

Released by [Fundación Mexicana para la Salud A.C.](https://funsalud.org.mx/) through [ai.ominis.org](https://ai.ominis.org)

## Table of Contents

- [Prerequisites](#prerequisites)
- [Development Setup](#development-setup)
- [Project Structure](#project-structure)
- [Frontend Development](#frontend-development)
- [Backend Development (Haystack)](#backend-development-haystack)
- [RAG Engine Development](#rag-engine-development)
- [Running Locally](#running-locally)
- [Testing](#testing)
- [Deployment](#deployment)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)

## Prerequisites

### Required Software

| Software | Version | Purpose |
|----------|---------|---------|
| Node.js | 18+ | Frontend |
| Python | 3.11+ | RAG engine |
| AWS CLI | 2.x | AWS operations |
| Git | Latest | Version control |

### Optional

| Software | Version | Purpose |
|----------|---------|---------|
| Ollama | Latest | Local LLM inference |
| PostgreSQL | 14+ | Backend database |

## Development Setup

### 1. Clone Repository

```bash
git clone https://github.com/funsalud/ia.ominis.org.git
cd ia.ominis.org
```

### 2. Setup RAG Engine (Python)

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/macOS
# venv\Scripts\activate   # Windows

# Install dependencies
pip install -r requirements.txt

# Verify
python -c "import faiss; print('FAISS installed')"
```

### 3. Setup Frontend (Next.js)

```bash
cd frontend
npm install

# Create environment file
cp .env.example .env.local
# Edit with your API URLs
```

### 4. Setup Backend (Haystack)

```bash
cd backend-haystack
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Create environment file
cp .env.example .env
# Edit with database URL and secrets
```

### 5. Setup Local LLM (Optional)

```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Create ominis-2.0 model
cat << 'EOF' > /tmp/Modelfile
FROM cniongolo/biomistral
PARAMETER temperature 0.3
SYSTEM "Eres un asistente médico de Ominis Health (FUNSALUD). Responde en español."
EOF
ollama create ominis-2.0 -f /tmp/Modelfile
```

## Project Structure

```
ia.ominis.org/
├── backend-haystack/            # FastAPI + Haystack (auth, RAG)
│   ├── app/                     # API, config
│   ├── src/
│   │   ├── api/                 # Content types
│   │   │   ├── api-key/         # API key management
│   │   │   ├── rag-source/      # RAG sources
│   │   │   ├── system-stat/     # System stats
│   │   │   └── query-log/       # Query logs
│   │   ├── middlewares/         # Custom middleware
│   │   └── policies/            # Authorization policies
│   └── scripts/                 # Seed scripts
│
├── frontend/                    # Next.js 16
│   ├── src/
│   │   ├── app/                 # App router pages
│   │   │   ├── page.tsx         # Chat interface
│   │   │   ├── modelo/          # Model info
│   │   │   ├── login/           # Login page
│   │   │   ├── register/        # Registration
│   │   │   ├── profile/         # User profile
│   │   │   └── api/             # API routes
│   │   ├── components/          # React components
│   │   │   ├── MainLayout.tsx   # Chat UI
│   │   │   ├── Header.tsx
│   │   │   ├── Footer.tsx
│   │   │   └── auth/            # Auth components
│   │   ├── hooks/               # Custom hooks
│   │   ├── services/            # API services
│   │   └── types/               # TypeScript types
│   └── public/                  # Static assets
│
├── infrastructure/              # Deployment scripts
│   ├── 09-deploy-ollama-ec2.sh  # CPU inference
│   ├── 13-deploy-gpu-ollama-us.sh # GPU inference
│   ├── 17-deploy-haystack-backend.sh # Haystack backend
│   └── status_watchdog.py       # Health monitor
│
├── lambda/query/                # Lambda handlers
│   ├── handler.py               # Basic
│   ├── handler_authenticated.py # With API key
│   ├── handler_improved.py      # Enhanced
│   └── auth.py                  # Auth utilities
│
├── scripts/
│   ├── ingestion/               # Data ingestion
│   │   ├── ingest_tainacan.py
│   │   ├── ingest_imss_guidelines.py
│   │   ├── ingest_issste_guidelines.py
│   │   └── ingest_mexican_health_sources.py
│   ├── rag/                     # RAG pipeline
│   │   ├── chunker.py
│   │   ├── embedder.py
│   │   ├── vector_store.py
│   │   ├── build_index.py
│   │   └── query_engine.py
│   └── (RAG sources via backend API)
│
├── docs/                        # Documentation
│   ├── ARCHITECTURE.md
│   ├── DATA_PRIVACY.md
│   ├── MODEL.md
│   ├── API_STRAPI.md
│   └── DEVELOPMENT.md
│
├── config/                      # Configuration
├── LICENSE
├── NOTICE
└── README.md
```

## Frontend Development

### Tech Stack

| Technology | Version | Purpose |
|------------|---------|---------|
| Next.js | 16.x | React framework |
| React | 19.x | UI library |
| Tailwind CSS | 4.x | Styling |
| TypeScript | 5.x | Type safety |

### Running Frontend

```bash
cd frontend

# Development (hot reload)
npm run dev

# Production build
npm run build
npm run start

# Lint
npm run lint
```

### Key Components

#### MainLayout.tsx (Chat Interface)

Features:
- Multi-source search (RAG, Web, PubMed toggles)
- Image upload support
- Message editing and regeneration
- Citation formatting
- Streaming responses

```tsx
// Key state
const [ragSearchEnabled, setRagSearchEnabled] = useState(true);
const [webSearchEnabled, setWebSearchEnabled] = useState(true);
const [pubmedSearchEnabled, setPubmedSearchEnabled] = useState(true);
```

#### Auth Components

| Component | Purpose |
|-----------|---------|
| `LoginForm.tsx` | Email/password login |
| `RegisterForm.tsx` | User registration |
| `ForgotPasswordForm.tsx` | Password reset request |
| `ResetPasswordForm.tsx` | New password form |

#### useAuth Hook

```tsx
const { user, login, logout, isAdmin, isSuperAdmin, loading } = useAuth();
```

### Environment Variables

```env
# frontend/.env.local
NEXT_PUBLIC_API_URL=https://api.ominis.org
NEXT_PUBLIC_OMINIS_API_URL=https://api.ominis.org
MEXICO_API_URL=http://mexico-server:8080/query
GPU_API_URL=http://gpu-server:8080/query
```

### Adding New Pages

```tsx
// frontend/src/app/new-page/page.tsx
import Header from "@/components/Header";
import Footer from "@/components/Footer";

export const metadata = {
  title: "New Page | OMINIS",
  description: "Description",
};

export default function NewPage() {
  return (
    <main>
      <Header />
      {/* Content */}
      <Footer />
    </main>
  );
}
```

## Backend Development (Haystack)

### Tech Stack

| Technology | Purpose |
|------------|---------|
| FastAPI | API server |
| Haystack | RAG pipeline |
| PostgreSQL | Production database |
| JWT | Authentication |

### Running the backend

```bash
cd backend-haystack
source venv/bin/activate

# Development (hot reload)
uvicorn app.main:app --reload

# Production
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Content Types

#### api-key
```json
{
  "name": "string",
  "keyHash": "string",
  "keyPrefix": "string",
  "status": "enum: active, revoked, expired",
  "permissions": "json",
  "rateLimit": "integer",
  "owner": "relation: user"
}
```

#### rag-source
```json
{
  "title": "string",
  "slug": "string",
  "sourceType": "enum: tainacan, wordpress, imss_guideline, ...",
  "status": "enum: pending, processing, indexed, failed",
  "content": "text",
  "chunksCount": "integer",
  "addedBy": "relation: user"
}
```

### Custom Middleware

```javascript
// src/middlewares/api-key-auth.js
module.exports = async (ctx, next) => {
  const apiKey = ctx.request.header['x-api-key'];
  // Validate and proceed
  await next();
};
```

### Custom Policies

```javascript
// src/policies/is-admin.js
module.exports = async (policyContext, config, { strapi }) => {
  const user = policyContext.state.user;
  return user?.role?.type === 'admin' || user?.role?.type === 'superadmin';
};
```

### Environment Variables

```env
# backend/.env
HOST=0.0.0.0
PORT=1337
APP_KEYS=generated-keys
ADMIN_JWT_SECRET=generated-secret
API_TOKEN_SALT=generated-salt
JWT_SECRET=generated-secret
DATABASE_CLIENT=sqlite
FRONTEND_URL=http://localhost:3000
```

## RAG Engine Development

### Ingestion

```bash
# Ingest Tainacan collection
python scripts/ingestion/ingest_tainacan.py \
    --url https://ominis.org \
    --collection-id 97

# Ingest IMSS guidelines
python scripts/ingestion/ingest_imss_guidelines.py

# Ingest Mexican health sources
python scripts/ingestion/ingest_mexican_health_sources.py
```

### Building Index

```bash
python scripts/rag/build_index.py \
    --raw-bucket ominis-health-raw-data-mx \
    --embeddings-bucket ominis-health-embeddings-mx \
    --prefixes tainacan/collection_97
```

### Testing Queries

```bash
# Direct query
python scripts/rag/query_engine.py "¿Qué es la diabetes?"

# Full pipeline test
python scripts/test_full_rag.py
```

### Component Usage

```python
# Chunker
from scripts.rag.chunker import DocumentChunker
chunker = DocumentChunker(chunk_size=512, chunk_overlap=50)
chunks = chunker.chunk_document(document)

# Embedder
from scripts.rag.embedder import EmbeddingGenerator
embedder = EmbeddingGenerator()
embeddings = embedder.embed_texts(["text"])

# Vector Store
from scripts.rag.vector_store import FAISSVectorStore
store = FAISSVectorStore(embedding_dim=384)
store.add_chunks(chunks_with_embeddings)
results = store.search(query_embedding, k=5)
```

## Running Locally

### Full Stack

```bash
# Terminal 1: Frontend
cd frontend && npm run dev

# Terminal 2: Backend
cd backend && npm run develop

# Terminal 3: Ollama
ollama serve

# Terminal 4: RAG Server (if needed)
python scripts/rag/query_engine.py
```

### Quick Test

```bash
# Test Ollama
curl http://localhost:11434/api/generate -d '{
  "model": "ominis-2.0",
  "prompt": "¿Qué es la diabetes?",
  "stream": false
}'

# Test backend
curl http://localhost:1337/v1/system-stats/health

# Test Frontend
open http://localhost:3000
```

## Testing

### Frontend

```bash
cd frontend
npm run lint
npx tsc --noEmit
```

### Backend

```bash
cd backend
npm run lint
```

### RAG Engine

```bash
python -m pytest tests/
python scripts/test_full_rag.py
python scripts/test_query.py
```

## Deployment

### Deploy CPU Inference (Mexico)

```bash
./infrastructure/09-deploy-ollama-ec2.sh
```

### Deploy GPU Inference (US)

```bash
./infrastructure/13-deploy-gpu-ollama-us.sh
```

**Note**: GPU costs ~$0.52/hour. Stop when not in use:
```bash
aws ec2 stop-instances --instance-ids i-xxx --region us-east-1
```

### Deploy Haystack backend

```bash
./infrastructure/17-deploy-haystack-backend.sh
```

### Deploy Frontend

```bash
# EC2
./infrastructure/11-deploy-frontend-ec2.sh
./infrastructure/12-sync-frontend.sh

# Or Vercel
cd frontend && npx vercel
```

## Troubleshooting

### Common Issues

#### Frontend build errors
```bash
rm -rf frontend/.next frontend/node_modules
cd frontend && npm install && npm run build
```

#### Backend connection errors
```bash
# Check backend
cd backend-haystack && uvicorn app.main:app --reload
```

#### FAISS import error
```bash
pip install faiss-cpu
```

#### Ollama not responding
```bash
curl http://localhost:11434/api/tags
ollama list
ollama create ominis-2.0 -f /tmp/Modelfile
```

### Debug Commands

```bash
# Check S3
aws s3 ls s3://ominis-health-embeddings-mx/vectors/

# Check backend health
curl http://localhost:8000/v1/system-stats/health

# Check GPU
ssh -i config/ominis-ollama-gpu-key.pem ubuntu@IP 'nvidia-smi'
```

## Contributing

### Code Style

- Python: PEP 8, type hints, docstrings
- TypeScript: ESLint, Prettier
- Commits: Conventional Commits

### Pull Request Process

1. Create feature branch from `main`
2. Make changes with clear commits
3. Update documentation
4. Submit PR with description

### Commit Format

```
type(scope): description

[optional body]
```

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`

Example:
```
feat(frontend): add PubMed search toggle
```

---

For API documentation, see [API_STRAPI.md](API_STRAPI.md).
For architecture details, see [ARCHITECTURE.md](ARCHITECTURE.md).
