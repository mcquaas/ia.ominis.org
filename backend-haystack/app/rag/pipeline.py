"""
Haystack RAG Pipeline definition — Haystack 2.23 native architecture.
"""

import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Optional

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
    ModelConfig,
    get_model_registry,
    get_settings,
)
from app.vast_serverless.generators import (
    ServerlessOllamaChatGenerator,
    ServerlessOpenAIChatGenerator,
)
from app.rag.document_store import get_document_store, migrate_chunks_from_s3

logger = logging.getLogger(__name__)
settings = get_settings()


def _vast_api_key() -> str:
    return (getattr(settings, "vast_api_key", None) or os.environ.get("VAST_API_KEY", "") or "").strip()


def _vast_cost(override: int) -> int:
    if override and override > 0:
        return int(override)
    return int(getattr(settings, "vast_serverless_default_cost", 500) or 500)


def _vast_client_timeout() -> float:
    """HTTP + worker timeout for vastai SDK (cold starts need many minutes)."""
    return float(getattr(settings, "vast_serverless_client_timeout", 900) or 900)


def _anthropic_api_key_for_model(model_cfg: ModelConfig) -> str:
    from app.admin.llm_credentials_read import get_stored_provider_token

    t = get_stored_provider_token(model_cfg.id, "claude")
    if t:
        return t
    return os.environ.get("ANTHROPIC_API_KEY", "") or ""


def _openai_api_key_for_model(model_cfg: ModelConfig) -> str:
    """Stored dashboard token per provider, then extra_params.api_key_env, then power_api_key."""
    from app.admin.llm_credentials_read import credential_key_for_provider, get_stored_provider_token

    lp = getattr(model_cfg, "llm_provider", None) or "ominis"
    ck = credential_key_for_provider(lp)
    if ck:
        tok = get_stored_provider_token(model_cfg.id, ck)
        if tok:
            return tok
    ep = getattr(model_cfg, "extra_params", None) or {}
    if isinstance(ep, dict):
        envn = (ep.get("api_key_env") or "").strip()
        if envn:
            return os.environ.get(envn, "") or ""
    return (getattr(settings, "power_api_key", None) or "EMPTY") or "EMPTY"


def _openai_http_timeout_for_model(model_cfg: ModelConfig) -> float:
    t = getattr(model_cfg, "timeout", None) or 0
    try:
        if t and float(t) > 0:
            return float(t)
    except (TypeError, ValueError):
        pass
    return float(getattr(settings, "power_timeout", 120) or 120)


def openai_model_uses_completion_tokens_only(openai_model: str) -> bool:
    """
    GPT-5 and o-series Chat Completions: use max_completion_tokens (not max_tokens) and
    do not send custom temperature — API only accepts the default sampling.
    """
    m = (openai_model or "").strip().lower()
    if m.startswith("gpt-5"):
        return True
    if re.match(r"^o[0-9]", m):
        return True
    if m.startswith(("o1", "o3", "o4")):
        return True
    return False


def openai_chat_completion_generation_kwargs(
    openai_model: str,
    *,
    temperature: float | None,
    num_predict: int | None,
) -> dict[str, Any]:
    """
    Map dashboard fields to OpenAI Chat Completions parameters.
    GPT-5 and o-series models require max_completion_tokens; max_tokens may be rejected.
    """
    out: dict[str, Any] = {}
    if temperature is not None and not openai_model_uses_completion_tokens_only(openai_model):
        out["temperature"] = float(temperature)
    n = int(num_predict) if num_predict is not None else 1024
    n = max(1, min(n, 128_000))
    m = (openai_model or "").strip().lower()
    if openai_model_uses_completion_tokens_only(m):
        out["max_completion_tokens"] = n
    else:
        out["max_tokens"] = n
    return out


def openai_endpoint_should_use_responses_api(openai_model: str, api_base_url: str) -> bool:
    """
    Some OpenAI models (e.g. gpt-5.4) may reject /v1/chat/completions with "not a chat model";
    the Responses API (/v1/responses) accepts the same accounts. Only enable for official
    api.openai.com so vLLM/Ollama-compatible bases keep using chat/completions.
    """
    if "api.openai.com" not in (api_base_url or "").lower():
        return False
    m = (openai_model or "").strip().lower()
    return m.startswith("gpt-5.4")


