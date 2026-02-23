"""
Research agents: Evidence Extractor and Bias Auditor.
Use the default chat model (Qwen) to produce structured outputs for the Synthesizer.
"""

import json
import logging
from typing import Any

from haystack.dataclasses import Document

logger = logging.getLogger(__name__)

EVIDENCE_EXTRACTOR_PROMPT = """You are an evidence extractor for health research. Given document excerpts, output a JSON object with one entry per source.
For each source [N] extract when present: study_design, N (sample size), OR/RR/HR (with 95% CI), p_values, outcomes, population, country.
Output ONLY valid JSON, no markdown. Example shape:
{"sources": [{"source_id": 1, "design": "RCT", "N": 500, "OR_95CI": "1.2 [0.9-1.6]", "p_value": 0.15, "outcomes": "...", "population": "..."}, ...]}
If a field is missing in the text, use null. Keep each source entry concise (one short paragraph for outcomes)."""

BIAS_AUDITOR_PROMPT = """You are a quality auditor for health research. Given evidence extractions or document summaries, output a JSON object assessing:
- study_types: list of study designs (e.g. RCT, cohort, systematic review)
- bias_concerns: short list of potential bias (selection, performance, detection, attrition, reporting)
- methodological_quality: brief overall (low/medium/high)
- limitations: 2-3 short bullets
Output ONLY valid JSON. Example:
{"study_types": ["RCT", "cohort"], "bias_concerns": ["unclear blinding"], "methodological_quality": "medium", "limitations": ["..."]}"""


def _truncate(text: str, max_chars: int = 600) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rsplit(" ", 1)[0] + "…"


def run_evidence_extractor_sync(generator, documents: list[Document], max_docs: int = 15) -> dict[str, Any] | list[Any]:
    """
    Run Evidence Extractor agent (sync). Returns structured JSON with OR/RR/HR, IC95, p-values, N, design.
    Uses the provided generator (e.g. Qwen).
    """
    if not documents:
        return {}
    from haystack.dataclasses import ChatMessage

    docs = documents[:max_docs]
    evidence_block = ""
    for i, doc in enumerate(docs, 1):
        content = (doc.content or "")[:800]
        title = doc.meta.get("title", "Sin título")
        evidence_block += f"\n[{i}] {title}\n{content}\n---"
    user_content = f"{EVIDENCE_EXTRACTOR_PROMPT}\n\nDOCUMENTS:\n{evidence_block}"
    messages = [
        ChatMessage.from_system("You output only valid JSON. No markdown, no explanation."),
        ChatMessage.from_user(user_content),
    ]
    try:
        result = generator.run(messages=messages)
        replies = result.get("replies", [])
        text = replies[0].content if replies else "{}"
        # Strip markdown code block if present
        if "```" in text:
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                text = text[start:end]
        return json.loads(text)
    except (json.JSONDecodeError, IndexError, KeyError) as e:
        logger.warning("Evidence extractor parse error: %s", e)
        return {}


def run_bias_auditor_sync(generator, evidence_extracts: dict | list | None, document_summaries: str = "") -> dict[str, Any]:
    """
    Run Bias Auditor agent (sync). Returns study_types, bias_concerns, methodological_quality, limitations.
    """
    from haystack.dataclasses import ChatMessage

    input_text = document_summaries
    if evidence_extracts:
        input_text = json.dumps(evidence_extracts, ensure_ascii=False)[:2000] + "\n\n" + input_text
    input_text = (input_text or "No structured input.").strip()
    user_content = f"{BIAS_AUDITOR_PROMPT}\n\nINPUT:\n{input_text}"
    messages = [
        ChatMessage.from_system("You output only valid JSON. No markdown, no explanation."),
        ChatMessage.from_user(user_content),
    ]
    try:
        result = generator.run(messages=messages)
        replies = result.get("replies", [])
        text = replies[0].content if replies else "{}"
        if "```" in text:
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                text = text[start:end]
        return json.loads(text)
    except (json.JSONDecodeError, IndexError, KeyError) as e:
        logger.warning("Bias auditor parse error: %s", e)
        return {}
