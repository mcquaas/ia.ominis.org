"""
Pydantic schemas for the SINBA Cubes Agent API.
"""

from typing import Optional

from pydantic import BaseModel


class CubeQueryRequest(BaseModel):
    """Request to query a SINBA cube with natural language."""
    question: str
    cube_id: str = "cubosaeh2025prod_plataforma"
    # Optional: specify a pre-built MDX query instead of using LLM
    mdx_query: str = ""
    # Optional: override XMLA endpoint (for custom proxy setups)
    xmla_url: str = ""
    # Max rows to return
    max_rows: int = 500


class CubeQueryResponse(BaseModel):
    """Response from a SINBA cube query."""
    success: bool
    cube_id: str
    cube_name: str = ""
    mdx_query: str = ""
    columns: list[str] = []
    rows: list[dict] = []
    row_count: int = 0
    error: str = ""
    natural_language_summary: str = ""


class CubeListResponse(BaseModel):
    """Response listing all discovered SINBA cubes."""
    cubes: list[dict]
    total: int


class CubeMetadataResponse(BaseModel):
    """Response with full metadata for a single cube."""
    cube_id: str
    name: str = ""
    title: str = ""
    category: str = ""
    year: str = ""
    url: str = ""
    is_preliminary: bool = False
    publication_date: str = ""
    info_cutoff_date: str = ""
    connection: dict = {}
    dimensions: list[dict] = []
    measures: list[dict] = []


class CubeConnectionTestResponse(BaseModel):
    """Response from testing XMLA connection to a cube."""
    connected: bool
    server: str = ""
    catalog: str = ""
    cube_name: str = ""
    error: str = ""
    datasources: list[dict] = []


class CubeExtractRequest(BaseModel):
    """Request to extract data from a cube and index into RAG."""
    cube_id: str
    mdx_query: str = ""
    xmla_url: str = ""
    # Category tag for RAG documents
    category: str = "sinba-cubo"
    # Title prefix for indexed documents
    title_prefix: str = ""


class MDXTemplateRequest(BaseModel):
    """Request to build MDX from a predefined template."""
    template: str  # e.g., 'total_by_state', 'top_n'
    cube_id: str
    params: dict[str, str] = {}
