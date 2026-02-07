"""
Haystack RAG Pipeline definition.
Supports multiple LLM models sharing the same retriever and document store.
Each model gets its own OllamaGenerator; the embedder and retriever are shared.
"""

import logging
from typing import Optional

from haystack import Pipeline
from haystack.components.builders import PromptBuilder
from haystack.components.embedders import SentenceTransformersTextEmbedder
from haystack.components.retrievers.in_memory import InMemoryEmbeddingRetriever
from haystack.document_stores.in_memory import InMemoryDocumentStore

from haystack_integrations.components.generators.ollama import OllamaGenerator

from app.config import (
    DEFAULT_MODEL_ID,
    ModelConfig,
    get_model_config,
    get_model_registry,
    get_settings,
)
from app.rag.document_store import get_document_store, load_chunks_from_s3

logger = logging.getLogger(__name__)
settings = get_settings()

# ---------------------------------------------------------------------------
# System prompt (shared across all models – the agent persona stays the same)
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """Eres OMINIS, el asistente de investigación en salud de la Fundación Mexicana para la Salud (FUNSALUD).
Tu misión es ayudar a investigadores y profesionales de la salud con información precisa y basada en evidencia.

CAPACIDADES:
- Responder preguntas sobre el sistema de salud en México
- Buscar información en fuentes médicas curadas (RAG)
- Buscar artículos científicos en PubMed cuando sea necesario
- Buscar información actualizada en la web cuando sea relevante

INSTRUCCIONES:
1. Responde SOLO basándote en la información proporcionada en las fuentes.
2. Si las fuentes no contienen información suficiente, indícalo claramente.
3. Siempre cita las fuentes que uses (por número [1], [2], etc.).
4. Usa un lenguaje claro y accesible.
5. No proporciones diagnósticos médicos. Recomienda consultar a un profesional cuando sea apropiado.
6. Responde en español mexicano.
7. Si el historial de conversación indica que el usuario está confirmando una propuesta anterior (ej. "Sí", "Claro"), procede con la acción propuesta.
"""

# ---------------------------------------------------------------------------
# RAG prompt template (shared – Jinja2, model-agnostic)
# ---------------------------------------------------------------------------
RAG_PROMPT_TEMPLATE = """{{ system_prompt }}

{% if history %}
HISTORIAL DE CONVERSACIÓN (últimos mensajes):
{% for msg in history %}
{{ "Usuario" if msg.role == "user" else "Asistente" }}: {{ msg.content }}
{% endfor %}
{% endif %}

FUENTES DISPONIBLES:
{% for document in documents %}
[Fuente {{ loop.index }}]
Título: {{ document.meta.title }}
URL: {{ document.meta.url }}
Contenido:
{{ document.content }}
---
{% endfor %}

Pregunta del usuario: {{ question }}

Proporciona una respuesta completa basada en las fuentes anteriores y el contexto de la conversación.
Incluye las referencias a las fuentes usadas [1], [2], etc."""


# ---------------------------------------------------------------------------
# Pipeline Manager – one pipeline per model, shared retriever/embedder
# ---------------------------------------------------------------------------