def make_openai_generator_for_research(
    *,
    openai_model: str,
    api_base_url: str,
    api_key: str,
    timeout: float,
    temperature: float,
    num_predict: int,
    log_label: str = "",
) -> Any:
    """
    Build OpenAIChatGenerator or OpenAIResponsesChatGenerator for research / dashboard overrides.
    """
    from app.rag.openai_responses_chat import OpenAIResponsesChatGenerator

    om = openai_model or ""
    gk = openai_chat_completion_generation_kwargs(
        om,
        temperature=temperature,
        num_predict=num_predict,
    )
    use_resp = openai_endpoint_should_use_responses_api(om, api_base_url)
    if not use_resp and not openai_model_uses_completion_tokens_only(om):
        gk["top_p"] = 0.9
    if use_resp:
        if log_label:
            logger.info(
                "OpenAIResponsesChatGenerator [%s] -> %s (model=%s)",
                log_label,
                (api_base_url or "").rstrip("/")[:80],
                om,
            )
        return OpenAIResponsesChatGenerator(
            model=om,
            api_key=api_key,
            api_base_url=api_base_url or "",
            timeout=timeout,
            default_generation_kwargs=gk,
        )
    return OpenAIChatGenerator(
        model=om,
        api_key=Secret.from_token(api_key),
        api_base_url=api_base_url,
        timeout=timeout,
        generation_kwargs=gk,
    )


def _make_openai_remote_generator(model_cfg: ModelConfig) -> Any:
    """Direct OpenAI-compatible HTTP generator: Chat Completions or Responses API as needed."""
    return make_openai_generator_for_research(
        openai_model=model_cfg.openai_model or "",
        api_base_url=model_cfg.openai_api_base or "",
        api_key=_openai_api_key_for_model(model_cfg),
        timeout=_openai_http_timeout_for_model(model_cfg),
        temperature=float(model_cfg.temperature),
        num_predict=int(model_cfg.num_predict or 1024),
        log_label=getattr(model_cfg, "display_name", "") or model_cfg.id,
    )


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

