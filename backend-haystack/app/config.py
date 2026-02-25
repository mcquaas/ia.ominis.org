"""
Application configuration using Pydantic Settings.
All values can be overridden via environment variables or .env file.
"""

from dataclasses import dataclass
from functools import lru_cache

from pydantic_settings import BaseSettings


@dataclass
class ModelConfig:
    """Configuration for a single LLM model (Ollama or OpenAI-compatible e.g. vLLM).
    Defaults favor scientific reliability: lower temperature (0.2–0.4) reduces hallucination
    and keeps responses evidence-aligned across any clinical/medical topic."""
    id: str                      # Internal identifier (never exposed publicly)
    ollama_model: str            # Model name in Ollama (empty when use_openai=True)
    display_name: str            # Human-readable name for the UI (public)
    public_id: str = "ominis-2.0"  # Public model ID returned in API responses
    description: str = ""        # Short description (public)
    version_label: str = ""      # Optional version string (e.g. "2.0.1"); editable in dashboard
    ollama_url: str = ""         # Ollama server URL (empty when use_openai=True)
    temperature: float = 0.3     # Generation temperature; 0.2–0.4 recommended for evidence-based consistency
    num_predict: int = 1024      # Max tokens to generate
    context_window: int = 4096   # Context window size
    num_gpu: int = 50            # Number of GPU layers (Ollama only)
    is_default: bool = False     # Whether this is the default model
    system_prompt: str = ""     # Override system prompt (empty = use default); editable in dashboard
    timeout: float | None = None  # Per-model HTTP timeout (s); None or 0 = use settings.ollama_timeout
    # OpenAI-compatible backend (e.g. vLLM serving gpt-oss)
    use_openai: bool = False     # If True, use OpenAIChatGenerator instead of Ollama
    openai_api_base: str = ""   # Base URL including /v1 (e.g. http://host:8000/v1)
    openai_model: str = ""      # Model name for API (e.g. openai/gpt-oss-20b)


def _build_model_registry() -> dict[str, ModelConfig]:
    """
    Build the model registry. Called after Settings are loaded.
    Chat models: ominis-2.0 (Qwen, general) and optionally ominis-2.0-med (Med42-v2, clinical).
    """
    settings = get_settings()

    registry = {
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
    }
    # Ominis 2.0 Med: Med42-v2 (clinical LLM, M42 Health). See https://huggingface.co/m42-health
    if (getattr(settings, "ollama_med_model", None) or "").strip():
        med_url = (getattr(settings, "ollama_med_url", None) or "").strip() or settings.ollama_url
        registry["ominis-2.0-med"] = ModelConfig(
            id="ominis-2.0-med",
            ollama_model=settings.ollama_med_model.strip(),
            public_id="ominis-2.0-med",
            display_name="Ominis Med",
            description="Modelo clínico Med42-v2 (M42 Health). Respuestas médicas y clínicas.",
            ollama_url=med_url,
            temperature=0.3,
            num_predict=2048,
            context_window=8192,
            num_gpu=-1,
            is_default=False,
        )
    # Merge dashboard overrides from DB (assignments, prompts, version, params)
    try:
        from app.admin.llm_config_db import get_llm_config_overrides
        overrides = get_llm_config_overrides()
        for model_id, cfg in list(registry.items()):
            o = overrides.get(model_id, {})
            if not o:
                continue
            if "display_name" in o:
                cfg.display_name = o["display_name"]
            if "version_label" in o:
                cfg.version_label = str(o["version_label"])
            if "description" in o:
                cfg.description = o["description"]
            if "system_prompt" in o:
                cfg.system_prompt = o["system_prompt"] or ""
            if "temperature" in o:
                cfg.temperature = float(o["temperature"])
            if "num_predict" in o:
                cfg.num_predict = int(o["num_predict"])
            if "is_default" in o:
                cfg.is_default = bool(o["is_default"])
            if "backend_model" in o:
                # backend_model must be the actual Ollama/API model name (e.g. qwen3:14b), not the product id (ominis-2.0)
                bm = (o["backend_model"] or "").strip()
                if bm and bm != model_id:
                    if getattr(cfg, "use_openai", False):
                        cfg.openai_model = bm
                    else:
                        cfg.ollama_model = bm
            if "backend_url_override" in o and (o["backend_url_override"] or "").strip():
                url = (o["backend_url_override"] or "").strip().rstrip("/")
                if getattr(cfg, "use_openai", False):
                    cfg.openai_api_base = f"{url}/v1" if url and not url.endswith("/v1") else url
                else:
                    cfg.ollama_url = url
            if "extra_params" in o and isinstance(o["extra_params"], dict):
                for k, v in o["extra_params"].items():
                    if k == "num_gpu" and hasattr(cfg, "num_gpu"):
                        cfg.num_gpu = int(v)
                    if k == "timeout" and v is not None:
                        try:
                            t = float(v)
                            if t > 0:
                                cfg.timeout = t
                        except (TypeError, ValueError):
                            pass
    except Exception:
        pass
    return registry


