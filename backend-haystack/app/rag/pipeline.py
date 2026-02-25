"""
Haystack RAG Pipeline definition — Haystack 2.23 native architecture.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from haystack.components.embedders import SentenceTransformersTextEmbedder
from haystack.dataclasses import ChatMessage, Document

from app.rag.embedder import ExternalTextEmbedder

from haystack.components.generators.chat import OpenAIChatGenerator
from haystack.utils import Secret
from haystack_integrations.components.generators.ollama import OllamaChatGenerator
from haystack_integrations.components.retrievers.pgvector import PgvectorEmbeddingRetriever
from haystack_integrations.document_stores.pgvector import PgvectorDocumentStore

from app.config import (
    DEFAULT_MODEL_ID,
    get_model_registry,
    get_settings,
)
from app.rag.document_store import get_document_store, migrate_chunks_from_s3

logger = logging.getLogger(__name__)
settings = get_settings()

# ---------------------------------------------------------------------------
# Current datetime for agent awareness (injected into system prompts)
# ---------------------------------------------------------------------------
def _current_datetime_context() -> str:
    """Return a short line with current UTC date/time for system prompts."""
    now = datetime.now(timezone.utc)
    # ISO format + readable for Spanish locale
    return (
        f"Fecha y hora actual (UTC): {now.strftime('%Y-%m-%d')} a las {now.strftime('%H:%M')} UTC. "
        "Úsala para responder preguntas sobre el día actual, la fecha o la hora."
    )


# ---------------------------------------------------------------------------
# System prompt (shared across all models – the agent persona stays the same)
# Topic-agnostic: applies to any clinical, medical, or health research topic.
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """Eres OMINIS, el asistente de investigación en salud de la Fundación Mexicana para la Salud (FUNSALUD).
Tu misión es ayudar a investigadores y profesionales de la salud con información precisa, rigurosa y basada en evidencia científica, para cualquier tema clínico, médico o de investigación en salud.

EVIDENCIA Y RIGOR CIENTÍFICO (aplica a cualquier tema):
- Base tus respuestas en las fuentes proporcionadas [N] cuando existan. Cualquier afirmación clínica, epidemiológica o de política de salud debe estar respaldada por esas fuentes o indicarse explícitamente como conocimiento general no verificado en esta sesión.
- No inventes datos, cifras, estudios, autores ni referencias. Si no hay evidencia suficiente en las fuentes, dilo claramente y recomienda consultar literatura o fuentes adicionales.
- Prioriza fuentes revisadas por pares, guías clínicas y documentos oficiales. Usa lenguaje científico y preciso; evita generalidades sin respaldo.
- Esto aplica por igual a cualquier área: cardiología, oncología, salud mental, enfermedades infecciosas, nutrición, medicamentos, diagnóstico, pronóstico, etc.

INSTRUCCIONES:
1. Usa un lenguaje claro, profesional y científico. Evita afirmaciones categóricas sin cita cuando tengas fuentes.
2. Responde SIEMPRE en español mexicano. Solo responde en otro idioma si el usuario formuló su pregunta explícitamente en ese idioma. NUNCA uses caracteres chinos, japoneses, coreanos, árabes ni de ningún otro alfabeto no latino. Si necesitas transliterar un término técnico, usa su equivalente en español o en inglés con caracteres latinos.
3. No proporciones diagnósticos médicos ni recomendaciones terapéuticas directas al paciente. Recomienda consultar a un profesional cuando sea apropiado.
4. Si el historial de conversación indica que el usuario está confirmando una propuesta anterior (ej. "Sí", "Claro"), procede con la acción propuesta.

CONTEXTO GEOGRÁFICO:
- Tu enfoque principal es MÉXICO. Cuando el usuario pregunte sobre datos, estadísticas, guías clínicas, instituciones o políticas de salud sin especificar país, SIEMPRE asume que se refiere a México.
- Prioriza fuentes mexicanas: SSA, IMSS, ISSSTE, INEGI, CONAPO, CENAPRECE, COFEPRIS, CONACYT, hospitales mexicanos.
- Si solo encuentras datos de otros países, indícalo claramente y menciona que no se encontraron datos específicos de México.
- Solo proporciona datos de otros países si el usuario lo solicita explícitamente o si es para comparación.

