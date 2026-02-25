# OMINIS Infrastructure Documentation

Complete inventory of servers, services, domains, and IPs for the ia.ominis.org project.

---

## Domains

| Domain | Purpose | Primary IP |
|--------|---------|------------|
| **ia.ominis.org** | Main frontend (chat UI) | 78.13.37.163 |
| **ai.ominis.org** | Alternate frontend URL | 78.13.37.163 |
| **chat.ominis.org** | Chat UI (Ominis-styled, Haystack backend) | *see Chat Server* |
| **api.ominis.org** | API gateway (Haystack + legacy RAG) | 78.12.33.205 |
| **ominis.org** | Main website / Tainacan content source | — |
| **roclab.ominis.org** | ROC Lab | — |

---

## Servers (EC2 Instances)

### Production Servers

| Server | Instance ID | IP | Region | Type | Purpose |
|--------|-------------|-----|--------|------|---------|
| **Frontend** | `i-0efb1b3c28d64cdb5` | 78.13.37.163 | — | — | Next.js chat UI |
| **Chat Server** | *from 25-deploy-chat-ec2.sh* | *Elastic IP in config/chat_server.txt* | mx-central-1 | t3.small | Chat UI (Ominis look, Haystack API) |
| **Haystack Backend** | `i-04464c8355e364211` | 78.12.33.205 | mx-central-1 | t3.large | FastAPI + Haystack RAG |
| **Old RAG API (Ollama)** | `i-02264316b8b094bad` | 78.13.254.66 | mx-central-1 | t3.medium | Legacy Python RAG, Ollama (stopped) |
| **GPU Ollama** | `i-067dd350739288262` | 3.213.91.241 | us-east-1 | — | Ominis-2.0, mistral, vision models |
| **OpenScholar** | `i-0bf5937dec0d1298f` | 44.217.135.115 | us-east-1 | g5.2xlarge | Academic LLM (vLLM) |
| **Falcon GPU** | `i-00f7b0692c3219b46` | 18.235.182.22 | us-east-1 | g5.2xlarge | Falcon-40B (Ollama) |
| **OpenScholar 128K** | `i-0c44f34ab8b001d5a` | 54.159.123.159 | us-east-1 | g5.2xlarge | Research LLM, contexto largo (vLLM) |
| **XMLA Proxy** | `i-02122ca56de796e2e` | 78.12.97.79 | — | — | SINBA XMLA proxy (port 5001) |

---

## GPU servers — sizes and model capacities

Los cuatro servidores con GPU que usamos para inferencia LLM:

| Nombre | Instance ID | Tipo | GPU | VRAM | IP | Uso en Ominis |
|--------|-------------|------|-----|------|-----|----------------|
| **ominis-ollama-gpu** | `i-067dd350739288262` | g4dn.xlarge | 1× NVIDIA T4 | 16 GB | 3.213.91.241 | Ollama: Ominis 2.0 (Qwen) y Ominis 2.0 Clinic (BioMistral). Un solo servidor para ambos modelos. |
| **ominis-falcon-gpu** | `i-00f7b0692c3219b46` | g5.2xlarge | 1× NVIDIA A10G | 24 GB | 18.235.182.22 | **Retirado** — Falcon no habla español; apagar y no usar en el chat. |
| **ominis-openscholar** | `i-0bf5937dec0d1298f` | g5.2xlarge | 1× NVIDIA A10G | 24 GB | 44.217.135.115 | vLLM: OpenSciLM/Llama-3.1_OpenScholar-8B. Modo investigación 8K (ominis-2.0-research). |
| **ominis-openscholar-128k** | `i-0c44f34ab8b001d5a` | g5.2xlarge | 1× NVIDIA A10G | 24 GB | 54.159.123.159 | vLLM: modelo contexto largo. Modo investigación 128K (ominis-2.0-research-128k). |

**Capacidad por tipo de instancia:**

- **g4dn.xlarge (T4 16 GB):** 7B en FP16/Q8; 7B–13B en Q4. Ideal para BioMistral, Mistral 7B, Llama 7B.
- **g5.2xlarge (A10G 24 GB):** 7B–13B en FP16; hasta ~40B en Q4 (p. ej. Falcon-40B). OpenScholar 8B y variantes de contexto largo.

**Config en repo:** `config/ollama_gpu_server.txt`, `config/falcon_gpu_server.txt`, `config/openscholar_server.txt`, `config/openscholar_128k_server.txt`.

**Ruteo y conexión a cada LLM:** ver [LLM_ROUTING.md](LLM_ROUTING.md) (qué URL y modelo usa cada `model_id`, por qué a veces "no responden").

---

## Services by Server

### Frontend (78.13.37.163)

