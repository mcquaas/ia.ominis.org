# Model and GPU changes (Feb 2026)

## Summary

- **Ominis 2.0** (uso general) → Qwen (`OLLAMA_MODEL`, e.g. `qwen2.5:14b`) on g4dn.
- **Ominis 2.0 Clinic** (conocimiento médico) → BioMistral (`OLLAMA_CLINIC_MODEL=biomistral`) on g4dn.
- **Ominis 2.0 Research** / **Ominis 2.0 Research 128K** → OpenScholar 8K/128K (unchanged).
- **Falcon** removed from chat options; server can be shut down.

One g4dn (config/ollama_gpu_server.txt) runs both Qwen and BioMistral. Dashboard has two switches (Ominis 2.0 and Ominis 2.0 Clinic) that can both control the same g4dn instance.

## After deploy: backend .env on server

Update the backend server `.env` so the new model and instance IDs are used:

1. **OLLAMA_URL** → g4dn Ollama (e.g. `http://3.213.91.241:11434` from config/ollama_gpu_server.txt).
2. **OLLAMA_MODEL** → `qwen2.5:14b` (or the exact name from `ollama list` on g4dn).
3. **OLLAMA_CLINIC_URL** → leave empty (same server as OLLAMA_URL).
4. **OLLAMA_CLINIC_MODEL** → `biomistral`.
5. **Instance IDs for dashboard**: run `./infrastructure/20e-update-backend-env-llm-instances.sh` to inject `OLLAMA_INSTANCE_ID` and `OLLAMA_CLINIC_INSTANCE_ID` (both set to the g4dn instance ID). No Falcon config needed.

Old keys (`OLLAMA_FAST_*`, `FALCON_OLLAMA_URL`) in `.env` are ignored by the backend; you can remove them when convenient.

## g4dn: ensure both models are present

On the g4dn instance:

```bash
ollama pull qwen2.5:14b
ollama pull biomistral   # or cniongolo/biomistral
ollama list
```

If the BioMistral model has a different name (e.g. `cniongolo/biomistral`), set `OLLAMA_CLINIC_MODEL` to that name in the backend .env.

## Docs

- **docs/LLM_ROUTING.md** — routing table and troubleshooting.
- **backend-haystack/models/README.md** — chat models and g4dn setup.
- **docs/INFRASTRUCTURE.md** — Falcon marked as retired; g4dn description updated.
