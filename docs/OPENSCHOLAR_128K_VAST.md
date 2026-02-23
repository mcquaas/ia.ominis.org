# OpenScholar 128K on Vast.ai

Research mode (Modo Investigación) uses **OpenScholar 128K** when the backend has `OPENSCHOLAR_128K_API_URL` set. This doc describes running the model on **Vast.ai** (no EC2).

## 1. Create the instance

```bash
./infrastructure/24e-vast-ai-create-openscholar-128k.sh
```

- Requires `vastai` CLI (see `infrastructure/setup-vast-cli.sh` if needed).
- Uses image `vllm/vllm-openai:latest`, model `OpenSciLM/Llama-3.1_OpenScholar-8B`, `--max-model-len 32768`.
- Waits until the instance is running: `vastai show instances`.

## 2. Get IP and port

In Vast.ai dashboard: instance → **IP Port Info** → note the mapping for **8000/tcp** (e.g. `1.2.3.4:45678`).

## 3. Configure backend

Create `config/openscholar_128k_vast.txt` (see `config/openscholar_128k_vast.txt.example`):

```bash
OPENSCHOLAR_128K_API_URL=http://<IP>:<PORT>
OPENSCHOLAR_128K_INSTANCE_ID=
```

Then update the Haystack backend .env on the server:

```bash
./infrastructure/20a-vast-update-backend-env-openscholar-128k.sh
# Or pass URL: ./infrastructure/20a-vast-update-backend-env-openscholar-128k.sh http://1.2.3.4:45678
```

Restart the backend so it picks up the new env.

## 4. Frontend

- **Modo Investigación** is in the plus (+) menu.
- When enabled, the chat uses `/api/academic-query-stream` (backend `/v1/academic_query-stream`).
- If `OPENSCHOLAR_128K_API_URL` is set, the backend uses the 128K model; otherwise it falls back to the default chat model with a degradation message.

## Notes

- No EC2 instance ID: Vast has no start/stop from our dashboard; the instance runs until you destroy it in Vast.
- Backend lists model `ominis-2.0-research-128k` in `/v1/models` when the URL is set.
- Login is required for the academic/research endpoint.
