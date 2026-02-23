# Ominis 2.0 Power — gpt-oss via vLLM

**Ominis 2.0 Power** is a chat model backed by [OpenAI’s gpt-oss](https://developers.openai.com/cookbook/articles/gpt-oss/run-vllm) served with [vLLM](https://docs.vllm.ai/) (OpenAI-compatible API). When configured, it appears in the model selector next to Ominis 2.0, Clinic, and Open.

**Hosting:** Run vLLM on your own GPU (EC2, etc.) or on [Vast.ai](https://www.vast.ai). See **[VAST_AI_POWER.md](VAST_AI_POWER.md)** for Vast.ai setup and best availability for ia.ominis.org.

## Model sizes

| Model | VRAM | Use case |
|-------|------|----------|
| `openai/gpt-oss-20b` | ~16 GB | g4dn.xlarge / g5.xlarge |
| `openai/gpt-oss-120b` | ≥60 GB | H100 or multi-GPU |

Both are MXFP4 quantized. The backend defaults to the 20B model; set `POWER_MODEL=openai/gpt-oss-120b` if you run the 120B server.

## 1. Run vLLM on a GPU server

**If you only deployed the app and never installed vLLM on a host:** use the **Docker** method (recommended; avoids pip/tokenizer issues):

```bash
VLLM_HOST=18.235.182.22 KEY_FILE=config/ominis-falcon-gpu-key.pem bash infrastructure/24a-run-gpt-oss-docker.sh
```

This installs Docker + nvidia-container-toolkit on the GPU host and runs `vllm/vllm-openai:gptoss` with gpt-oss-20b. Then ensure the backend has `POWER_API_URL` pointing to that host and run `./infrastructure/20m-update-backend-env-power-gpt.sh`.

Alternative (pip/venv, may hit tokenizer compat on some setups): `24-install-gpt-oss-vllm.sh`.

Manual install on a machine with enough VRAM (e.g. EC2 g5.2xlarge for 20B):

```bash
# Optional: use uv for environment
uv venv --python 3.12 --seed
source .venv/bin/activate

uv pip install --pre vllm==0.10.1+gptoss \
    --extra-index-url https://wheels.vllm.ai/gpt-oss/ \
    --extra-index-url https://download.pytorch.org/whl/nightly/cu128 \
    --index-strategy unsafe-best-match

# Serve (downloads from HuggingFace on first run)
vllm serve openai/gpt-oss-20b
# Or for 120B: vllm serve openai/gpt-oss-120b
```

vLLM listens on `http://0.0.0.0:8000` and exposes an OpenAI-compatible API at `http://<host>:8000/v1`. Use `--host 0.0.0.0` if needed for remote access.

## 2. Configure the Ominis backend

Set these in the backend environment (e.g. `.env` or deployment env):

```env
# Base URL of the vLLM server (no /v1 — the backend appends it)
POWER_API_URL=http://<vllm-host>:8000
# Model name must match what vLLM serves (openai/gpt-oss-20b or openai/gpt-oss-120b)
POWER_MODEL=openai/gpt-oss-20b
POWER_API_KEY=EMPTY
POWER_TIMEOUT=120
# Optional: EC2 instance ID for dashboard start/stop (enables Power server card)
POWER_INSTANCE_ID=
```

- If `POWER_API_URL` is empty, **Ominis 2.0 Power** is not registered and will not appear in the UI.
- The backend uses `OpenAIChatGenerator` with `api_base_url=<POWER_API_URL>/v1`, so do not include `/v1` in `POWER_API_URL`.

## 3. How to test

**1) Check vLLM is up** (replace with your Power host if different):

```bash
curl -s http://18.235.182.22:8000/v1/models
```

You should see a JSON list including `openai/gpt-oss-20b`. If the container is still loading the model, wait a few minutes and retry.

**2) Check the backend sees GPT** (from your machine; backend must have `POWER_API_URL` set):

```bash
curl -s https://api.ominis.org/v1/models | jq '.data[] | select(.id == "ominis-2.0-power")'
```

**3) Test in the chat UI**

- Open https://ia.ominis.org
- In the model selector, choose **GPT** (Ominis 2.0 Power)
- Send a short message; you should get a streamed reply from gpt-oss

If the request fails (e.g. timeout or connection refused), confirm the Docker container on the Power host is running: `ssh -i config/ominis-falcon-gpu-key.pem ubuntu@18.235.182.22 'sudo docker ps && sudo docker logs ominis-gptoss --tail 30'`

## 4. Performance (why the first response is slow)

**GPT (gpt-oss-20b)** often takes **30–60 seconds** before the first token appears. This is normal: the model is large and the server must run “prefill” (process the full prompt) before streaming. What we did to help:

- **Less context for Power:** The backend sends at most 4 sources and 400 characters per source (instead of 8 and 800) so prefill is faster.
- **Longer timeout:** The stream waits up to 180 s for the first token (vs 120 s for other models) so it doesn’t abort while the model is still loading.
- **Message in the UI:** While waiting, the user sees that “GPT (20B) suele tardar 30–60 s en la primera respuesta.”

After the first token, streaming is usually smooth. To speed up further: use a smaller/faster model for quick answers, or run gpt-oss on a more powerful GPU (e.g. H100).

## 5. Behaviour in the app

- **Model selector:** When `POWER_API_URL` is set, the backend adds `ominis-2.0-power` to `GET /v1/models` and the frontend shows **GPT** in the dropdown. **Access:** only **admin** and **superadmin** can use GPT (gpt-oss); researchers see it as locked with “Solo administradores”.
- **Chat:** Same RAG/chat flow as Ominis 2.0 / Clinic / Open; no research mode. Requests are sent to the vLLM Chat Completions endpoint.
- **Dashboard:** When `POWER_INSTANCE_ID` is set, the Power EC2 appears in “Servidores GPU” with start/stop. Set `POWER_API_URL` to the instance’s public IP (or Elastic IP) so the backend can call vLLM. For Vast.ai, leave `POWER_INSTANCE_ID` empty so the card shows as “Ominis 2.0 Power (API remota)”.

## Cost estimate (on-demand, us-east-1, approximate)

| Instance       | Use case      | $/hr (on-demand) | ~$/month (24/7) |
|----------------|---------------|-------------------|------------------|
| g4dn.xlarge    | gpt-oss-20b   | ~\$0.53           | ~\$380           |
| g5.2xlarge     | gpt-oss-20b   | ~\$1.21           | ~\$875           |
| g5.12xlarge / H100 | gpt-oss-120b | much higher      | check AWS Pricing |

Use Spot or reserved instances to reduce cost. Stop the instance from the dashboard when not needed.

## References

- [OpenAI cookbook: Run gpt-oss with vLLM](https://developers.openai.com/cookbook/articles/gpt-oss/run-vllm)
- [vLLM quickstart](https://docs.vllm.ai/en/latest/getting_started/quickstart.html)
- Backend: `app/config.py` (Power settings, `_build_model_registry`), `app/rag/pipeline.py` (OpenAIChatGenerator for Power)
