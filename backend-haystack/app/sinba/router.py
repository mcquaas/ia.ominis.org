"""
SINBA Cubes Agent — FastAPI router for querying Mexico's health OLAP cubes.

Endpoints:
  GET  /v1/sinba/cubes              — List all discovered SINBA cubes
  GET  /v1/sinba/cubes/{cube_id}    — Get metadata for a specific cube
  POST /v1/sinba/query              — Query a cube (natural language or MDX)
  POST /v1/sinba/test-connection    — Test XMLA connection to a cube
  POST /v1/sinba/extract            — Extract cube data and index into RAG
  POST /v1/sinba/mdx-template       — Build MDX from a predefined template
  GET  /v1/sinba/catalog            — Discover and catalog all cubes (slow)
"""

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from haystack.dataclasses import ChatMessage

from app.sinba.cube_parser import (
    CubeMetadata,
    catalog_all_cubes,
    discover_cube_pages,
    get_cube_metadata,
)
from app.sinba.xmla_client import (
    SINBAProxyClient,
    SINBAXmlaClient,
    XmlaConnectionConfig,
    build_client_from_connection,
    build_proxy_client,
)
from app.sinba.mdx_builder import (
    build_mdx_prompt,
    build_template_mdx,
    extract_mdx_from_response,
)
from app.sinba.schemas import (
    CubeConnectionTestResponse,
    CubeExtractRequest,
    CubeListResponse,
    CubeMetadataResponse,
    CubeQueryRequest,
    CubeQueryResponse,
    MDXTemplateRequest,
)
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(prefix="/sinba", tags=["sinba-cubes"])

# In-memory cache of cube metadata (populated on demand)
_cube_cache: dict[str, CubeMetadata] = {}
_cube_pages_cache: list[dict] = []


async def _ensure_cube_pages() -> list[dict]:
    """Ensure the cube pages index is loaded."""
    global _cube_pages_cache
    if not _cube_pages_cache:
        _cube_pages_cache = await discover_cube_pages()
    return _cube_pages_cache


async def _get_or_fetch_cube(cube_id: str) -> Optional[CubeMetadata]:
    """Get cube metadata from cache or fetch from SINBA."""
    if cube_id in _cube_cache:
        return _cube_cache[cube_id]

    metadata = await get_cube_metadata(cube_id)
    if metadata:
        _cube_cache[cube_id] = metadata
    return metadata


def _get_proxy_client() -> SINBAProxyClient:
    """Get the .NET XMLA proxy client (localhost:5001)."""
    return build_proxy_client(settings.sinba_xmla_url or "http://127.0.0.1:5001")


async def _generate_mdx_with_llm(question: str, metadata: CubeMetadata) -> str:
    """Use the LLM to generate an MDX query from a natural language question."""
    from app.rag.pipeline import get_pipeline_manager

    pm = get_pipeline_manager()
    generator = pm.get_generator()

    messages = build_mdx_prompt(question, metadata)
    result = generator.run(messages=messages)

    if result and "replies" in result:
        replies = result["replies"]
        if replies:
            raw_text = replies[0].text if hasattr(replies[0], "text") else str(replies[0])
            return extract_mdx_from_response(raw_text)

    return ""


