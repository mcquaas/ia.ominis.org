# IA Ominis Tools, Orchestration, Stack, and Dashboard Functions

## 1) Scope

This document summarizes:

- All current **search/retrieval tools** exposed in `ia.ominis.org`.
- How these tools are **orchestrated** in chat requests.
- The current **technical stack**.
- What functions are available in **Dashboard > RAG** and **Dashboard > Options**, plus the dedicated `/rag` management page.

It is based on the current implementation in `frontend/` and `backend-haystack/`.

## 2) Tool Inventory

## 2.1 Chat Tools (Plus Menu in `/c`)

These toggles are available in the chat `+` menu (`MainLayout`):

- `Ominis` -> indexed internal corpus (RAG).
- `PubMed` -> biomedical literature search.
- `Web` -> general web retrieval.
- `OpenScholar` -> academic evidence (Semantic Scholar pipeline).
- `Ensayos (Mexico)` -> ClinicalTrials.gov constrained to Mexico.
- `Directorio MX` -> doctor directory (Mexico, ingested profiles).
- `All.Can Mexico` -> patient/support organizations from All.Can Strapi.
- `Investigacion` mode -> research route (8K/128K path depending on availability and settings).

Notes:

- The three Mexico-specific tools (`clinical_trials`, `doctor_directory_mx`, `allcan_mexico`) are only effective for authenticated users.
- Chat can run with manual toggles or orchestration automation (`tool_automation`).

## 2.2 Standalone Tools Pages

User-facing pages under `/tools`:

- `/tools/clinical-trials` -> assisted ClinicalTrials flow.
- `/tools/directorio-mx` -> doctor directory search UI.
- `/tools/allcan` -> All.Can directory search + map UI.

Main index:

- `/tools` -> tool selector page.

## 2.3 Tool APIs (Frontend Proxy -> Backend)

- `POST /api/query-stream` -> proxies to backend `POST /v1/query-stream`.
- `POST /api/clinical-trials/assist` -> backend `POST /v1/clinical-trials/assist`.
- `GET /api/doctor-directory/search` -> backend `GET /v1/doctor-directory/search`.
- `GET /api/allcan-directory/search` -> backend `GET /v1/allcan-directory/search`.
- `GET /api/allcan-directory/facets` -> reads Strapi facets for filter dropdowns.

## 3) Orchestration: How Tools Are Activated

## 3.1 Request Flow

1. Frontend (`MainLayout`) builds a request with toggles:
   - `rag_search`, `web_search`, `pubmed_search`, `openscholar_search`
   - `clinical_trials_search`, `doctor_directory_search`, `allcan_search`
   - `research_mode`, `research_2_1`, `tool_automation`, `num_sources`, etc.
2. Frontend sends to `POST /api/query-stream`.
3. Next.js route forwards to backend `POST /v1/query-stream` as SSE.
4. Backend streams status/chunks/sources/done events back to UI.

## 3.2 Tool Planning Logic

In backend orchestration (`tool_orchestration.py` + `rag/router.py`):

- If turn is detected as conversation-only, retrieval tools are disabled.
- If not in research mode and `tool_automation=true`:
  - It computes a tool plan from:
    - intent mapper output (`tool_sources`), and
    - deterministic heuristics (regex/signals from the question).
  - It merges both and enforces at least one source (`ominis_rag` fallback).
  - It sends a transparent SSE status event with activated sources.
- Anonymous users are gated out from:
  - ClinicalTrials, Directorio MX, All.Can MX.

## 3.3 Source Gathering (Parallel)

`_gather_sources()` executes enabled backends in parallel:

- Ominis RAG:
  - vector retrieval (pgvector/Haystack embedder+retriever),
  - plus keyword fallback directly against source/chunk metadata.
- Web search.
- PubMed search.
- OpenScholar search.
- Optional Health Datastore retrieval (if enabled).
- ClinicalTrials.gov (keyword extraction -> API -> docs).
- Doctor Directory semantic retrieval from ingested profiles.
- All.Can semantic retrieval from Strapi organizations.

It can also run refined query variants and then merge all documents for synthesis/citation.

