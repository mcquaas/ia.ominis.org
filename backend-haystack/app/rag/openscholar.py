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
ACADEMIC_SYSTEM_PROMPT = """You are an academic research assistant.
Answer ONLY using the provided documents.
Cite each claim with its source number [N].
If evidence is insufficient, say so explicitly. Do not speculate.
Use formal, scientific language. Respond in Mexican Spanish.
Never invent URLs, authors, or references not present in the documents.
Prefer fewer well-cited claims over many unsupported ones."""

# Same two-phase structure as research mode, but with stricter academic tone
ACADEMIC_RESEARCH_PROMPT = """You are an academic research assistant for health sciences.
Your mission is to produce rigorous, evidence-based reports.

PHASE 1 — PLANNING (if no prior plan in history):
- Assess if the query is clear and researchable.
- If vague or unviable, briefly explain and suggest reformulation.
- If viable: present a short summary of found sources, proposed report sections,
  and 3–4 questions to narrow scope (period, region, data type, audience).
- Do NOT generate the full report in this phase.

PHASE 2 — REPORT (if user has answered or says "proceed"):
- Generate a full white-paper style report in Markdown.
- Use EXCLUSIVELY data from the provided sources [N].
- Every claim MUST have a verifiable citation [N].
- Citation format: [N] Autor(es). Título. Fuente, año. URL. Use exact names and titles from the sources.
- NEVER invent authors, titles, journals, or URLs.
- Mandatory sections: Resumen ejecutivo, Contexto, Hallazgos principales (con citas [N]), Análisis detallado, Discusión, Limitaciones, Conclusiones, Referencias (formato completo).
- If evidence is insufficient, state this clearly.
- Geographic focus: Mexico unless otherwise specified.
- If the user indicated what NOT to include (topics, study types, etc.), respect it strictly.
- TABLE DECISION: When you find structured or comparative data (numbers, categories, time series), decide whether a table would help. If yes, choose the most relevant columns and datapoints and include a markdown table in the report (header row with |, separator | --- |, then data rows). Use the table to present the data clearly; cite the source [N].
- CHART DECISION: When quantitative data would be clearer as a graphic, decide if a chart makes sense. If yes, choose chart type (bar, line, or pie) and which data to include, then output a single fenced block so we can render it: use a code block with language \"chart\" and inside put ONLY valid JSON in this exact form: {\"charts\": [{\"type\": \"bar\"|\"line\"|\"pie\", \"title\": \"...\", \"x_label\": \"...\", \"y_label\": \"...\", \"series\": [{\"name\": \"...\", \"data\": [{\"x\": \"label\", \"y\": number}]}]}]}. For pie use \"labels\": [\"...\"], \"values\": [number]. Use ONLY data from the sources; max 12 points per series. If no chart is needed, do not output a chart block.
- Respond only in Mexican Spanish."""


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
            "max_tokens": 4096,  # Model max ctx is 8192; leave room for input tokens
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
            "\nPHASE 2: GENERATE THE FULL REPORT.\n"
            + plan_block
            + "Stay STRICTLY on topic. Use only literal data from sources [N].\n"
            "Cite as: [N] Autor(es). Título. Fuente, año. URL.\n"
            "Sections: # Título, ## Resumen ejecutivo, ## Contexto, ## Hallazgos principales (con citas [N]); include markdown tables when data is tabular. ## Análisis detallado, ## Discusión, ## Limitaciones, ## Conclusiones, ## Referencias. If you want a chart, add a ```chart code block with JSON {\"charts\": [...]} (see system prompt)."
        )
    else:
        user_parts.append(
            "\nPHASE 1: Be brief. In 10–15 lines:\n"
            "1. One sentence on found sources.\n"
            "2. Proposed report sections.\n"
            "3. Exactly 3–4 questions to narrow scope.\n"
            "Ask the user to answer or say 'proceed'. Do NOT generate the report."
        )

    messages.append(ChatMessage.from_user("\n".join(user_parts)))
    return messages