async def _generate_summary_with_llm(
    question: str, mdx_result: dict, metadata: CubeMetadata
) -> str:
    """Use the LLM to summarize query results in natural language."""
    from app.rag.pipeline import get_pipeline_manager

    pm = get_pipeline_manager()
    generator = pm.get_generator()

    # Build a concise data summary for the LLM
    rows_preview = mdx_result.get("rows", [])[:20]
    columns = mdx_result.get("columns", [])
    row_count = mdx_result.get("row_count", 0)

    data_text = f"Columnas: {', '.join(columns)}\n"
    data_text += f"Total filas: {row_count}\n"
    data_text += "Primeras filas:\n"
    for row in rows_preview:
        data_text += "  " + " | ".join(f"{k}: {v}" for k, v in row.items()) + "\n"

    messages = [
        ChatMessage.from_system(
            "Eres un analista de datos de salud de México. "
            "Responde en español mexicano de forma clara y concisa. "
            "Resume los datos proporcionados respondiendo la pregunta del usuario."
        ),
        ChatMessage.from_user(
            f"Cubo OLAP: {metadata.name} ({metadata.category})\n\n"
            f"Datos obtenidos:\n{data_text}\n\n"
            f"Pregunta: {question}\n\n"
            f"Proporciona un resumen claro de los datos:"
        ),
    ]

    result = generator.run(messages=messages)
    if result and "replies" in result:
        replies = result["replies"]
        if replies:
            return replies[0].text if hasattr(replies[0], "text") else str(replies[0])

    return ""


# --- Endpoints ---


@router.get("/proxy-status")
async def proxy_status():
    """
    Check if the XMLA proxy is reachable.
    Returns 200 if healthy, 503 if proxy is down or not configured.
    """
    url = settings.sinba_xmla_url or "http://127.0.0.1:5001"
    if not url or url.strip() == "":
        return {
            "healthy": False,
            "error": "SINBA_XMLA_URL not configured. The XMLA proxy must be running to query cubes.",
            "hint": "Deploy the .NET proxy (see xmla-proxy/) or configure SINBA_XMLA_URL.",
        }
    proxy = build_proxy_client(url)
    try:
        result = await proxy.health_check()
        if result.get("status") == "healthy":
            return {"healthy": True, "proxy_url": url}
        return {
            "healthy": False,
            "error": result.get("error", "Proxy unhealthy"),
            "proxy_url": url,
        }
    finally:
        await proxy.close()


@router.get("/cubes", response_model=CubeListResponse)
async def list_cubes():
    """
    List all available SINBA cube pages discovered from the index.
    This is a lightweight call that only parses the index page.
    """
    pages = await _ensure_cube_pages()
    return CubeListResponse(
        cubes=pages,
        total=len(pages),
    )


@router.get("/cubes/{cube_id}", response_model=CubeMetadataResponse)
async def get_cube_detail(cube_id: str):
    """
    Get full metadata for a specific SINBA cube.
    Fetches and parses the cube HTML page to extract OWC configuration,
    including connection details, dimensions, and measures.
    """
    metadata = await _get_or_fetch_cube(cube_id)
    if not metadata:
        raise HTTPException(
            status_code=404,
            detail=f"Cube '{cube_id}' not found or has no OWC data. "
            f"Try listing cubes with GET /v1/sinba/cubes to see available IDs.",
        )

    data = metadata.to_dict()
    return CubeMetadataResponse(**data)


