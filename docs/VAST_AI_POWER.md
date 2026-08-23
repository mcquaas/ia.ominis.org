# Ominis Power (gpt-oss) on Vast.ai

This guide describes how to host **Ominis Power** (gpt-oss via vLLM) on [Vast.ai](https://www.vast.ai) instead of a fixed EC2 GPU, and how to get the **best availability** for ia.ominis.org.

References: [Vast.ai docs](https://docs.vast.ai/documentation/get-started), [GPT_OSS_POWER.md](GPT_OSS_POWER.md). For **pay-per-use Serverless** (scale-down GPU billing) vs always-on instances, see [VAST_SERVERLESS.md](VAST_SERVERLESS.md).

---

## Why Vast.ai for gpt-oss

- **Marketplace pricing**: Often cheaper than fixed cloud GPUs; pay per second.
- **Wide GPU choice**: A10G, A100, RTX 3090/4090, H100, etc.; filter by VRAM (≥16 GB for gpt-oss-20b).
- **Flexibility**: Rent on-demand or reserve for discounts; no long-term commitment unless you want it.

For **production availability** (ia.ominis.org), use **On-demand** or **Reserved** instances (not Interruptible), and prefer **Secure Cloud** hosts.

---

## Availability for ia.ominis.org

To maximize uptime and reliability:

| Recommendation | Why |
|----------------|-----|
| **On-demand or Reserved** | High priority; not paused. Interruptible can be paused when outbid. |
| **Secure Cloud (Datacenter)** | Blue label; verified TIER 2/3 or ISO 27001; recommended for production. |
| **Reliability score** | Prefer higher scores (historical uptime). |
| **Reserved instances** | Pre-pay for up to ~50% discount; same high priority as on-demand. |
| **Entrypoint launch mode** | Run the vLLM container as-is; no SSH/Jupyter overhead; ideal for API-only. |

Filter in the [Vast.ai Create](https://cloud.vast.ai/create/) page: **On-demand**, **Secure Cloud** (or Verified), and GPU with **≥16 GB** VRAM for gpt-oss-20b.

---

## Prerequisites

1. **Vast.ai account**: [Sign up](https://cloud.vast.ai/).
2. **Credits**: Add credits (Billing) before creating instances.
3. **API key** (for CLI): [Account → API Keys](https://cloud.vast.ai/account/) or `vastai create api-key`.
4. **CLI** (in-repo): Run once `./infrastructure/setup-vast-cli.sh` to install the Vast CLI in `infrastructure/venv-vast/`. Then `infrastructure/venv-vast/bin/vastai set api-key <key>` (or use `VAST_USE_SSM=1` with AWS CLI for key from SSM).

---

## 1. GPU and instance type

- **gpt-oss-20b**: ~16 GB VRAM → e.g. 1× A10G, RTX 3090/4090, A100 40GB.
- **gpt-oss-120b**: ≥60 GB VRAM → H100 or multi-GPU.

Use **On-demand** (or convert to **Reserved** after rent for discount). Avoid Interruptible for production.

---

## 2. Template (Docker image and port)

Create a template that runs the official vLLM gpt-oss image:

| Setting | Value |
|--------|--------|
| **Image** | `vllm/vllm-openai:gptoss` |
| **Version tag** | `gptoss` or `latest` (must have a tag) |
| **Launch mode** | **Entrypoint** (API-only; no SSH/Jupyter) |
| **Docker run options** | `-p 8000:8000 --gpus all --ipc=host` |
| **Entrypoint args** | `--model openai/gpt-oss-20b --host 0.0.0.0` |

So the container serves the OpenAI-compatible API on port 8000 inside the instance. Vast.ai will map that to a **random external port** on the host’s public IP.

---

## 3. Create instance (Web UI)

1. Go to [cloud.vast.ai/create](https://cloud.vast.ai/create/).
2. Set filters:
   - **Rental type**: On-demand (or Interruptible only for dev/test).
   - **GPU**: e.g. 16+ GB VRAM (A10G, RTX 3090, etc.).
   - **Secure Cloud** (recommended) and/or **Verified**.
   - **Disk**: e.g. 50 GB (model + image).
3. Open **Template** (upper left) → **Change Template** → create/edit:
   - Image: `vllm/vllm-openai:gptoss`
   - Launch: **Entrypoint**
   - Docker options: `-p 8000:8000 --gpus all --ipc=host`
   - Args: `--model openai/gpt-oss-20b --host 0.0.0.0`
4. Click **Rent** on a chosen offer.
5. Wait for the instance to become **running** (model download on first start can take several minutes).

---

## 4. Get the public API URL

Vast.ai maps internal port 8000 to a **random external port** on the host’s public IP.

1. Open your [Instances](https://cloud.vast.ai/instances/) page.
2. Click the instance → open **IP Port Info** (or similar).
3. Find the mapping for **8000/tcp**, e.g.:
   - `65.130.162.74:33526 -> 8000/tcp`
4. Your vLLM base URL is:
   - `http://65.130.162.74:33526`  
   (no `/v1`; the backend adds `/v1` when calling the API.)

Use this as **POWER_API_URL** in the Ominis backend.

---

## 5. Configure the Ominis backend

Set in the backend environment (e.g. `.env` or deployment):

```env
POWER_API_URL=http://<VAST_PUBLIC_IP>:<EXTERNAL_PORT>
POWER_MODEL=openai/gpt-oss-20b
POWER_API_KEY=EMPTY
POWER_TIMEOUT=120
```

Do **not** put `/v1` in `POWER_API_URL`. Then run:

```bash
./infrastructure/20m-update-backend-env-power-gpt.sh
```

(Ensure `config/power_gpt_server.txt` contains the same `POWER_*` values if that script reads from it.)

---

## 6. Reserved instance (discount and commitment)

For long-running, stable capacity:

1. Rent an **On-demand** instance (steps above).
2. On the [Instances](https://cloud.vast.ai/instances/) page, open the instance card.
3. Click the **green discount badge** (e.g. “Save X%”).
4. Choose a pre-pay period (e.g. 1, 3, 6 months); the UI shows deposit and discount.
5. Confirm. The instance keeps the same priority (high) at a lower effective rate.

Notes:

- Reserved = same machine; you cannot migrate to another host.
- If you destroy the instance early, you get a partial refund (remaining balance minus discount already used).
- Avoid adding small prepay amounts near the end of the term; it can reduce the effective discount.

---

## 7. CLI and helper scripts

- **Search:** `./infrastructure/24b-vast-ai-gpt-oss-search.sh` — search for GPUs and print template hints.
- **Create gpt-oss instance:** `./infrastructure/24c-vast-ai-create-gpt-oss.sh` — creates an on-demand instance with `vllm/vllm-openai:gptoss` and gpt-oss-20b. Optionally set `VAST_USE_SSM=1` to load the API key from AWS SSM (`/ominis/vastai/api-key`).

**Manual create** (after getting an offer ID from `vastai search offers --on-demand -g 16`):

```bash
vastai create instance <OFFER_ID> \
  --image vllm/vllm-openai:gptoss \
  --disk 50 \
  --env '-p 8000:8000 --gpus all --ipc=host' \
  --args --model openai/gpt-oss-20b --host 0.0.0.0
```

(No `--ssh` or `--jupyter` so the container runs in entrypoint mode with the given args.)

**Update existing instance to gpt-oss:** If you already have a Vast instance (e.g. running another vLLM image), you can switch it to gpt-oss without losing the contract:

```bash
vastai update instance <INSTANCE_ID> --image vllm/vllm-openai:gptoss --args '--model openai/gpt-oss-20b --host 0.0.0.0'
vastai recycle instance <INSTANCE_ID>   # apply new image (container restart)
```

Then wait until status is `running`; get the public IP and port 8000 mapping from the instance’s IP Port Info.

With the [Vast.ai CLI](https://docs.vast.ai/cli/commands/) and API key set:

```bash
# List your instances
vastai show instances

# Search offers (GPU, on-demand, 16+ GB VRAM)
vastai search offers --on-demand -g 16
```

Create instance via API/CLI using the same image and args as in the template above; ensure port **8000** is exposed (e.g. in docker run options: `-p 8000:8000`). After creation, get the public IP and mapped port from the instance details (Web UI or `vastai show instance <id>` if the CLI returns port info).

---

## 8. Verify

1. **vLLM**:
   ```bash
   curl -s "http://<VAST_PUBLIC_IP>:<EXTERNAL_PORT>/v1/models"
   ```
   You should see `openai/gpt-oss-20b` in the list.

2. **Backend**: With `POWER_API_URL` set and backend restarted:
   ```bash
   curl -s https://api.ominis.org/v1/models | jq '.data[] | select(.id == "ominis-2.0-power")'
   ```

3. **Chat**: On https://ia.ominis.org choose **GPT** (Ominis 2.0 Power) and send a message.

---

## 9. Cost and lifecycle

- **Billing**: Per second while the instance is running; storage is billed while the instance exists (even stopped).
- **Stop**: Stopping releases the GPU; you keep the disk. Restart from the Instances page (the **external port may change**; update `POWER_API_URL` from IP Port Info).
- **Destroy**: Removes the instance and stops all billing; no data persistence unless you backed it up.

For **best availability** for ia.ominis.org: use **On-demand** or **Reserved** on **Secure Cloud** hosts with a **high reliability score**, and keep `POWER_API_URL` updated if you restart the instance (new port mapping).

---

## 10. Ominis 2.0 Med (Med42) on Vast

You can run **Ominis 2.0 Med** (Med42 via Ollama) on Vast.ai instead of a g4dn/g5 Ollama server. Same GPUs (e.g. RTX 5090) give faster inference and keep Power and Med in one place.

| Option | Pros | Cons |
|--------|------|------|
| **Med on Vast** | Faster (better GPUs), single cloud | Extra Vast instance cost (~\$0.30–0.70/hr depending on GPU) |
| **Med on g4dn/g5 Ollama** | Reuses existing Ollama server | Slower than high-end Vast GPUs |

### Create Ollama instance on Vast

1. **CLI (recommended):**
   ```bash
   ./infrastructure/24d-vast-ai-create-ollama-med.sh
   ```
   Uses the same Vast CLI and optional `VAST_USE_SSM=1` as gpt-oss.

2. **Web UI:** [Create](https://cloud.vast.ai/create/) → choose On-demand, GPU ≥16 GB → **Template**:
   - Image: `ollama/ollama`
   - Launch: **Entrypoint**
   - Docker options: `-p 11434:11434 --gpus all`
   - No entrypoint args (Ollama starts the server by default).

3. When the instance is **running**, open **IP Port Info** and note the mapping for **11434/tcp** (e.g. `74.48.140.179:41234`).

4. **Pull Med42** (once per instance):
   ```bash
   ./infrastructure/pull-med42-via-api.sh http://<VAST_IP>:<EXTERNAL_PORT>
   ```
   Or: `curl -X POST "http://<VAST_IP>:<EXTERNAL_PORT>/api/pull" -d '{"name":"med42"}'`. Wait until the pull finishes (first time can take several minutes).

5. **Point backend to Vast Ollama:**
   - In `config/ollama_med_server.txt` set:
     ```bash
     OLLAMA_MED_MODEL=med42
     OLLAMA_MED_URL=http://<VAST_IP>:<EXTERNAL_PORT>
     OLLAMA_MED_INSTANCE_ID=
     ```
     Leave `OLLAMA_MED_INSTANCE_ID` empty (Vast instances are not EC2; start/stop is from the Vast dashboard).
   - Push env:
     ```bash
     ./infrastructure/20med-update-backend-env-ollama-med.sh
     ```

6. Restart backend if needed; then use **Ominis 2.0 Med** in the chat.

If you stop the Vast Med instance, the external port may change on next start; update `OLLAMA_MED_URL` and re-run `20med-update-backend-env-ollama-med.sh`.

---

For faster chat response time in general (Power, Med, Ominis 2.0), see [PERFORMANCE_RESPONSE_SPEED.md](PERFORMANCE_RESPONSE_SPEED.md).

---

## References

- [Vast.ai Get Started](https://docs.vast.ai/documentation/get-started)
- [Instances Overview](https://docs.vast.ai/documentation/instances/overview)
- [Find & Rent](https://docs.vast.ai/documentation/instances/choosing/find-and-rent)
- [Instance Types](https://docs.vast.ai/documentation/instances/choosing/instance-types) (On-demand vs Reserved vs Interruptible)
- [Reserved Instances](https://docs.vast.ai/documentation/instances/choosing/reserved-instances)
- [Networking & Ports](https://docs.vast.ai/documentation/instances/connect/networking)
- [Templates](https://docs.vast.ai/documentation/templates/introduction)
- [GPT_OSS_POWER.md](GPT_OSS_POWER.md) (backend config, model sizes, existing EC2/Docker options)
