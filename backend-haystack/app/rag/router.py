"""
RAG query routes with SSE streaming support and multi-model selection.

SSE event format (unchanged):
  data: {"type": "status", "message": "..."}\n\n
  data: {"type": "chunk", "text": "..."}\n\n
  data: {"type": "sources", "sources": [...]}\n\n
  data: {"type": "done", "answer": "...", "sources": [...]}\n\n
"""

import asyncio
import json
import logging
import time
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from haystack.dataclasses import StreamingChunk

from app.config import DEFAULT_MODEL_ID, get_model_config, get_settings
from app.rag.pipeline import (
    SYSTEM_PROMPT,
    get_pipeline_manager,
    get_rag_pipeline,
)
from app.rag.document_store import get_document_store

logger = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter(tags=["query"])


# --- Request/Response schemas ---

class HistoryMessage(BaseModel):
    role: str
    content: str


class QueryRequest(BaseModel):
    question: str
    history: list[HistoryMessage] = []
    image: Optional[str] = None  # Base64 encoded image (reserved for future use)
    model: Optional[str] = None  # Model ID (e.g. "ominis-2.0", "falcon-40b-instruct")
    rag_search: bool = True
    web_search: bool = True
    pubmed_search: bool = True
    num_sources: int = 5


class QueryResponse(BaseModel):
    answer: str
    sources: list[dict]
    query: str
    model: str  # Which model actually generated the answer


# --- SSE Helpers ---

def sse_event(data: dict) -> str:
    """Format a dict as an SSE data line."""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


# --- Model listing endpoint ---

@router.get("/models")
async def list_models():
    """
    List all available LLM models.
    Returns model IDs, display names, descriptions, and which is default.
    """
    manager = get_pipeline_manager()
    return {"models": manager.available_models, "default": DEFAULT_MODEL_ID}


# --- Streaming endpoint ---

@router.post("/query-stream")
async def query_stream(body: QueryRequest, request: Request):
    """
    Streaming RAG query endpoint.
    Accepts an optional `model` field to select the LLM.
    Returns Server-Sent Events matching the existing GPU API format.
    """
    # Resolve model
    manager = get_pipeline_manager()
    model_id = manager.get_model_id(body.model)
    model_cfg = get_model_config(model_id)

    async def event_generator():
        start_time = time.time()
        full_answer = ""
        sources_list = []

        try:
            yield sse_event({
                "type": "status",
                "message": f"Buscando información relevante...",
                "model": model_id,
            })

            pipeline = manager.get_pipeline(model_id)

            # Step 1: Embed query and retrieve documents
            text_embedder = pipeline.get_component("text_embedder")
            retriever = pipeline.get_component("retriever")

            embed_result = text_embedder.run(text=body.question)
            query_embedding = embed_result["embedding"]

            retrieval_result = retriever.run(
                query_embedding=query_embedding,
                top_k=body.num_sources,
            )
            documents = retrieval_result.get("documents", [])

            sources_list = [
                {
                    "title": doc.meta.get("title", "Sin título"),
                    "url": doc.meta.get("url", ""),
                    "score": round(doc.score or 0.0, 4),
                }
                for doc in documents
            ]

            if sources_list:
                yield sse_event({"type": "sources", "sources": sources_list})

            yield sse_event({
                "type": "status",
                "message": f"Generando respuesta con {model_cfg.display_name}...",
            })

            # Step 2: Build the prompt
            prompt_builder = pipeline.get_component("prompt_builder")
            prompt_result = prompt_builder.run(
                documents=documents,
                question=body.question,
                system_prompt=SYSTEM_PROMPT,
                history=[msg.model_dump() for msg in body.history] if body.history else [],
            )
            prompt_text = prompt_result["prompt"]

            # Step 3: Stream generation via Ollama
            chunk_queue: asyncio.Queue[Optional[str]] = asyncio.Queue()

            def streaming_callback(chunk: StreamingChunk):
                text = chunk.content
                if text:
                    chunk_queue.put_nowait(text)

            generator = pipeline.get_component("generator")

            async def run_generator():
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    None,
                    lambda: generator.run(
                        prompt=prompt_text,
                        streaming_callback=streaming_callback,
                    ),
                )
                await chunk_queue.put(None)
                return result

            gen_task = asyncio.create_task(run_generator())

            while True:
                try:
                    token = await asyncio.wait_for(chunk_queue.get(), timeout=120.0)
                except asyncio.TimeoutError:
                    yield sse_event({"type": "error", "message": "Generation timed out"})
                    break

                if token is None:
                    break

                full_answer += token
                yield sse_event({"type": "chunk", "text": token})

            await gen_task

            elapsed_ms = int((time.time() - start_time) * 1000)
            yield sse_event({
                "type": "done",
                "answer": full_answer,
                "sources": sources_list,
                "model": model_id,
                "elapsed_ms": elapsed_ms,
            })

            asyncio.create_task(
                _log_query(
                    question=body.question,
                    answer=full_answer,
                    sources=sources_list,
                    elapsed_ms=elapsed_ms,
                    model_used=model_id,
                    rag_search=body.rag_search,
                    web_search=body.web_search,
                    pubmed_search=body.pubmed_search,
                )
            )

        except Exception as e:
            logger.error(f"Streaming error: {e}", exc_info=True)
            yield sse_event({"type": "error", "message": str(e)})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# --- Non-streaming endpoint ---

