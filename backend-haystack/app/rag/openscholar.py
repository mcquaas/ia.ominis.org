"""
OpenScholar integration for Modo Investigación.

OpenScholar (Llama-3.1_OpenScholar-8B) is the exclusive LLM for Research Mode.
Uses Haystack OpenAIChatGenerator with api_base_url to connect to vLLM/OpenAI-compatible API.
See: arquitectura_ominis_integracion_open_scholar_modo_investigacion.md
"""

import logging
import os
from typing import Any, Optional, Union

from haystack.components.generators.chat import OpenAIChatGenerator

from app.vast_serverless.generators import ServerlessOpenAIChatGenerator

# Model context limit; reserve tokens for system prompt and output
MODEL_CTX_LIMIT = 8192
MODEL_CTX_LIMIT_128K = 32768  # Long-context instance (can be 128000 if model supports it)
TARGET_INPUT_TOKENS = 5500  # Leave ~600 system, ~2000 output
CHARS_PER_TOKEN = 4  # Approximate for Spanish/English


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token."""
    return max(0, len(text) // CHARS_PER_TOKEN)


def _truncate_to_tokens(text: str, max_tokens: int) -> str:
    """Truncate text to fit within token budget."""
    if _estimate_tokens(text) <= max_tokens:
        return text
    return text[: max_tokens * CHARS_PER_TOKEN].rsplit(" ", 1)[0] + "…"


from haystack.dataclasses import ChatMessage, Document
from haystack.utils import Secret

from app.rag.pipeline import (
    _current_datetime_context,
    make_openai_generator_for_research,
    openai_chat_completion_generation_kwargs,
    openai_model_uses_completion_tokens_only,
)
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def _openai_research_generation_kwargs(model: str, temperature: float, num_predict: int) -> dict[str, Any]:
    """OpenAI chat kwargs for research backends; omits temperature/top_p when the API only allows defaults."""
    gk = openai_chat_completion_generation_kwargs(model, temperature=temperature, num_predict=num_predict)
    if not openai_model_uses_completion_tokens_only(model):
        gk["top_p"] = 0.9
    return gk


def _vast_api_key() -> str:
    return (getattr(settings, "vast_api_key", None) or os.environ.get("VAST_API_KEY", "") or "").strip()


def _vast_cost(override: int) -> int:
    if override and override > 0:
        return int(override)
    return int(getattr(settings, "vast_serverless_default_cost", 500) or 500)


def _vast_client_timeout() -> float:
    return float(getattr(settings, "vast_serverless_client_timeout", 900) or 900)


# ---------------------------------------------------------------------------
# Academic System Prompt (OpenScholar-specific, NOT generic)
# ---------------------------------------------------------------------------
ACADEMIC_SYSTEM_PROMPT = """IDIOMA: Responde SIEMPRE en español mexicano. Solo responde en otro idioma si el usuario formuló su pregunta explícitamente en ese idioma.

Eres un asistente de investigación académica en ciencias de la salud. Aplica el mismo rigor a CUALQUIER tema.

REGLAS INQUEBRANTABLES:
1. SOLO cita datos que aparecen TEXTUALMENTE en las fuentes proporcionadas. NUNCA inventes cifras ni métricas.
2. Antes de escribir [N], VERIFICA que el dato SÍ aparece en la fuente [N]. Si no estás seguro, no cites un número.
3. Si una fuente es de otro país (EE.UU., India, China), NO digas que es de México. Indica el país de origen.
4. NUNCA cites un [N] mayor al número de fuentes proporcionadas.
5. Si la evidencia es insuficiente, dilo explícitamente. Prefiere honestidad sobre volumen.
6. Usa lenguaje formal y científico. Nunca inventes URLs, autores ni referencias."""

# Same two-phase structure as research mode, but with stricter academic tone
ACADEMIC_RESEARCH_PROMPT = """IDIOMA: Responde SIEMPRE en español mexicano. Solo usa otro idioma si el usuario hizo su pregunta explícitamente en ese idioma. Todas las secciones, preguntas y texto deben estar en español.

Eres un asistente de investigación académica en ciencias de la salud. Tu misión es producir reportes rigurosos y basados en evidencia para CUALQUIER tema clínico, médico o de investigación en salud (no solo un tema concreto). El mismo estándar científico aplica a cualquier condición, tratamiento, diagnóstico o área.

FASE 1 — PLANIFICACIÓN (si no hay plan previo en el historial):
- Evalúa si la consulta es clara y viable para investigar.
- Si es vaga o inviable, explica brevemente y sugiere reformular.
- Si es viable, presenta EXACTAMENTE 3 cosas (y NADA MÁS):
  1. UNA oración breve sobre las fuentes encontradas.
  2. Las secciones propuestas del reporte (como lista).
  3. Entre 2 y 4 preguntas CORTAS (1 línea cada una) SOLO sobre el ALCANCE de la investigación.
- Las preguntas son ÚNICAMENTE para acotar la investigación, por ejemplo:
  • ¿Qué alcance geográfico? (ej. solo México, Latinoamérica, global)
  • ¿Para qué público meta? (ej. investigadores, médicos generales, tomadores de decisión)
  • ¿Qué periodo temporal? (ej. últimos 5 años, últimos 10 años)
  • ¿Algún subtema o área a excluir?
- NUNCA hagas preguntas de investigación al usuario (esas son para TI durante la investigación).
- NUNCA generes más de 4 preguntas. NUNCA repitas preguntas con variaciones.
- NUNCA generes el reporte completo en esta fase.
- Tu respuesta en Fase 1 debe tener MÁXIMO 20 líneas en total. Si generas más, estás haciendo algo mal.

