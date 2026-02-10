# LLM Models for Ominis Health

Ollama model names and routing are configured in `app/config.py`, not by Modelfiles in this directory.

## Chat models (user selects in UI)

| UI option | model_id | Ollama model name (env) | Typical server |
|-----------|----------|-------------------------|----------------|
| **Ominis 2.0** (uso general) | ominis-2.0 | OLLAMA_MODEL (default `qwen2.5:14b`) | g4dn |
| **Ominis 2.0 Clinic** (conocimiento médico) | ominis-2.0-clinic | OLLAMA_CLINIC_MODEL (default `biomistral`) | g4dn (same) |

Research options (Ominis 2.0 Research, Ominis 2.0 Research 128K) use OpenScholar vLLM, not Ollama.

## g4dn setup (one server for both chat models)

On the g4dn instance (see `config/ollama_gpu_server.txt`):

```bash
# Qwen for general use
ollama pull qwen2.5:14b

# BioMistral for medical
ollama pull biomistral   # or cniongolo/biomistral

ollama list   # should show both
```

Backend .env: `OLLAMA_URL=http://<g4dn-ip>:11434`, `OLLAMA_MODEL=qwen2.5:14b`, `OLLAMA_CLINIC_MODEL=biomistral`. Leave `OLLAMA_CLINIC_URL` empty to use the same server.

## Falcon (deprecated)

Falcon-40B is no longer in the chat registry. The Modelfile in this directory is kept for reference only. The Falcon GPU server can be shut down.