@router.post("/query", response_model=QueryResponse)
async def query(body: QueryRequest):
    """
    Non-streaming RAG query endpoint.
    Accepts an optional `model` field to select the LLM.
    """
    manager = get_pipeline_manager()
    model_id = manager.get_model_id(body.model)

    start_time = time.time()
    pipeline = manager.get_pipeline(model_id)

    result = pipeline.run(
        {
            "text_embedder": {"text": body.question},
            "retriever": {"top_k": body.num_sources},
            "prompt_builder": {
                "question": body.question,
                "system_prompt": SYSTEM_PROMPT,
                "history": [msg.model_dump() for msg in body.history] if body.history else [],
            },
        }
    )

    replies = result.get("generator", {}).get("replies", [])
    answer = replies[0] if replies else "No se pudo generar respuesta."

    documents = result.get("retriever", {}).get("documents", [])
    sources = [
        {
            "title": doc.meta.get("title", "Sin título"),
            "url": doc.meta.get("url", ""),
            "score": round(doc.score or 0.0, 4),
        }
        for doc in documents
    ]

    elapsed_ms = int((time.time() - start_time) * 1000)

    asyncio.create_task(
        _log_query(
            question=body.question,
            answer=answer,
            sources=sources,
            elapsed_ms=elapsed_ms,
            model_used=model_id,
            rag_search=body.rag_search,
            web_search=body.web_search,
            pubmed_search=body.pubmed_search,
        )
    )

    return QueryResponse(answer=answer, sources=sources, query=body.question, model=model_id)


# --- Query logging helper ---

async def _log_query(
    question: str,
    answer: str,
    sources: list[dict],
    elapsed_ms: int,
    model_used: str = "",
    rag_search: bool = True,
    web_search: bool = False,
    pubmed_search: bool = False,
    user_id: Optional[int] = None,
    api_key_id: Optional[int] = None,
):
    """Log a query to the database asynchronously."""
    try:
        from app.database import async_session
        from app.admin.models import QueryLog

        async with async_session() as db:
            log = QueryLog(
                question=question,
                answer=answer,
                sources_used=json.dumps(sources, ensure_ascii=False),
                model_used=model_used or settings.ollama_model,
                response_time_ms=elapsed_ms,
                user_id=user_id,
                api_key_id=api_key_id,
                rag_search=rag_search,
                web_search=web_search,
                pubmed_search=pubmed_search,
            )
            db.add(log)
            await db.commit()
    except Exception as e:
        logger.error(f"Failed to log query: {e}")
