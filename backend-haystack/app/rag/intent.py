"""
Metadata Intent Mapper — first step of the Ominis architecture.

Uses Qwen (orchestrator) to map the user query to a structured intent that governs
RAG retrieval, depth, PubMed usage, clinical risk, and long-context needs.
See: Arquitectura Ia Ominis – Brief Para Agente.pdf
"""

import json
import logging
from typing import Any

from haystack.dataclasses import ChatMessage

from app.rag.taxonomy import RAG_TAXONOMY, filter_valid_taxonomy_values

logger = logging.getLogger(__name__)

# Depth levels for retrieval
DEPTH_SHALLOW = "shallow"
DEPTH_STANDARD = "standard"
DEPTH_DEEP = "deep"

# Clinical risk levels
CLINICAL_RISK_LOW = "low"
CLINICAL_RISK_MEDIUM = "medium"
CLINICAL_RISK_HIGH = "high"


INTENT_MAPPER_PROMPT = """Eres el mapeador de intención del sistema Ominis (salud, México).
Aplica a CUALQUIER tema clínico, médico o de investigación en salud (enfermedades, diagnósticos, tratamientos, medicamentos, epidemiología, etc.). Tu salida gobierna todo el pipeline posterior. Responde ÚNICAMENTE con un JSON válido, sin markdown ni texto extra.

Analiza la pregunta del usuario (y el contexto si aplica) y produce este objeto JSON:

{
  "retrieval_constraints": {
    "institucion": [],
    "tipo_documento": [],
    "dominio_salud": [],
    "territorio": [],
    "vigencia": []
  },
  "priority_tags": [],
  "exclude": {},
  "depth": "shallow" | "standard" | "deep",
  "needs_pubmed": true | false,
  "clinical_risk": "low" | "medium" | "high",
  "needs_long_context": true | false
}

REGLAS:
- retrieval_constraints: listas de valores que DEBEN cumplir los documentos. Valores vacíos = no filtrar esa dimensión.
  Dimensiones y valores válidos (usa solo estos):
  - institucion: SSA, IMSS, IMSS-Bienestar, ISSSTE, Servicios Estatales de Salud, COFEPRIS, OSC, Privado, Internacional
  - tipo_documento: ley, norma, politica_publica, programa, guia_clinica, protocolo, informe, evaluacion, manual, articulo_cientifico, base_datos
  - dominio_salud: salud_publica, enfermedades_cronicas, enfermedades_transmisibles, salud_mental, salud_materna_infantil, cancer, nutricion, adicciones, discapacidad, determinantes_sociales
  - territorio: nacional, estatal, municipal, local, rural, urbano
  - vigencia: vigente, historico, transitorio, emergencia_sanitaria
- depth: "shallow" para preguntas simples o factuales; "standard" para la mayoría; "deep" para análisis comparativos o revisiones.
- needs_pubmed: true si la pregunta requiere literatura científica, estudios, evidencia clínica o autores.
- clinical_risk: "low" solo si es informativa general sin implicación clínica. "medium" si menciona tratamientos, diagnósticos, riesgos de medicamentos, seguridad de fármacos, agonistas (ej. GLP-1), inhibidores o efectos adversos; "high" si pide recomendación clínica, dosificación o decisión diagnóstica/terapéutica.
- needs_long_context: true solo si la pregunta implica ≥15 documentos, revisión narrativa, meta-análisis o análisis histórico multi-fuente extenso.

Pregunta y contexto:
"""


def _extract_json_object(text: str) -> dict | None:
    """Extract the first JSON object from text."""
    try:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        return json.loads(text[start : end + 1])
    except Exception:
        return None