## 3.4 Response and Follow-up Hints

During stream completion:

- Backend returns `sources` and `sources_not_used`.
- Backend may return `suggested_add_tools`:
  - missing source suggestions ("Agregar"), or
  - deeper second-pass suggestions ("profundizar").
- Frontend can trigger follow-up runs with:
  - `tool_automation=false` (manual explicit activation),
  - optional `num_sources` increase for deeper retrieval.

## 4) Technical Stack

## 4.1 Frontend

- Framework: Next.js `16.1.6`
- UI: React `19.2.3`
- Language: TypeScript
- Styling: Tailwind CSS v4
- Maps: Leaflet + React Leaflet
- Pattern: Next.js app routes + server-side proxy routes to backend

## 4.2 Backend

- Framework: FastAPI
- ORM: SQLAlchemy async + Alembic migrations
- Core RAG/LLM pipeline: Haystack
- Vector store: pgvector on PostgreSQL
- Auth: JWT-based role system (researcher/developer/admin/superadmin)

Key libraries in use include:

- `haystack-ai`, `pgvector-haystack`, `sentence-transformers`
- `openai`, `anthropic`, `ollama-haystack`
- `httpx`, `aiohttp`
- `beautifulsoup4`, `trafilatura`, `pypdf`, `python-docx`
- `duckdb`, `pyarrow`, `pyreadstat`

## 4.3 Data/Source Integrations

- Internal indexed corpus (`rag_sources` + chunks in pgvector document store).
- ClinicalTrials.gov API v2.
- PubMed retrieval pipeline.
- OpenScholar/Semantic Scholar retrieval pipeline.
- All.Can Strapi (`api.allcan.mx`) for organizations.
- Mexico doctor directory ingestion from:
  - Top Doctors,
  - Doctoralia Mexico,
  - DoctorAnytime Mexico.
- Optional Health Datastore pipeline (nightly ingestion + retrieval checks).

## 5) Dashboard Functions (Focus: RAG and Options)

Dashboard tabs currently include:

- `overview`, `servers`, `llms`, `rag`, `users`, `options`.

## 5.1 Dashboard > RAG (DataStore tab)

Main functions:

- **Workers view**
  - Shows indexing responsibilities (API server background indexing vs external health worker).
- **Embeddings panel**
  - Shows document totals, embedding model, storage type (`pgvector`).
  - Link to `/rag` for full source management.
  - Health Datastore status and recent activity table.
- **DataStore access**
  - Direct entry to source management (`/rag`).
- **Doctor Directory scraping control**
  - Source selector (Top Doctors / Doctoralia / DoctorAnytime).
  - Max profiles and delay controls.
  - Start scrape run and monitor runs/stats.

## 5.2 Dashboard > Options

Default chat configuration for all users:

- `default_model` (e.g., Ominis 2.0 / Med / Research).
- `public_access_enabled` (guest access vs login required).
- `research_mode` default.
- `research_2_1` default.
- `rag_search` default.
- `pubmed_search` default.
- `web_search` default.
- `openscholar_search` default.

Superadmin-only:

- Global banner/notification management (`site-config`).

## 6) Dedicated `/rag` Page Functions (DataStore Management)

Role-gated (admin/developer). Major capabilities:

- Stats and taxonomy schema loading.
- Source ingestion modes:
  - file upload,
  - raw text,
  - URL(s) and optional crawl,
  - scrape files from a page (PDF/CSV/XLS/XLSX),
  - dataset preview/index,
  - Tainacan preview/import,
  - datos.gob.mx CKAN preview/import.
- Source operations:
  - list/filter/search/paginate,
  - taxonomy filtering,
  - reindex (single and batch),
  - classify taxonomy,
  - delete source,
  - view chunks.
- Data integrity utilities:
  - mark stuck indexing as failed,
  - reconcile status/counts with actual vectors.

## 7) Operational Notes

- Tool orchestration is intentionally hybrid:
  - user toggles + backend automation.
- Backend remains source-of-truth for permissions and final tool activation.
- Frontend displays orchestration transparency through streamed status events and tool suggestions.

