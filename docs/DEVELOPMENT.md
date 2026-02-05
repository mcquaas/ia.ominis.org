# Ominis Health LLM - Development Guide

This guide covers setting up a development environment, understanding the codebase, and contributing to the project.

Released by [Fundación Mexicana para la Salud A.C.](https://funsalud.org.mx/) through [ai.ominis.org](https://ai.ominis.org)

## Table of Contents

- [Prerequisites](#prerequisites)
- [Development Setup](#development-setup)
- [Project Structure](#project-structure)
- [Component Guide](#component-guide)
- [Running Locally](#running-locally)
- [Testing](#testing)
- [Deployment](#deployment)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)

## Prerequisites

### Required Software

| Software | Version | Purpose |
|----------|---------|---------|
| Python | 3.11+ | Core runtime |
| AWS CLI | 2.x | AWS interactions |
| pip | Latest | Package management |
| Git | Latest | Version control |

### Optional (for LLM development)

| Software | Version | Purpose |
|----------|---------|---------|
| Ollama | Latest | Ominis-2.0 runtime |

### AWS Requirements

- AWS account with mx-central-1 access
- AWS CLI configured (`aws configure`)
- IAM permissions for S3, Lambda, API Gateway, EC2

### Recommended Tools

- VS Code or PyCharm for development
- Postman or curl for API testing
- AWS Console access for debugging

## Development Setup

### 1. Clone the Repository

```bash
git clone https://github.com/funsalud/ia.ominis.org.git
cd ia.ominis.org
```

### 2. Create Virtual Environment

```bash
# Create virtual environment
python -m venv venv

# Activate (Linux/macOS)
source venv/bin/activate

# Activate (Windows)
venv\Scripts\activate
```

### 3. Install Dependencies

```bash
# Install all dependencies
pip install -r requirements.txt

# Verify installation
python -c "import faiss; print('FAISS installed')"
```

### 4. Configure Environment

```bash
# Copy sample configuration
cp config/settings.sh.example config/settings.sh

# Edit with your settings
nano config/settings.sh
```

Required settings:

```bash
export AWS_REGION="mx-central-1"
export AWS_ACCOUNT_ID="your-account-id"
export WORDPRESS_API_URL="https://your-wordpress-site.com"
export OLLAMA_URL="http://your-ollama-server:11434"
```

### 5. Setup AWS Infrastructure (First Time)

```bash
# Run all infrastructure setup
./infrastructure/setup-all.sh
```

### 6. Setup Ominis-2.0 (LLM inference)

On your EC2 instance in mx-central-1:

```bash
# Install Ollama runtime
curl -fsSL https://ollama.com/install.sh | sh

# Create Ominis-2.0 model
cat << 'EOF' > /tmp/Modelfile
FROM cniongolo/biomistral
PARAMETER temperature 0.3
SYSTEM "Eres un asistente médico de Ominis Health (FUNSALUD). Responde en español."
EOF
ollama create ominis-2.0 -f /tmp/Modelfile

# Start server (runs on port 11434)
ollama serve
```

## Project Structure

```
ia.ominis.org/
├── config/                     # Configuration files
│   ├── settings.sh             # Environment variables
│   └── api_endpoint.txt        # Deployed API endpoint
│
├── docs/                       # Documentation
│   ├── ARCHITECTURE.md         # System architecture
│   ├── DATA_PRIVACY.md         # Privacy policy
│   └── DEVELOPMENT.md          # This file
│
├── frontend/                   # Web interface
│   └── index.html              # Chat interface
│
├── infrastructure/             # AWS infrastructure scripts
│   ├── iam-policies/           # IAM policy JSON files
│   ├── 01-setup-s3.sh          # S3 bucket creation
│   ├── 02-setup-iam.sh         # IAM role creation
│   ├── 03-verify-setup.sh      # Verify infrastructure
│   ├── 07-deploy-lambda.sh     # Lambda deployment
│   ├── 08-deploy-api-gateway.sh # API Gateway deployment
│   └── setup-all.sh            # Master setup script
│
├── lambda/                     # Lambda function code
│   └── query/
│       ├── handler.py          # Lambda entry point
│       └── requirements.txt    # Lambda-specific deps
│
├── scripts/                    # Python scripts
│   ├── ingestion/              # Data ingestion
│   │   ├── __init__.py
│   │   ├── wordpress_client.py # WordPress API client
│   │   ├── tainacan_client.py  # Tainacan API client
│   │   ├── ingest_wordpress.py # WordPress pipeline
│   │   └── ingest_tainacan.py  # Tainacan pipeline
│   │
│   ├── rag/                    # RAG components
│   │   ├── __init__.py
│   │   ├── chunker.py          # Document chunking
│   │   ├── embedder.py         # Embedding generation
│   │   ├── vector_store.py     # FAISS operations
│   │   ├── build_index.py      # Index builder
│   │   └── query_engine.py     # Query processing
│   │
│   ├── test_full_rag.py        # Full pipeline test
│   └── test_query.py           # Query endpoint test
│
├── requirements.txt            # Python dependencies
├── LICENSE                     # Apache 2.0 License
├── NOTICE                      # Attribution notices
└── README.md                   # Project overview
```

## Component Guide

### Ingestion Components

#### `wordpress_client.py`
WordPress REST API client for fetching posts and pages.

```python
from scripts.ingestion.wordpress_client import WordPressClient

client = WordPressClient("https://example.com")
posts = client.get_all_posts(post_type='posts', max_posts=100)
```

**Key Methods:**
- `test_connection()`: Verify API access
- `get_all_posts(post_type, max_posts)`: Fetch posts
- `extract_content(post)`: Extract clean content

#### `tainacan_client.py`
Tainacan collection API client for WordPress sites with Tainacan.

```python
from scripts.ingestion.tainacan_client import TainacanClient

client = TainacanClient("https://example.com")
collections = client.get_collections()
items = client.get_all_items(collection_id=97)
```

**Key Methods:**
- `get_collections()`: List all collections
- `get_all_items(collection_id)`: Fetch collection items
- `extract_item_content(item)`: Structure item data

### RAG Components

#### `chunker.py`
Document segmentation for optimal retrieval.

```python
from scripts.rag.chunker import DocumentChunker

chunker = DocumentChunker(chunk_size=512, chunk_overlap=50)
chunks = chunker.chunk_document(document)
```

**Parameters:**
- `chunk_size`: Tokens per chunk (default: 512)
- `chunk_overlap`: Overlap between chunks (default: 50)

#### `embedder.py`
Text-to-vector embedding generation using local models.

```python
from scripts.rag.embedder import EmbeddingGenerator

# Local embeddings (no external API calls)
embedder = EmbeddingGenerator(model_name='sentence-transformers/all-MiniLM-L6-v2')
embeddings = embedder.embed_texts(["Sample text"])
```

**Model:**
- Default: `sentence-transformers/all-MiniLM-L6-v2` (384 dimensions)
- Runs locally - no external API calls

#### `vector_store.py`
FAISS-based similarity search.

```python
from scripts.rag.vector_store import FAISSVectorStore

store = FAISSVectorStore(embedding_dim=384)
store.add_chunks(chunks_with_embeddings)
results = store.search(query_embedding, k=5)
store.save_to_s3(bucket, prefix, region)
```

**Key Methods:**
- `add_chunks(chunks)`: Add documents to index
- `search(query_embedding, k)`: Find similar documents
- `save_to_s3()` / `load_from_s3()`: Persistence

#### Lambda Handler (`lambda/query/handler.py`)
Lightweight query handler using Ominis-2.0 for LLM inference.

**Key Features:**
- Keyword-based semantic search (no external embeddings at query time)
- Ominis-2.0 API integration for answer generation
- 100% Mexico data residency

## Running Locally

### Test Ingestion

```bash
# Test WordPress connection
python scripts/ingestion/wordpress_client.py https://ominis.org

# Test Tainacan connection
python scripts/ingestion/tainacan_client.py https://ominis.org
```

### Test RAG Pipeline

```bash
# Build index from local documents
python scripts/rag/build_index.py \
    --raw-bucket ominis-health-raw-data-mx \
    --embeddings-bucket ominis-health-embeddings-mx \
    --prefixes tainacan/collection_97

# Test query locally (requires Ominis-2.0 running)
python scripts/rag/query_engine.py "¿Qué es la diabetes?"
```

### Test Full Pipeline

```bash
# Run comprehensive test
python scripts/test_full_rag.py
```

### Run Frontend Locally

```bash
# Simple HTTP server
cd frontend
python -m http.server 8000

# Open http://localhost:8000 in browser
```

### Run Ominis-2.0 Locally (for development)

```bash
# Install Ollama runtime
curl -fsSL https://ollama.com/install.sh | sh

# Create Ominis-2.0 model
cat << 'EOF' > /tmp/Modelfile
FROM cniongolo/biomistral
PARAMETER temperature 0.3
SYSTEM "Eres un asistente médico de Ominis Health (FUNSALUD). Responde en español."
EOF
ollama create ominis-2.0 -f /tmp/Modelfile

# Start server
ollama serve

# Test
curl http://localhost:11434/api/generate -d '{
  "model": "ominis-2.0",
  "prompt": "¿Qué es la diabetes?",
  "stream": false
}'
```

## Testing

### Unit Tests

```bash
# Run all tests
python -m pytest tests/

# Run specific test file
python -m pytest tests/test_chunker.py -v

# Run with coverage
python -m pytest --cov=scripts tests/
```

### Integration Tests

```bash
# Test API endpoint
python scripts/test_query.py

# Full RAG pipeline test
python scripts/test_full_rag.py
```

### Manual API Testing

```bash
# Test deployed API
curl -X POST 'https://your-api-id.execute-api.mx-central-1.amazonaws.com/query' \
     -H 'Content-Type: application/json' \
     -d '{"question": "¿Qué es la diabetes?", "num_sources": 5}'
```

## Deployment

### Deploy Lambda Function

```bash
# Package and deploy
./infrastructure/07-deploy-lambda.sh
```

This script:
1. Creates deployment package with dependencies
2. Uploads to S3
3. Creates/updates Lambda function
4. Configures environment variables (including OLLAMA_URL)

### Deploy API Gateway

```bash
# Create/update API Gateway
./infrastructure/08-deploy-api-gateway.sh
```

### Update Index

After adding new content:

```bash
# Re-ingest content
python scripts/ingestion/ingest_tainacan.py \
    --url https://ominis.org \
    --collection-id 97

# Rebuild index
python scripts/rag/build_index.py
```

### Verify Deployment

```bash
# Check infrastructure
./infrastructure/03-verify-setup.sh

# Test API
python scripts/test_query.py
```

## Troubleshooting

### Common Issues

#### ImportError: No module named 'faiss'

```bash
# Install FAISS CPU version
pip install faiss-cpu
```

#### AWS Credentials Error

```bash
# Verify credentials
aws sts get-caller-identity

# Reconfigure if needed
aws configure
```

#### Ominis-2.0 Connection Error

```bash
# Check Ollama runtime is running
curl http://localhost:11434/api/tags

# Check model is available
ollama list

# Recreate model if missing
ollama create ominis-2.0 -f /tmp/Modelfile
```

#### Lambda Timeout

- Increase Lambda timeout (default 30s, max 15min)
- Check Ominis-2.0 EC2 instance is running
- Verify VPC connectivity between Lambda and EC2

#### Empty Search Results

- Verify index was built successfully
- Check if embeddings bucket contains files
- Ensure chunks.json is populated

### Debug Commands

```bash
# Check S3 buckets
aws s3 ls s3://ominis-health-embeddings-mx/vectors/

# Check Lambda logs
aws logs tail /aws/lambda/ominis-query --follow

# Test Ominis-2.0 directly
curl http://ollama-ec2:11434/api/generate -d '{
  "model": "ominis-2.0",
  "prompt": "Hello",
  "stream": false
}'
```

## Contributing

### Code Style

- Follow PEP 8 for Python code
- Use type hints where possible
- Document functions with docstrings
- Keep functions focused and testable

### Pull Request Process

1. Create feature branch from `main`
2. Make changes with clear commits
3. Update documentation if needed
4. Ensure tests pass
5. Submit PR with description

### Documentation Updates

When making changes:
- Update README.md for user-facing changes
- Update ARCHITECTURE.md for system changes
- Update DATA_PRIVACY.md for data handling changes
- Update this file for development process changes

### Commit Message Format

```
type(scope): description

[optional body]

[optional footer]
```

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`

Example:
```
feat(ingestion): add Tainacan pagination support

Added support for paginated fetching of large Tainacan collections.
Uses X-WP-Total and X-WP-TotalPages headers for pagination.
```

### License

This project is licensed under Apache 2.0. See [LICENSE](../LICENSE) for details.

When contributing, you agree that your contributions will be licensed under the same license.

---

For architecture details, see [ARCHITECTURE.md](ARCHITECTURE.md).
For data privacy information, see [DATA_PRIVACY.md](DATA_PRIVACY.md).