def _sanitize_intent(raw: dict) -> dict:
    """Validate and sanitize intent fields; ensure valid taxonomy values and enums."""
    constraints = raw.get("retrieval_constraints") or {}
    sanitized_constraints: dict[str, list[str]] = {}
    for dim in ("institucion", "tipo_documento", "dominio_salud", "territorio", "vigencia"):
        vals = constraints.get(dim)
        if isinstance(vals, list):
            sanitized_constraints[dim] = filter_valid_taxonomy_values(dim, [str(v) for v in vals])
        elif isinstance(vals, str) and vals:
            sanitized_constraints[dim] = filter_valid_taxonomy_values(dim, [vals])
        else:
            sanitized_constraints[dim] = []

    depth = raw.get("depth", DEPTH_STANDARD)
    if depth not in (DEPTH_SHALLOW, DEPTH_STANDARD, DEPTH_DEEP):
        depth = DEPTH_STANDARD

    clinical_risk = raw.get("clinical_risk", CLINICAL_RISK_LOW)
    if clinical_risk not in (CLINICAL_RISK_LOW, CLINICAL_RISK_MEDIUM, CLINICAL_RISK_HIGH):
        clinical_risk = CLINICAL_RISK_LOW

    needs_pubmed = bool(raw.get("needs_pubmed", False))
    needs_long_context = bool(raw.get("needs_long_context", False))

    priority_tags = raw.get("priority_tags")
    if not isinstance(priority_tags, list):
        priority_tags = []
    exclude = raw.get("exclude")
    if not isinstance(exclude, dict):
        exclude = {}

    return {
        "retrieval_constraints": sanitized_constraints,
        "priority_tags": priority_tags[:20],
        "exclude": exclude,
        "depth": depth,
        "needs_pubmed": needs_pubmed,
        "clinical_risk": clinical_risk,
        "needs_long_context": needs_long_context,
    }


async def run_metadata_intent_mapper(
    question: str,
    history: list[dict] | None,
    generator,
) -> dict[str, Any]:
    """
    Run the Metadata Intent Mapper using the orchestrator (Qwen).
    Returns a sanitized intent dict that governs retrieval and downstream steps.
    """
    context = ""
    if history and len(history) > 0:
        recent = history[-4:]
        context = "\nContexto reciente:\n" + "\n".join(
            f"{m.get('role', 'user')}: {(m.get('content') or '')[:200]}"
            for m in recent
        )

    user_content = INTENT_MAPPER_PROMPT + "\n" + question.strip() + context

    messages = [
        ChatMessage.from_system(
            "Respondes ÚNICAMENTE con un objeto JSON válido. Sin explicación, sin markdown."
        ),
        ChatMessage.from_user(user_content),
    ]

    try:
        import asyncio
        loop = asyncio.get_event_loop()
        result = await asyncio.wait_for(
            loop.run_in_executor(
                None,
                lambda: generator.run(messages=messages, generation_kwargs={"num_predict": 512}),
            ),
            timeout=30.0,
        )
        replies = result.get("replies", [])
        text = replies[0].text if replies else ""
        raw = _extract_json_object(text)
        if raw:
            intent = _sanitize_intent(raw)
            logger.info(
                "Intent: depth=%s needs_pubmed=%s clinical_risk=%s needs_long_context=%s",
                intent["depth"],
                intent["needs_pubmed"],
                intent["clinical_risk"],
                intent["needs_long_context"],
            )
            return intent
    except asyncio.TimeoutError:
        logger.warning("Intent mapper timeout")
    except Exception as e:
        logger.warning("Intent mapper error: %s", e)

    # Default intent when LLM fails or returns invalid JSON
    return _sanitize_intent({
        "retrieval_constraints": {},
        "priority_tags": [],
        "exclude": {},
        "depth": DEPTH_STANDARD,
        "needs_pubmed": False,
        "clinical_risk": CLINICAL_RISK_LOW,
        "needs_long_context": False,
    })


def get_rag_top_k_multiplier(intent: dict[str, Any] | None) -> int:
    """
    Return multiplier for RAG top_k so that after in-memory taxonomy filter we have enough docs.
    Orchestrator defines retrieval_constraints and depth; when constraints exist we oversample.
    """
    if not intent:
        return 2
    constraints = intent.get("retrieval_constraints") or {}
    has_constraints = any(constraints.get(dim) for dim in ("institucion", "tipo_documento", "dominio_salud", "territorio", "vigencia"))
    depth = intent.get("depth", DEPTH_STANDARD)
    if not has_constraints:
        return 3 if depth == DEPTH_DEEP else 2
    # With constraints we need more candidates so filter leaves enough
    return 6 if depth == DEPTH_DEEP else 5