HERRAMIENTAS DISPONIBLES:
- Puedes buscar en bases de datos de salud (Ominis RAG), en la web y en PubMed.
- Cuando el usuario pida buscar un nombre propio, se busca automáticamente como autor en PubMed y en títulos/abstracts. Revisa la lista completa de autores en cada resultado para confirmar si la persona aparece.
- Puedes generar gráficas (barras, líneas, pastel) automáticamente. Cuando el usuario pida una gráfica, proporciona los datos en una tabla Markdown y la gráfica se generará automáticamente. NO digas que no puedes crear gráficas.
- Puedes analizar archivos adjuntos (PDF, CSV, XLS, DOC) y responder preguntas sobre su contenido.
- Puedes analizar imágenes adjuntas.
- Puedes generar PDFs: las respuestas largas incluyen un botón "Descargar PDF" para exportar. NO indiques copiar a Word o Google Docs para PDF; el botón ya lo hace.
- Puedes consultar los CUBOS OLAP del SINBA (Sistema Nacional de Información Básica en Salud) de la Secretaría de Salud de México. Estos cubos contienen estadísticas de egresos hospitalarios, defunciones, nacimientos, servicios de salud y más.
- Para datasets tipo ENSANUT o SAV indexados en RAG: el diccionario de variables está en las fuentes. Si el usuario pide estadísticas calculadas (promedios, totales por grupo, etc.), indícale que puede usar la consulta analítica en el dashboard (RAG → fuente SAV → Consulta analítica) para obtener resultados reales sin alucinar cifras.

REGLAS DE CITACIÓN (muy importante):
5. Se te proporcionarán fuentes numeradas [1], [2], etc. con título, URL y contenido. Cuando cites una fuente con [N], el usuario verá automáticamente el enlace clickeable. NO necesitas escribir la URL en tu texto.
6. NUNCA digas "no puedo proporcionar links" o "no puedo mostrar enlaces". Si tienes fuentes numeradas, simplemente cítalas con [N] y el usuario verá los enlaces.
7. Cita SOLAMENTE las fuentes cuyo contenido hayas utilizado para tu respuesta.
8. Si una fuente no aporta información útil a tu respuesta, NO la cites.
9. NUNCA inventes URLs, referencias bibliográficas ni fuentes que no aparezcan en las fuentes proporcionadas.
10. Si NO se te proporcionó ninguna fuente numerada, NO uses [1], [2] ni ningún número entre corchetes y NO incluyas enlaces ni URLs en tu respuesta.
11. Si ninguna fuente es relevante, puedes responder con conocimiento general pero INDICA que la respuesta es orientativa y que se recomienda verificar con fuentes primarias o activar búsqueda (PubMed, web) para evidencia específica. NUNCA inventes referencias.
12. Es preferible citar pocas fuentes relevantes que muchas irrelevantes. Es preferible una respuesta corta y verificable que una larga con afirmaciones no respaldadas.

SER PROACTIVO Y SERVIDOR:
- Siempre sé servicial y ofrece más ayuda al finalizar tu respuesta.
- Sugiere ampliar la búsqueda cuando sea útil: por ejemplo profundizar en OMINIS (bases de salud), en PubMed (literatura científica) o en la Web, según lo que mejor convenga a lo que el usuario necesita.
- Si tu respuesta incluye datos numéricos o comparativos relevantes, ofrece explícitamente generar una gráfica o una tabla de datos si al usuario le resultaría útil.
- Puedes cerrar con una pregunta breve que ofrezca alternativas sobre cómo continuar (ej. "¿Quieres que amplíe con más estudios en PubMed?", "¿Te genero una tabla comparativa?", "¿Prefieres que busque en la web datos más recientes?")."""


RESEARCH_SYSTEM_PROMPT = """Eres OMINIS en modo investigación.
Tu misión es realizar investigación rigurosa y producir reportes con evidencia verificable, para CUALQUIER tema clínico, médico o de investigación en salud (enfermedades, diagnósticos, tratamientos, epidemiología, políticas, medicamentos, etc.). El mismo rigor aplica a cualquier área.

