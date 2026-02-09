# OMINIS Infrastructure Documentation

Complete inventory of servers, services, domains, and IPs for the ia.ominis.org project.

---

## Domains

| Domain | Purpose | Primary IP |
|--------|---------|------------|
| **ia.ominis.org** | Main frontend (chat UI) | 78.13.37.163 |
| **ai.ominis.org** | Alternate frontend URL | 78.13.37.163 |
| **api.ominis.org** | API gateway (Haystack + legacy RAG) | 78.12.33.205 |
| **admin.ominis.org** | Strapi admin panel | — |
| **ominis.org** | Main website / Tainacan content source | — |
| **roclab.ominis.org** | ROC Lab | — |

---

## Servers (EC2 Instances)

### Production Servers

| Server | Instance ID | IP | Region | Type | Purpose |
|--------|-------------|-----|--------|------|---------|
| **Frontend** | `i-0efb1b3c28d64cdb5` | 78.13.37.163 | — | — | Next.js chat UI |
| **Haystack Backend** | `i-04464c8355e364211` | 78.12.33.205 | mx-central-1 | t3.large | FastAPI + Haystack RAG |
| **Old RAG API (Ollama)** | `i-02264316b8b094bad` | 78.13.254.66 | mx-central-1 | t3.medium | Legacy Python RAG, Ollama (stopped) |
| **GPU Ollama** | `i-067dd350739288262` | 3.213.91.241 | us-east-1 | — | Ominis-2.0, mistral, vision models |
| **OpenScholar** | `i-0bf5937dec0d1298f` | 44.217.135.115 | us-east-1 | g5.2xlarge | Academic LLM (vLLM) |
| **Falcon GPU** | `i-00f7b0692c3219b46` | 18.235.182.22 | us-east-1 | g5.2xlarge | Falcon-40B (Ollama) |
| **XMLA Proxy** | `i-02122ca56de796e2e` | 78.12.97.79 | — | — | SINBA XMLA proxy (port 5001) |

---

## Services by Server

### Frontend (78.13.37.163)

| Service | Port | URL |
|---------|------|-----|
| Next.js | 3000 | https://ia.ominis.org |
| Nginx | 80, 443 | Reverse proxy |

### Haystack Backend (78.12.33.205) — Main Agent Server

| Service | Port | URL |
|---------|------|-----|
| FastAPI | 8000 | https://api.ominis.org |
| PostgreSQL | 5432 | localhost only |
| Status Watchdog | — | https://api.ominis.org/status/ |
| Nginx | 80, 443 | Reverse proxy |

### Old RAG API (78.13.254.66) — DEPRECATED / To Decommission

| Status | Action |
|--------|--------|
| **Deprecated** | Watchdog moved to Haystack. No longer in query path. |
| **Decommission** | Run `infrastructure/22-decommission-legacy-rag.sh` after verifying status page on Haystack. |

### GPU Ollama (3.213.91.241)

| Service | Port | URL |
|---------|------|-----|
| Ollama | 11434 | http://3.213.91.241:11434 |
| Models | — | mistral:7b-instruct, llama3.2-vision:11b |

### OpenScholar (44.217.135.115)

| Service | Port | URL |
|---------|------|-----|
| vLLM OpenAI API | 8000 | http://44.217.135.115:8000 |
| Model | — | OpenSciLM/Llama-3.1_OpenScholar-8B |

### Falcon GPU (18.235.182.22)

| Service | Port | URL |
|---------|------|-----|
| Ollama | 11434 | http://18.235.182.22:11434 |
| Model | — | falcon-40b-instruct |

### XMLA Proxy (78.12.97.79)

| Service | Port | URL |
|---------|------|-----|
| ASP.NET XMLA Proxy | 5001 | http://78.12.97.79:5001 |

---

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| https://api.ominis.org/v1/query | POST | Haystack RAG query |
| https://api.ominis.org/v1/query-stream | POST | Streaming query |
| https://api.ominis.org/v1/health | GET | Health check |
| https://api.ominis.org/status | GET | Status page (served from Haystack) |
| https://api.ominis.org/v1 | GET | Strapi API (if deployed) |

---

## Configuration Files

| File | Content |
|------|---------|
| `config/frontend_server.txt` | Frontend IP, domain |
| `config/haystack_backend.txt` | Haystack backend IP |
| `config/ollama_server.txt` | Old RAG API (Mexico) |
| `config/ollama_gpu_server.txt` | GPU Ollama (US) |
| `config/openscholar_server.txt` | OpenScholar server |
| `config/falcon_gpu_server.txt` | Falcon GPU server |
| `config/xmla_proxy_server.txt` | XMLA proxy |
| `config/api_endpoint.txt` | Lambda API Gateway |

---

## Network Flow

```
User → [ia.ominis.org] Frontend (78.13.37.163)
         │
         ├─ /api/query       → api.ominis.org → Haystack (78.12.33.205)
         │
         ├─ /api/query-gpu   → api.ominis.org → Haystack (78.12.33.205)
         │
         └─ /api/query-stream → Haystack (78.12.33.205)
                                     │
                                     ├──→ GPU Ollama (3.213.91.241)
                                     ├──→ Falcon GPU (18.235.182.22)
                                     └──→ OpenScholar (44.217.135.115)
```

---

## DNS / Routing Notes

- **api.ominis.org** resolves to **78.12.33.205** (Haystack backend).
- Status page (`/status`) is served from Haystack.
- Legacy RAG server (78.13.254.66) is deprecated; schedule decommission.

---

## AWS Resources

### Lambda / API Gateway

- **API Gateway**: `https://juxgiigca3.execute-api.mx-central-1.amazonaws.com/prod`

### S3 (mx-central-1)

- ominis-health-raw-data-mx
- ominis-health-processed-data-mx
- ominis-health-embeddings-mx

---

## SSH Aliases (~/.ssh/config)

| Host | IP |
|------|-----|
| ominis-haystack, api.ominis.org | 78.12.33.205 |
| ominis-api | 78.13.254.66 (legacy, to decommission) |
| ominis-gpu | 3.213.91.241 |
| ominis-frontend | 78.13.37.163 |
| ominis-openscholar | 44.217.135.115 |

---

## Security (Restricted Access)

| Server | Port | Allowed Sources |
|--------|------|-----------------|
| OpenScholar | 8000 | Haystack (78.12.33.205) |
| GPU Ollama | 11434 | Haystack (78.12.33.205) |
| SSH | 22 | User IP (dynamic) |

---

*Last updated: 2026-02-08*
