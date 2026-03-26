# Vast.ai: After Recreating an Instance

When a Vast instance is lost (e.g. payment lapse, host reclaim) and you create a **new** instance, the **IP and port change**. Follow the steps below for the instance you recreated.

**Current production setup (only these three):** Ominis 2.0 (Ollama Qwen/VL), Ominis 2.0 Med, Ominis 2.0 Research 128k. GPT (Power / gpt-oss) is not in use.

**UI → backend mapping:** Ominis 2.0 = Qwen 3 (OLLAMA_URL + OLLAMA_MODEL). Ominis 2.0 Med = Med42 (OLLAMA_MED_URL + OLLAMA_MED_MODEL). Ominis 2.0 Research 128k = OpenScholar (OPENSCHOLAR_128K_API_URL).

---

## Which instance did you recreate?

| Instance | Config file | Backend env (via script) | Internal port |
|----------|-------------|---------------------------|---------------|
| **Ollama Qwen3 + Qwen2.5-VL** (chat + vision) | `config/ollama_qwen_vast.txt` | `20c-vast-update-backend-env-ollama-qwen-vl.sh` | **11434** |
| **Power (gpt-oss)** (vLLM) | `config/power_gpt_server.txt` | `20m-update-backend-env-power-gpt.sh` | **8000** |
| Med42 (Ollama) | `config/med42_vast.txt` | `20b-vast-update-backend-env-med42.sh` | (see instance) |
| OpenScholar 128K | (see docs) | `20a-vast-update-backend-env-openscholar-128k.sh` | **8000** |

---

## A. Ollama Qwen3 + Qwen2.5-VL (chat + vision)

1. **Get new IP and port**  
   Vast → [Instances](https://cloud.vast.ai/instances/) → your instance → **IP & Port Info** → mapping for **11434** (e.g. `1.2.3.4:45678`).

2. **Update config**
   ```bash
   # Edit config/ollama_qwen_vast.txt
   OLLAMA_QWEN_VAST_URL=http://<NEW_IP>:<NEW_PORT>
   OLLAMA_MODEL=qwen3:14b
   VISION_MODEL=qwen2.5vl:7b
   ```

3. **Pull models on the new instance** (fresh instance has no models)
   - **Option A – via backend (if backend can reach Vast):**
     ```bash
     ./infrastructure/pull-ollama-qwen-vl-via-backend.sh
     ```
   - **Option B – from Vast Connect:** Instance → **Connect** → shell:
     ```bash
     ollama pull qwen3:14b
     ollama pull qwen2.5vl:7b
     ollama list
     ```
   - **Option C – curl (if your network can reach the instance):**
     ```bash
     curl -X POST http://<NEW_IP>:<NEW_PORT>/api/pull -d '{"name":"qwen3:14b"}'
     curl -X POST http://<NEW_IP>:<NEW_PORT>/api/pull -d '{"name":"qwen2.5vl:7b"}'
     ```

4. **Point backend at new URL and restart**
   ```bash
   ./infrastructure/20c-vast-update-backend-env-ollama-qwen-vl.sh
   ```

5. **Verify**
   ```bash
   ./infrastructure/vast-verify-endpoints.sh
   ```
   And in the app: send a chat message (Ominis 2.0) and, if possible, one with an image (vision).

---

## B. Power (gpt-oss, vLLM)

1. **Get new IP and port**  
   Vast → Instances → your instance → **IP & Port Info** → mapping for **8000** (e.g. `1.2.3.4:33526`).

2. **Update config**
   ```bash
   # Edit config/power_gpt_server.txt
   POWER_API_URL=http://<NEW_IP>:<NEW_PORT>
   POWER_MODEL=openai/gpt-oss-20b
   POWER_API_KEY=EMPTY
   POWER_TIMEOUT=120
   POWER_INSTANCE_ID=
   ```

3. **No separate “install” step**  
   The vLLM image downloads the model on first start. Wait until the instance is **running** and the model has loaded (can take several minutes).

4. **Point backend at new URL and restart**
   ```bash
   ./infrastructure/20m-update-backend-env-power-gpt.sh
   ```

5. **Verify**
   ```bash
   ./infrastructure/vast-verify-endpoints.sh
   ```
   And in the app: choose “GPT” in the chat and send a message.

---

## Verify endpoints (optional)

From the repo root:

```bash
./infrastructure/vast-verify-endpoints.sh
```

This script reads `config/ollama_qwen_vast.txt` and `config/power_gpt_server.txt`, then:

- For **Ollama**: `GET <OLLAMA_QWEN_VAST_URL>/api/tags` (lists models).
- For **Power**: `GET <POWER_API_URL>/v1/models` (lists vLLM models).

If run from a machine that cannot reach Vast (e.g. your laptop behind NAT), the curls may fail; the backend EC2 might still reach Vast. In that case run the same curls from the backend or use the app to test.

---

## Cost savings

- **Ollama Qwen/VL:** The doc recommends A100 40GB for Qwen3 + Qwen2.5-VL. If you recreate, use 40GB (e.g. A100 PCIE) instead of 80GB SXM4 to reduce hourly cost.
- **Power (gpt-oss):** Not in use; no instance needed.
- **On-demand vs reserved:** Use on-demand when usage is sporadic; convert to reserved only if the instance runs 24/7 to get the discount.

---

## References

- [VAST_OLLAMA_QWEN_VL.md](VAST_OLLAMA_QWEN_VL.md) – Ollama Qwen/VL setup from scratch  
- [VAST_AI_POWER.md](VAST_AI_POWER.md) – gpt-oss (Power) on Vast  
- [VAST_DEPLOY_AND_EC2_CLEANUP.md](VAST_DEPLOY_AND_EC2_CLEANUP.md) – overview of Vast services
