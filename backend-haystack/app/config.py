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
    env vars like OLLAMA_URL and OLLAMA_CLINIC_URL are available.
    Chat models: ominis-2.0 (Qwen, general), ominis-2.0-clinic (BioMistral, medical).
    Research models (ominis-2.0-research, ominis-2.0-research-128k) are not in the registry;
    they are handled in the router and use OpenScholar.
    """
    settings = get_settings()

    return {
        "ominis-2.0": ModelConfig(
            id="ominis-2.0",
            ollama_model=settings.ollama_model,
            public_id="ominis-2.0",
            display_name="Ominis 2.0",
            description="Uso general (Qwen). Modelo de IA especializado en salud, desarrollado por FUNSALUD.",
            ollama_url=settings.ollama_url,
            temperature=0.3,
            num_predict=2048,
            context_window=4096,
            num_gpu=-1,
            is_default=True,
        ),
        "ominis-2.0-clinic": ModelConfig(
            id="ominis-2.0-clinic",
            ollama_model=settings.ollama_clinic_model,
            public_id="ominis-2.0-clinic",
            display_name="Ominis 2.0 Clinic",
            description="Conocimiento médico (BioMistral 7B). Ideal para preguntas clínicas.",
            ollama_url=(settings.ollama_clinic_url or settings.ollama_url).strip() or settings.ollama_url,
            temperature=0.3,
            num_predict=1024,
            context_window=4096,
            num_gpu=-1,
            is_default=False,
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

    # Ollama - chat models (g4dn typically serves both Qwen and BioMistral)
    ollama_url: str = "http://localhost:11434"           # Main server for ominis-2.0 (Qwen) and vision
    ollama_model: str = "qwen2.5:14b"                    # Ollama model name for ominis-2.0 (general use)
    ollama_clinic_url: str = ""                          # Optional: separate URL for clinic. If empty, uses ollama_url (same g4dn)
    ollama_clinic_model: str = "biomistral"              # Ollama model name for ominis-2.0-clinic (BioMistral 7B, medical)
    ollama_timeout: float = 90                            # HTTP timeout (seconds) for Ollama calls
    vision_model: str = "minicpm-v"                      # Vision model for image analysis (uses ollama_url)

    # Embeddings
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dimension: int = 384

    # S3
    aws_region: str = "mx-central-1"
    embeddings_bucket: str = "ominis-health-embeddings-mx"
    vector_prefix: str = "vectors"

    # SINBA OLAP Cubes
    sinba_xmla_url: str = ""  # XMLA endpoint URL (e.g., http://server/olap/msmdpump.dll)

    # OpenScholar (Modo Investigación - academic research LLM, ominis-2.0-research)
    openscholar_api_url: str = "http://44.217.135.115:8000"  # OpenAI-compatible vLLM endpoint
    openscholar_model: str = "openscholar"  # Must match vLLM --served-model-name
    openscholar_temperature: float = 0.2
    openscholar_api_key: str = "dummy"  # vLLM often accepts any value
    openscholar_timeout: float = 120  # seconds before HTTP timeout (prevents indefinite hang)
    openscholar_instance_id: str = ""  # EC2 instance ID for start/stop (e.g. i-xxx)

    # OpenScholar 128K (long-context research, ominis-2.0-research-128k) — optional second GPU
    openscholar_128k_api_url: str = ""  # e.g. http://<eip>:8000
    openscholar_128k_instance_id: str = ""  # EC2 instance ID for start/stop
    openscholar_128k_auto_stop_minutes: int = 60  # Auto-stop 128k instance after this many minutes
    openscholar_128k_timeout: float = 300  # HTTP timeout for 128K (long reports need more than 120s)

    # LLM GPU instance (start/stop from dashboard): g4dn runs both Qwen and BioMistral
    ollama_instance_id: str = ""        # EC2 instance ID for Ominis server (ominis-2.0), e.g. g4dn from config/ollama_gpu_server.txt
    ollama_clinic_instance_id: str = "" # EC2 instance ID for Ominis Clinic (ominis-2.0-clinic). Often same as ollama_instance_id (one g4dn)

    # AWS (for research/LLM instance start/stop; region where GPU instances live)
    aws_region_gpu: str = "us-east-1"
    aws_access_key_id: str = ""  # Optional; if empty, use default credential chain
    aws_secret_access_key: str = ""

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
        "extra": "ignore",  # Ignore deprecated keys (e.g. falcon_ollama_url, ollama_fast_*) in existing .env
    }

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",")]


@lru_cache
def get_settings() -> Settings:
    return Settings()
