# Vast.ai: Ollama Qwen3 + Qwen2.5-VL (chat + vision)

Single Vast.ai instance with **Ollama** serving:
- **Qwen3** (e.g. `qwen3:14b`) for general chat when there is **no image**.
- **Qwen2.5-VL** (e.g. `qwen2.5vl:7b`) when the user sends an **image** (vision).

One A100 40GB so both models can be loaded in VRAM.

## 1. Create the instance

```bash
./infrastructure/24f-vast-ai-create-ollama-qwen-vl.sh
```

Wait until the instance is **running** in the Vast dashboard.

New instances created with the script run **ollama serve** automatically on start (onstart script). If you had to run `ollama serve` manually, see **Make Ollama permanent (existing instance)** below.

## 2. Get IP and port

In Vast.ai → **Instances** → your instance → **IP & Port Info**: note the **external** host and port mapped to internal **11434** (e.g. `1.2.3.4:45678`).

## 3. Pull models (from any machine that can reach the instance)

**Option A – curl (if your network can reach the instance):**
```bash
curl -X POST http://<IP>:<PORT>/api/pull -d '{"name":"qwen3:14b"}'
curl -X POST http://<IP>:<PORT>/api/pull -d '{"name":"qwen2.5vl:7b"}'
```
Wait for each pull to finish before starting the next.

**Option B – via backend:** `./infrastructure/pull-ollama-qwen-vl-via-backend.sh`

**Option C – from Vast Connect (always works):** In Vast dashboard → instance → **Connect** → shell:
```bash
ollama pull qwen3:14b
ollama pull qwen2.5vl:7b
ollama list
```

## 4. Configure backend

Copy the example and set the URL:

```bash
cp config/ollama_qwen_vast.txt.example config/ollama_qwen_vast.txt
# Edit config/ollama_qwen_vast.txt: set OLLAMA_QWEN_VAST_URL=http://<IP>:<PORT>
```

Then update the Haystack backend env and restart:

```bash
./infrastructure/20c-vast-update-backend-env-ollama-qwen-vl.sh
```

The script reads `config/ollama_qwen_vast.txt` (or you can pass the URL as first argument). It sets `OLLAMA_URL`, `OLLAMA_MODEL`, and `VISION_MODEL` on the backend and restarts the service.

## Summary: three Vast setups

| Vast instance | Script | Backend update | Use |
|---------------|--------|----------------|-----|
| **Med42** | (already there) | `20b-vast-update-backend-env-med42.sh` | Clinical translator (Research mode) |
| **OpenScholar 128K** | `24e-vast-ai-create-openscholar-128k.sh` | `20a-vast-update-backend-env-openscholar-128k.sh` | Long synthesis (Research), A100 |
| **Ollama Qwen + VL** | `24f-vast-ai-create-ollama-qwen-vl.sh` | `20c-vast-update-backend-env-ollama-qwen-vl.sh` | General chat + vision |

See also: [VAST_DEPLOY_AND_EC2_CLEANUP.md](VAST_DEPLOY_AND_EC2_CLEANUP.md).

---

## Make Ollama permanent (existing instance)

If you created the instance **before** the script had the onstart (or had to run `ollama serve` manually once), make it start on every boot from the Vast **Connect** shell:

```bash
(crontab -l 2>/dev/null; echo '@reboot export OLLAMA_HOST=0.0.0.0 && nohup ollama serve >> /var/log/ollama.log 2>&1 &') | crontab -
```

After that, `ollama serve` will run automatically when the instance starts. You can leave the current `ollama serve` running; the crontab only affects the next boot.
