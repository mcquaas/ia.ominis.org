# LLM Routing and Server Connections

How the backend routes each request to the correct LLM. User chooses one of four options in the chat UI.

## Model options (user-facing)

| Option | Backend model_id | Backend routing |
|--------|------------------|------------------|
| **Ominis 2.0** (uso general) | ominis-2.0 | Ollama at OLLAMA_URL, model OLLAMA_MODEL (e.g. qwen2.5:14b) |
| **Ominis 2.0 Clinic** (conocimiento médico) | ominis-2.0-clinic | Ollama at OLLAMA_CLINIC_URL or OLLAMA_URL, model OLLAMA_CLINIC_MODEL (biomistral) |
| **Ominis 2.0 Research** (investigación general) | ominis-2.0-research | OpenScholar 8K (vLLM) or fallback to chat default |
| **Ominis 2.0 Research 128K** (investigación profunda) | ominis-2.0-research-128k | OpenScholar 128K (vLLM) or fallback to chat default |

Falcon has been removed from options (server can be shut down).

## Chat (non-research)

- **Manual routing by model_id**: one `OllamaChatGenerator` per registry entry; we pick by `model_id`.
- **Registry** (`app/config.py`):
  - `ominis-2.0` → OLLAMA_URL, ollama_model=OLLAMA_MODEL (default `qwen2.5:14b`)
  - `ominis-2.0-clinic` → OLLAMA_CLINIC_URL or OLLAMA_URL, ollama_model=OLLAMA_CLINIC_MODEL (default `biomistral`)

Typically **one g4dn** runs Ollama with both Qwen and BioMistral; OLLAMA_URL and OLLAMA_CLINIC_URL point to the same host (or CLINIC_URL is empty). Dashboard has two switches (Ominis 2.0 and Ominis 2.0 Clinic) that can both control the same g4dn instance.

- **Vision**: always OLLAMA_URL + vision_model (e.g. minicpm-v).

## Research mode

- Not in the chat registry. Router uses `_get_research_generator_and_model_id(body.research_model)`:
  - OpenScholar 8K or 128K when those instances are running; else fallback to default chat model (Ollama).

## Why "no response" can happen

1. **Server stopped**: g4dn off → timeout or connection refused.
2. **Model name mismatch**: Server up but missing the requested model name (e.g. we send `biomistral`, server only has `qwen2.5:14b`). Set OLLAMA_MODEL / OLLAMA_CLINIC_MODEL to a name that `ollama list` shows on that host.
3. **Timeout**: ollama_timeout (default 90s).

## Verifying connections

- **Script `infrastructure/check-ollama-servers.py`**: queries Ollama URLs (from config or env) with `GET /api/tags` (same as `ollama list`). Run from repo root:
  - `python3 infrastructure/check-ollama-servers.py` — uses config/ollama_gpu_server.txt.
  - With env: `OLLAMA_URL=... OLLAMA_CLINIC_URL=... python3 infrastructure/check-ollama-servers.py`.
- **Dashboard → Servidores LLM**: "Estado real de cada servidor Ollama" shows reachable URLs and model names.
- **Logs**: each request logs `model_id`, `Ollama url=...`, `ollama_model=...`.

## Troubleshooting: Ominis 2.0 Clinic (BioMistral) no responde

1. **Model name**: OLLAMA_CLINIC_MODEL must match a name from `ollama list` on the server (e.g. `biomistral` or `cniongolo/biomistral`).
2. **Server**: If OLLAMA_CLINIC_URL is empty, clinic uses OLLAMA_URL. That server must have both OLLAMA_MODEL (Qwen) and OLLAMA_CLINIC_MODEL (BioMistral). Use the dashboard to start the g4dn if needed.
3. **Backend .env**: OLLAMA_INSTANCE_ID and OLLAMA_CLINIC_INSTANCE_ID (often the same g4dn) for dashboard start/stop. Run `infrastructure/20e-update-backend-env-llm-instances.sh` to inject them.
