# Faster response speed (chat / RAG)

Ways to reduce time-to-first-token and total response time.

---

## 1. Backend (already tuned for Power and Med)

- **Power (gpt-oss) and Med (Med42)**: Only the first **4** documents are sent, with **400** chars per doc (others get 800). Shorter prompt = faster prefill.
- **History**: For Power and Med we only send the last **2** exchanges (4 messages) so the prompt stays smaller.
- **Streaming**: Tokens are streamed as they arrive; the UI shows “Conectando con el modelo…” and then text as soon as the first token is received.
- **Timeouts**: Power and Med have a 180s generation timeout (others 120s) so slow first token does not abort too soon.

Optional tweaks you can do without code changes:

- **Dashboard**: For Power (or any model), lower **num_predict** (e.g. 1024 instead of 2048) to cap response length and speed up generation.
- **Ollama (Med / Clinic / Ominis 2.0)**: Run on a stronger GPU for faster inference. **Med** in particular: use an Ollama instance on Vast (see [VAST_AI_POWER.md](VAST_AI_POWER.md) §10 and `24d-vast-ai-create-ollama-med.sh`) instead of the same g4dn as Ominis 2.0 — same GPUs as Power (e.g. RTX 5090) make Med much faster.

---

## 2. Vast / vLLM (Power)

- **GPU**: Your 2× RTX 5090 is already strong. Prefill (time to first token) is dominated by prompt length and model size.
- **Region**: If the backend (EC2) and the Vast instance are in different regions, network RTT adds latency. Prefer a Vast host in the same region as the backend (e.g. both US or both EU) when choosing an offer.
- **vLLM args** (when creating/updating the Vast template): Some versions support:
  - `--enable-chunked-prefill` — can improve time-to-first-token (check vLLM release notes).
  - `--max-num-seqs 1` — we only stream one request at a time; keeps memory predictable.

Leave existing args as-is unless you upgrade the image and confirm compatibility.

---

## 3. Prompt size (biggest lever)

- **Fewer sources**: Users can set “Número de fuentes” to 3 (default); fewer docs = smaller prompt = faster prefill.
- **Shorter system prompt**: If you customize the system prompt in the dashboard, a shorter one reduces prefill time.
- **History**: For Power and Med we only send the last 2 turns of chat history (see code: `router.py` + `fast_prefill_models`).

---

## 4. Frontend

- Already uses SSE and shows status (“Conectando…”, “El modelo está generando…”) so the user sees progress.
- No change needed for basic speed; optional: show a “first token in Xs” metric for debugging.

---

## Summary

| Area              | Action |
|-------------------|--------|
| Backend           | Already: 4 docs, 400 chars/doc, last 2 turns history for Power and Med; streaming; 180s timeout for both. Optional: lower `num_predict` in dashboard. |
| Vast / vLLM       | Same region as backend; optional vLLM flags (`--enable-chunked-prefill`, `--max-num-seqs 1`) if supported. |
| Ollama (Med etc.) | Use a faster GPU (e.g. Med on Vast). |
| Prompt            | Fewer sources, shorter system prompt, limited history for Power. |
