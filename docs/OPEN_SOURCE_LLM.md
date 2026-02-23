# Using the Latest Open-Source LLM as a Model

There is no official "open-source GPT" (GPT is proprietary). The project already uses **Ollama** for chat; you can use the **latest open-source models** (Qwen 3, Qwen 3.5, Llama 3.3, DeepSeek R1, etc.) via Ollama with minimal changes.

## Option A: Replace the default general model (simplest)

Use a newer model for **Ominis 2.0** (general use) without adding UI options.

1. **On the g4dn** (Ollama server, see `config/ollama_gpu_server.txt`):

   ```bash
   # Examples (pick one; ~16GB VRAM fits 14B–32B or quantized 70B)
   ollama pull qwen3:14b        # Qwen 3 14B (Apache 2.0), similar size to current Qwen 2.5 14B
   # ollama pull qwen3.5:cloud  # Qwen 3.5 text (256K context) — when available locally
   # ollama pull qwen3:32b      # Better quality, needs ~20GB VRAM
   # ollama pull llama3.3:70b-instruct-q4_0   # Quantized 70B if you have 24GB+ VRAM
   ollama list
   ```

2. **Backend `.env`** (same server, new model name):

   ```bash
   OLLAMA_MODEL=qwen3:14b
   # or when Qwen 3.5 local tags exist: OLLAMA_MODEL=qwen3.5:14b
   # OLLAMA_URL unchanged (e.g. http://<g4dn-ip>:11434)
   ```

3. Restart the backend (or redeploy). Chat option **Ominis 2.0** will use the new model.

No code changes required.

---

## Option B: Add a third chat option (e.g. "Ominis 2.0 Open")

Keep **Ominis 2.0** (Qwen 2.5) and **Ominis 2.0 Clinic** (BioMistral), and add a separate option for a newer open-source model (e.g. Qwen 3 or Llama 3.3).

1. **On the g4dn** (or a second Ollama host):

   ```bash
   ollama pull qwen3:14b
   # or: ollama pull qwen3.5:cloud   # Qwen 3.5 (see table below)
   # or: ollama pull llama3.3:70b-instruct-q4_0
   ollama list
   ```

2. **Backend `.env`**:

   ```bash
   # New optional vars for the "open" model
   OLLAMA_OPEN_MODEL=qwen3:14b
   # OLLAMA_OPEN_MODEL=qwen3.5:cloud   # when you want to try Qwen 3.5
   OLLAMA_OPEN_URL=   # Leave empty to use OLLAMA_URL (same server)
   ```

3. **Backend**: Registry and settings already support `ominis-2.0-open` when `OLLAMA_OPEN_MODEL` is set (see `app/config.py`).

4. **Frontend**: The chat selector loads models from `GET /v1/models`; when the backend has `ominis-2.0-open` in the registry, "Ominis 2.0 Open" appears automatically.

5. **Dashboard**: The third option can share the same g4dn as Ominis 2.0 (no extra instance). If you use a separate server for the open model, add `OLLAMA_OPEN_INSTANCE_ID` and dashboard logic later.

---

## Suggested models (Ollama, 2025–2026)

| Model | Ollama tag | VRAM (approx) | Notes |
|-------|------------|----------------|-------|
| **Qwen 3.5** | `qwen3.5:cloud`, `qwen3.5:397b-cloud` | — | New (Feb 2026). 256K context; cloud tags on Ollama. Local 14B/32B may appear later. [Blog](https://qwen.ai/blog?id=qwen3.5) |
| **Qwen 3 14B** | `qwen3:14b` | ~10GB | Direct upgrade from Qwen 2.5 14B, Apache 2.0. Best local option for g4dn today. |
| **Qwen 3 32B** | `qwen3:32b` | ~20GB | Stronger reasoning |
| **Llama 3.3 70B** | `llama3.3:70b-instruct` or `...-q4_0` | ~40GB / ~24GB quantized | Top-tier open, 128K context |
| **DeepSeek R1** | `deepseek-r1:70b` (or smaller) | Check Ollama library | Reasoning-focused |
| **Mistral / Mixtral** | `mistral:7b`, `mixtral:8x7b` | ~6GB / ~22GB | Good quality/size tradeoff |

Check current tags: [Ollama library](https://ollama.com/library) or [qwen3.5 tags](https://ollama.com/library/qwen3.5/tags); run `ollama list` after pull.

---

## Summary

- **Fast path:** Change `OLLAMA_MODEL` to e.g. `qwen3:14b`, run `ollama pull qwen3:14b` on the g4dn, restart backend.
- **Qwen 3.5:** Use `qwen3.5:cloud` (or `qwen3.5:397b-cloud` for vision) when you want the latest; confirm on the g4dn with `ollama pull qwen3.5:cloud` and set `OLLAMA_MODEL` or `OLLAMA_OPEN_MODEL` to that tag. When smaller local tags (e.g. `qwen3.5:14b`) appear on Ollama, prefer them for g4dn.
- **Extra option:** Set `OLLAMA_OPEN_MODEL` (and optionally `OLLAMA_OPEN_URL`); the "Ominis 2.0 Open" option appears in the chat selector automatically. Pull the model on the server first.

All of these models are open-source and run via Ollama; no OpenAI or other third-party inference is required.
