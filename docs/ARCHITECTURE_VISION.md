# System Vision: Multimodal Open-Source Architecture

**Goal:** Build a multimodal open-source system for:

- **Deep scientific research** (multi-paper synthesis)
- **Public health**
- **Clinical support**
- **Structured PDF analysis**
- **Scientific image interpretation**
- **Evidence-based reports** with verifiable citations

---

## 1. Models and Roles

| Model | Where | Role |
|-------|--------|------|
| **OpenScholar 128K** | Vast.ai | Deep multi-document synthesis, systematic reviews, long reports, multi-source integration |
| **Med42** | A100 (current) | Clinical reasoning, evidence → medical implications, clinical cases |
| **Qwen2.5-VL** | New A100 (recommended) | Image interpretation, advanced OCR, scientific figures, tables, scanned PDFs |
| **Qwen (text)** | AWS | Intermediate generation, auxiliary agents, classification and routing |
| **Embeddings service** | New microservice | bge-large-en-v1.5 or bge-m3 — RAG indexing, precise biomedical retrieval |

---

## 2. End-to-End Flows

### A) PDF ingestion

```
Upload PDF
    → Docling (structured JSON)
    → Split: main text | tables | figures
    → Embeddings
    → Qdrant

If scanned PDF:
    Page → Qwen2.5-VL
    → Extract structured text
    → Embeddings
```

### B) Query (Deep Research)

1. **Retrieval** — Dense (bge) + BM25 hybrid; optional cross-encoder reranker.
2. **Evidence Extractor Agent** (Qwen text) — Extract OR/RR/HR, IC95, p-values, N, design → structured JSON.
3. **Quality Auditor Agent** — Study type, bias, confounding, methodological quality → structured output.
4. **Synthesizer Agent** (OpenScholar 128K) — Input: structured extracts + retrieved evidence + quality evaluations → integrated synthesis, evidence level, consistency.
5. **Clinical Translator** (if applicable) — Med42: clinical implications, risks, prudent recommendations.

---

## 3. Agents (e.g. LibreChat)

| Agent | Model | Purpose |
|-------|--------|---------|
| Evidence Extractor | Qwen (text) | Structured extraction from papers |
| Bias Auditor | Qwen (text) | Bias / quality assessment |
| Synthesizer | OpenScholar 128K | Multi-paper synthesis |
| Clinical Translator | Med42 | Evidence → clinical implications |
| Visual Interpreter | Qwen2.5-VL | Images, figures, tables, scanned PDFs |

**Routing:** By input type (image / PDF / text), question type (clinical vs research), and required length.

---

## 4. Serving

- **vLLM** on each Vast node → OpenAI-compatible endpoint.
- LibreChat (or frontend) connects via custom endpoints.

---

## 5. Vector DB (Qdrant)

**Collections:**

- `papers_text`
- `figures`
- `tables`
- `clinical_guidelines`

**Required metadata:** year, journal, design, population, country, DOI.

---

## 6. Quality Control

- **Mandatory citations** by chunk ID.
- Separate **“evidence”** vs **“interpretation”**.
- **Uncertainty flag** when appropriate.
- **No unsourced claims.**

---

## 7. Recommended Infrastructure

| Node | Purpose |
|------|---------|
| **Vast 1** | Med42 (already active) |
| **Vast 2** | OpenScholar 128K |
| **Vast 3** (new) | Qwen2.5-VL 32B on A100 |
| **AWS** | Qwen text + embeddings |

**Cost optimization:** Use Qwen2.5-VL 7B quantized if reducing A100s; keep OpenScholar for final synthesis only; use Med42 on demand.

---

## 7.1 Experimental phase: cost-optimal setup

For the **experimental phase**, avoid over-provisioning. H100 is not justified; invest in architecture and pipelines instead.

### Per model

| Model | Experimental recommendation | Rationale |
|-------|-----------------------------|-----------|
| **OpenScholar 128K** | **A100 40GB**, 4-bit quantization | Enough if you don't need >60–80K real tokens, batching, or many concurrent users. H100 adds throughput/latency/context, not quality. |
| **Qwen2.5-VL** | **A100 40GB** (32B) or **RTX 4090** (7B) | For testing, 4090 is excellent cost/benefit. 32B on A100 when you need maximum vision quality. |
| **Med42** | **A100 40GB** | Keep as-is; well suited to its role. |
| **Embeddings** (bge) | **Off A100** — use **RTX 4090**, **L4**, or **A10G** | Saves cost and frees big GPUs for LLMs. |

### Recommended experimental layout (Vast)

| Vast node | GPU | Workload |
|-----------|-----|----------|
| **Vast 1** | A100 40GB | Med42 |
| **Vast 2** | A100 40GB | OpenScholar 128K (4-bit) |
| **Vast 3** | **RTX 4090** | Qwen2.5-VL **+** embeddings (bge) |

This covers the experimental stack at lower cost.

### What matters most in experimental phase

The bottleneck is **not** the GPU. Priority:

1. **Agent architecture** — clear roles, handoffs, structured outputs.
2. **PDF pipeline quality** — Docling, text/tables/figures split, chunking.
3. **RAG design** — retrieval, reranking, chunk IDs, metadata.
4. **Citation control** — mandatory sources, evidence vs interpretation.
5. **Bias and quality evaluation** — study type, methodology, uncertainty.

These have **far more impact** than moving to H100.

### Conclusion (experimental)

- **Do not** buy H100 for this phase.
- **A100 40GB** is the right tier for Med42 and OpenScholar 128K.
- **RTX 4090** (or L4/A10G) for Qwen2.5-VL and embeddings.
- **Invest effort in architecture and pipelines**, not in premium hardware.

---

## 8. Current vs Target (ia.ominis.org)

| Capability | Current | Target |
|------------|---------|--------|
| OpenScholar 128K | ✅ Vast.ai, research stream | As above (Synthesizer agent) |
| Med42 / clinic | ✅ Ominis 2.0 Clinic (BioMistral on g5) | Dedicated Med42 on A100 / Vast |
| Qwen text | ✅ Ominis 2.0 (Qwen on g5) | Same + agent routing |
| Qwen2.5-VL | MinicPM-V or similar on Ollama | Dedicated Qwen2.5-VL service (Vast 3) |
| Embeddings | In-process / existing RAG | Dedicated bge microservice |
| Docling + structured PDF | Partial (RAG indexing) | Full pipeline → text/tables/figures → Qdrant |
| Evidence / Bias / Synthesizer agents | Research pipeline (single stream) | Explicit agents + routing |
| Qdrant collections | Single or few | papers_text, figures, tables, clinical_guidelines |
| LibreChat | Not integrated | Optional UI for agent endpoints |

---

## 9. Final Capabilities (Target)

With this architecture:

- ✔ Real multimodal (text + images + PDFs)
- ✔ Serious biomedical RAG
- ✔ Long multi-paper synthesis
- ✔ Bias and quality evaluation
- ✔ Clinical translation
- ✔ Structured, cited reports
- ✔ Scalable (Vast + AWS)

---

## Related docs

- [ARCHITECTURE.md](./ARCHITECTURE.md) — Current system overview
- [LLM_INFRA.md](./LLM_INFRA.md) — AWS GPU instances (Ollama)
- [OPENSCHOLAR_128K_VAST.md](./OPENSCHOLAR_128K_VAST.md) — OpenScholar 128K on Vast.ai
- [LLM_ROUTING.md](./LLM_ROUTING.md) — Backend model routing