@router.post("/query", response_model=CubeQueryResponse)
async def query_cube(request: CubeQueryRequest):
    """
    Query a SINBA cube using natural language or raw MDX.

    If `mdx_query` is provided, it is executed directly.
    Otherwise, the LLM generates an MDX query from the `question`.

    Requires an XMLA endpoint to be accessible (configure SINBA_XMLA_URL
    environment variable or pass `xmla_url` in the request).
    """
    # 1. Get cube metadata
    metadata = await _get_or_fetch_cube(request.cube_id)
    if not metadata:
        raise HTTPException(
            status_code=404,
            detail=f"Cube '{request.cube_id}' not found",
        )

    # 2. Get or generate MDX query
    mdx = request.mdx_query
    if not mdx:
        if not request.question:
            raise HTTPException(
                status_code=400,
                detail="Provide either 'question' or 'mdx_query'",
            )
        try:
            mdx = await _generate_mdx_with_llm(request.question, metadata)
        except Exception as e:
            logger.error(f"MDX generation failed: {e}")
            return CubeQueryResponse(
                success=False,
                cube_id=request.cube_id,
                cube_name=metadata.name,
                error=f"Failed to generate MDX query: {e}",
            )

    if not mdx:
        return CubeQueryResponse(
            success=False,
            cube_id=request.cube_id,
            cube_name=metadata.name,
            error="Could not generate a valid MDX query from the question",
        )

    # 3. Execute MDX via the .NET XMLA proxy
    proxy = _get_proxy_client()
    # Quick health check before long-running query
    health = await proxy.health_check()
    if health.get("status") != "healthy":
        err = health.get("error", "Proxy unreachable")
        return CubeQueryResponse(
            success=False,
            cube_id=request.cube_id,
            cube_name=metadata.name,
            mdx_query=mdx,
            error=f"XMLA proxy no disponible: {err}. "
            "El proxy debe estar en ejecución para consultar cubos SSAS.",
        )

    try:
        result = await proxy.execute_mdx(
            query=mdx,
            server=metadata.connection.server,
            catalog=metadata.connection.catalog,
            username=metadata.connection.user_id,
            password=metadata.connection.password,
        )

        # 4. Generate natural language summary if we have results
        summary = ""
        if result.success and request.question:
            try:
                summary = await _generate_summary_with_llm(
                    request.question, result.to_dict(), metadata
                )
            except Exception as e:
                logger.warning(f"Summary generation failed: {e}")

        rows = result.rows[:request.max_rows] if result.rows else []

        return CubeQueryResponse(
            success=result.success,
            cube_id=request.cube_id,
            cube_name=metadata.name,
            mdx_query=mdx,
            columns=result.columns,
            rows=rows,
            row_count=result.row_count,
            error=result.error,
            natural_language_summary=summary,
        )
    except Exception as e:
        return CubeQueryResponse(
            success=False,
            cube_id=request.cube_id,
            cube_name=metadata.name,
            mdx_query=mdx,
            error=str(e),
        )
    finally:
        await proxy.close()


@router.post("/test-connection", response_model=CubeConnectionTestResponse)
async def test_cube_connection(
    cube_id: str,
    xmla_url: str = "",
):
    """
    Test the XMLA connection to a SINBA cube's SSAS server.
    Returns connection status and discovered data sources.
    """
    metadata = await _get_or_fetch_cube(cube_id)
    if not metadata:
        raise HTTPException(status_code=404, detail=f"Cube '{cube_id}' not found")

    proxy = _get_proxy_client()
    try:
        # Test by discovering cubes in the catalog
        result = await proxy.discover(
            discover_type="cubes",
            server=metadata.connection.server,
            catalog=metadata.connection.catalog,
            username=metadata.connection.user_id,
            password=metadata.connection.password,
        )
        return CubeConnectionTestResponse(
            connected=result.success,
            server=metadata.connection.server,
            catalog=metadata.connection.catalog,
            cube_name=metadata.name,
            error=result.error,
            datasources=result.rows,
        )
    finally:
        await proxy.close()


