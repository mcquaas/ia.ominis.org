"""Configuration for nightly health datastore pipeline. Load from .env or environment."""

import os
from pathlib import Path

# Load .env from repo root, backend-haystack, or pipeline dir
for _path in [
    Path(__file__).resolve().parent.parent / ".env",
    Path(__file__).resolve().parent.parent / "backend-haystack" / ".env",
    Path(__file__).resolve().parent / ".env",
]:
    if _path.exists():
        try:
            from dotenv import load_dotenv
            load_dotenv(_path)
        except ImportError:
            pass
        break

# Database (sync URL for pipeline). psycopg2 expects postgresql:// not postgresql+psycopg2://
def _pg_sync_url() -> str:
    u = os.environ.get("DATABASE_URL_SYNC") or os.environ.get("DATABASE_URL", "postgresql://ominis_admin:password@127.0.0.1:5432/ominis_haystack")
    import re
    return re.sub(r"postgresql\+\w+://", "postgresql://", u)

DATABASE_URL_SYNC = _pg_sync_url()

# Embedding (default: general-purpose; for PubMed/papers consider allenai/specter2 or MedCPT — see docs/HEALTH_EMBEDDINGS_SCIENCE.md)
HEALTH_EMBEDDING_MODEL = os.environ.get("HEALTH_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
HEALTH_EMBEDDING_DIM = int(os.environ.get("HEALTH_EMBEDDING_DIM", "384"))

# S3 for FAISS index
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
HEALTH_FAISS_S3_BUCKET = os.environ.get("HEALTH_FAISS_S3_BUCKET", os.environ.get("EMBEDDINGS_BUCKET", "ominis-health-embeddings-mx"))
HEALTH_FAISS_S3_PREFIX = os.environ.get("HEALTH_FAISS_S3_PREFIX", "health-datastore/faiss")

# S3 raw docs from Lambda ingest (pipeline reads from here when --from-s3)
PIPELINE_RAW_BUCKET = os.environ.get("PIPELINE_RAW_BUCKET", HEALTH_FAISS_S3_BUCKET)
PIPELINE_RAW_PREFIX = os.environ.get("PIPELINE_RAW_PREFIX", "pipeline/raw_docs")

# OpenSearch (AWS or self-hosted)
OPENSEARCH_URL = os.environ.get("OPENSEARCH_URL", "")  # e.g. https://...us-east-1.es.amazonaws.com
OPENSEARCH_INDEX = os.environ.get("OPENSEARCH_INDEX", "health-chunks")
OPENSEARCH_AUTH = os.environ.get("OPENSEARCH_AUTH", "")  # optional: user:pass for basic auth
OPENSEARCH_USE_SSL = os.environ.get("OPENSEARCH_USE_SSL", "true").lower() == "true"
OPENSEARCH_VERIFY_CERTS = os.environ.get("OPENSEARCH_VERIFY_CERTS", "true").lower() == "true"

# Scoring weights (for retrieval)
HEALTH_BOOST_COUNTRY_MEXICO = float(os.environ.get("HEALTH_BOOST_COUNTRY_MEXICO", "0.15"))
HEALTH_BOOST_YEAR_RECENT = float(os.environ.get("HEALTH_BOOST_YEAR_RECENT", "0.10"))
HEALTH_BOOST_NOM_GPC = float(os.environ.get("HEALTH_BOOST_NOM_GPC", "0.12"))

# Chunking
CHUNK_MIN_TOKENS = int(os.environ.get("CHUNK_MIN_TOKENS", "400"))
CHUNK_MAX_TOKENS = int(os.environ.get("CHUNK_MAX_TOKENS", "600"))
CHUNK_OVERLAP_PCT = float(os.environ.get("CHUNK_OVERLAP_PCT", "0.15"))

# Paths
PIPELINE_ROOT = Path(__file__).resolve().parent
REPORTS_DIR = PIPELINE_ROOT / "reports"
LOGS_DIR = PIPELINE_ROOT / "logs"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# --- Mexican health ingestion: PubMed queries and URLs (sistema de salud mexicano) ---
PUBMED_QUERIES_MEXICAN_HEALTH = [
    # Política pública y marco legal
    "Mexico[affiliation] OR public health[mesh] OR clinical guidelines[tiab]",
    "health policy Mexico[tiab] OR public health policy[tiab] Mexico OR Ley General de Salud",
    "(IMSS OR ISSSTE OR Mexican health system)[tiab] OR healthcare Mexico[tiab]",
    "universal health coverage[tiab] Mexico OR seguro popular Mexico",
    # Salud digital e IA
    "digital health[tiab] Mexico OR e-health[tiab] Mexico OR telemedicine Mexico",
    "artificial intelligence[tiab] health OR AI healthcare[tiab] OR machine learning clinical",
    # Instituciones y organismos
    "FUNSALUD Mexico OR health foundation Mexico",
    "CONBIOETICA Mexico OR bioethics[tiab] Mexico OR Comisión Nacional Bioética",
    "SINAVE Mexico OR epidemiological surveillance[tiab] Mexico OR vigilancia epidemiológica",
    "CCINSHAE Mexico OR scientific health information Mexico",
    # Protocolos y guías
    "clinical practice guidelines[tiab] Mexico OR guías práctica clínica México",
    "health protocols[tiab] Mexico OR clinical protocols[tiab] Mexico OR protocolos salud",
    # Enfermedades prioritarias
    "(diabetes mellitus OR hypertension)[mesh] AND Mexico[affiliation]",
    "diabetes[tiab] Mexico OR diabetes mellitus type 2[mesh] Mexico",
    "cancer[tiab] Mexico OR neoplasms[mesh] Mexico[affiliation] OR cáncer México",
    "cardiovascular[tiab] Mexico OR cardiovascular diseases[mesh] Mexico[affiliation]",
    "(maternal health OR perinatal)[tiab] AND Mexico",
    "mental health[tiab] Mexico OR psychiatric Mexico[affiliation]",
    "infectious diseases[mesh] Mexico OR enfermedades transmisibles México",
]
MEXICAN_HEALTH_URLS = [
    "https://www.gob.mx/salud",
    "https://www.gob.mx/salud/cenaprece",
    "https://www.imss.gob.mx",
    "https://www.gob.mx/issste",
    "https://cenetec-difusion.com/gpc-sns/",
    "https://www.gob.mx/salud/documentos",
    "https://funsalud.org.mx",
    "https://www.conbioetica-mexico.salud.gob.mx",
    "https://www.gob.mx/salud/conbioetica",
    "https://www.sinave.gob.mx",
]

# Crawl: seed URLs to follow links (same domain). Used with --source crawl.
CRAWL_SEED_URLS = [
    "https://www.gob.mx/salud",
    "https://www.gob.mx/salud/documentos",
    "https://www.gob.mx/salud/cenaprece",
]
CRAWL_MAX_PAGES = 80  # max pages to fetch per run
