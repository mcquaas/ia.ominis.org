"""
Pydantic schemas for admin endpoints.
Matches the frontend's expected types (RagSource, SystemStats, QueryStats).
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


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


class RAGSourceUpdate(BaseModel):
    title: Optional[str] = None
    sourceType: Optional[str] = None
    sourceUrl: Optional[str] = None
    status: Optional[str] = None
    content: Optional[str] = None
    category: Optional[str] = None
    language: Optional[str] = None


# --- System Stats schemas ---

class SystemStatsOut(BaseModel):
    totalSources: int = 0
    indexedSources: int = 0
    totalChunks: int = 0
    modelVersion: str = "ominis-2.0"
    modelStatus: str = "active"
    cpuServerStatus: str = "unknown"
    gpuServerStatus: str = "unknown"
    totalQueries24h: int = 0
    totalQueriesWeek: int = 0
    totalQueriesMonth: int = 0
    errorRate24h: float = 0.0
    lastHealthCheck: Optional[str] = None


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


# --- Pagination ---

class PaginationMeta(BaseModel):
    total: int


class RAGSourceListResponse(BaseModel):
    data: list[RAGSourceOut]
    meta: dict