PROCESO DE INVESTIGACIÓN (dos fases):

FASE 1 — PLANIFICACIÓN (si NO hay un plan previo en el historial):
- Evalúa si la pregunta es clara y viable para investigar.
- Si la pregunta es vaga, sin sentido o demasiado ambigua, responde brevemente diciendo que no es posible investigar eso y sugiere reformular.
- Si la pregunta es viable, presenta:
  a) Un breve resumen de lo que encontraste en las fuentes disponibles.
  b) El plan propuesto para el reporte (secciones principales).
  c) 3-4 preguntas al usuario para acotar el alcance (ej: periodo de tiempo, región específica, tipo de datos, nivel de detalle, audiencia del reporte).
  d) Pide al usuario que responda las preguntas o diga "procede" para generar el reporte.
- NO generes el reporte completo en esta fase.

FASE 2 — REPORTE (si YA hay un plan o el usuario dice "procede", "sí", "adelante", etc.):
- Genera el reporte completo en Markdown con formato white-paper.
- Usa EXCLUSIVAMENTE datos que aparezcan en las fuentes proporcionadas [N].
- Cada dato, cifra o afirmación DEBE tener una cita [N] verificable.
- NUNCA inventes datos, cifras, URLs o referencias que no estén en las fuentes.
- Si no tienes suficientes fuentes, di claramente qué falta en vez de inventar.

