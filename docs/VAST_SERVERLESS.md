# Vast.ai Serverless (pay per use)

This guide explains how **Vast Serverless** differs from **always-on Vast instances** (the model used by scripts like `24f-vast-ai-create-ollama-qwen-vl.sh`), and how to move toward **GPU billing only when workloads run**.

References: [Vast Serverless overview](https://docs.vast.ai/documentation/serverless/index), [Pricing](https://docs.vast.ai/serverless/pricing), [Quickstart (vLLM)](https://docs.vast.ai/documentation/serverless/quickstart), [Architecture](https://docs.vast.ai/documentation/serverless/architecture).

---

## 1. Always-on instance vs Serverless

| | **On-demand / reserved instance** (current scripts) | **Serverless** |
|---|-----------------------------------------------------|----------------|
| **Billing** | GPU compute billed whenever the instance is running (24/7 if you leave it up). | GPU compute billed mainly when workers are **Ready** or **Loading**; **Inactive** workers do not bill GPU compute (you still pay **storage** and **bandwidth**). |
| **URL** | Stable **IP:port** → backend sets `OLLAMA_URL`, `power_api_url`, `OPENSCHOLAR_128K_API_URL`, etc. | No single stable inference URL: the engine assigns a **worker URL per request** via the **route** API or **Python SDK**. |
| **Best for** | Predictable load, long sessions, Ollama + custom pull scripts, minimal app changes. | Bursty inference, scaling to zero–ish GPU cost between bursts (with correct endpoint settings). |

---

## 2. Cost behavior (what “only when needed” means)

From [Vast Serverless pricing](https://docs.vast.ai/serverless/pricing):

- **Ready / Loading**: GPU + storage + bandwidth.
- **Inactive**: **No** GPU compute; storage + bandwidth still apply.
- **Endpoint states**: You can **suspend** or **stop** an endpoint so workers go inactive; **destroy** stops all billing.

For **low idle cost**, tune [Managing scale](https://docs.vast.ai/documentation/serverless/managing-scale):

- **`min_load`**: Set to **`0`** so the engine can scale active capacity down (workers can go **inactive** when idle).
- **`min_workers` / cold pool**: Affects how many **inactive** workers are kept around for faster warm-up; they still incur **storage** (and related) costs—lower if you accept slower first request after idle.

The dashboard quickstart examples use high `min_workers` for instant demos; **production “cheap when idle”** usually means **lower `min_workers`** and **`min_load` = 0**, accepting **cold start** latency after quiet periods.

**What actually makes responses *fast* (low time-to-first-token):**

| Lever | Effect |
|--------|--------|
| **`min_workers` / cold pool** | Keeps workers **Ready** (or pre-warmed) so the first request after idle does not pay full cold start. **Tradeoff:** higher idle cost. |
| **Model & GPU** | Smaller / more quantized models and a GPU with enough VRAM load and generate faster. |
| **Region / path** | Place backend and workers in **similar regions** when possible; long RTT adds latency. |
| **Timeouts (app)** | Large `vast_serverless_client_timeout` and SSE client timeout **do not** speed up inference—they only **avoid false timeouts** during cold start. |

---

## 3. Creating Serverless endpoints (dashboard)

1. Open **[Serverless dashboard](https://cloud.vast.ai/serverless/)** → **Get Started**.
2. Create an **endpoint** (name it per use case, e.g. chat vs long-context).
3. Create a **workergroup** using a template:
   - **vLLM** templates fit **OpenAI-compatible** stacks (similar to Power / OpenScholar-style serving). See [vLLM on Serverless](https://docs.vast.ai/documentation/serverless/vllm) and [Quickstart](https://docs.vast.ai/documentation/serverless/quickstart).
4. Set account **HF_TOKEN** under **Environment Variables** if the model is gated on Hugging Face (see quickstart).

**Ollama** on Serverless is **not** a one-click swap for the current `24f` Ollama images: Serverless workers are built around **PyWorker + templates** (vLLM, TGI, ComfyUI, etc.). Running **Ollama** would mean a **custom PyWorker** or staying on a **normal Vast instance** for Ollama-only workflows. See [Creating custom PyWorkers](https://docs.vast.ai/documentation/serverless/creating-new-pyworkers).

---

## 4. Backend integration (implemented)

The Haystack backend uses the official **`vastai-sdk`** (`Serverless` client) on a **dedicated background asyncio thread** so synchronous Haystack `.run()` calls still route correctly. Each request: **route → worker →** `/v1/chat/completions` (vLLM) or `/api/chat` (Ollama PyWorker).

**Requirements:** `VAST_API_KEY` (or `vast_api_key` in `.env`) and the **endpoint name** exactly as in [Serverless dashboard](https://cloud.vast.ai/serverless/).

### OMINIS model ↔ Vast workload mapping

| Product / UI | Backend env for Serverless | Typical template | Models / notes |
|--------------|----------------------------|------------------|----------------|
| **Ominis 2.0** (chat) | `vast_serverless_ollama_endpoint` | Ollama PyWorker or multi-model Ollama | `OLLAMA_MODEL` (e.g. `qwen3:14b`); pull on workers |
| **Vision** (no Qwen URL) | same as chat if using Ollama vision | same | `VISION_MODEL` (e.g. `qwen2.5vl:7b`) |
| **Ominis 2.0 Power** | `vast_serverless_power_endpoint` | vLLM Serverless | `POWER_MODEL` e.g. `openai/gpt-oss-20b` |
| **Research OpenScholar 8K** | `vast_serverless_openscholar_endpoint` | vLLM | `OPENSCHOLAR_MODEL` |
| **Research 128K** | `vast_serverless_openscholar_128k_endpoint` | vLLM long-context | same served name as your vLLM `--served-model-name` |
| **Med42 translator** | `vast_serverless_med42_endpoint` | vLLM / OpenAI-compat | `MED42_MODEL` |
| **Qwen2.5-VL** (vision URL path) | `vast_serverless_qwen_vl_endpoint` | vLLM multimodal | `QWEN_VL_MODEL` |

Use `infrastructure/vast_serverless_search_templates.py` to find `template_id` / `hash_id`, then `config/vast_serverless_manifest.example.json` + `infrastructure/vast_serverless_provision_manifest.py` to create all endpoints. Health: `GET /v1/system-stats/health` treats **serverless** as healthy when `VAST_API_KEY` + `vast_serverless_ollama_endpoint` are set even if direct Ollama is unreachable. Detail: `GET /v1/system-stats/health/vast-serverless`.

### Environment variables (`backend-haystack` / `.env`)

| Variable | Purpose |
|----------|---------|
| `VAST_API_KEY` | Vast API key (also read as `vast_api_key` in settings) |
| `vast_serverless_default_cost` | Default route **cost** hint (default `500`) |
| `vast_serverless_ollama_endpoint` | Ollama workergroup: `/api/chat` for chat + Med models |
| `vast_serverless_ollama_cost` | Override cost (0 = use default) |
| `vast_serverless_power_endpoint` | vLLM workergroup: **Ominis 2.0 Power** (`ominis-2.0-power`) |
| `vast_serverless_power_cost` | Override cost |
| `vast_serverless_openscholar_endpoint` | OpenScholar 8K (research) |
| `vast_serverless_openscholar_128k_endpoint` | OpenScholar 128K |
| `vast_serverless_med42_endpoint` | Med42 clinical translator |
| `vast_serverless_qwen_vl_endpoint` | Qwen2.5-VL vision (OpenAI multimodal) |

If a **serverless endpoint** is set for a service, it takes precedence over static URLs (`power_api_url`, `openscholar_128k_api_url`, `med42_api_url`, etc.) for that service.

**Power model:** set `power_api_url` **or** `vast_serverless_power_endpoint` (registry registers `ominis-2.0-power` when either is set).

### Automated provisioning (API)

```bash
export VAST_API_KEY=...
python3 infrastructure/vast_serverless_provision.py \
  --endpoint-name ominis-vllm-power \
  --template-hash YOUR_TEMPLATE_HASH \
  --min-load 0 --cold-workers 0 --max-workers 12
```

You must pass **`--template-hash`** or **`--template-id`** from the Vast UI (vLLM / Ollama template). See [create endpoint](https://docs.vast.ai/api-reference/serverless/create-endpoint) and [create workergroup](https://docs.vast.ai/api-reference/serverless/create-workergroup).

---

## 5. Suggested migration order

1. Create Serverless endpoints with **`min_load = 0`** and low **`cold_workers`** where you accept cold starts.
2. Add `VAST_API_KEY` and per-service `vast_serverless_*_endpoint` names to the backend `.env`.
3. Deploy backend; smoke-test chat, research 128K, vision.
4. Destroy or stop legacy always-on Vast GPU instances when satisfied.

---

## 6. Related repo docs

- [VAST_AI_POWER.md](VAST_AI_POWER.md) — gpt-oss on **classic** Vast instances.
- [VAST_OLLAMA_QWEN_VL.md](VAST_OLLAMA_QWEN_VL.md) — Ollama on **classic** instances.
- [VAST_DEPLOY_AND_EC2_CLEANUP.md](VAST_DEPLOY_AND_EC2_CLEANUP.md) — mapping scripts to services.

**SDK reference:** [Vast Serverless SDK](https://docs.vast.ai/documentation/serverless/SDKoverview).
