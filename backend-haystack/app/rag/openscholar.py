"""
OpenScholar integration for Modo Investigación.

OpenScholar (Llama-3.1_OpenScholar-8B) is the exclusive LLM for Research Mode.
Uses Haystack OpenAIChatGenerator with api_base_url to connect to vLLM/OpenAI-compatible API.
See: arquitectura_ominis_integracion_open_scholar_modo_investigacion.md
"""

import logging
from typing import Optional

from haystack.components.generators.chat import OpenAIChatGenerator

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

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# ---------------------------------------------------------------------------
# Academic System Prompt (OpenScholar-specific, NOT generic)
# ---------------------------------------------------------------------------
ACADEMIC_SYSTEM_PROMPT = """IDIOMA: Responde SIEMPRE en español mexicano. Solo responde en otro idioma si el usuario formuló su pregunta explícitamente en ese idioma.

Eres un asistente de investigación académica en ciencias de la salud. Aplica el mismo rigor a CUALQUIER tema clínico, médico o de investigación (enfermedades, diagnósticos, tratamientos, medicamentos, epidemiología, etc.).
Responde ÚNICAMENTE usando los documentos proporcionados. Base cada afirmación en evidencia explícita de las fuentes.
Cita cada afirmación con el número de fuente [N]. Si la evidencia es insuficiente, dilo explícitamente. No especules.
Usa lenguaje formal y científico. Nunca inventes URLs, autores ni referencias que no estén en los documentos.
Prefiere menos afirmaciones bien citadas que muchas sin respaldo."""

# Same two-phase structure as research mode, but with stricter academic tone
ACADEMIC_RESEARCH_PROMPT = """IDIOMA: Responde SIEMPRE en español mexicano. Solo usa otro idioma si el usuario hizo su pregunta explícitamente en ese idioma. Todas las secciones, preguntas y texto deben estar en español.

Eres un asistente de investigación académica en ciencias de la salud. Tu misión es producir reportes rigurosos y basados en evidencia para CUALQUIER tema clínico, médico o de investigación en salud (no solo un tema concreto). El mismo estándar científico aplica a cualquier condición, tratamiento, diagnóstico o área.

FASE 1 — PLANIFICACIÓN (si no hay plan previo en el historial):
- Evalúa si la consulta es clara y viable para investigar.
- Si es vaga o inviable, explica brevemente y sugiere reformular.
- Si es viable: presenta un resumen breve de las fuentes encontradas, las secciones propuestas del reporte y 3–4 preguntas para acotar el alcance (periodo, región, tipo de datos, audiencia).
- NO generes el reporte completo en esta fase.

FASE 2 — REPORTE (si el usuario respondió o dice "procede", "adelante", "sí"):
- El reporte debe ser RIGUROSAMENTE científico y médico: incluye diseño de estudios, N, sensibilidad/especificidad, valores de corte (ej. BNP/NT-proBNP), resultados numéricos y métodos. Evita lenguaje genérico o de relleno. PREFIERE profundidad y datos concretos sobre párrafos cortos o decorativos.
- Usa EXCLUSIVAMENTE datos de las fuentes proporcionadas [N]. Cita fuentes DIFERENTES para afirmaciones distintas; no repitas la misma cita [2] en todo el texto.
- Hallazgos y Análisis deben ser SUSTANCIALES: incluye valores específicos (prevalencia %, N, sensibilidad, especificidad, puntos de corte), nombres de estudios y citas [N]. Si el usuario pidió técnicas concretas (ej. pruebas de laboratorio BNP/NT-proBNP), inclúyelas con números extraídos de las fuentes.
- NO repitas el mismo párrafo en varias secciones. Cada sección debe aportar información NUEVA y específica.
- NUNCA cites una fuente que sea página de error (404), página genérica (ej. portada NCBI) o que no hayas usado. Solo cita fuentes del bloque EVIDENCE que hayas leído y usado.
- En el cuerpo: cita SOLO con el número, ej. [1], [2]. El formato completo (Título. Autor. Fecha. DOI. URL debajo) solo en ## Referencias.
- NUNCA inventes autores, títulos, revistas ni URLs.
- Secciones obligatorias: Resumen ejecutivo, Contexto, Hallazgos principales (con citas [N] variadas), Análisis detallado, Discusión, Limitaciones, Conclusiones, Referencias.
- REFERENCIAS: Una sola sección al final. Por cada fuente que SÍ citaste, escribe en formato científico: **Título**. Autor. Fecha. DOI (si está en la evidencia). En la línea siguiente, la URL en texto pequeño. NO uses el prefijo OPENSCHOLAR ni el nombre de la base de datos en el título; solo el título del trabajo.
- Si la evidencia es insuficiente, dilo claramente.
- Enfoque geográfico: México salvo que se indique otro.
- Si el usuario indicó qué NO incluir, respétalo estrictamente.
- TABLAS: Si hay datos estructurados o comparativos (números, categorías, series temporales), incluye una tabla en markdown (cabecera con |, separador | --- |, filas de datos). Cita la fuente [N].
- GRÁFICAS: Incluye una gráfica SOLO cuando las fuentes aporten números comparativos REALES (prevalencia por grupo, sensibilidad de una prueba, resultados de estudios). NUNCA incluyas gráfica con categorías genéricas (ej. Sí/No, Diagnóstico vs X) sin proporciones o números extraídos explícitamente de las fuentes; en ese caso NO incluyas bloque de chart. Si no hay datos numéricos comparativos claros en la evidencia, omite la gráfica y prioriza más texto con datos concretos. Cuando sí haya datos: usa bloque \"chart\" con JSON {\"charts\": [{\"type\": \"bar\"|\"line\"|\"pie\", \"title\": \"...\", \"x_label\": \"...\", \"y_label\": \"...\", \"series\": [{\"name\": \"...\", \"data\": [{\"x\": \"label\", \"y\": number}]}]}]}. Para pie: \"labels\": [\"...\"], \"values\": [number]. Máximo 12 puntos por serie.
- Responde únicamente en español mexicano."""


