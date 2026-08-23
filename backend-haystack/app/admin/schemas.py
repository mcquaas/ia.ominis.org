"""
Pydantic schemas for admin endpoints.
Matches the frontend's expected types (RagSource, SystemStats, QueryStats).
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


# --- Taxonomía para investigadores ---
TaxonomyDict = dict[str, list[str]]


# --- RAG Source schemas ---

class RAGSourceOut(BaseModel):
    id: int
    title: str
    slug: str
    sourceType: str
    status: str
    content: Optional[str] = None
    sourceUrl: Optional[str] = None
    category: Optional[str] = None
    language: Optional[str] = "es"
    description: Optional[str] = None
    publisher: Optional[str] = None
    documentDate: Optional[str] = None
    taxonomy: Optional[TaxonomyDict] = None
    chunksCount: int = 0
    lastIndexedAt: Optional[str] = None
    indexingError: Optional[str] = None
    createdAt: str
    updatedAt: str

    model_config = {"from_attributes": True}


class RAGSourceCreate(BaseModel):
    title: str
    slug: Optional[str] = None
    sourceType: str = "webpage"
    sourceUrl: Optional[str] = None
    content: Optional[str] = None
    category: Optional[str] = None
    language: str = "es"
    taxonomy: Optional[TaxonomyDict] = None


class RAGSourceUpdate(BaseModel):
    title: Optional[str] = None
    sourceType: Optional[str] = None
    sourceUrl: Optional[str] = None
    status: Optional[str] = None
    content: Optional[str] = None
    category: Optional[str] = None
    language: Optional[str] = None
    taxonomy: Optional[TaxonomyDict] = None


# --- Analytical query (SAV/Parquet statistics) ---

class AnalyticalQueryRequest(BaseModel):
    variable: str
    statistic: str = "mean"  # mean, sum, count, min, max
    group_by: Optional[str] = None
    weight_var: Optional[str] = None


# --- File Upload schemas ---

class FileUploadResponse(BaseModel):
    message: str
    sourceId: int
    chunksCount: int
    status: str


# --- Batch URLs (multiple URLs + optional crawl) ---

class UrlsBatchRequest(BaseModel):
    urls: list[str]
    crawl: bool = False
    category: Optional[str] = None


class UrlsBatchResponse(BaseModel):
    queued: int
    message: str


# --- Scrape schemas ---

class ScrapeUrlRequest(BaseModel):
    url: str
    category: str = ""
    language: str = "es"


class ScrapedPdfItem(BaseModel):
    title: str
    pdfUrl: str
    sourcePage: str


class ScrapedFileItem(BaseModel):
    """Unified item for PDF, CSV, XLS, XLSX from scrape."""
    title: str
    fileUrl: str
    sourcePage: str
    format: str = "pdf"  # pdf, csv, xls, xlsx


class ScrapePreviewResponse(BaseModel):
    url: str
    totalPdfs: int
    pdfs: list[ScrapedPdfItem]
    totalFiles: int = 0
    files: list[ScrapedFileItem] = []  # PDF + CSV + XLS + XLSX when using scrape-files


class ScrapeIndexRequest(BaseModel):
    url: str
    category: str = ""
    language: str = "es"
    pdfs: list[ScrapedPdfItem] | None = None  # legacy: PDF-only
    files: list[ScrapedFileItem] | None = None  # unified: PDF/CSV/XLS/XLSX with format


class ScrapeIndexResponse(BaseModel):
    message: str
    totalQueued: int
    sources: list[dict]


# --- Document/Chunk schemas ---

class ChunkOut(BaseModel):
    id: str
    contentPreview: str
    title: Optional[str] = None
    url: Optional[str] = None
    sourceType: Optional[str] = None
    sourceId: Optional[int] = None

    model_config = {"from_attributes": True}


class ChunkListResponse(BaseModel):
    data: list[ChunkOut]
    meta: dict


# --- Store Stats schemas ---

class StoreStatsOut(BaseModel):
    totalDocuments: int = 0
    embeddingModel: str = ""
    embeddingDimension: int = 0
    storageType: str = "pgvector (PostgreSQL)"


# --- System Stats schemas ---

class SystemStatsOut(BaseModel):
    totalSources: int = 0
    indexedSources: int = 0
    totalChunks: int = 0
    modelVersion: str = "ominis-2.0"
    modelStatus: str = "active"
    cpuServerStatus: str = "unknown"
    gpuServerStatus: str = "unknown"
    totalQueries1h: int = 0
    totalQueries24h: int = 0
    totalQueriesWeek: int = 0
    totalQueriesMonth: int = 0
    errorRate24h: float = 0.0
    lastHealthCheck: Optional[str] = None


class QuerySeriesPoint(BaseModel):
    bucketStart: str
    count: int


class QuerySeriesOut(BaseModel):
    last7Days: list[QuerySeriesPoint]
    last30Days: list[QuerySeriesPoint]
    last12Weeks: list[QuerySeriesPoint]
    last12Months: list[QuerySeriesPoint]


# --- Query Stats schemas ---

class QueryStatsOut(BaseModel):
    period: str
    startDate: str
    endDate: str
    total: int = 0
    successful: int = 0
    failed: int = 0
    successRate: float = 0.0
    avgResponseTimeMs: float = 0.0
    totalTokens: int = 0
    byEndpoint: dict = {"query": 0, "query-gpu": 0}


# --- Source Stats schemas ---

class SourceStatsOut(BaseModel):
    total: int = 0
    byStatus: dict = {"indexed": 0, "pending": 0, "processing": 0, "failed": 0}
    totalChunks: int = 0


# --- Dataset Scrape schemas ---

class DatasetPreviewRequest(BaseModel):
    url: str


class DatasetResourceItem(BaseModel):
    title: str
    description: str = ""
    url: str
    format: str = ""
    resourceId: str = ""
    sourcePage: str = ""


class DatasetPreviewResponse(BaseModel):
    pageTitle: str = ""
    pageMetadata: dict = {}
    totalResources: int = 0
    resources: list[DatasetResourceItem] = []


class DatasetIndexRequest(BaseModel):
    url: str
    category: str = ""
    language: str = "es"
    pageTitle: str = ""
    pageMetadata: dict = {}
    resources: list[DatasetResourceItem] | None = None


class DatasetIndexResponse(BaseModel):
    message: str
    totalQueued: int = 0
    sources: list[dict] = []


# --- Tainacan Import schemas ---

class TainacanPreviewResponse(BaseModel):
    totalItems: int = 0
    indexableFiles: int = 0
    metadataOnly: int = 0
    byExtension: dict = {}


class TainacanImportRequest(BaseModel):
    category: str = "tainacan"
    language: str = "es"
    maxItems: Optional[int] = None
    skipExisting: bool = True


class TainacanImportResponse(BaseModel):
    message: str
    totalQueued: int = 0
    skipped: int = 0


# --- datos.gob.mx (CKAN) metadata import ---


class DatosGobMxPreviewResponse(BaseModel):
    totalPackages: int = 0
    groupName: str = "salud"
    groupTitle: str = ""
    totalResourcesSample: int = 0
    resourceFormatsSample: dict[str, int] = {}
    sampleTitles: list[str] = []


class DatosGobMxImportRequest(BaseModel):
    category: str = "datos.gob.mx"
    language: str = "es"
    maxItems: Optional[int] = None
    skipExisting: bool = True
    group: str = "salud"


class DatosGobMxImportResponse(BaseModel):
    message: str
    totalQueued: int = 0
    skipped: int = 0


class BatchReindexRequest(BaseModel):
    onlyWithTaxonomy: bool = True  # Only reindex sources that have taxonomy (to propagate to chunks)
    maxConcurrent: int = 3


class BatchReindexResponse(BaseModel):
    message: str
    queued: int
    skipped: int = 0


# --- Pagination ---

class PaginationMeta(BaseModel):
    total: int


class RAGSourceListResponse(BaseModel):
    data: list[RAGSourceOut]
    meta: dict


# --- LLM model config (dashboard: assignments, prompts, version, params) ---

class LLMModelConfigOut(BaseModel):
    model_id: str
    display_name: str
    version_label: str = ""
    description: str = ""
    backend_type: str  # "ollama" | "openai" | "anthropic"
    llm_provider: str = "ominis"  # ominis | openai | google | deepseek | claude
    provider_keys_present: dict[str, bool] = {}
    backend_model: str
    backend_url_override: Optional[str] = None
    system_prompt: Optional[str] = None
    temperature: Optional[float] = None
    num_predict: Optional[int] = None
    extra_params: Optional[dict] = None
    is_default: bool = False
    overridden: list[str] = []  # keys that are set in DB (saved overrides)
    available_for_researcher: Optional[bool] = None  # None = use default (True)


class LLMModelConfigUpdate(BaseModel):
    display_name: Optional[str] = None
    version_label: Optional[str] = None
    description: Optional[str] = None
    backend_model: Optional[str] = None
    backend_url_override: Optional[str] = None
    system_prompt: Optional[str] = None
    temperature: Optional[float] = None
    num_predict: Optional[int] = None
    extra_params: Optional[dict] = None
    is_default: Optional[bool] = None
    available_for_researcher: Optional[bool] = None
    llm_provider: Optional[str] = None
    provider_credentials_patch: Optional[dict[str, str]] = None


class LLMListModelsRequest(BaseModel):
    model_id: str
    provider_id: str
    api_token: Optional[str] = None


class VisionLlmConfigOut(BaseModel):
    llm_provider: str = "ominis"
    backend_model: str = ""
    ollama_url: str = ""
    openai_base_url: str = ""
    provider_keys_present: dict[str, bool] = {}


class VisionLlmConfigUpdate(BaseModel):
    llm_provider: Optional[str] = None
    backend_model: Optional[str] = None
    ollama_url: Optional[str] = None
    openai_base_url: Optional[str] = None
    provider_credentials_patch: Optional[dict[str, str]] = None