def build_retrieval_filters_from_intent(intent: dict[str, Any]) -> dict | None:
    """
    Build Haystack/Pgvector filter dict from intent.retrieval_constraints.
    Returns None if no constraints (retrieve without filter).
    Taxonomy may be stored in meta.taxonomy as a dict; we filter in memory if needed.
    """
    constraints = intent.get("retrieval_constraints") or {}
    conditions = []
    for dim, values in constraints.items():
        if not values:
            continue
        # Document store may store taxonomy as meta.taxonomy.dimension or flattened meta.dimension
        # We use meta.taxonomy in indexing; pgvector often stores nested as JSON. Use $in for "any of"
        field = f"meta.taxonomy.{dim}"
        # Haystack filter: "$in" for list of values. Check doc store filter syntax.
        for v in values:
            conditions.append({"field": field, "operator": "==", "value": v})
    if not conditions:
        return None
    # OR within same dimension: doc matches if any of the values. AND across dimensions.
    if len(conditions) == 1:
        return {"operator": "AND", "conditions": conditions}
    return {"operator": "AND", "conditions": [{"operator": "OR", "conditions": conditions}]}


def filter_documents_by_intent(documents: list, intent: dict[str, Any]):
    """
    In-memory filter: keep documents whose taxonomy matches retrieval_constraints.
    Each doc may have meta.taxonomy = { "institucion": ["SSA"], "tipo_documento": ["ley"], ... }.
    If a dimension has values in intent, doc must have at least one matching value.
    """
    from haystack import Document

    constraints = intent.get("retrieval_constraints") or {}
    if not constraints or not documents:
        return list(documents)

    filtered = []
    for doc in documents:
        if not isinstance(doc, Document):
            filtered.append(doc)
            continue
        meta = doc.meta or {}
        taxonomy = meta.get("taxonomy") or {}
        if isinstance(taxonomy, str):
            try:
                taxonomy = json.loads(taxonomy)
            except Exception:
                taxonomy = {}
        match = True
        for dim, allowed in constraints.items():
            if not allowed:
                continue
            doc_vals = taxonomy.get(dim)
            if not doc_vals:
                # No taxonomy for this dimension: keep doc (no constraint)
                continue
            if isinstance(doc_vals, str):
                doc_vals = [doc_vals]
            if not any(v in allowed for v in doc_vals):
                match = False
                break
        if match:
            filtered.append(doc)
    return filtered


def should_use_clinical_validator(intent: dict[str, Any], documents: list) -> bool:
    """
    Part of the rule for running Ominis Med (BioMistral): any clinical response
    must be validated. This returns True when intent/documents indicate clinical context.
    The router also runs the validator when content_has_clinical_signals(question, answer).
    """
    if intent.get("clinical_risk") != CLINICAL_RISK_LOW:
        return True
    constraints = intent.get("retrieval_constraints") or {}
    if "guia_clinica" in (constraints.get("tipo_documento") or []):
        return True
    if "protocolo" in (constraints.get("tipo_documento") or []):
        return True
    # Check document taxonomies for funcion_salud
    from haystack import Document
    for doc in documents:
        if not isinstance(doc, Document):
            continue
        taxonomy = (doc.meta or {}).get("taxonomy") or {}
        func = taxonomy.get("funcion_salud") or []
        if isinstance(func, str):
            func = [func]
        if "tratamiento" in func or "diagnostico" in func:
            return True
    return False


def decide_research_model(
    intent: dict[str, Any],
    n_docs: int,
    temporal_range_years: float | None,
    use_128k_available: bool,
) -> tuple[str, bool]:
    """
    Decide between OpenScholar 8K and 128K per architecture rules.
    Returns (model_key, used_128k).
    128K only if: n_docs >= 15, (temporal_range > 10 or tipo has evaluacion/articulo_cientifico), needs_long_context, and 128K available.
    """
    if not use_128k_available:
        return "openscholar", False

    if n_docs < 15:
        return "openscholar", False
    if not intent.get("needs_long_context"):
        return "openscholar", False

    constraints = intent.get("retrieval_constraints") or {}
    tipos = constraints.get("tipo_documento") or []
    if "evaluacion" in tipos or "articulo_cientifico" in tipos:
        return "openscholar_128k", True
    if temporal_range_years is not None and temporal_range_years > 10:
        return "openscholar_128k", True

    return "openscholar", False