@router.post("/extract")
async def extract_and_index(request: CubeExtractRequest):
    """
    Extract data from a SINBA cube and index it into the RAG document store.

    This endpoint executes an MDX query, converts the results into
    text chunks, and indexes them via the simple indexing pipeline
    (cleaner → splitter → embedder → writer) into pgvector for
    natural language querying via the main chat interface.
    """
    from app.rag.indexing import index_raw_text

    metadata = await _get_or_fetch_cube(request.cube_id)
    if not metadata:
        raise HTTPException(status_code=404, detail=f"Cube '{request.cube_id}' not found")

    # Use provided MDX or a default "get everything" query
    mdx = request.mdx_query
    if not mdx and metadata.measures:
        # Build a default query that gets all data
        measure_names = ", ".join(m.source_name for m in metadata.measures[:5])
        dim_name = metadata.dimensions[0].source_name if metadata.dimensions else ""
        if dim_name and measure_names:
            mdx = (
                f"SELECT NON EMPTY {{{measure_names}}} ON COLUMNS, "
                f"NON EMPTY {{{dim_name}.Members}} ON ROWS "
                f"FROM [{metadata.name}]"
            )

    if not mdx:
        raise HTTPException(
            status_code=400,
            detail="Could not build a default MDX query. Provide one via 'mdx_query'.",
        )

    # Execute MDX via proxy
    proxy = _get_proxy_client()
    try:
        result = await proxy.execute_mdx(
            query=mdx,
            server=metadata.connection.server,
            catalog=metadata.connection.catalog,
            username=metadata.connection.user_id,
            password=metadata.connection.password,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"XMLA query failed: {e}")
    finally:
        await proxy.close()

    if not result.success:
        raise HTTPException(status_code=502, detail=f"MDX query error: {result.error}")

    # Index data into pgvector using the existing indexing pipeline
    title_prefix = request.title_prefix or f"SINBA {metadata.name}"
    total_indexed = 0

    # Index a summary document
    summary_text = (
        f"Datos del cubo OLAP: {metadata.name}\n"
        f"Categoría: {metadata.category}\n"
        f"Catálogo: {metadata.connection.catalog}\n"
        f"Total de registros: {result.row_count}\n"
        f"Columnas: {', '.join(result.columns)}\n"
    )
    total_indexed += index_raw_text(
        content=summary_text,
        title=f"{title_prefix} - Resumen",
        url=metadata.url,
        source_type="sinba_cube",
        category=request.category,
    )

    # Index data rows in chunks
    chunk_size = 20  # rows per text chunk
    for i in range(0, len(result.rows), chunk_size):
        chunk_rows = result.rows[i : i + chunk_size]
        chunk_text = f"Datos de {metadata.name} (filas {i + 1}-{i + len(chunk_rows)}):\n"
        for row in chunk_rows:
            chunk_text += " | ".join(f"{k}: {v}" for k, v in row.items()) + "\n"

        total_indexed += index_raw_text(
            content=chunk_text,
            title=f"{title_prefix} - Datos {i + 1}-{i + len(chunk_rows)}",
            url=metadata.url,
            source_type="sinba_cube",
            category=request.category,
        )

    return {
        "success": True,
        "cube_id": metadata.cube_id,
        "cube_name": metadata.name,
        "rows_extracted": result.row_count,
        "documents_indexed": total_indexed,
    }


@router.post("/mdx-template")
async def build_mdx_from_template(request: MDXTemplateRequest):
    """
    Build an MDX query from a predefined template.

    Available templates:
      - total_by_state: Total {measure} by {dimension}
      - top_n: Top {n} by {measure} in {dimension}
      - total: Grand total of {measure}
      - cross_tab: Cross-tabulation of {dim1} × {dim2} for {measure}
    """
    metadata = await _get_or_fetch_cube(request.cube_id)
    if not metadata:
        raise HTTPException(status_code=404, detail=f"Cube '{request.cube_id}' not found")

    mdx = build_template_mdx(
        template_name=request.template,
        cube_name=metadata.name,
        params=request.params,
    )

    if not mdx:
        raise HTTPException(
            status_code=400,
            detail=f"Template '{request.template}' not found or missing parameters. "
            f"Available: total_by_state, top_n, total, cross_tab",
        )

    return {
        "template": request.template,
        "cube_id": request.cube_id,
        "cube_name": metadata.name,
        "mdx_query": mdx,
        "params": request.params,
    }


@router.get("/catalog")
async def full_catalog(max_cubes: int = Query(default=0, description="Max cubes to parse (0=all)")):
    """
    Discover and parse ALL SINBA cubes from the index.
    This is a slow operation that fetches every cube page.
    Results are cached for subsequent calls.
    """
    cubes = await catalog_all_cubes(max_cubes=max_cubes)

    # Cache results
    for cube in cubes:
        _cube_cache[cube.cube_id] = cube

    return {
        "total": len(cubes),
        "cubes": [c.to_dict() for c in cubes],
    }
