# Implementation Roadmap: Vision Architecture

Phased implementation of [ARCHITECTURE_VISION.md](./ARCHITECTURE_VISION.md). Check off as completed.

---

## Phase 1 – Foundation & config

- [x] **Config**: `EMBEDDING_SERVICE_URL`, `MED42_API_URL`, `QWEN_VL_API_URL` (and model/timeout for each).
- [x] **Optional external embedder**: When `EMBEDDING_SERVICE_URL` is set, use HTTP `/embed` API (bge) for query + document embedding; else keep SentenceTransformers. Wired into `PipelineManager`, indexing, and S3 migration.
- [x] **Paper metadata**: Optional fields when indexing: `year`, `journal`, `design`, `population`, `country`, `doi`. Pass in `meta` to `index_file_with_meta`; stored in `doc.meta` (pgvector keeps meta).

---

## Phase 2 – Agents in research flow

- [x] **Evidence Extractor agent**: Before synthesis (phase 2 only), call Qwen with prompt to extract OR/RR/HR, IC95, p-values, N, design from retrieved chunks → structured JSON. Injected into synthesizer context via `build_academic_messages(evidence_extracts=..., bias_audit=...)`.
- [x] **Bias Auditor agent**: Call Qwen with prompt to evaluate study type, bias, methodology → structured output. Injected into synthesizer context.
- [x] **Clinical Translator step**: After synthesis, if `MED42_API_URL` set and phase 2, call Med42 to produce "Implicaciones clínicas"; appended to report.
- [x] **Vision override**: If `QWEN_VL_API_URL` set, use it for `analyze_image` (OpenAI-compatible `/chat/completions` with image_url) instead of Ollama.

---

## Phase 3 – PDF pipeline & collections

- [ ] **Docling pipeline**: Optional path for PDF ingestion: Docling → structured JSON (text, tables, figures). Chunk text and tables; store with collection-like metadata (`papers_text`, `tables`). Figures: store references or describe via Qwen2.5-VL later.
- [ ] **Scanned PDF**: Path: page image → Qwen2.5-VL → extract text → embed → store.
- [ ] **Qdrant (optional)**: Migrate or add Qdrant alongside pgvector with collections `papers_text`, `figures`, `tables`, `clinical_guidelines` and same metadata schema. Keep pgvector as default for minimal infra.

---

## Phase 4 – Quality control & routing

- [ ] **Citation control**: Enforce chunk IDs in responses; separate “evidence” vs “interpretation” in prompts; flag uncertainty when appropriate; reject unsourced claims in post-processing or prompts.
- [ ] **Routing**: By input type (image / PDF / text) and question type (clinical vs research) to choose Evidence Extractor → Bias Auditor → Synthesizer → Clinical Translator and/or Visual Interpreter.

---

## Phase 5 – Scale & optional UI

- [ ] **LibreChat**: Optional integration with agent endpoints for power users.
- [ ] **Cost & monitoring**: Track token usage per model (OpenScholar, Med42, Qwen-VL, Qwen text) for cost optimization.

---

## Current status (updated as we go)

| Phase | Status | Notes |
|-------|--------|------|
| 1 | Done | Config, external embedder, paper meta |
| 2 | Done | Evidence Extractor, Bias Auditor, Med42, Qwen-VL vision |
| 3 | Pending | Docling + Qdrant optional |
| 4 | Pending | Citation + routing |
| 5 | Pending | Optional |