def get_openscholar_generator() -> OpenAIChatGenerator:
    """
    Create or return the OpenScholar generator.
    Uses OpenAI-compatible API (vLLM) at the configured URL.
    """
    # vLLM expects base_url to include /v1 (see vLLM OpenAI-compatible server docs)
    base_url = settings.openscholar_api_url.rstrip("/")
    if not base_url.endswith("/v1"):
        base_url = f"{base_url}/v1"
    timeout = getattr(settings, "openscholar_timeout", 120) or 120  # seconds, prevents indefinite hang

    generator = OpenAIChatGenerator(
        model=settings.openscholar_model,
        api_key=Secret.from_token(settings.openscholar_api_key or "dummy"),
        api_base_url=base_url,
        timeout=timeout,
        generation_kwargs={
            "temperature": settings.openscholar_temperature,
            "top_p": 0.9,
            "max_tokens": 2048,  # 8K ctx: safe default; router passes lower when input is large
        },
    )
    return generator


def get_openscholar_128k_generator() -> OpenAIChatGenerator:
    """
    Create OpenScholar 128K generator (long-context research instance).
    Uses openscholar_128k_api_url; same API shape as 8K.
    """
    url = getattr(settings, "openscholar_128k_api_url", "") or ""
    if not url:
        raise ValueError("openscholar_128k_api_url not configured")
    base_url = url.rstrip("/")
    if not base_url.endswith("/v1"):
        base_url = f"{base_url}/v1"
    timeout = getattr(settings, "openscholar_128k_timeout", 300) or getattr(settings, "openscholar_timeout", 120) or 300
    generator = OpenAIChatGenerator(
        model=getattr(settings, "openscholar_model", "openscholar"),
        api_key=Secret.from_token(settings.openscholar_api_key or "dummy"),
        api_base_url=base_url,
        timeout=timeout,
        generation_kwargs={
            "temperature": getattr(settings, "openscholar_temperature", 0.2),
            "top_p": 0.9,
            "max_tokens": 8192,  # Long context allows larger output
        },
    )
    return generator


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
) -> list[ChatMessage]:
    """
    Build ChatMessage objects for OpenScholar (academic research mode).
    Truncates history and document content to stay within model context limit (8192 tokens).
    """
    messages: list[ChatMessage] = []
    messages.append(ChatMessage.from_system(ACADEMIC_RESEARCH_PROMPT))

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

    # Document budget: allocate ~4000 tokens for evidence (scale per doc count)
    doc_budget_tokens = 4000
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
            "Secciones: # Título, ## Resumen ejecutivo, ## Contexto, ## Hallazgos principales (con citas [N] variadas y datos concretos: N, sensibilidad, valores de corte), ## Análisis detallado, ## Discusión, ## Limitaciones, ## Conclusiones, ## Referencias. Tablas cuando los datos sean tabulares. Gráfica ```chart SOLO si en las fuentes hay números comparativos reales (prevalencia, sensibilidad, N por grupo); NUNCA incluyas gráfica con categorías genéricas (Sí/No, Diagnóstico vs X) sin datos reales—en ese caso omite el bloque chart."
        )
    else:
        user_parts.append(
            "\nFASE 1: Sé breve. Responde en español, en 10–15 líneas:\n"
            "1. Una oración sobre las fuentes encontradas.\n"
            "2. Secciones propuestas para el reporte.\n"
            "3. Exactamente 3–4 preguntas para acotar el alcance.\n"
            "Pide al usuario que responda o diga 'procede'. NO generes el reporte."
        )

    messages.append(ChatMessage.from_user("\n".join(user_parts)))
    return messages