class PipelineManager:
    """
    Manages multiple Haystack RAG pipelines that share the same document store
    and embedding model but use different LLM generators.
    """

    def __init__(self):
        self._pipelines: dict[str, Pipeline] = {}
        self._document_store: Optional[InMemoryDocumentStore] = None
        self._ready = False

    @property
    def ready(self) -> bool:
        return self._ready

    @property
    def available_models(self) -> list[dict]:
        """Return metadata for all registered models."""
        return [
            {
                "id": m.id,
                "displayName": m.display_name,
                "description": m.description,
                "isDefault": m.is_default,
            }
            for m in get_model_registry().values()
        ]

    def get_pipeline(self, model_id: str | None = None) -> Pipeline:
        """Get the pipeline for a given model, falling back to default."""
        mid = model_id if model_id and model_id in self._pipelines else DEFAULT_MODEL_ID
        pipeline = self._pipelines.get(mid)
        if pipeline is None:
            raise RuntimeError(
                f"Pipeline for model '{mid}' not initialized. Call initialize() first."
            )
        return pipeline

    def get_model_id(self, model_id: str | None = None) -> str:
        """Resolve a model ID, falling back to default."""
        if model_id and model_id in get_model_registry():
            return model_id
        return DEFAULT_MODEL_ID

    async def initialize(self):
        """Build all pipelines and load documents. Called at app startup."""
        logger.info("Initializing PipelineManager...")

        # 1. Document store (shared)
        self._document_store = get_document_store()
        doc_count = await load_chunks_from_s3()
        logger.info(f"Document store has {doc_count} documents")

        if doc_count > 0:
            logger.info("Embedding documents (may take a moment on first run)...")
            await self._embed_documents()

        # 2. Build one pipeline per registered model
        for model_id, model_cfg in get_model_registry().items():
            logger.info(f"Building pipeline for model: {model_cfg.display_name}")
            pipeline = self._build_pipeline(model_cfg)
            pipeline.warm_up()
            self._pipelines[model_id] = pipeline
            logger.info(f"  Pipeline '{model_id}' ready.")

        self._ready = True
        logger.info(
            f"PipelineManager ready with {len(self._pipelines)} model(s): "
            f"{', '.join(self._pipelines.keys())}"
        )

    def _build_pipeline(self, model_cfg: ModelConfig) -> Pipeline:
        """Build a single RAG pipeline for one model."""
        pipeline = Pipeline()

        # Shared: text embedder (same model for all pipelines)
        text_embedder = SentenceTransformersTextEmbedder(
            model=settings.embedding_model,
        )

        # Shared: retriever (points to the shared document store)
        retriever = InMemoryEmbeddingRetriever(
            document_store=self._document_store,
            top_k=5,
        )

        # Shared: prompt builder (same template, same agent persona)
        prompt_builder = PromptBuilder(template=RAG_PROMPT_TEMPLATE)

        # Model-specific: LLM generator via Ollama
        # Each model can point to a different Ollama server
        ollama_url = model_cfg.ollama_url or settings.ollama_url
        logger.info(f"  Generator for '{model_cfg.id}' -> Ollama at {ollama_url}")

        generator = OllamaGenerator(
            model=model_cfg.ollama_model,
            url=ollama_url,
            generation_kwargs={
                "temperature": model_cfg.temperature,
                "num_predict": model_cfg.num_predict,
            },
        )

        pipeline.add_component("text_embedder", text_embedder)
        pipeline.add_component("retriever", retriever)
        pipeline.add_component("prompt_builder", prompt_builder)
        pipeline.add_component("generator", generator)

        pipeline.connect("text_embedder.embedding", "retriever.query_embedding")
        pipeline.connect("retriever.documents", "prompt_builder.documents")
        pipeline.connect("prompt_builder", "generator")

        return pipeline

    async def _embed_documents(self):
        """Embed all documents in the store that don't yet have embeddings."""
        from haystack.components.embedders import SentenceTransformersDocumentEmbedder

        embedder = SentenceTransformersDocumentEmbedder(
            model=settings.embedding_model,
        )
        embedder.warm_up()

        all_docs = self._document_store.filter_documents()
        docs_to_embed = [d for d in all_docs if d.embedding is None]

        if not docs_to_embed:
            logger.info("All documents already have embeddings.")
            return

        logger.info(f"Embedding {len(docs_to_embed)} documents...")
        result = embedder.run(documents=docs_to_embed)
        embedded_docs = result["documents"]

        self._document_store.write_documents(embedded_docs, policy="overwrite")
        logger.info(f"Embedded and stored {len(embedded_docs)} documents.")


# ---------------------------------------------------------------------------
# Global singleton
# ---------------------------------------------------------------------------

_pipeline_manager: Optional[PipelineManager] = None


def get_pipeline_manager() -> PipelineManager:
    """Get the global PipelineManager. Must be initialized first."""
    global _pipeline_manager
    if _pipeline_manager is None or not _pipeline_manager.ready:
        raise RuntimeError("PipelineManager not initialized. Call initialize_pipeline() first.")
    return _pipeline_manager


async def initialize_pipeline():
    """Initialize the global PipelineManager. Called during app startup."""
    global _pipeline_manager
    _pipeline_manager = PipelineManager()
    await _pipeline_manager.initialize()


# ---------------------------------------------------------------------------
# Backwards-compatible helper (used by existing code that doesn't pick a model)
# ---------------------------------------------------------------------------

def get_rag_pipeline(model_id: str | None = None) -> Pipeline:
    """Convenience wrapper: get a pipeline from the manager."""
    return get_pipeline_manager().get_pipeline(model_id)
