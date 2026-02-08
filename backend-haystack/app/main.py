"""
Ominis Health - Agent Backend
FastAPI application entry point.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.database import init_db
from app.auth.router import router as auth_router
from app.api_keys.router import router as api_keys_router
from app.rag.router import router as rag_router
from app.admin.router import router as admin_router
from app.chat.router import router as chat_router
from app.feedback.router import router as feedback_router
from app.sinba.router import router as sinba_router
from app.auth.dependencies import get_current_user
from app.auth.models import RoleEnum, User
from app.middleware.rate_limit import RateLimitMiddleware
from app.middleware.api_key_auth import APIKeyAuthMiddleware

logger = logging.getLogger(__name__)
settings = get_settings()

# Roles allowed to view API docs
DOCS_ROLES = {RoleEnum.developer, RoleEnum.superadmin}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown events."""
    logger.info("Starting Ominis Agent...")

    # Initialize database tables (create_all is idempotent — safe in production)
    await init_db()

    # Initialize the RAG pipeline (loads document store, embeddings, etc.)
    from app.rag.pipeline import initialize_pipeline
    await initialize_pipeline()

    logger.info("Backend ready.")
    yield

    logger.info("Shutting down...")


# Disable automatic docs — we serve them behind auth below
app = FastAPI(
    title="Ominis Health API",
    description="Ominis Agent — AI-powered health research assistant by FUNSALUD",
    version="2.0.0",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


# --- Protected API docs (developer + superadmin only) ---

async def _verify_docs_user(request: Request) -> User:
    """Extract and verify the user from query param or header for docs access."""
    from app.auth.service import decode_access_token, get_user_by_id
    from app.database import async_session

    token = request.query_params.get("token") or request.headers.get(
        "Authorization", ""
    ).replace("Bearer ", "")

    if not token:
        raise HTTPException(status_code=401, detail="Provide ?token=JWT to access docs")

    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    async with async_session() as db:
        user = await get_user_by_id(db, int(payload.get("sub", 0)))

    if not user or user.role not in DOCS_ROLES:
        raise HTTPException(status_code=403, detail="Docs access requires developer or superadmin role")

    return user


@app.get("/openapi.json", include_in_schema=False)
async def get_openapi_schema(request: Request):
    await _verify_docs_user(request)
    return JSONResponse(
        get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
        )
    )


@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui(request: Request):
    await _verify_docs_user(request)
    token = request.query_params.get("token", "")
    return get_swagger_ui_html(
        openapi_url=f"/openapi.json?token={token}",
        title=f"{app.title} — Docs",
    )


@app.get("/redoc", include_in_schema=False)
async def custom_redoc(request: Request):
    await _verify_docs_user(request)
    token = request.query_params.get("token", "")
    return get_redoc_html(
        openapi_url=f"/openapi.json?token={token}",
        title=f"{app.title} — ReDoc",
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
app.include_router(chat_router, prefix="/v1")
app.include_router(feedback_router, prefix="/v1")
app.include_router(sinba_router, prefix="/v1")


@app.get("/v1/health", tags=["system"])
async def health_check():
    """Public health check endpoint."""
    return {
        "status": "healthy",
        "service": "ominis-agent",
        "version": "2.0.0",
    }
