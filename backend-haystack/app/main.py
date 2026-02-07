"""
Ominis Health - Haystack Backend
FastAPI application entry point.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import init_db
from app.auth.router import router as auth_router
from app.api_keys.router import router as api_keys_router
from app.rag.router import router as rag_router
from app.admin.router import router as admin_router
from app.middleware.rate_limit import RateLimitMiddleware
from app.middleware.api_key_auth import APIKeyAuthMiddleware

logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown events."""
    logger.info("Starting Ominis Health Haystack Backend...")

    # Initialize database tables (use Alembic in production)
    if settings.debug:
        await init_db()

    # Initialize the RAG pipeline (loads document store, embeddings, etc.)
    from app.rag.pipeline import initialize_pipeline
    await initialize_pipeline()

    logger.info("Backend ready.")
    yield

    logger.info("Shutting down...")


app = FastAPI(
    title="Ominis Health API",
    description="Health research assistant powered by BioMistral + RAG via Haystack",
    version="2.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate limiting
app.add_middleware(RateLimitMiddleware)

# API key authentication for query endpoints
app.add_middleware(APIKeyAuthMiddleware)

# Routers
app.include_router(auth_router, prefix="/v1")
app.include_router(api_keys_router, prefix="/v1")
app.include_router(rag_router, prefix="/v1")
app.include_router(admin_router, prefix="/v1")


@app.get("/v1/health", tags=["system"])
async def health_check():
    """Public health check endpoint."""
    return {
        "status": "healthy",
        "service": "ominis-health-api",
        "version": "2.0.0",
    }