# When refiner_hint=True (Ominis 2.0), model can request a second phase from Med or Research
REFINAR_INSTRUCTION = (
    "\n\nAl final de tu respuesta, si la pregunta se beneficiaría de una opinión clínica más precisa (Ominis Med) "
    "o de investigación con más fuentes (Research), escribe exactamente en una nueva línea: [REFINAR:med] o [REFINAR:research]. "
    "Si no hace falta, no escribas esa línea."
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
    refiner_hint: bool = False,
    extra_system_suffix: str | None = None,
) -> list[ChatMessage]:
    """
    Build a list of ChatMessage objects for the OllamaChatGenerator.
    This is the Haystack-native way to construct prompts with proper roles.
    If system_prompt is provided (e.g. from dashboard config), it overrides the default SYSTEM_PROMPT.
    max_content_per_doc: max chars per document content (smaller = faster prefill for large models like gpt-oss).
    med_orchestrator: when True (Ominis Med as orchestrator), appends instructions to decide image/file relevance and table/chart use.
    refiner_hint: when True (Ominis 2.0), adds instruction so the model can request a follow-up from Med or Research via [REFINAR:med] / [REFINAR:research].
    extra_system_suffix: optional transparency instructions (e.g. which search tools ran).
    """
    messages: list[ChatMessage] = []

    # 1. System message (per-model override from dashboard or default)
    prompt = (system_prompt or "").strip() or SYSTEM_PROMPT
    if med_orchestrator:
        prompt = prompt.rstrip() + MED_ORCHESTRATOR_INSTRUCTION
    if refiner_hint:
        prompt = prompt.rstrip() + REFINAR_INSTRUCTION
    if extra_system_suffix:
        prompt = prompt.rstrip() + "\n\n" + extra_system_suffix.strip()
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
            cap = max_content_per_doc if raw_type != "clinicaltrials" else max(max_content_per_doc, 2400)
            content = (doc.content or "")[:cap]
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
        if any((d.meta or {}).get("source_type") == "clinicaltrials" for d in documents):
            user_parts.append(
                "\nPRIORIDAD (ENSAYOS CLÍNICOS — ClinicalTrials.gov, criterio México en la API):\n"
                "- Responde PRIMERO con la información de las fuentes marcadas CLINICALTRIALS [N] (estado, fechas, sedes en México, condiciones, intervenciones, resumen).\n"
                "- Redacta en español mexicano; si el registro trae texto en inglés, traduce o parafrasea los datos (no dejes estados crudos en inglés si ya hay etiqueta en español en el contenido).\n"
                "- Incluye en la respuesta metadatos concretos de cada ensayo relevante (estado, inicio, sitios mexicanos cuando consten).\n"
                "- Las demás fuentes (OMINIS, PubMed, web, etc.) son complementarias: no las uses para contradecir datos explícitos de los ensayos citados.\n"
                "- Cita con [N] cada ensayo del que tomes datos."
            )

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
        if any((d.meta or {}).get("source_type") == "clinicaltrials" for d in documents):
            user_parts.append(
                "\nPRIORIDAD (ENSAYOS CLÍNICOS — ClinicalTrials.gov):\n"
                "- Si el tema incluye ensayos o estudios clínicos, prioriza las fuentes CLINICALTRIALS [N] en el reporte y traduce/parafrasea al español los metadatos del registro.\n"
                "- No contradigas con fuentes web genéricas lo que indiquen explícitamente esos registros."
            )

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
        self._generators: dict[str, Any] = {}
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

    def _setup_vision_generator(self, vk: str, v_ollama_ep: str) -> None:
        """Configure multimodal vision: Ollama ImageContent or OpenAI-compatible (handled in vision.py)."""
        from app.admin.vision_runtime import get_vision_runtime_settings, vision_prefers_openai_multimodal

        vr = get_vision_runtime_settings()
        if vision_prefers_openai_multimodal(vr):
            self._vision_generator = None
            logger.info("Vision: OpenAI-compatible multimodal (dashboard or QWEN_VL); Ollama vision generator skipped.")
            return
        if not vr.use_ollama_vision:
            self._vision_generator = None
            return
        vm = (vr.vision_model or "").strip()
        if not vm:
            self._vision_generator = None
            return
        qwen_http = (getattr(settings, "qwen_vl_api_url", "") or "").strip()
        qwen_slv = (getattr(settings, "vast_serverless_qwen_vl_endpoint", "") or "").strip()
        vision_timeout = int(getattr(settings, "ollama_timeout", 90) or 90)
        vision_url = (vr.ollama_url or settings.ollama_url or "").rstrip("/")
        if getattr(vr, "force_direct_ollama", False):
            logger.info(
                "Creating Vision OllamaChatGenerator (dashboard) model=%s -> %s",
                vm,
                vision_url,
            )
            self._vision_generator = OllamaChatGenerator(
                model=vm,
                url=vision_url,
                timeout=vision_timeout,
                generation_kwargs={
                    "temperature": 0.3,
                    "num_predict": 1024,
                },
            )
            logger.info("  Vision OllamaChatGenerator ready (direct).")
            return
        if v_ollama_ep and vk and not qwen_http and not (qwen_slv and vk):
            logger.info(
                "Creating Vision ServerlessOllamaChatGenerator (model=%s) -> endpoint=%s",
                vm,
                v_ollama_ep,
            )
            vst = _vast_client_timeout()
            oc = int(getattr(settings, "vast_serverless_ollama_cost", 0) or 0)
            self._vision_generator = ServerlessOllamaChatGenerator(
                endpoint_name=v_ollama_ep,
                model=vm,
                api_key=vk,
                cost=_vast_cost(oc),
                timeout=vst,
                worker_timeout=vst,
                generation_kwargs={
                    "temperature": 0.3,
                    "num_predict": 1024,
                },
            )
            logger.info("  Vision ServerlessOllamaChatGenerator ready.")
        elif not qwen_http and not (qwen_slv and vk):
            logger.info(
                "Creating Vision OllamaChatGenerator (model=%s) -> %s",
                vm,
                vision_url,
            )
            self._vision_generator = OllamaChatGenerator(
                model=vm,
                url=vision_url,
                timeout=vision_timeout,
                generation_kwargs={
                    "temperature": 0.3,
                    "num_predict": 1024,
                },
            )
            logger.info("  Vision OllamaChatGenerator ready.")
        else:
            self._vision_generator = None
            logger.info("Vision: Qwen-VL URL or Vast Qwen-VL active; Ollama vision generator skipped.")

    def rebuild_vision_generator(self) -> None:
        """Reload vision generator after dashboard vision settings change."""
        vk = _vast_api_key()
        v_ollama_ep = (getattr(settings, "vast_serverless_ollama_endpoint", "") or "").strip()
        self._setup_vision_generator(vk, v_ollama_ep)

    def _rebuild_generators(self) -> None:
        """Rebuild _generators from current get_model_registry() (used after invalidate_generators)."""
        vk = _vast_api_key()
        v_ollama_ep = (getattr(settings, "vast_serverless_ollama_endpoint", "") or "").strip()
        for model_id, model_cfg in get_model_registry().items():
            if model_id == "research-8k":
                try:
                    from app.rag.openscholar import get_openscholar_generator

                    self._generators["research-8k"] = get_openscholar_generator()
                    logger.info("  research-8k (Ominis Research) ready.")
                except Exception as e:
                    logger.warning("research-8k generator skipped: %s", e)
                continue
            if model_id == "research-128k":
                try:
                    from app.rag.openscholar import get_openscholar_128k_generator

                    self._generators["research-128k"] = get_openscholar_128k_generator()
                    logger.info("  research-128k (Ominis Research 128K) ready.")
                except Exception as e:
                    logger.warning("research-128k generator skipped: %s", e)
                continue
            if getattr(model_cfg, "use_anthropic", False):
                oto = _openai_http_timeout_for_model(model_cfg)
                akey = _anthropic_api_key_for_model(model_cfg)
                from app.rag.anthropic_chat import AnthropicChatGenerator

                self._generators[model_id] = AnthropicChatGenerator(
                    model=model_cfg.openai_model,
                    api_key=akey,
                    timeout=oto,
                    generation_kwargs={
                        "temperature": model_cfg.temperature,
                        "max_tokens": model_cfg.num_predict,
                    },
                )
            elif getattr(model_cfg, "use_openai", False) and model_cfg.openai_api_base:
                v_ep = (getattr(model_cfg, "vast_serverless_endpoint", None) or "").strip()
                if v_ep and vk:
                    oc = int(getattr(settings, "vast_serverless_power_cost", 0) or 0)
                    vst = _vast_client_timeout()
                    self._generators[model_id] = ServerlessOpenAIChatGenerator(
                        endpoint_name=v_ep,
                        model=model_cfg.openai_model,
                        api_key=vk,
                        cost=_vast_cost(oc),
                        timeout=vst,
                        worker_timeout=vst,
                        generation_kwargs=openai_chat_completion_generation_kwargs(
                            model_cfg.openai_model or "",
                            temperature=model_cfg.temperature,
                            num_predict=model_cfg.num_predict,
                        ),
                    )
                elif "vast-serverless.invalid" not in (model_cfg.openai_api_base or ""):
                    self._generators[model_id] = _make_openai_remote_generator(model_cfg)
                else:
                    logger.warning(
                        "Model %s needs VAST_API_KEY / vast_api_key for Serverless or a real power_api_url",
                        model_id,
                    )
            elif v_ollama_ep and vk and not getattr(model_cfg, "use_openai", False) and not getattr(
                model_cfg, "use_anthropic", False
            ):
                vst = _vast_client_timeout()
                oc = int(getattr(settings, "vast_serverless_ollama_cost", 0) or 0)
                self._generators[model_id] = ServerlessOllamaChatGenerator(
                    endpoint_name=v_ollama_ep,
                    model=model_cfg.ollama_model,
                    api_key=vk,
                    cost=_vast_cost(oc),
                    timeout=vst,
                    worker_timeout=vst,
                    generation_kwargs={
                        "temperature": model_cfg.temperature,
                        "num_predict": model_cfg.num_predict,
                        "num_gpu": model_cfg.num_gpu,
                    },
                )
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
        # Legacy public id before ominis-2.0-research
        if model_id == "ominis-research":
            model_id = "ominis-2.0-research"
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
        vk = _vast_api_key()
        v_ollama_ep = (getattr(settings, "vast_serverless_ollama_endpoint", "") or "").strip()
        for model_id, model_cfg in get_model_registry().items():
            if model_id == "research-8k":
                try:
                    from app.rag.openscholar import get_openscholar_generator

                    self._generators["research-8k"] = get_openscholar_generator()
                    logger.info("  research-8k (Ominis Research) ready.")
                except Exception as e:
                    logger.warning("research-8k generator skipped: %s", e)
                continue
            if model_id == "research-128k":
                try:
                    from app.rag.openscholar import get_openscholar_128k_generator

                    self._generators["research-128k"] = get_openscholar_128k_generator()
                    logger.info("  research-128k (Ominis Research 128K) ready.")
                except Exception as e:
                    logger.warning("research-128k generator skipped: %s", e)
                continue
            if getattr(model_cfg, "use_anthropic", False):
                logger.info(
                    "Creating AnthropicChatGenerator for '%s' -> model=%s",
                    model_cfg.display_name,
                    model_cfg.openai_model,
                )
                oto = _openai_http_timeout_for_model(model_cfg)
                akey = _anthropic_api_key_for_model(model_cfg)
                from app.rag.anthropic_chat import AnthropicChatGenerator

                self._generators[model_id] = AnthropicChatGenerator(
                    model=model_cfg.openai_model,
                    api_key=akey,
                    timeout=oto,
                    generation_kwargs={
                        "temperature": model_cfg.temperature,
                        "max_tokens": model_cfg.num_predict,
                    },
                )
                logger.info("  AnthropicChatGenerator '%s' ready.", model_id)
            elif getattr(model_cfg, "use_openai", False) and model_cfg.openai_api_base:
                v_ep = (getattr(model_cfg, "vast_serverless_endpoint", None) or "").strip()
                if v_ep and vk:
                    logger.info(
                        "Creating ServerlessOpenAIChatGenerator for '%s' -> endpoint=%s (model=%s)",
                        model_cfg.display_name,
                        v_ep,
                        model_cfg.openai_model,
                    )
                    oc = int(getattr(settings, "vast_serverless_power_cost", 0) or 0)
                    vst = _vast_client_timeout()
                    self._generators[model_id] = ServerlessOpenAIChatGenerator(
                        endpoint_name=v_ep,
                        model=model_cfg.openai_model,
                        api_key=vk,
                        cost=_vast_cost(oc),
                        timeout=vst,
                        worker_timeout=vst,
                        generation_kwargs=openai_chat_completion_generation_kwargs(
                            model_cfg.openai_model or "",
                            temperature=model_cfg.temperature,
                            num_predict=model_cfg.num_predict,
                        ),
                    )
                    logger.info("  ServerlessOpenAIChatGenerator '%s' ready.", model_id)
                elif "vast-serverless.invalid" not in (model_cfg.openai_api_base or ""):
                    logger.info(
                        "Creating OpenAI remote generator for '%s' -> %s (model=%s)",
                        model_cfg.display_name,
                        model_cfg.openai_api_base,
                        model_cfg.openai_model,
                    )
                    self._generators[model_id] = _make_openai_remote_generator(model_cfg)
                    logger.info("  OpenAI remote generator '%s' ready.", model_id)
                else:
                    logger.warning(
                        "Skipping model %s: set VAST_API_KEY and vast_serverless_power_endpoint or power_api_url",
                        model_id,
                    )
            elif v_ollama_ep and vk and not getattr(model_cfg, "use_openai", False) and not getattr(
                model_cfg, "use_anthropic", False
            ):
                logger.info(
                    "Creating ServerlessOllamaChatGenerator for '%s' -> endpoint=%s (model=%s)",
                    model_cfg.display_name,
                    v_ollama_ep,
                    model_cfg.ollama_model,
                )
                vst = _vast_client_timeout()
                oc = int(getattr(settings, "vast_serverless_ollama_cost", 0) or 0)
                self._generators[model_id] = ServerlessOllamaChatGenerator(
                    endpoint_name=v_ollama_ep,
                    model=model_cfg.ollama_model,
                    api_key=vk,
                    cost=_vast_cost(oc),
                    timeout=vst,
                    worker_timeout=vst,
                    generation_kwargs={
                        "temperature": model_cfg.temperature,
                        "num_predict": model_cfg.num_predict,
                        "num_gpu": model_cfg.num_gpu,
                    },
                )
                logger.info("  ServerlessOllamaChatGenerator '%s' ready.", model_id)
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

        # 5. Vision generator (dashboard + env; OpenAI multimodal vs Ollama)
        self._setup_vision_generator(vk, v_ollama_ep)

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