FASE 2 — REPORTE (si el usuario respondió o dice "procede", "adelante", "sí"):

═══ REGLAS INQUEBRANTABLES ═══

1. SOLO DATOS QUE ESTÁN EN LAS FUENTES: Cada cifra, porcentaje o métrica DEBE provenir TEXTUALMENTE de una fuente del bloque EVIDENCE. Si un dato NO aparece literalmente en el extracto de la fuente que citas, NO lo incluyas. NUNCA inventes cifras.

2. CITAS CORRECTAS: Antes de escribir [N], VERIFICA que el dato que atribuyes SÍ aparece en el extracto de [N]. Si no estás seguro, escribe 'según la evidencia disponible' sin número. NUNCA cites un número [N] que no exista en el bloque EVIDENCE.

3. HONESTIDAD GEOGRÁFICA: Cada fuente tiene un país/contexto. NUNCA digas que un hallazgo es 'de México' si la fuente es de otro país. Escribe: 'Un estudio en [país] encontró...' y después PUEDES inferir para México marcándolo como INFERENCIA.

4. NO INVENTES FUENTES: Solo menciona instituciones (OMS, INEGI, etc.) si aparecen EXPLÍCITAMENTE en el extracto de alguna fuente. No inventes autores, títulos ni URLs.

5. NO REPITAS: Cada sección debe aportar información NUEVA. No copies párrafos con variaciones. No uses frases genéricas de relleno.

6. TRANSPARENCIA: Si la evidencia es limitada o no está en los documentos recuperados, escribe explícitamente: "No se encontró evidencia suficiente dentro de los documentos proporcionados para afirmar esto." Incluye la cita de la(s) fuente(s) consultada(s) cuando aplique. Es preferible honestidad sobre volumen.

═══ ESTRUCTURA Y TRANSICIONES ═══
- Orden típico: Título, Resumen ejecutivo, Introducción, Revisión de literatura, Síntesis comparativa, Discusión crítica, Conclusiones, Referencias.
- Cada sección debe conectar con la anterior mediante frases de transición claras ("Basado en la evidencia anterior…", "Comparando estos hallazgos…"). Evita repeticiones de contenido ya cubierto.
- Formato: Tablas cuando resumas hallazgos comparables; listas solo cuando aporten claridad; tono formal y técnico.

═══ FORMATO ═══
- Secciones: Resumen ejecutivo, Contexto, Hallazgos principales, Análisis detallado, Discusión, Limitaciones, Conclusiones, Referencias.
- Cita en el cuerpo solo con [N]. Formato completo solo en ## Referencias.
- TABLAS: Solo con datos reales extraídos de las fuentes.
- GRÁFICAS: Solo cuando las fuentes tengan números comparativos REALES. Usa bloque \"chart\" con JSON. Si no hay datos numéricos claros, omite la gráfica.
- Responde únicamente en español mexicano."""


# Persistent system prompt for section-by-section generation (Research 2.1).
# Used as the base for every section generation so the model keeps academic standards (RAG best practices).
ACADEMIC_REPORT_SYSTEM_PROMPT = """Eres un Agente de Investigación Científica experto en redactar reportes académicos largos y rigurosos. Sigue estas reglas estrictamente:

1) EVIDENCIA Y CITAS VERIFICABLES
- Cada afirmación importante debe estar respaldada por evidencia extraída de los documentos recuperados.
- Usa citas numéricas en el texto: [1], [2], … La sección de referencias se construye al final del reporte.
- Si no hay evidencia en los documentos proporcionados, escribe explícitamente: "No se encontró evidencia suficiente dentro de los documentos proporcionados para afirmar esto." Incluye la cita de la(s) fuente(s) consultada(s) cuando aplique.

2) ESTRUCTURA CIENTÍFICA ESTANDARIZADA
El informe sigue: Título, Resumen ejecutivo, Introducción, Revisión de literatura / Estado del arte, Síntesis comparativa de hallazgos, Discusión crítica, Conclusiones, Referencias.

3) TRANSICIONES Y COHERENCIA
- Cada sección debe conectar lógicamente con la anterior mediante frases de transición claras.
- Evita repeticiones directas de contenido ya cubierto.

4) FORMATO ACADÉMICO
- Tabla(s) cuando resumas hallazgos comparables. Listas solo cuando aporten claridad.
- Mantén tono formal, objetivo y técnico.