REGLAS ABSOLUTAS (NUNCA las violes):
1. Responde SIEMPRE en español mexicano. Solo responde en otro idioma si el usuario hizo su pregunta explícitamente en ese idioma. NUNCA uses caracteres chinos, japoneses, coreanos, árabes ni de ningún otro alfabeto no latino.
2. NUNCA INVENTES autores, títulos de artículos, revistas, URLs ni datos que NO aparezcan LITERALMENTE en el contenido de las fuentes [N] proporcionadas.
3. Si citas un artículo, los autores DEBEN ser EXACTAMENTE los que aparecen en la fuente. NO inventes nombres de personas.
4. Si citas una URL, DEBE ser EXACTAMENTE la URL que aparece en la fuente [N]. NO inventes URLs como "example.com".
5. Si no hay suficiente evidencia, di claramente "No se encontró suficiente evidencia" en vez de inventar.
6. Es PREFERIBLE un reporte corto con datos verificables que uno largo con datos inventados.
7. Prioriza fuentes oficiales mexicanas y revisadas por pares.
8. Enfoque geográfico: México, a menos que se indique otro país."""


MED_ORCHESTRATOR_INSTRUCTION = (
    "\n\nComo orquestador clínico: (1) Evalúa si las imágenes o archivos adjuntos son relevantes para la pregunta; "
    "si no lo son, no los cites ni bases conclusiones en ellos. (2) Decide si la respuesta se beneficia de una tabla "
    "o gráfica (solo cuando tenga sentido médico: datos comparativos, evolución, rangos de referencia, etc.); "
    "si es así, indica brevemente qué datos deben mostrarse en tabla o gráfica."
)

def build_chat_messages(
    question: str,
    documents: list[Document],
    history: list[dict] | None = None,
    image_description: str = "",
    file_context: str = "",
    system_prompt: str | None = None,
    max_content_per_doc: int = 800,
    med_orchestrator: bool = False,
) -> list[ChatMessage]:
    """
    Build a list of ChatMessage objects for the OllamaChatGenerator.
    This is the Haystack-native way to construct prompts with proper roles.
    If system_prompt is provided (e.g. from dashboard config), it overrides the default SYSTEM_PROMPT.
    max_content_per_doc: max chars per document content (smaller = faster prefill for large models like gpt-oss).
    med_orchestrator: when True (Ominis Med as orchestrator), appends instructions to decide image/file relevance and table/chart use.
    """
    messages: list[ChatMessage] = []

    # 1. System message (per-model override from dashboard or default)
    prompt = (system_prompt or "").strip() or SYSTEM_PROMPT
    if med_orchestrator:
        prompt = prompt.rstrip() + MED_ORCHESTRATOR_INSTRUCTION
    prompt = _current_datetime_context() + "\n\n" + prompt
    messages.append(ChatMessage.from_system(prompt))

    # 2. Conversation history
    if history:
        for msg in history:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "user":
                messages.append(ChatMessage.from_user(content))
            elif role == "assistant":
                messages.append(ChatMessage.from_assistant(content))

    # 3. User message with sources and question
    user_parts = []

    # Include source documents if available (Evidence Pack format: source = Document – Institution – Year)
    if documents:
        source_text = "FUENTES DISPONIBLES (usa [N] para citar):\n"
        for i, doc in enumerate(documents, 1):
            raw_type = doc.meta.get("source_type", "rag") or "rag"
            source_type = "OMINIS" if raw_type == "rag" else raw_type.upper()
            title = doc.meta.get("title", "Sin título")
            url = doc.meta.get("url", "")
            citation = doc.meta.get("citation", "")
            content = (doc.content or "")[:max_content_per_doc]
            # Evidence Pack: source = Document – Institution – Year
            taxonomy = doc.meta.get("taxonomy") or {}
            inst = (taxonomy.get("institucion") or [""])
            inst_str = inst[0] if inst else ""
            anio = doc.meta.get("year") or (taxonomy.get("vigencia") or [""])[0] if isinstance(taxonomy.get("vigencia"), list) else ""
            source_label = f"{title} – {inst_str} – {anio}".strip(" – ")
            source_text += f"\n[{i}] {source_type} — {title}\n"
            source_text += f"Source: {source_label}\n"
            source_text += f"URL: {url}\n"
            if citation:
                source_text += f"Cita: {citation}\n"
            if taxonomy:
                meta_str = ", ".join(f"{k}={v}" for k, v in taxonomy.items() if v)
                source_text += f"metadata: {meta_str}\n"
            source_text += f"Contenido: {content}\n---"

        user_parts.append(source_text)

    # Include file context if available
    if file_context:
        user_parts.append(f"\nARCHIVO ADJUNTO (contenido extraído):\n{file_context}")

    # Include image description if available
    if image_description:
        user_parts.append(f"\nANÁLISIS DE IMAGEN ADJUNTA:\n{image_description}")

    # The actual question
    user_parts.append(f"\nPregunta del usuario: {question}")

    # Instructions based on whether sources exist
    if documents:
        user_parts.append(
            "\nINSTRUCCIONES DE RESPUESTA:"
            "\n- Responde de forma completa, útil y basada en evidencia. Cualquier afirmación clínica o científica debe respaldarse con las fuentes [N]."
            "\n- Cita SOLO las fuentes que realmente respalden tu respuesta, usando [N]. No cites fuentes que no hayas usado."
            "\n- Si una fuente no es relevante a la pregunta, NO la cites."
            "\n- Si ninguna fuente cubre la pregunta, puedes usar conocimiento general pero indica que es orientativo y recomienda verificar con fuentes. NO inventes referencias."
            "\n- NO inventes fuentes adicionales, datos ni estudios."
            "\n- Si el usuario solicita una gráfica o visualización, incluye una tabla breve con los datos numéricos usados."
        )
    else:
        user_parts.append(
            "\nNo se encontraron fuentes en las búsquedas. "
            "Puedes responder con conocimiento general pero DEBES indicar que la respuesta es orientativa y que se recomienda verificar con fuentes primarias o activar búsqueda (PubMed, web, Ominis) para evidencia. "
            "PROHIBIDO: NO uses [1], [2] ni ningún número entre corchetes; NO incluyas enlaces, URLs ni referencias bibliográficas; NO inventes estudios, autores ni fuentes. "
            "Si el usuario solicita una gráfica, incluye una tabla breve con los datos numéricos usados."
        )

    messages.append(ChatMessage.from_user("\n".join(user_parts)))

    return messages


def build_research_messages(
    question: str,
    documents: list[Document],
    plan: dict | None = None,
    history: list[dict] | None = None,
    image_description: str = "",
    file_context: str = "",
) -> list[ChatMessage]:
    """
    Build ChatMessage objects for research mode.
    Provides a structured plan and evidence list for a final report.
    """
    messages: list[ChatMessage] = []
    research_system = _current_datetime_context() + "\n\n" + RESEARCH_SYSTEM_PROMPT
    messages.append(ChatMessage.from_system(research_system))

    if history:
        for msg in history:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "user":
                messages.append(ChatMessage.from_user(content))
            elif role == "assistant":
                messages.append(ChatMessage.from_assistant(content))

    user_parts: list[str] = []

    if plan:
        focus = plan.get("focus", "")
        queries = plan.get("queries", [])
        sections = plan.get("sections", [])
        plan_text = "PLAN DE INVESTIGACIÓN:\n"
        if focus:
            plan_text += f"- Enfoque: {focus}\n"
        if queries:
            plan_text += "- Consultas sugeridas:\n"
            for q in queries:
                plan_text += f"  - {q}\n"
        if sections:
            plan_text += "- Secciones del reporte:\n"
            for s in sections:
                plan_text += f"  - {s}\n"
        user_parts.append(plan_text)

    # Detect phase FIRST (needed for content sizing below)
    is_phase2 = False
    if history and len(history) >= 2:
        for msg in history:
            if msg.get("role") == "assistant" and "?" in (msg.get("content") or "") and len(msg.get("content", "")) > 50:
                is_phase2 = True
                break

    if documents:
        source_text = "EVIDENCIA DISPONIBLE (usa [N] para citar):\n"
        for i, doc in enumerate(documents, 1):
            raw_type = doc.meta.get("source_type", "rag") or "rag"
            source_type = "OMINIS" if raw_type == "rag" else raw_type.upper()
            title = doc.meta.get("title", "Sin título")
            url = doc.meta.get("url", "")
            citation = doc.meta.get("citation", "")
            # Research reports get much more content per source
            max_content = 4000 if (plan and is_phase2) else (1500 if plan else 800)
            content = (doc.content or "")[:max_content]

            source_text += f"\n[{i}] {source_type} — {title}\n"
            source_text += f"URL: {url}\n"
            if citation:
                source_text += f"Cita: {citation}\n"
            source_text += f"Contenido: {content}\n---"
        user_parts.append(source_text)

    if file_context:
        user_parts.append(f"\nARCHIVO ADJUNTO (contenido extraído):\n{file_context}")

    if image_description:
        user_parts.append(f"\nANÁLISIS DE IMAGEN ADJUNTA:\n{image_description}")

    user_parts.append(f"\nPregunta del usuario: {question}")

    if is_phase2:
        # Extract the original topic from history for focus
        original_topic_text = ""
        user_specs_text = ""
        if history:
            for msg in history:
                if msg.get("role") == "user":
                    if not original_topic_text:
                        original_topic_text = msg.get("content", "")
                    else:
                        user_specs_text += msg.get("content", "") + " "

        user_parts.append(
            "\nFASE 2: GENERA EL REPORTE COMPLETO.\n"
            f"TEMA PRINCIPAL: {original_topic_text}\n"
            f"ESPECIFICACIONES DEL USUARIO: {user_specs_text} {question}\n\n"
            "REGLA CRÍTICA: Mantente ESTRICTAMENTE en el tema principal.\n\n"
            "CONTEXTO: Este es un reporte CIENTÍFICO/MÉDICO para investigadores.\n"
            "Usa lenguaje técnico-científico apropiado y referencia correctamente.\n\n"
            "INSTRUCCIONES PARA EL REPORTE:\n"
            "- Reporte extenso y detallado (mínimo 3000 palabras).\n"
            "- Analiza CADA fuente relevante en detalle. Dedica al menos un párrafo a cada una.\n"
            "- Usa SOLO datos LITERALES de las fuentes [N].\n"
            "- Cuando menciones autores, copia los NOMBRES EXACTOS de la fuente (no escribas 'Autores').\n"
            "- Cuando menciones un título, copia el TÍTULO EXACTO de la fuente (no lo parafrasees).\n"
            "- NUNCA inventes autores, títulos, revistas ni URLs.\n"
            "- Cita con [N]. Ejemplo: 'Según el estudio de Liu H, Xing F, et al. [3], se encontró...' En el cuerpo NO repitas el formato completo de la referencia; solo el número [N].\n"
            "- Compara hallazgos entre fuentes. Señala coincidencias y discrepancias.\n"
            "- Si una fuente no tiene datos relevantes, no la cites.\n\n"
            "FORMATO Markdown:\n"
            "# Título descriptivo del reporte\n"
            "## Resumen ejecutivo\n"
            "## Metodología de búsqueda\n"
            "## Contexto y antecedentes\n"
            "## Hallazgos principales\n"
            "## Análisis detallado por subtema\n"
            "## Discusión e implicaciones clínicas\n"
            "## Limitaciones\n"
            "## Conclusiones y recomendaciones\n"
            "## Referencias\n\n"
            "REFERENCIAS: Una sola sección al final. Para cada fuente citada en el reporte, escribe UNA línea con datos REALES copiados de la EVIDENCIA DISPONIBLE: Nombres de autores. \"Título exacto del artículo\". Fuente (Año). URL. No uses texto placeholder; no dupliques la misma referencia; no pongas una segunda lista de referencias en otro lugar.\n"
            "GRÁFICAS: Incluye una gráfica (bloque ```chart con JSON) SOLO si hay datos cuantitativos comparativos que aporten valor. Si no es claro o sería confuso, no incluyas gráfica. Eje X = categorías (ej. Año, Tratamiento); Eje Y = magnitud numérica (ej. Número de estudios, Prevalencia (%)). Nunca pongas \"Año\" en el eje Y si los valores son números como 0.2 o 0.5.\n"
        )
    else:
        user_parts.append(
            "\nFASE 1: Sé BREVE y conciso. Responde en máximo 10-15 líneas:\n"
            "1. Una oración sobre las fuentes encontradas.\n"
            "2. Lista corta de las secciones propuestas para el reporte.\n"
            "3. Exactamente 3-4 preguntas breves para acotar el alcance.\n"
            "Termina pidiendo al usuario que responda las preguntas.\n"
            "NO generes el reporte. NO inventes fuentes. Sé directo."
        )

    messages.append(ChatMessage.from_user("\n".join(user_parts)))
    return messages


# ---------------------------------------------------------------------------
# Pipeline Manager – one pipeline per model, shared retriever/embedder
# ---------------------------------------------------------------------------

class PipelineManager:
    """
    Manages Haystack RAG components using OllamaChatGenerator (Haystack 2.23).
    Uses PgvectorDocumentStore for persistent storage.
    Shares the same document store and embedding model across models.
    Includes a dedicated vision generator for image analysis.
    """

    def __init__(self):
        self._generators: dict[str, OllamaChatGenerator] = {}
        self._vision_generator: Optional[OllamaChatGenerator] = None
        self._text_embedder: Optional[SentenceTransformersTextEmbedder] = None
        self._retriever: Optional[PgvectorEmbeddingRetriever] = None
        self._document_store: Optional[PgvectorDocumentStore] = None
        self._ready = False

    @property
    def ready(self) -> bool:
        return self._ready

    @property
    def available_models(self) -> list[dict]:
        """Return public-facing metadata for all registered models."""
        return [
            {
                "id": m.public_id,
                "displayName": m.display_name,
                "description": m.description,
                "versionLabel": getattr(m, "version_label", "") or "",
                "isDefault": m.is_default,
            }
            for m in get_model_registry().values()
        ]

    def get_generator(self, model_id: str | None = None):
        """Get the chat generator for a given model (Ollama or OpenAI). Rebuilds generators if cache was invalidated."""
        if not self._generators:
            self._rebuild_generators()
        mid = model_id if model_id and model_id in self._generators else DEFAULT_MODEL_ID
        generator = self._generators.get(mid)
        if generator is None:
            raise RuntimeError(f"Generator for model '{mid}' not initialized.")
        return generator

    def invalidate_generators(self) -> None:
        """Clear generator cache so next get_generator() rebuilds from current registry (e.g. after LLM config change)."""
        self._generators.clear()

    def _rebuild_generators(self) -> None:
        """Rebuild _generators from current get_model_registry() (used after invalidate_generators)."""
        for model_id, model_cfg in get_model_registry().items():
            if getattr(model_cfg, "use_openai", False) and model_cfg.openai_api_base:
                power_key = getattr(settings, "power_api_key", "EMPTY") or "EMPTY"
                power_timeout = getattr(settings, "power_timeout", 120) or 120
                generator = OpenAIChatGenerator(
                    model=model_cfg.openai_model,
                    api_key=Secret.from_token(power_key),
                    api_base_url=model_cfg.openai_api_base,
                    timeout=power_timeout,
                    generation_kwargs={
                        "temperature": model_cfg.temperature,
                        "max_tokens": model_cfg.num_predict,
                    },
                )
                self._generators[model_id] = generator
            else:
                ollama_url = model_cfg.ollama_url or settings.ollama_url
                timeout = (getattr(model_cfg, "timeout", None) or 0) or getattr(settings, "ollama_timeout", 90) or 90
                generator = OllamaChatGenerator(
                    model=model_cfg.ollama_model,
                    url=ollama_url,
                    timeout=timeout,
                    generation_kwargs={
                        "temperature": model_cfg.temperature,
                        "num_predict": model_cfg.num_predict,
                        "num_gpu": model_cfg.num_gpu,
                    },
                )
                self._generators[model_id] = generator

    def get_vision_generator(self) -> Optional[OllamaChatGenerator]:
        """Get the vision-capable OllamaChatGenerator."""
        return self._vision_generator

    def get_text_embedder(self):
        """Returns SentenceTransformersTextEmbedder or ExternalTextEmbedder (when embedding_service_url set)."""
        if self._text_embedder is None:
            raise RuntimeError("Text embedder not initialized.")
        return self._text_embedder

    def get_retriever(self) -> PgvectorEmbeddingRetriever:
        if self._retriever is None:
            raise RuntimeError("Retriever not initialized.")
        return self._retriever

    def get_document_store(self) -> PgvectorDocumentStore:
        if self._document_store is None:
            raise RuntimeError("Document store not initialized.")
        return self._document_store

    def get_model_id(self, model_id: str | None = None) -> str:
        """Resolve a model ID (accepts both internal and public IDs)."""
        if not model_id:
            return DEFAULT_MODEL_ID
        registry = get_model_registry()
        if model_id in registry:
            return model_id
        for mid, cfg in registry.items():
            if cfg.public_id == model_id:
                return mid
        return DEFAULT_MODEL_ID

    def get_public_model_id(self, internal_model_id: str) -> str:
        """Map an internal model ID to its public-facing ID."""
        registry = get_model_registry()
        cfg = registry.get(internal_model_id)
        return cfg.public_id if cfg else "ominis-2.0"

    async def initialize(self):
        """Build all generators, embedders, and retriever. Called at app startup."""
        logger.info("Initializing PipelineManager (Haystack 2.23 + PgvectorDocumentStore)...")

        # 1. Document store (persistent PostgreSQL via pgvector)
        self._document_store = get_document_store()
        doc_count = self._document_store.count_documents()
        logger.info(f"PgvectorDocumentStore has {doc_count} documents")

        # If empty, try one-time S3 migration
        if doc_count == 0:
            logger.info("Attempting S3 migration for initial data...")
            doc_count = await migrate_chunks_from_s3()

        # 2. Shared text embedder (for query embedding): external bge service or SentenceTransformers
        if (getattr(settings, "embedding_service_url", None) or "").strip():
            self._text_embedder = ExternalTextEmbedder()
            self._text_embedder.warm_up()
            logger.info("Using external embedding service: %s", settings.embedding_service_url.strip())
        else:
            self._text_embedder = SentenceTransformersTextEmbedder(
                model=settings.embedding_model,
            )
            self._text_embedder.warm_up()

        # 3. PgvectorEmbeddingRetriever (Haystack native)
        self._retriever = PgvectorEmbeddingRetriever(
            document_store=self._document_store,
            top_k=5,
        )

        # 4. Build one generator per registered model (Ollama or OpenAI-compatible e.g. vLLM)
        for model_id, model_cfg in get_model_registry().items():
            if getattr(model_cfg, "use_openai", False) and model_cfg.openai_api_base:
                logger.info(
                    f"Creating OpenAIChatGenerator for '{model_cfg.display_name}' "
                    f"-> {model_cfg.openai_api_base} (model={model_cfg.openai_model})"
                )
                power_key = getattr(settings, "power_api_key", "EMPTY") or "EMPTY"
                power_timeout = getattr(settings, "power_timeout", 120) or 120
                generator = OpenAIChatGenerator(
                    model=model_cfg.openai_model,
                    api_key=Secret.from_token(power_key),
                    api_base_url=model_cfg.openai_api_base,
                    timeout=power_timeout,
                    generation_kwargs={
                        "temperature": model_cfg.temperature,
                        "max_tokens": model_cfg.num_predict,
                    },
                )
                self._generators[model_id] = generator
                logger.info(f"  OpenAIChatGenerator '{model_id}' ready.")
            else:
                ollama_url = model_cfg.ollama_url or settings.ollama_url
                logger.info(
                    f"Creating OllamaChatGenerator for '{model_cfg.display_name}' "
                    f"-> Ollama at {ollama_url}"
                )
                timeout = (getattr(model_cfg, "timeout", None) or 0) or getattr(settings, "ollama_timeout", 90) or 90
                generator = OllamaChatGenerator(
                    model=model_cfg.ollama_model,
                    url=ollama_url,
                    timeout=timeout,
                    generation_kwargs={
                        "temperature": model_cfg.temperature,
                        "num_predict": model_cfg.num_predict,
                        "num_gpu": model_cfg.num_gpu,
                    },
                )
                self._generators[model_id] = generator
                logger.info(f"  OllamaChatGenerator '{model_id}' ready.")

        # 5. Vision generator (separate OllamaChatGenerator with vision model)
        if settings.vision_model:
            vision_url = settings.ollama_url
            logger.info(
                f"Creating Vision OllamaChatGenerator "
                f"(model={settings.vision_model}) -> {vision_url}"
            )
            vision_timeout = getattr(settings, "ollama_timeout", 90) or 90
            self._vision_generator = OllamaChatGenerator(
                model=settings.vision_model,
                url=vision_url,
                timeout=vision_timeout,
                generation_kwargs={
                    "temperature": 0.3,
                    "num_predict": 1024,
                },
            )
            logger.info("  Vision OllamaChatGenerator ready.")

        self._ready = True
        logger.info(
            f"PipelineManager ready with {len(self._generators)} model(s), "
            f"{doc_count} documents in pgvector store."
        )


# ---------------------------------------------------------------------------
# Global singleton
# ---------------------------------------------------------------------------

_pipeline_manager: Optional[PipelineManager] = None


def get_pipeline_manager() -> PipelineManager:
    """Get the global PipelineManager. Must be initialized first."""
    global _pipeline_manager
    if _pipeline_manager is None or not _pipeline_manager.ready:
        raise RuntimeError("PipelineManager not initialized.")
    return _pipeline_manager


async def initialize_pipeline():
    """Initialize the global PipelineManager. Called during app startup."""
    global _pipeline_manager
    _pipeline_manager = PipelineManager()
    await _pipeline_manager.initialize()
