"""
Clinical Validator (BioMistral) — audits clinical claims per Ominis architecture.

Any clinical response must be validated by BioMistral (Ominis-2.0-clinic).
We run the validator when: intent/documents indicate clinical context, OR when
the question/answer content contains clinical signals (dosis, tratamiento, etc.).
Output is structured (warnings, reformulations); used to add disclaimers.
"""

import json
import re
import logging
from typing import Any

from haystack.dataclasses import ChatMessage

logger = logging.getLogger(__name__)

VALIDATOR_SYSTEM = """Eres un validador clínico. Audita la respuesta dada a la pregunta del usuario para CUALQUIER tema médico o clínico (diagnósticos, tratamientos, medicamentos, pronósticos, etc.).
Tu salida NO es visible directamente al usuario. Devuelve ÚNICAMENTE un JSON válido.

Evalúa:
- Riesgo: afirmaciones que puedan interpretarse como recomendación clínica directa.
- Extrapolaciones: datos aplicados fuera de contexto.
- Ambigüedad: frases que deban matizarse.

Formato de respuesta (solo este JSON):
{
  "warnings": ["advertencia 1", "advertencia 2"],
  "reformulations": ["sugerencia de reformulación si aplica"],
  "disclaimer": "Una oración corta de advertencia si hay riesgo clínico, o cadena vacía."
}

Si no hay nada que señalar, devuelve {"warnings": [], "reformulations": [], "disclaimer": ""}.
Responde solo en español. No incluyas texto fuera del JSON."""


# Keywords that suggest clinical content (question or answer) — any match triggers validation
_CLINICAL_SIGNALS = re.compile(
    r"\b(dosis|dosificación|tratamiento|diagnóstico|diagnosticar|recomendar|"
    r"contraindicación|síntoma|enfermedad|medicamento|fármaco|terapia|"
    r"pronóstico|patología|clínica|médico|paciente|prescri|indicación|"
    r"efectos?\s+adversos|reacción\s+adversa|interacción\s+medicamentosa|"
    r"riesgo[s]?|seguridad\s+(del\s+)?(medicamento|fármaco|tratamiento)?|"
    r"agonista[s]?|antagonista[s]?|inhibidor(es)?|GLP-?1|SGLT-?2|"
    r"semaglutide|tirzepatide|liraglutide|exenatide|"
    r"estatina[s]?|IECA|ARA-?II|antihipertensivo)\b",
    re.IGNORECASE,
)


def content_has_clinical_signals(question: str, answer: str) -> bool:
    """
    True if question or answer contains clinical keywords.
    Used to ensure any clinical response is validated by BioMistral even when
    intent mapper did not set clinical_risk (e.g. intent failed or was conservative).
    """
    text = f" {question or ''} {answer or ''} "
    return bool(_CLINICAL_SIGNALS.search(text))


def _extract_json(text: str) -> dict | None:
    try:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end <= start:
            return None
        return json.loads(text[start : end + 1])
    except Exception:
        return None


def run_clinical_validator_sync(
    question: str,
    draft_answer: str,
    generator,
) -> dict[str, Any]:
    """
    Run BioMistral to audit the draft answer. Returns structured output.
    If generator is None or call fails, returns safe empty result.
    """
    if not draft_answer or not draft_answer.strip():
        return {"warnings": [], "reformulations": [], "disclaimer": ""}

    user_content = (
        f"Pregunta del usuario: {question}\n\n"
        f"Respuesta a auditar:\n{draft_answer[:6000]}"
    )
    messages = [
        ChatMessage.from_system(VALIDATOR_SYSTEM),
        ChatMessage.from_user(user_content),
    ]
    try:
        result = generator.run(messages=messages, generation_kwargs={"num_predict": 512})
        replies = result.get("replies", [])
        text = replies[0].text if replies else ""
        out = _extract_json(text)
        if out and isinstance(out, dict):
            return {
                "warnings": out.get("warnings") or [],
                "reformulations": out.get("reformulations") or [],
                "disclaimer": (out.get("disclaimer") or "").strip(),
            }
    except Exception as e:
        logger.warning("Clinical validator failed: %s", e)
    return {"warnings": [], "reformulations": [], "disclaimer": ""}


def format_validator_disclaimer(validator_out: dict[str, Any]) -> str:
    """Build a single disclaimer line to append to the answer."""
    disclaimer = (validator_out.get("disclaimer") or "").strip()
    if disclaimer:
        return f"\n\n---\n*{disclaimer}*"
    warnings = validator_out.get("warnings") or []
    if warnings:
        return "\n\n---\n*Nota: Esta respuesta es informativa. Para decisiones clínicas consulte a un profesional de la salud.*"
    return ""


# Shown when clinical validation was requested but Ominis Med (ominis-2.0-clinic/BioMistral) was unavailable
VALIDATOR_UNAVAILABLE_DISCLAIMER = (
    "\n\n---\n*Validación clínica (BioMistral) no disponible. "
    "Esta respuesta es informativa; para decisiones clínicas consulte a un profesional de la salud.*"
)
