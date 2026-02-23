# Vast.ai: Why Some Instances Are Not Reachable from the Backend

## Summary

- **Med42** (50.217.254.161:41474): Reachable and working from the backend.
- **OpenScholar 128K** (207.180.148.74:45806): Reachable from the backend (HTTP 200). No change needed.
- **Ollama Qwen+VL** (118.163.199.123:18660): **Connection refused** from the backend.

## Root cause: Ollama binding

Ollama by default binds to **127.0.0.1** (localhost only). In a Vast container, that means only traffic originating inside the container is accepted. Connections from the backend (via the host’s port mapping) come from the Docker bridge (e.g. 172.17.0.1), so Ollama rejects them → **connection refused**.

Med42 and OpenScholar use servers that listen on **0.0.0.0** by default (or are configured to), so they accept connections from the host and work.

## Fix for Ollama (Qwen+VL)

1. **For new instances**  
   The create script was updated to pass `OLLAMA_HOST=0.0.0.0` so Ollama listens on all interfaces:
   - `infrastructure/24f-vast-ai-create-ollama-qwen-vl.sh` now uses:
     `ENV_OPTS="-p 11434:11434 -e OLLAMA_HOST=0.0.0.0 --gpus all"`

2. **For the current Ollama instance (31900763)**  
   The container was created without `OLLAMA_HOST`, so it keeps listening on 127.0.0.1. Options:
   - **Recommended:** Destroy this instance and create a new one with the updated script:
     ```bash
     # In Vast dashboard: destroy instance 31900763 (Ominis Qwen 3 / Qwen 2.5VL)
     ./infrastructure/24f-vast-ai-create-ollama-qwen-vl.sh
     ```
     Then set the new IP:port in `config/ollama_qwen_vast.txt`, pull models again, and run `./infrastructure/20c-vast-update-backend-env-ollama-qwen-vl.sh`.
   - **Alternative:** Use Vast’s “Instance Portal” (Cloudflare tunnel) for that instance if you need a URL reachable from the backend without recreating.

## Verifying from the backend

From a machine that can SSH to the backend (78.12.33.205):

```bash
# OpenScholar 128K (should return 200 and model list)
curl -s -o /dev/null -w "%{http_code}" http://207.180.148.74:45806/v1/models

# Ollama (after fix: 200 and JSON; before fix: connection refused)
curl -s -o /dev/null -w "%{http_code}" http://<OLLAMA_IP>:<PORT>/api/tags
```

## Why OpenScholar works and Ollama didn’t

- **OpenScholar** (vLLM): Listens on `0.0.0.0` by default (`--host 0.0.0.0` in our args). Backend can connect.
- **Ollama**: Default is `127.0.0.1`. Without `OLLAMA_HOST=0.0.0.0`, only local connections are accepted → connection refused from the backend.
- **Med42**: Same host/configuration as your working setup; reachable from the backend.

No firewall or allowlist was found in the Vast CLI; the issue was the Ollama process binding, not Vast networking.