# Lazy-initialized registry (populated after settings are loaded)
_model_registry: dict[str, ModelConfig] | None = None


def get_model_registry() -> dict[str, ModelConfig]:
    global _model_registry
    if _model_registry is None:
        _model_registry = _build_model_registry()
    return _model_registry


def invalidate_model_registry() -> None:
    """Clear the model registry cache so next get_model_registry() rebuilds from env + DB."""
    global _model_registry
    _model_registry = None



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
    # Optional third chat model (e.g. Qwen 3, Llama 3.3). If set, "Ominis 2.0 Open" appears in the UI.
    ollama_open_model: str = ""                          # e.g. qwen3:14b or llama3.3:70b-instruct-q4_0
    ollama_open_url: str = ""                            # If empty, uses ollama_url (same server)

    # Ominis 2.0 Med: Med42-v2 (clinical LLM by M42 Health). If set, "Ominis 2.0 Med" appears in the UI.
    ollama_med_model: str = ""                          # e.g. med42 or med42-v2-8b (Ollama model name)
    ollama_med_url: str = ""                            # If empty, uses ollama_url (same server)

    # Ominis 2.0 Power: gpt-oss via vLLM (OpenAI-compatible). If set, "Ominis 2.0 Power" appears in the UI.
    power_api_url: str = ""                              # e.g. http://<host>:8000 (vLLM serve; add /v1 in code)
    power_model: str = "openai/gpt-oss-20b"             # 20B ~16GB VRAM; use openai/gpt-oss-120b for ≥60GB
    power_api_key: str = "EMPTY"                         # vLLM often accepts any value
    power_timeout: float = 120                           # HTTP timeout (seconds)
    power_instance_id: str = ""                          # EC2 instance ID for dashboard start/stop (e.g. g5.2xlarge)

    # Embeddings
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dimension: int = 384
    # Optional: external embedding service (e.g. bge on RTX 4090). If set, used for query + document embedding.
    # When set, EMBEDDING_DIMENSION must match the service output (e.g. 1024 for bge-large-en-v1.5).
    embedding_service_url: str = ""   # e.g. http://host:8080

    # Optional: dedicated Med42 (A100) for clinical translation step in research
    med42_api_url: str = ""   # OpenAI-compatible base e.g. http://host:8000/v1
    med42_model: str = "med42"
    med42_timeout: float = 60

    # Optional: Qwen2.5-VL for vision (figures, OCR, scanned PDF). When set, used for analyze_image instead of Ollama.
    qwen_vl_api_url: str = ""   # OpenAI-compatible base e.g. http://host:8000/v1
    qwen_vl_model: str = "qwen2.5-vl"
    qwen_vl_timeout: float = 60

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
    openscholar_128k_enabled: bool = True  # If False, never use 128K (save GPU); turn on only for certain users/moments

    # LLM GPU instance (start/stop from dashboard): g4dn runs both Qwen and BioMistral
    ollama_instance_id: str = ""        # EC2 instance ID for Ominis server (ominis-2.0), e.g. g4dn from config/ollama_gpu_server.txt
    ollama_clinic_instance_id: str = "" # EC2 instance ID for Ominis Clinic (ominis-2.0-clinic). Often same as ollama_instance_id (one g4dn)
    ollama_med_instance_id: str = ""    # EC2 instance ID for Ominis Med (ominis-2.0-med). Often same as ollama_instance_id (one g4dn)

    # AWS (for research/LLM instance start/stop; region where GPU instances live)
    aws_region_gpu: str = "us-east-1"
    aws_access_key_id: str = ""  # Optional; if empty, use default credential chain
    aws_secret_access_key: str = ""

    # CORS
    frontend_url: str = "http://localhost:3000"
    allowed_origins: str = "http://localhost:3000"

    # Google OAuth (optional; if set, "Continuar con Google" is enabled)
    google_client_id: str = ""
    google_client_secret: str = ""
    # Optional: backend public base URL for OAuth redirect_uri (e.g. https://api.ominis.org). If empty, uses request.base_url (set when behind a proxy that forwards X-Forwarded-Proto/Host).
    backend_public_url: str = ""

    # OIDC (LibreChat): use same user base as ia.ominis.org. Set issuer base (e.g. https://api.ominis.org) and LibreChat client.
    oidc_librechat_client_id: str = "librechat"
    oidc_librechat_client_secret: str = ""
    oidc_librechat_redirect_uris: str = "https://chat.ominis.org/oauth/openid/callback"

    # Rate Limiting
    rate_limit_requests: int = 100
    rate_limit_window_seconds: int = 60

    # Analytical layer (SAV → Parquet for tool-based statistics)
    analytical_data_dir: str = ""  # If set, SAV uploads are exported as Parquet here (e.g. /opt/ominis-backend/data/analytical)

    # Open Scholar (Semantic Scholar) — academic paper search as a source option (default off)
    semantic_scholar_api_key: str = ""  # Set in .env for higher rate limits; optional for low-volume use

    # Health datastore (nightly Mexican health pipeline: FAISS + OpenSearch)
    health_datastore_enabled: bool = True
    health_faiss_s3_bucket: str = ""  # e.g. omnis-health-embeddings-mx
    health_faiss_s3_prefix: str = "health-datastore/faiss"
    health_faiss_path: str = ""  # Optional: local path to index (overrides S3 if set)
    health_embedding_dim: int = 384  # Must match pipeline HEALTH_EMBEDDING_DIM
    health_boost_country_mexico: float = 0.15
    health_boost_year_recent: float = 0.10
    health_boost_nom_gpc: float = 0.12
    opensearch_url: str = ""  # e.g. https://xxx.us-east-1.es.amazonaws.com
    opensearch_index: str = "health-chunks"
    opensearch_auth: str = ""  # optional user:pass

    # LiveAvatar (HeyGen) — for /live page. FULL mode uses HeyGen LLM; CUSTOM mode uses Pipecat + Ominis Med
    heygen_live_avatar_api_key: str = ""  # From app.liveavatar.com. Required for HeyGen FULL mode.
    heygen_live_avatar_avatar_id: str = "bf00036b-558a-44b5-b2ff-1e3cec0f4ceb"  # Marianne Sitting
    heygen_live_avatar_voice_id: str = "1bd001e7e50f421d891986aad0228f13"  # Alessandra - IA
    heygen_live_avatar_sandbox: bool = False  # False to use Marianne; sandbox only allows Wayne

    # Pipecat Cloud — when set, /live uses Ominis Med (ominis-2.0-clinic) via Pipecat (CUSTOM mode)
    pipecat_agent_name: str = ""  # e.g. ominis-live-avatar. When set, session uses Pipecat instead of HeyGen FULL.
    pipecat_api_token: str = ""  # Pipecat Cloud API token
    pipecat_api_url: str = "https://api.pipecat.daily.co/v1/public"  # Pipecat Cloud API base
    live_join_base_url: str = "https://ia.ominis.org"  # Base URL for /live/join (frontend)

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