5) GENERACIÓN POR SECCIÓN
- Genera SOLO el texto de la sección solicitada. No incluyas encabezados de otras secciones.
- No repitas información ya cubierta en secciones previas (usa el contexto de secciones ya escritas para evitar duplicación)."""


# Section-specific user prompt templates (RAG best practices: clear objective per section).
SECTION_USER_PROMPTS = {
    "resumen_ejecutivo": (
        "Usando únicamente los documentos y notas recuperadas, redacta un **resumen ejecutivo** de 150–300 palabras que:\n"
        "- Describa el problema de investigación.\n- Indique los hallazgos principales.\n"
        "- Mencione discrepancias o vacíos importantes en la evidencia.\n- Señale implicaciones generales.\n\n"
        "Todas las afirmaciones deben llevar citas numéricas [1], [2], … según fuentes relevantes."
    ),
    "introduccion": (
        "Con la evidencia disponible, redacta la **Introducción**:\n"
        "- Explica el contexto y la importancia del tema.\n- Define claramente el problema de investigación.\n"
        "- Menciona brevemente los enfoques previos y qué lagunas pretende abordar este reporte.\n\n"
        "Conecta cada punto con referencias [N]."
    ),
    "revision_literatura": (
        "Desarrolla una **Revisión de Literatura** estructurada por subtemas relevantes:\n"
        "- Para cada subtema, sintetiza los hallazgos de los documentos.\n"
        "- Resalta acuerdos y desacuerdos entre los estudios.\n"
        "- Indica explícitamente qué evidencia existe y cuáles son las limitaciones.\n\n"
        "Incluye **una tabla comparativa** cuando existan múltiples estudios con datos comparables. Usa citas numéricas [N]."
    ),
    "sintesis_comparativa": (
        "Redacta una sección que compare directamente los hallazgos (**Síntesis comparativa**):\n"
        "- Explica similitudes y diferencias metodológicas y de resultados.\n- Señala tendencias generales.\n"
        "- Identifica brechas persistentes en la evidencia.\n\n"
        "Incluye citas numéricas [N] para cada afirmación."
    ),
    "hallazgos": (
        "Redacta la sección de **Hallazgos/Resultados** con evidencia concreta:\n"
        "- N, sensibilidad, especificidad, intervalos cuando aparezcan en las fuentes.\n"
        "- Solo datos que aparecen literalmente en las fuentes [N]. No inferencias sin marcar.\n"
        "- Incluye tabla si hay datos comparables. Cita [N] en cada afirmación."
    ),
    "discusion": (
        "Discute críticamente (**Discusión**):\n"
        "- Qué implican los hallazgos respecto al estado del arte.\n- Qué contradicciones o incertidumbres persisten.\n"
        "- Qué preguntas quedan abiertas o requieren investigación futura.\n\n"
        "Evita repetir datos; integra evidencia y análisis con citas [N]."
    ),
    "conclusiones": (
        "Redacta una **Conclusión** de 150–250 palabras que:\n"
        "- Resuma los hallazgos centrales.\n- Mencione brechas clave.\n"
        "- Proponga líneas futuras de investigación o implicaciones prácticas.\n\n"
        "Incluye citas donde sea necesario [N]."
    ),
}


def _registry_research_generator(internal_id: str) -> Any:
    """
    Build research generator from merged model registry (dashboard: provider, model, encrypted API keys).
    Used for research-8k / research-128k when configured (OpenAI, Anthropic, etc.).
    """
    from app.config import get_model_config, get_model_registry
    from app.rag.pipeline import (
        _anthropic_api_key_for_model,
        _openai_api_key_for_model,
        _openai_http_timeout_for_model,
    )

    if internal_id not in get_model_registry():
        return None
    cfg = get_model_config(internal_id)
    if getattr(cfg, "use_anthropic", False) and (cfg.openai_model or "").strip():
        from app.rag.anthropic_chat import AnthropicChatGenerator

        oto = _openai_http_timeout_for_model(cfg)
        akey = _anthropic_api_key_for_model(cfg)
        return AnthropicChatGenerator(
            model=cfg.openai_model,
            api_key=akey,
            timeout=oto,
            generation_kwargs={
                "temperature": cfg.temperature,
                "max_tokens": min(int(cfg.num_predict or 4096), 8192),
            },
        )
    if not (getattr(cfg, "use_openai", False) and (cfg.openai_api_base or "").strip()):
        return None
    base = (cfg.openai_api_base or "").strip().rstrip("/")
    if "placeholder.invalid" in base:
        return None
    if not base.endswith("/v1"):
        base = f"{base}/v1"
    okey = _openai_api_key_for_model(cfg)
    oto = _openai_http_timeout_for_model(cfg)
    mt = min(int(cfg.num_predict or 4096), 16384)
    return make_openai_generator_for_research(
        openai_model=cfg.openai_model or "",
        api_base_url=base,
        api_key=okey,
        timeout=oto,
        temperature=float(cfg.temperature),
        num_predict=mt,
        log_label=internal_id,
    )


def _direct_openai_from_dashboard_research(slot: str) -> Any:
    """
    Dashboard mapping for Investigación (llm_model_config: research-8k / research-128k).
    OpenAI-compatible URL + model; API key from extra_params.api_key_env or OPENAI_API_KEY / openscholar_api_key.
    """
    try:
        from app.admin.llm_config_db import get_llm_config_overrides
    except Exception:
        return None
    key = "research-8k" if slot == "8k" else "research-128k"
    o = get_llm_config_overrides().get(key) or {}
    url = (o.get("backend_url_override") or "").strip()
    model = (o.get("backend_model") or "").strip()
    if not url or not model:
        return None
    ex = o.get("extra_params") or {}
    base = url.rstrip("/")
    if not base.endswith("/v1"):
        base = f"{base}/v1"
    envn = (ex.get("api_key_env") or "").strip()
    if envn:
        token = os.environ.get(envn, "") or ""
    else:
        token = os.environ.get("OPENAI_API_KEY", "") or (getattr(settings, "openscholar_api_key", None) or "dummy")
    t_default = 300.0 if slot == "128k" else 120.0
    try:
        timeout = float(ex.get("timeout") or t_default)
    except (TypeError, ValueError):
        timeout = t_default
    max_tok = 8192 if slot == "128k" else 2048
    logger.info("Research %s: using dashboard backend override -> %s (model=%s)", slot, base, model)
    temp = float(getattr(settings, "openscholar_temperature", 0.2))
    return make_openai_generator_for_research(
        openai_model=model,
        api_base_url=base,
        api_key=token,
        timeout=timeout,
        temperature=temp,
        num_predict=max_tok,
        log_label=f"dashboard {slot}",
    )


def get_openscholar_generator() -> Union[OpenAIChatGenerator, ServerlessOpenAIChatGenerator]:
    """
    Create or return the OpenScholar generator.
    Uses OpenAI-compatible API (vLLM) at the configured URL.
    """
    reg = _registry_research_generator("research-8k")
    if reg is not None:
        return reg
    direct = _direct_openai_from_dashboard_research("8k")
    if direct is not None:
        return direct
    vk = _vast_api_key()
    v_ep = (getattr(settings, "vast_serverless_openscholar_endpoint", "") or "").strip()
    if v_ep and vk:
        oc = int(getattr(settings, "vast_serverless_openscholar_cost", 0) or 0)
        vst = _vast_client_timeout()
        om = settings.openscholar_model or ""
        return ServerlessOpenAIChatGenerator(
            endpoint_name=v_ep,
            model=settings.openscholar_model,
            api_key=vk,
            cost=_vast_cost(oc),
            timeout=vst,
            worker_timeout=vst,
            generation_kwargs=_openai_research_generation_kwargs(
                om, float(settings.openscholar_temperature), 2048
            ),
        )
    # vLLM expects base_url to include /v1 (see vLLM OpenAI-compatible server docs)
    base_url = settings.openscholar_api_url.rstrip("/")
    if not base_url.endswith("/v1"):
        base_url = f"{base_url}/v1"
    timeout = getattr(settings, "openscholar_timeout", 120) or 120  # seconds, prevents indefinite hang

    return make_openai_generator_for_research(
        openai_model=settings.openscholar_model or "",
        api_base_url=base_url,
        api_key=settings.openscholar_api_key or "dummy",
        timeout=timeout,
        temperature=float(settings.openscholar_temperature),
        num_predict=2048,
        log_label="openscholar env 8k",
    )


def get_openscholar_128k_generator() -> Union[OpenAIChatGenerator, ServerlessOpenAIChatGenerator]:
    """
    Create OpenScholar 128K generator (long-context research instance).
    Uses openscholar_128k_api_url; same API shape as 8K.
    """
    reg = _registry_research_generator("research-128k")
    if reg is not None:
        return reg
    direct = _direct_openai_from_dashboard_research("128k")
    if direct is not None:
        return direct
    vk = _vast_api_key()
    v_ep = (getattr(settings, "vast_serverless_openscholar_128k_endpoint", "") or "").strip()
    if v_ep and vk:
        oc = int(getattr(settings, "vast_serverless_openscholar_128k_cost", 0) or 0)
        vst = _vast_client_timeout()
        om = getattr(settings, "openscholar_model", "openscholar") or ""
        return ServerlessOpenAIChatGenerator(
            endpoint_name=v_ep,
            model=getattr(settings, "openscholar_model", "openscholar"),
            api_key=vk,
            cost=_vast_cost(oc),
            timeout=vst,
            worker_timeout=vst,
            generation_kwargs=_openai_research_generation_kwargs(
                om, float(getattr(settings, "openscholar_temperature", 0.2)), 8192
            ),
        )
    url = getattr(settings, "openscholar_128k_api_url", "") or ""
    if not url:
        raise ValueError("openscholar_128k_api_url not configured (or set vast_serverless_openscholar_128k_endpoint + VAST_API_KEY)")
    base_url = url.rstrip("/")
    if not base_url.endswith("/v1"):
        base_url = f"{base_url}/v1"
    timeout = getattr(settings, "openscholar_128k_timeout", 300) or getattr(settings, "openscholar_timeout", 120) or 300
    return make_openai_generator_for_research(
        openai_model=getattr(settings, "openscholar_model", "openscholar") or "",
        api_base_url=base_url,
        api_key=settings.openscholar_api_key or "dummy",
        timeout=timeout,
        temperature=float(getattr(settings, "openscholar_temperature", 0.2)),
        num_predict=8192,
        log_label="openscholar env 128k",
    )


def build_academic_messages(
    question: str,
    documents: list[Document],
    plan: dict | None = None,
    history: list[dict] | None = None,
    file_context: str = "",
    image_description: str = "",
    is_phase2: bool = False,
    research_notes: list[str] | None = None,
    excluded_topics: list[str] | None = None,
    evidence_extracts: dict | list | None = None,
    bias_audit: dict | None = None,
    context_token_budget: int | None = None,
) -> list[ChatMessage]:
    """
    Build ChatMessage objects for OpenScholar (academic research mode).
    Truncates history and document content to stay within model context limit (8192 tokens).
    """
    ctx_budget = int(context_token_budget) if context_token_budget else MODEL_CTX_LIMIT
    ctx_budget = max(MODEL_CTX_LIMIT, min(ctx_budget, 200_000))
    messages: list[ChatMessage] = []
    academic_system = _current_datetime_context() + "\n\n" + ACADEMIC_RESEARCH_PROMPT
    messages.append(ChatMessage.from_system(academic_system))

    # Truncate history: keep last 6 messages, max ~80 tokens each (~500 tokens total)
    if history:
        recent = history[-6:]
        for msg in recent:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            content = _truncate_to_tokens(content, 80)  # ~80 tokens per message
            if role == "user":
                messages.append(ChatMessage.from_user(content))
            elif role == "assistant":
                messages.append(ChatMessage.from_assistant(content))

    user_parts: list[str] = []

    if evidence_extracts or bias_audit:
        if evidence_extracts:
            import json
            user_parts.append(
                "STRUCTURED EVIDENCE (extracted for synthesis):\n"
                + json.dumps(evidence_extracts, ensure_ascii=False, indent=0)[:3000]
                + "\n"
            )
        if bias_audit:
            import json
            user_parts.append(
                "QUALITY ASSESSMENT:\n"
                + json.dumps(bias_audit, ensure_ascii=False, indent=0)[:1500]
                + "\n"
            )

    if plan:
        focus = plan.get("focus", "")
        queries = plan.get("queries", [])
        sections = plan.get("sections", [])
        plan_text = "RESEARCH PLAN:\n"
        if focus:
            plan_text += f"- Focus: {focus}\n"
        if queries:
            plan_text += "- Queries:\n"
            for q in queries:
                plan_text += f"  - {q}\n"
        if sections:
            plan_text += "- Report sections:\n"
            for s in sections:
                plan_text += f"  - {s}\n"
        user_parts.append(plan_text)

    # Document budget: scale with model context (large windows = more evidence per doc)
    doc_budget_tokens = max(4000, min((ctx_budget * 55) // 100, 80_000))
    num_docs = len(documents) if documents else 1
    max_content_per_doc = max(600, (doc_budget_tokens * CHARS_PER_TOKEN) // num_docs)

    if documents:
        source_text = "EVIDENCE (cite with [N]):\n"
        for i, doc in enumerate(documents, 1):
            raw_type = doc.meta.get("source_type", "rag") or "rag"
            source_type = "OMINIS" if raw_type == "rag" else raw_type.upper()
            title = doc.meta.get("title", "Sin título")
            url = doc.meta.get("url", "")
            citation = doc.meta.get("citation", "")
            content = (doc.content or "")[:max_content_per_doc]

            source_text += f"\n[{i}] {source_type} — {title}\n"
            source_text += f"URL: {url}\n"
            if citation:
                source_text += f"Citation: {citation}\n"
            source_text += f"Content: {content}\n---"
        user_parts.append(source_text)

    if file_context:
        user_parts.append(f"\nATTACHED FILE:\n{_truncate_to_tokens(file_context, 800)}")

    if image_description:
        user_parts.append(f"\nIMAGE ANALYSIS:\n{_truncate_to_tokens(image_description, 300)}")

    if research_notes and is_phase2:
        notes_text = "RESEARCH NOTES (key findings per source — use for structure and citations):\n"
        for i, note in enumerate(research_notes[:20], 1):  # Cap at 20 notes
            notes_text += f"- [{i}] {_truncate_to_tokens(note, 80)}\n"
        user_parts.append(notes_text)

    user_parts.append(f"\nUser question: {question}")

    if is_phase2:
        original_topic = ""
        user_specs = ""
        if history:
            for msg in history:
                if msg.get("role") == "user":
                    if not original_topic:
                        original_topic = msg.get("content", "")
                    else:
                        user_specs += msg.get("content", "") + " "
        user_specs += question
        original_topic = _truncate_to_tokens(original_topic, 150)
        user_specs = _truncate_to_tokens(user_specs, 200)
        focus = (plan.get("focus", "") if plan else "")[:200]

        exclusion_note = "Las fuentes deseleccionadas ya fueron excluidas."
        if excluded_topics:
            exclusion_note += f" NO incluir: {', '.join(excluded_topics[:10])}."
        else:
            exclusion_note += " Si el usuario indicó temas o tipos de información que NO incluir, respétalos."
        plan_block = (
            "\nPLAN DE INVESTIGACIÓN (con retroalimentación del usuario):\n"
            f"- Focus: {focus or original_topic}\n"
            f"- Qué incluir: {user_specs}\n"
            f"- Qué no hacer: {exclusion_note}\n"
        )
        user_parts.append(
            "\nFASE 2: GENERA EL REPORTE COMPLETO. Responde en español. Tono científico/médico.\n"
            + plan_block
            + "Reglas: (1) Incluye datos concretos: N, sensibilidad/especificidad, diseño del estudio, resultados numéricos. (2) No repitas el mismo párrafo en varias secciones; cada sección debe aportar información nueva. (3) Cita fuentes distintas [1], [2], [3] para afirmaciones distintas; no uses solo [2] en todo el texto. (4) NUNCA cites fuentes que sean página de error (404) o portada genérica; solo las del EVIDENCE que hayas usado. (5) En ## Referencias solo las fuentes que SÍ citaste, con datos copiados de EVIDENCE.\n"
            "OBLIGATORIO: Escribe TODAS las secciones siguientes; NO te detengas después del Resumen ejecutivo. Debes incluir siempre: # Título, ## Resumen ejecutivo, ## Contexto, ## Hallazgos principales (con citas [N] variadas y datos concretos: N, sensibilidad, valores de corte), ## Análisis detallado, ## Discusión, ## Limitaciones, ## Conclusiones, ## Referencias. Tablas cuando los datos sean tabulares. Gráfica ```chart SOLO si en las fuentes hay números comparativos reales (prevalencia, sensibilidad, N por grupo); NUNCA incluyas gráfica con categorías genéricas (Sí/No, Diagnóstico vs X) sin datos reales—en ese caso omite el bloque chart."
        )
    else:
        user_parts.append(
            "\nFASE 1: Sé MUY breve (máximo 20 líneas). Responde en español:\n"
            "1. UNA oración sobre las fuentes encontradas.\n"
            "2. Secciones propuestas para el reporte (lista breve).\n"
            "3. EXACTAMENTE 3 o 4 preguntas CORTAS (1 línea cada una) SOLO sobre el ALCANCE:\n"
            "   - Alcance geográfico, periodo temporal, público meta, subtemas a excluir.\n"
            "   - NO hagas preguntas de investigación (esas son tuyas, no del usuario).\n"
            "   - NO repitas preguntas con variaciones. MÁXIMO 4 preguntas.\n"
            "PARA. No escribas más después de las preguntas. NO generes el reporte."
        )

    messages.append(ChatMessage.from_user("\n".join(user_parts)))
    return messages


def build_section_messages(
    section_name: str,
    documents: list[Document],
    plan: dict,
    question: str,
    focus: str,
    max_content_per_doc: int = 2000,
    previous_sections_summary: str = "",
    clinical_hint: str = "",
    section_description: str = "",
    narrative_thread: str = "",
) -> list[ChatMessage]:
    """
    Build messages for Research 2.1: write ONLY one section of the report.
    Uses section-type-specific academic standards and strict citation rules (APA-style, DOI/URL verified).
    """
    messages: list[ChatMessage] = []
    num_docs = len(documents)
    section_lower = section_name.lower()

    # Pick section-specific user prompt template (RAG best practices)
    section_template = None
    if "resumen" in section_lower or "ejecutivo" in section_lower:
        section_template = SECTION_USER_PROMPTS.get("resumen_ejecutivo")
    elif "introducción" in section_lower or "contexto" in section_lower:
        section_template = SECTION_USER_PROMPTS.get("introduccion")
    elif "estado del arte" in section_lower or "revisión" in section_lower or "literatura" in section_lower:
        section_template = SECTION_USER_PROMPTS.get("revision_literatura")
    elif "síntesis" in section_lower or "comparativ" in section_lower:
        section_template = SECTION_USER_PROMPTS.get("sintesis_comparativa")
    elif "hallazgos" in section_lower or "resultados" in section_lower:
        section_template = SECTION_USER_PROMPTS.get("hallazgos")
    elif "discusión" in section_lower:
        section_template = SECTION_USER_PROMPTS.get("discusion")
    elif "conclusiones" in section_lower:
        section_template = SECTION_USER_PROMPTS.get("conclusiones")

    # Fallback section guide for system message (short objective)
    if "resumen" in section_lower or "ejecutivo" in section_lower:
        section_guide = "OBJETIVO: Síntesis breve de hallazgos principales, metodología y conclusiones. Solo datos que están en las fuentes. Cita [N] para cada afirmación clave."
    elif "introducción" in section_lower or "contexto" in section_lower:
        section_guide = "OBJETIVO: Establecer contexto, definir alcance, presentar brechas de conocimiento. No inventes datos. Cita [N] cuando menciones estudios o cifras."
    elif "estado del arte" in section_lower or "revisión" in section_lower or "literatura" in section_lower:
        section_guide = "OBJETIVO: Sintetizar hallazgos de las fuentes con comparaciones directas. Incluye tabla comparativa si los datos lo permiten. Solo citas [N] verificables."
    elif "hallazgos" in section_lower or "resultados" in section_lower:
        section_guide = "OBJETIVO: Evidencia concreta (N, sensibilidad, especificidad, intervalos). Solo datos que aparecen literalmente en las fuentes [N]. No inferencias sin marcar."
    elif "discusión" in section_lower:
        section_guide = "OBJETIVO: Fortalezas, limitaciones, incertidumbres y direcciones futuras, claramente citadas [N]. Si no hay evidencia directa, indica 'según la evidencia disponible' o 'no se encontró suficiente evidencia'."
    elif "conclusiones" in section_lower:
        section_guide = "OBJETIVO: Resumir evidencia clave e implicaciones de políticas o clínicas. Solo lo respaldado por las fuentes [N]. No generar nuevos hechos."
    else:
        section_guide = "OBJETIVO: Desarrollar el tema con evidencia de las fuentes. Cita [N] para cada dato o afirmación. No inventes autores, títulos ni URLs."

    # System: persistent academic report prompt + invariant rules + section guide
    system = (
        ACADEMIC_REPORT_SYSTEM_PROMPT
        + "\n\nIDIOMA: Responde SIEMPRE en español mexicano. Redacta UNA SOLA SECCIÓN del reporte.\n\n"
        "═══ REGLAS INQUEBRANTABLES ═══\n\n"
        "1. SOLO DATOS QUE ESTÁN EN LAS FUENTES: Cada cifra, porcentaje, métrica, hallazgo o afirmación DEBE "
        "provenir TEXTUALMENTE de una fuente del bloque EVIDENCE. Si un dato NO aparece literalmente en el "
        "extracto de la fuente que citas, NO lo incluyas. NUNCA inventes cifras, porcentajes ni métricas.\n\n"
        "2. CITAS: Solo puedes citar [1] a [" + str(num_docs) + "]. "
        "Antes de escribir [N], VERIFICA que el dato que estás atribuyendo SÍ aparece en el extracto de la fuente [N]. "
        "Si no hay evidencia directa, indica claramente que es INFERENCIA y no generes nuevo hecho.\n\n"
        "3. HONESTIDAD GEOGRÁFICA: Cada fuente tiene un PAÍS/CONTEXTO. "
        "NUNCA digas que un hallazgo es 'de México' si la fuente es de otro país. "
        "Escribe: 'Un estudio en [país] encontró que...' y después PUEDES agregar inferencia para México marcándola como tal.\n\n"
        "4. NO INVENTES FUENTES: Solo menciona instituciones (OMS, INEGI, etc.) si aparecen EXPLÍCITAMENTE en alguna fuente [N]. "
        "NUNCA cites [N] si N es mayor que " + str(num_docs) + ".\n\n"
        "5. PROFUNDIDAD SIN REPETICIÓN: Desarrolla cada punto con contexto, evidencia concreta y análisis. "
        "NO repitas el mismo párrafo. Cada oración debe aportar información NUEVA.\n\n"
        "6. TRANSPARENCIA: Si la evidencia es limitada, dilo EXPLÍCITAMENTE: 'La evidencia disponible no permite establecer...' "
        "o 'No se encontró evidencia suficiente dentro de los documentos proporcionados para afirmar esto.'\n\n"
        "7. EXTENSIÓN: Escribe tanto como la evidencia REAL permita. No rellenes con párrafos genéricos.\n\n"
        "GUÍA PARA ESTA SECCIÓN: " + section_guide
    )
    system = _current_datetime_context() + "\n\n" + system
    messages.append(ChatMessage.from_system(system))

    all_sections = plan.get("sections", [])
    user_parts = [
        f"PLAN DEL REPORTE — Enfoque: {focus[:300]}",
        "Estructura completa: " + " → ".join(all_sections),
    ]
    if section_template:
        user_parts.append(f"\nTAREA (redacta ÚNICAMENTE la sección «{section_name}»):\n\n" + section_template)
    else:
        user_parts.append(f"\nTAREA: Redacta ÚNICAMENTE la sección «{section_name}».")
    if previous_sections_summary:
        user_parts.append(
            "\nBasado en lo ya cubierto, esta sección debe enfocarse específicamente en lo indicado en la TAREA; no repitas contenido de secciones previas."
        )
    if section_description:
        user_parts.append(f"\nOBJETIVO DE ESTA SECCIÓN:\n{section_description[:1000]}")
    if narrative_thread:
        user_parts.append(f"\nHILO CONDUCTOR DEL REPORTE (mantén coherencia con esto):\n{narrative_thread[:2000]}")
    if previous_sections_summary:
        user_parts.append(f"\nCONTEXTO — Resumen de secciones ya escritas (NO repitas este contenido):\n{previous_sections_summary[:3000]}")
    if clinical_hint:
        user_parts.append(f"\nPERSPECTIVA CLÍNICA (de Ominis Med, intégrala en tu análisis):\n{clinical_hint[:2000]}")
    user_parts.append(f"\n═══ EVIDENCE — {num_docs} fuentes (cite ONLY [1]-[{num_docs}]) ═══")
    for i, doc in enumerate(documents, 1):
        title = doc.meta.get("title", "Sin título")
        url = doc.meta.get("url", "")
        source_type = doc.meta.get("source_type", "")
        content = (doc.content or "")[:max_content_per_doc]
        user_parts.append(f"\n[{i}] «{title}»\nURL: {url}\nTipo: {source_type}\n{content}\n---")
    user_parts.append(f"\nPregunta original: {question}")
    user_parts.append(
        f"\nRedacta la sección «{section_name}» completa, en markdown (## {section_name}). "
        f"RECUERDA: Solo cita [1]-[{num_docs}]. Solo datos que ESTÁN en los extractos. "
        "Si un hallazgo es de otro país, dilo. Sin preámbulo ni conclusiones de otras secciones."
    )
    messages.append(ChatMessage.from_user("\n".join(user_parts)))
    return messages


def get_deepening_queries_prompt(focus: str, research_notes: list[str]) -> tuple[str, str]:
    """Return (system, user) for LLM to generate 3-5 deepening search queries from research notes."""
    notes_text = "\n".join(research_notes[:30])[:6000]
    system = (
        "Eres un experto en búsqueda académica. Dado el enfoque de investigación y las notas de fuentes ya leídas, "
        "genera entre 3 y 5 consultas de búsqueda NUEVAS para profundizar SOLO en temas que coincidan con el enfoque. "
        "CRÍTICO: Las consultas DEBEN ser estrictamente sobre el enfoque indicado (ej. IA en salud, tiempo de espera, zonas rurales, México). "
        "NO generes consultas sobre: educación general, manejo forestal, economía no sanitaria, telessicología, anticoagulantes, biodiversidad, "
        "accesibilidad vial urbana, etc. Si en las notas hay temas ajenos al enfoque, ignóralos. "
        "Devuelve SOLO un JSON válido: {\"queries\": [\"consulta1\", \"consulta2\", ...]}. "
        "Las consultas deben ser muy específicas. Mezcla inglés (para PubMed) y español (para web)."
    )
    user = (
        f"Enfoque OBLIGATORIO (solo genera consultas sobre esto): {focus}\n\n"
        "Notas de fuentes ya leídas (pueden incluir temas irrelevantes; ignóralos):\n" + notes_text + "\n\n"
        "Genera 3-5 consultas para buscar más evidencia SOLO sobre el enfoque indicado."
    )
    return system, user


def get_gap_analysis_prompt(focus: str, research_notes: list[str], user_spec: str = "") -> tuple[str, str]:
    """Return (system, user) for LLM to identify knowledge gaps and generate targeted queries with coverage criteria."""
    notes_text = "\n".join(research_notes[:40])[:8000]
    system = (
        "Eres un investigador senior revisando la evidencia recopilada para un reporte de investigación. "
        "Tu tarea: (1) Identificar LAGUNAS DE CONOCIMIENTO — ¿qué falta para un reporte completo y riguroso? "
        "(2) Generar 3-4 consultas MUY ESPECÍFICAS para llenar esas lagunas.\n\n"
        "CRITERIOS DE COBERTURA (obligatorios):\n"
        "- Solo genera consultas para lagunas donde ESPERAS encontrar evidencia recuperable (PubMed, web, guías). "
        "No generes consultas de relleno ni preguntas demasiado amplias.\n"
        "- Prioriza lagunas que aporten: datos comparativos faltantes, contexto geográfico (México), estudios recientes, "
        "guías clínicas, contraindicaciones, efectos adversos, costos, accesibilidad, poblaciones especiales.\n"
        "- Cada query debe tener COBERTURA MÍNIMA ESPERADA: debe ser plausible que la búsqueda devuelva al menos 2-3 fuentes relevantes. "
        "Si una laguna es demasiado nicho o improbable de cubrir con búsqueda, no generes query para ella.\n"
        "Devuelve SOLO JSON: {\"gaps\": [\"gap1\", ...], \"queries\": [\"query1\", ...]}. "
        "Máximo 4 queries. Las queries deben ser concretas (términos técnicos, años, región) para que la recuperación sea efectiva."
    )
    user = (
        f"Enfoque de investigación: {focus}\n"
        + (f"Especificaciones del usuario: {user_spec[:500]}\n" if user_spec else "")
        + f"\nEvidencia recopilada hasta ahora:\n{notes_text}\n\n"
        "¿Qué lagunas faltan? Genera solo consultas con cobertura mínima esperada (evidencia recuperable)."
    )
    return system, user


def get_detailed_outline_prompt(focus: str, research_notes: list[str], question: str, user_spec: str = "") -> tuple[str, str]:
    """Return (system, user) for LLM to design a detailed document outline with 12-18 specific sections and academic standards per section type."""
    notes_text = "\n".join(research_notes[:40])[:8000]
    system = (
        "Eres un investigador académico de alto nivel diseñando la estructura de un REPORTE DE INVESTIGACIÓN EXHAUSTIVO. "
        "Basándote en la evidencia recopilada, diseña un ÍNDICE DETALLADO con 12-18 secciones/subsecciones.\n\n"
        "ESTÁNDARES CIENTÍFICOS POR TIPO DE SECCIÓN:\n"
        "- *Introducción / Contexto:* Establecer contexto, definir alcance, presentar brechas de conocimiento. Objetivos claros.\n"
        "- *Estado del arte / Revisión de literatura:* Sintetizar hallazgos de las fuentes con comparaciones directas (tabla comparativa cuando aplique).\n"
        "- *Hallazgos / Resultados:* Evidencia concreta (N, sensibilidad, especificidad, intervalos). Solo datos que están en las fuentes.\n"
        "- *Discusión:* Fortalezas, limitaciones, incertidumbres y direcciones futuras, claramente citadas [N]. No inventar.\n"
        "- *Conclusiones:* Resumir evidencia clave y sugerir implicaciones de políticas o clínicas. Solo lo respaldado por las fuentes.\n\n"
        "REGLAS:\n"
        "- El índice debe ser ESPECÍFICO al tema, no genérico.\n"
        "- Secciones obligatorias: Resumen ejecutivo, Referencias (al final).\n"
        "- Incluye secciones de contenido según la evidencia: contexto epidemiológico, mecanismos, diagnóstico, tratamientos, comparativos, guías clínicas, limitaciones, perspectivas para México, etc.\n"
        "- Para cada sección: 1-2 líneas describiendo qué datos y argumentos incluir.\n"
        "- Marca con [CLÍNICO] las secciones que requieren perspectiva clínica.\n"
        "- Marca con [DATOS] las secciones que podrían beneficiarse de tabla o gráfica.\n"
        "Devuelve SOLO JSON: {\"sections\": [{\"title\": \"...\", \"description\": \"...\", \"needs_clinical\": bool, \"needs_chart\": bool}]}"
    )
    user = (
        f"Pregunta de investigación: {question}\n"
        f"Enfoque: {focus}\n"
        + (f"Especificaciones del usuario: {user_spec[:500]}\n" if user_spec else "")
        + f"\nEvidencia recopilada ({len(research_notes)} fuentes leídas):\n{notes_text}\n\n"
        "Diseña el índice detallado del reporte."
    )
    return system, user


def build_section_analysis_prompt(section_name: str, section_desc: str, focus: str, documents_summary: str) -> tuple[str, str]:
    """Return (system, user) for Med42 to provide clinical perspective for a specific section."""
    system = (
        "Eres un médico clínico experimentado. Se te pide aportar la perspectiva clínica para UNA sección "
        "de un reporte de investigación. Sé conciso (200-400 palabras) pero incluye:\n"
        "- Implicaciones clínicas prácticas\n"
        "- Riesgos o contraindicaciones relevantes\n"
        "- Cómo aplica la evidencia en la práctica médica en México\n"
        "- Recomendaciones prudentes basadas en la evidencia\n"
        "Responde en español."
    )
    user = (
        f"Sección: {section_name}\n"
        f"Descripción: {section_desc}\n"
        f"Enfoque del reporte: {focus}\n\n"
        f"Evidencia relevante:\n{documents_summary[:6000]}\n\n"
        "Aporta tu perspectiva clínica para esta sección."
    )
    return system, user
