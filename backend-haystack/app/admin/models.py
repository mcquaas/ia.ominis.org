"""
Admin models: RAG Source metadata, Query Logs, System Stats.
"""

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB

from app.database import Base


class SourceStatus(str, enum.Enum):
    active = "active"
    inactive = "inactive"
    indexing = "indexing"
    error = "error"


class RAGSource(Base):
    __tablename__ = "rag_sources"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(255), nullable=False)
    slug = Column(String(255), unique=True, nullable=False, index=True)
    source_type = Column(String(50), nullable=False, default="webpage")
    source_url = Column(Text, nullable=True)
    status = Column(Enum(SourceStatus), nullable=False, default=SourceStatus.active)
    content = Column(Text, nullable=True)
    category = Column(String(100), nullable=True)
    language = Column(String(10), nullable=True, default="es")

    # LLM-generated metadata
    description = Column(Text, nullable=True)  # One-sentence description
    publisher = Column(String(255), nullable=True)  # Publishing organization
    document_date = Column(String(100), nullable=True)  # Date found on document

    # Researcher-oriented taxonomy (institucion, tipo_documento, dominio_salud, etc.)
    taxonomy = Column(JSONB, nullable=True)

    chunks_count = Column(Integer, default=0, nullable=False)
    last_indexed_at = Column(DateTime(timezone=True), nullable=True)
    indexing_error = Column(Text, nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def __repr__(self):
        return f"<RAGSource {self.title} status={self.status}>"


class QueryLog(Base):
    __tablename__ = "query_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=True)
    sources_used = Column(Text, nullable=True)  # JSON string
    model_used = Column(String(100), nullable=True)
    response_time_ms = Column(Integer, nullable=True)
    tokens_used = Column(Integer, nullable=True)
    tokens_per_second = Column(Float, nullable=True)
    user_id = Column(Integer, nullable=True)  # nullable for anonymous queries
    api_key_id = Column(Integer, nullable=True)

    rag_search = Column(Boolean, default=True)
    web_search = Column(Boolean, default=False)
    pubmed_search = Column(Boolean, default=False)

    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def __repr__(self):
        return f"<QueryLog q='{self.question[:50]}...'>"


class SystemStat(Base):
    """Singleton table for system-wide statistics."""

    __tablename__ = "system_stats"

    id = Column(Integer, primary_key=True, default=1)
    model_version = Column(String(50), nullable=True, default="ominis-2.0")
    model_status = Column(String(20), nullable=True, default="active")
    total_queries = Column(Integer, default=0)
    total_users = Column(Integer, default=0)
    total_sources = Column(Integer, default=0)
    total_chunks = Column(Integer, default=0)
    cpu_server_status = Column(String(20), nullable=True, default="unknown")
    gpu_server_status = Column(String(20), nullable=True, default="unknown")

    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class SiteConfig(Base):
    """Singleton: site-wide config (e.g. global banner message). id=1."""

    __tablename__ = "site_config"

    id = Column(Integer, primary_key=True, default=1)
    banner_message = Column(Text, nullable=True)  # Yellow notification at top of app (superadmin only to set)

    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class ChatDefaults(Base):
    """Singleton: default toggles for the chat (Investigación, Ominis/RAG, PubMed, Web). Applied when a user opens the chat."""

    __tablename__ = "chat_defaults"

    id = Column(Integer, primary_key=True, default=1)
    research_mode = Column(Boolean, default=False, nullable=False)
    rag_search = Column(Boolean, default=True, nullable=False)
    web_search = Column(Boolean, default=True, nullable=False)
    pubmed_search = Column(Boolean, default=True, nullable=False)
    openscholar_search = Column(Boolean, default=False, nullable=False)  # Semantic Scholar (default off)

    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class LLMModelConfig(Base):
    """
    Per-model overrides for chat LLMs (ominis-2.0, ominis-2.0-med, ominis-2.0-open, ominis-2.0-power).
    Which models exist is still defined by env; this table overrides display name, version, assignment, prompt, params.
    """
    __tablename__ = "llm_model_config"

    model_id = Column(String(80), primary_key=True)
    display_name = Column(String(255), nullable=True)
    version_label = Column(String(64), nullable=True)
    description = Column(Text(), nullable=True)
    backend_model = Column(String(255), nullable=True)
    backend_url_override = Column(String(512), nullable=True)
    system_prompt = Column(Text(), nullable=True)
    temperature = Column(Float(), nullable=True)
    num_predict = Column(Integer(), nullable=True)
    extra_params = Column(JSONB, nullable=True)
    is_default = Column(Boolean(), nullable=True)
    available_for_researcher = Column(Boolean(), nullable=True)  # SuperAdmin: allow researchers to use this model (default True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
