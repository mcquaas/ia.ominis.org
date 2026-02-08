"""
Application configuration using Pydantic Settings.
All values can be overridden via environment variables or .env file.
"""

from dataclasses import dataclass
from functools import lru_cache

from pydantic_settings import BaseSettings


@dataclass
class ModelConfig:
    """Configuration for a single LLM model available via Ollama."""
    id: str                      # Internal identifier (never exposed publicly)
    ollama_model: str            # Model name in Ollama (never exposed publicly)
    display_name: str            # Human-readable name for the UI (public)
    public_id: str = "ominis-2.0"  # Public model ID returned in API responses
    description: str = ""        # Short description (public)
    ollama_url: str = ""         # Ollama server URL (never exposed publicly)
    temperature: float = 0.3     # Default generation temperature
    num_predict: int = 1024      # Max tokens to generate
    context_window: int = 4096   # Context window size
    num_gpu: int = 50            # Number of GPU layers (reduce if VRAM is tight)
    is_default: bool = False     # Whether this is the default model


def _build_model_registry() -> dict[str, ModelConfig]:
    """
    Build the model registry. Called after Settings are loaded so that
    env vars like OLLAMA_URL and FALCON_OLLAMA_URL are available.
    """
    settings = get_settings()

    return {
        "ominis-2.0": ModelConfig(
            id="ominis-2.0",
            ollama_model="ominis-2.0",
            public_id="ominis-2.0",
            display_name="Ominis 2.0",
            description="Modelo de IA especializado en salud, desarrollado por FUNSALUD.",
            ollama_url=settings.ollama_url,
            temperature=0.3,
            num_predict=2048,
            context_window=4096,
            num_gpu=-1,  # All layers on GPU (14B fits entirely in A10G 24GB)
            is_default=True,
        ),
    }


# Lazy-initialized registry (populated after settings are loaded)
_model_registry: dict[str, ModelConfig] | None = None


def get_model_registry() -> dict[str, ModelConfig]:
    global _model_registry
    if _model_registry is None:
        _model_registry = _build_model_registry()
    return _model_registry



DEFAULT_MODEL_ID = "ominis-2.0"


def get_model_config(model_id: str | None = None) -> ModelConfig:
    """Get a model config by ID, falling back to the default."""
    registry = get_model_registry()
    if model_id and model_id in registry:
        return registry[model_id]
    return registry[DEFAULT_MODEL_ID]


class Settings(BaseSettings):
    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False

    # Database
    database_url: str = "postgresql+asyncpg://ominis_admin:password@127.0.0.1:5432/ominis_haystack"
    database_url_sync: str = "postgresql+psycopg2://ominis_admin:password@127.0.0.1:5432/ominis_haystack"

    # JWT
    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    jwt_expiration_minutes: int = 1440  # 24 hours

    # Ollama - each model can run on a different Ollama server
    ollama_url: str = "http://localhost:11434"           # Default server (ominis-2.0 / BioMistral)
    falcon_ollama_url: str = "http://localhost:11434"    # Falcon-40B server (separate GPU)
    ollama_model: str = "ominis-2.0"                     # Default model ID
    vision_model: str = "minicpm-v"                      # Vision model for image analysis

    # Embeddings
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dimension: int = 384

    # S3
    aws_region: str = "mx-central-1"
    embeddings_bucket: str = "ominis-health-embeddings-mx"
    vector_prefix: str = "vectors"

    # SINBA OLAP Cubes
    sinba_xmla_url: str = ""  # XMLA endpoint URL (e.g., http://server/olap/msmdpump.dll)

    # CORS
    frontend_url: str = "http://localhost:3000"
    allowed_origins: str = "http://localhost:3000"

    # Rate Limiting
    rate_limit_requests: int = 100
    rate_limit_window_seconds: int = 60

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
    }

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",")]


@lru_cache
def get_settings() -> Settings:
    return Settings()
