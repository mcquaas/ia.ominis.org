# Ominis IA — Orchestration (HayStack)

This document summarizes the architecture implemented per *Arquitectura Ia Ominis – Brief Para Agente*. HayStack (backend-haystack) is the orchestrator; the user chooses **where to search** (Ominis, PubMed, Web) and **whether to run Research**, but **not which models** — the system optimizes that.

## Flow

1. **Query Interpreter / Metadata Intent Mapper (Qwen)**  
   First step: map the user query to a structured intent:
   - `retrieval_constraints` (institucion, tipo_documento, dominio_salud, territorio, vigencia)
   - `depth`: shallow | standard | deep
   - `needs_pubmed`, `clinical_risk` (low | medium | high), `needs_long_context`

2. **Structured RAG retrieval (filtered)**  
   - The orchestrator defines **retrieval_constraints** (institucion, tipo_documento, dominio_salud, territorio, vigencia). Only documents whose taxonomy matches these constraints are used.
   - RAG requests use **depth** and constraints to request enough candidates (larger top_k when constraints exist) so that after the in-memory taxonomy filter there are still enough relevant docs.
   - Evidence Pack format: each chunk includes source (Document – Institution – Year) and metadata.

3. **Primary Reasoner**  
   - **Chat**: Qwen (Ominis 2.0) synthesizes from evidence.
   - **Research**: OpenScholar 8K (default) or 128K when rules require it.

4. **Research model selection (8K vs 128K)**  
   Backend decides; user does not choose.  
   **128K** is used only when all are true:
   - `n_docs ≥ 15`
   - `needs_long_context` from intent
   - Either `tipo_documento` includes `evaluacion` or `articulo_cientifico`, or temporal range > 10 years  
   **128K** can be turned off globally via `OPENSCHOLAR_128K_ENABLED=false` (e.g. to save GPU or for certain users/moments).

5. **Clinical Validator (BioMistral, Ominis-2.0-clinic)**  
   **Any clinical response must be validated by BioMistral.** The validator runs when:
   - Intent/documents: `clinical_risk` ≠ low, or `tipo_documento` includes `guia_clinica`/`protocolo`, or document taxonomy has `funcion_salud` (tratamiento/diagnóstico), or
   - Content: the question or the answer contains clinical signals (e.g. dosis, tratamiento, diagnóstico, medicamento, síntomas, contraindicación).
   Output is used to append a disclaimer (and optionally warnings); not shown as a separate step to the user.

6. **Synthesis**  
   Final answer is always produced by the orchestrator/reasoner; clinical validator only adds disclaimers when needed.

## Degradation

- **Qwen unavailable**: Service degraded; complex requests may be rejected.
- **OpenScholar 128K unavailable**: Use 8K, limit depth; frontend can show a degradation message.
- **OpenScholar 8K unavailable**: Fallback to Qwen for limited synthesis; response marked as preliminary.
- **BioMistral unavailable** with high clinical risk: Only allow answers when `clinical_risk` is low, or add a strong disclaimer.

## User-facing options

- **Sources**: Ominis (RAG), PubMed, Web (toggles).
- **Mode**: Normal chat vs **Investigación** (research).
- **Models**: Not selectable; backend chooses Qwen, BioMistral (validator), OpenScholar 8K/128K.

## Config (backend-haystack)

- `OPENSCHOLAR_128K_ENABLED`: Set to `false` to never use 128K (e.g. save GPU).
- Intent mapper, retrieval filters, and research model decision are in `app/rag/intent.py`; clinical validator in `app/rag/clinical_validator.py`.

## Connection / report not finishing

If research streams disconnect with "Connection error" and the report never completes:

1. **Nginx**: The default `proxy_read_timeout` (120s) closes the stream after 2 minutes. Run `infrastructure/20d-backend-nginx-long-timeout.sh` to set it to 600s so long reports (5+ min) can complete.
2. **Timeouts**: Backend allows up to ~5 min for report generation (8K) and ~5.5 min (128K). If OpenScholar or the network is slow, the user may still see a timeout; suggest narrowing the scope or retrying.