| Service | Port | URL |
|---------|------|-----|
| Next.js | 3000 | https://ia.ominis.org |
| Nginx | 80, 443 | Reverse proxy |

### Chat Server (chat.ominis.org)

| Service | Port | URL |
|---------|------|-----|
| LibreChat (Ominis-styled) | 3080 | https://chat.ominis.org (via Nginx) |
| Nginx | 80, 443 | Reverse proxy |

Deploy: `./infrastructure/25-deploy-chat-ec2.sh` then `./infrastructure/26-sync-chat-librechat.sh`. Backend must list `https://chat.ominis.org` in `ALLOWED_ORIGINS`. See [CHAT_OMINIS.md](CHAT_OMINIS.md).

### Haystack Backend (78.12.33.205) — Main Agent Server

| Service | Port | URL |
|---------|------|-----|
| FastAPI | 8000 | https://api.ominis.org |
| PostgreSQL | 5432 | localhost only |
| Status Watchdog | — | https://api.ominis.org/status/ |
| Nginx | 80, 443 | Reverse proxy |

**RAG file upload (CSV, PDF, etc.):** Uploads go to `POST /v1/api/rag-sources/upload`. For files &gt; 1MB, Nginx must allow larger bodies: run `infrastructure/20g-backend-nginx-upload-size.sh` on the backend host (sets `client_max_body_size 50M`). CORS must include the frontend origin (e.g. `https://ia.ominis.org`); set `ALLOWED_ORIGINS` in backend `.env` and run `20f-update-backend-env-cors.sh` if needed.

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

### OpenScholar 128K (54.159.123.159)

| Service | Port | URL |
|---------|------|-----|
| vLLM OpenAI API | 8000 | http://54.159.123.159:8000 |
| Model | — | Long-context research (ominis-2.0-research-128k) |

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
| https://api.ominis.org/v1 | GET | Haystack backend API |

---

## Configuration Files

| File | Content |
|------|---------|
| `config/frontend_server.txt` | Frontend IP, domain |
| `config/haystack_backend.txt` | Haystack backend IP |
| `config/ollama_server.txt` | Old RAG API (Mexico) |
| `config/ollama_gpu_server.txt` | GPU Ollama (US) — BioMistral / ominis-2.0-fast (puede estar apagado) |
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

Credenciales: usuario **ubuntu**, clave privada **config/ominis-ollama-key.pem** (backend/frontend usan distintas keys; ver tabla). La key del backend Haystack es `ominis-ollama-key.pem`.

Bloque listo para pegar en `~/.ssh/config` (ajusta `IdentityFile` si tu key está en otra ruta):

```
# Haystack Backend (api.ominis.org)
Host ominis-haystack api.ominis.org
    HostName 78.12.33.205
    User ubuntu
    IdentityFile ~/Dev/ia.ominis.org/config/ominis-ollama-key.pem
    IdentitiesOnly yes

# Frontend (ia.ominis.org)
Host ominis-frontend
    HostName 78.13.37.163
    User ubuntu
    IdentityFile ~/Dev/ia.ominis.org/config/ominis-frontend-key.pem
    IdentitiesOnly yes

# GPU Ollama (Ominis 2.0, BioMistral)
Host ominis-gpu
    HostName 3.213.91.241
    User ubuntu
    IdentityFile ~/Dev/ia.ominis.org/config/ominis-ollama-gpu-key.pem
    IdentitiesOnly yes

# OpenScholar (research vLLM)
Host ominis-openscholar
    HostName 44.217.135.115
    User ubuntu
    IdentityFile ~/Dev/ia.ominis.org/config/<openscholar-key>.pem
    IdentitiesOnly yes
```

Después: `ssh ominis-haystack` o `ssh api.ominis.org`.

| Host | IP | User | Key (en repo) |
|------|-----|------|----------------|
| ominis-haystack, api.ominis.org | 78.12.33.205 | ubuntu | config/ominis-ollama-key.pem |
| ominis-api | 78.13.254.66 | ubuntu | (legacy, to decommission) |
| ominis-gpu | 3.213.91.241 | ubuntu | config/ominis-ollama-gpu-key.pem |
| ominis-frontend | 78.13.37.163 | ubuntu | config/ominis-frontend-key.pem |
| ominis-openscholar | 44.217.135.115 | ubuntu | (creada al desplegar 14-deploy-openscholar.sh) |

---

## Security (Restricted Access)

| Server | Port | Allowed Sources |
|--------|------|-----------------|
| OpenScholar | 8000 | Haystack (78.12.33.205) |
| GPU Ollama | 11434 | Haystack (78.12.33.205) |
| SSH | 22 | User IP (dynamic) |

---

*Last updated: 2026-02-08*
