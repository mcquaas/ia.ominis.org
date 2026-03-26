"""
Orchestrated tool selection for query-stream: which search backends to activate from
question + intent (LLM tool_sources + deterministic heuristics).
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

TOOL_KEYS = (
    "ominis_rag",
    "web",
    "pubmed",
    "openscholar",
    "clinical_trials",
    "doctor_directory_mx",
    "allcan_mexico",
)


def _empty_tools() -> dict[str, bool]:
    return {k: False for k in TOOL_KEYS}


def sanitize_tool_sources_from_llm(raw: Any) -> dict[str, bool]:
    out = _empty_tools()
    if not isinstance(raw, dict):
        return out
    for k in TOOL_KEYS:
        if k in raw:
            out[k] = bool(raw[k])
    return out


def infer_tool_sources_heuristic(question: str, intent: dict[str, Any] | None) -> dict[str, bool]:
    """Rule-based signals when the LLM omits or misclassifies tool_sources."""
    q = (question or "").strip()
    low = q.lower()
    out = _empty_tools()

    # OMINIS indexed docs: norms, policies, Mexican health system
    if re.search(
        r"\b(NOM-?\s*\d+|norma oficial|COFEPRIS|pol[ií]tica(s)?\s+de\s+salud|ley\s+general|"
        r"gu[ií]a(s)?\s+de\s+pr[aá]ctica|programa(s)?\s+de\s+salud|manual\s+de\s+procedimientos|"
        r"lineamiento(s)?|secretar[ií]a\s+de\s+salud|SSA\b|IMSS\b|ISSSTE\b|"
        r"taxonom[ií]a|clasificaci[oó]n\s+ominis)\b",
        low,
        re.I,
    ):
        out["ominis_rag"] = True

    # All.Can / patient organizations / cancer support in Mexico
    if re.search(
        r"(all\.?\s*can|allcan|asociaci[oó]n(es)?\s+de\s+pacientes|fundaci[oó]n(es)?|"
        r"grupo(s)?\s+de\s+apoyo|acompa[nñ]amiento|pacientes\s+con\s+c[aá]ncer|"
        r"oncolog[ií]a.*paciente|centro(s)?\s+de\s+atenci[oó]n.*paciente|"
        r"organizaci[oó]n(es)?.*c[aá]ncer|sociedad(es)?\s+de\s+pacientes)",
        low,
        re.I,
    ):
        out["allcan_mexico"] = True

    # Doctor directory: specialists by location / specialty
    specialist_terms = re.search(
        r"\b(m[eé]dico(s|as)?|doctor(a|es|as)?|especialista(s)?|cirujano(s|as)?|"
        r"cardi[oó]logo(s|as)?|dermat[oó]logo(s|as)?|ginec[oó]logo(s|as)?|onc[oó]logo(s|as)?|"
        r"pediatra(s)?|neur[oó]logo(s|as)?|oftalm[oó]logo(s|as)?|u[ró]logo(s|as)?)\b",
        low,
        re.I,
    )
    location_terms = re.search(
        r"\b(en\s+|cerca\s+de\s+|ciudad\s+|estado\s+|cdmx|jalisco|nuevo\s+le[oó]n|"
        r"guadalajara|monterrey|puebla|yucat[aá]n|tijuana|mexicali|quer[eé]taro|"
        r"veracruz|oaxaca|michoac[aá]n|baja\s+california|chiapas|tabasco)\b",
        low,
        re.I,
    )
    if specialist_terms and location_terms:
        out["doctor_directory_mx"] = True
    if re.search(
        r"\b(busco|buscar|recomienda|encuentra|necesito|quiero|dame|mu[eé]strame).{0,50}"
        r"(m[eé]dico|especialista|doctor|dermat[oó]logo|onc[oó]logo|cardi[oó]logo|ginec[oó]logo)",
        low,
        re.I,
    ):
        out["doctor_directory_mx"] = True

    # Clinical trials (Spanish: "estudios clínicos" is common; older regex only caught "ensayo clínico")
    if re.search(
        r"\b("
        r"ensayos?\s+cl[ií]nicos?|estudios?\s+cl[ií]nicos?|"
        r"investigaci[oó]n(es)?\s+cl[ií]nica(s)?|medicina\s+cl[ií]nica\s+de\s+ensayo|"
        r"clinical\s*trial|clinicaltrials|clinicaltrials\.gov|"
        r"\bNCT\s*\d+|reclutamiento\s+de\s+pacientes|fase\s+[I1V2345]|"
        r"registro(s)?\s+de\s+ensayo|ensayo(s)?\s+en\s+reclutamiento"
        r")\b",
        low,
        re.I,
    ):
        out["clinical_trials"] = True
    # Geographic / volume questions about where trials run (still CT.gov territory)
    if re.search(
        r"\b(estados?|ciudad(es)?|m[eé]xico).{0,80}(m[aá]s\s+)?(ensayos|estudios)\s+cl[ií]nicos|"
        r"(ensayos|estudios)\s+cl[ií]nicos.{0,80}(estados?|sedes?|m[eé]xico)",
        low,
        re.I,
    ):
        out["clinical_trials"] = True

    # "Ensayos" without the word "clínico" (very common: "busca ensayos sobre X", "ensayos de fase 2")
    if re.search(
        r"\b(busca|buscar|encuentra|encuentre|listar|listado|mu[eé]strame|hay|existen|"
        r"revisar|consultar)\s+ensayos?\b",
        low,
        re.I,
    ):
        out["clinical_trials"] = True
    if re.search(r"\bensayos?\s+(sobre|de|del|con|para|usando|relacionados?)\b", low, re.I):
        out["clinical_trials"] = True

    # Named biologics / onco drugs → trials + literature (ClinicalTrials.gov + PubMed/OpenScholar)
    if re.search(
        r"\b(pembrolizumab|nivolumab|atezolizumab|durvalumab|cemiplimab|ipilimumab|"
        r"trastuzumab|bevacizumab|rituximab|cetuximab|infliximab|adalimumab|"
        r"osimertinib|palbociclib|ribociclib|abemaciclib|lenalidomide|carfilzomib)\b",
        low,
        re.I,
    ):
        out["clinical_trials"] = True
        out["pubmed"] = True
        out["openscholar"] = True

    # PubMed / biomedical literature
    if re.search(r"\b(pubmed|pub\s*med|art[ií]culo(s)?\s+(m[eé]dico|biom[eé]dico)|literatura\s+m[eé]dica)\b", low, re.I):
        out["pubmed"] = True

    # OpenScholar / scientific evidence
    if re.search(
        r"\b(evidencia\s+cient[ií]fica|revisi[oó]n\s+sistem[aá]tica|meta[\s-]?an[aá]lisis|"
        r"estudios\s+observacionales|RCT\b|ensayo\s+aleatorizado|literatura\s+acad[eé]mica|"
        r"papers?\s+cient[ií]ficos)\b",
        low,
        re.I,
    ):
        out["openscholar"] = True

    # Web: recency or general web need
    if re.search(
        r"\b(noticias?|actualidad|últim[oa]s?|reciente|este\s+año|202[4-9]|"
        r"reforma\s+reciente|qué\s+pasó)\b",
        low,
        re.I,
    ):
        out["web"] = True
    if intent and intent.get("needs_recent_info"):
        out["web"] = True

    # Intent mapper: needs_pubmed → prefer PubMed (and often OpenScholar for academic)
    if intent:
        if intent.get("needs_pubmed"):
            out["pubmed"] = True
            out["openscholar"] = True
        if intent.get("needs_evidence_sources") and not any(out.values()):
            out["ominis_rag"] = True

    return out


def merge_tool_sources(
    llm: dict[str, bool] | None,
    heuristic: dict[str, bool],
) -> dict[str, bool]:
    """Union: activate if either the intent LLM or heuristics suggests a source."""
    merged = _empty_tools()
    llm = llm or _empty_tools()
    for k in TOOL_KEYS:
        merged[k] = bool(llm.get(k)) or bool(heuristic.get(k))
    return merged


def ensure_minimum_sources(sources: dict[str, bool]) -> dict[str, bool]:
    """If nothing selected, default to OMINIS RAG for substantive answers."""
    if not any(sources.values()):
        sources = dict(sources)
        sources["ominis_rag"] = True
    return sources


def tool_labels_es(sources: dict[str, bool]) -> list[str]:
    labels: list[str] = []
    if sources.get("ominis_rag"):
        labels.append("OMINIS (base indexada)")
    if sources.get("web"):
        labels.append("Web")
    if sources.get("pubmed"):
        labels.append("PubMed")
    if sources.get("openscholar"):
        labels.append("OpenScholar (evidencia académica)")
    if sources.get("clinical_trials"):
        labels.append("ClinicalTrials.gov")
    if sources.get("doctor_directory_mx"):
        labels.append("Directorio de médicos MX")
    if sources.get("allcan_mexico"):
        labels.append("All.Can México (organizaciones)")
    return labels


def format_tool_plan_message(sources: dict[str, bool]) -> str:
    labels = tool_labels_es(sources)
    if not labels:
        return "Generando respuesta sin búsqueda externa."
    return "Fuentes activadas para esta respuesta: " + "; ".join(labels) + "."


def plan_tools_for_query(question: str, intent: dict[str, Any] | None) -> dict[str, Any]:
    """
    Returns { "sources": dict[str,bool], "message": str, "labels": list[str] }.
    """
    llm_ts = sanitize_tool_sources_from_llm((intent or {}).get("tool_sources"))
    heur = infer_tool_sources_heuristic(question, intent)
    merged = merge_tool_sources(llm_ts, heur)
    merged = ensure_minimum_sources(merged)
    labels = tool_labels_es(merged)
    msg = format_tool_plan_message(merged)
    logger.info("Tool plan: %s", labels)
    return {"sources": merged, "message": msg, "labels": labels}


def apply_tool_plan_to_query_request(
    body: Any,
    sources: dict[str, bool],
    *,
    user: Any | None = None,
) -> dict[str, bool]:
    """
    Mutate a QueryRequest-like object with boolean search flags.
    Guest users cannot use doctor directory, All.Can, or clinical trials (backend enforces the same).
    Returns the effective tool map after gating (for SSE messaging).
    """
    eff = dict(sources)
    if user is None:
        eff["doctor_directory_mx"] = False
        eff["allcan_mexico"] = False
        eff["clinical_trials"] = False
    body.rag_search = bool(eff.get("ominis_rag"))
    body.web_search = bool(eff.get("web"))
    body.pubmed_search = bool(eff.get("pubmed"))
    body.openscholar_search = bool(eff.get("openscholar"))
    body.clinical_trials_search = bool(eff.get("clinical_trials"))
    body.doctor_directory_search = bool(eff.get("doctor_directory_mx"))
    body.allcan_search = bool(eff.get("allcan_mexico"))
    if not any(
        [
            eff.get("ominis_rag"),
            eff.get("web"),
            eff.get("pubmed"),
            eff.get("openscholar"),
            eff.get("clinical_trials"),
            eff.get("doctor_directory_mx"),
            eff.get("allcan_mexico"),
        ]
    ):
        eff["ominis_rag"] = True
        body.rag_search = True
    return eff


TOOL_SUGGESTION_UI_LABELS: dict[str, str] = {
    "ominis_rag": "OMINIS",
    "web": "Web",
    "pubmed": "PubMed",
    "openscholar": "OpenScholar",
    "clinical_trials": "ClinicalTrials.gov",
    "doctor_directory_mx": "Directorio MX",
    "allcan_mexico": "All.Can MX",
}


def eff_from_body(body: Any) -> dict[str, bool]:
    """Map QueryRequest flags to orchestration tool keys."""
    return {
        "ominis_rag": bool(getattr(body, "rag_search", False)),
        "web": bool(getattr(body, "web_search", False)),
        "pubmed": bool(getattr(body, "pubmed_search", False)),
        "openscholar": bool(getattr(body, "openscholar_search", False)),
        "clinical_trials": bool(getattr(body, "clinical_trials_search", False)),
        "doctor_directory_mx": bool(getattr(body, "doctor_directory_search", False)),
        "allcan_mexico": bool(getattr(body, "allcan_search", False)),
    }


def suggest_tools_to_add(
    question: str,
    intent: dict[str, Any] | None,
    eff: dict[str, bool],
    *,
    user: Any | None,
) -> list[dict[str, str]]:
    """
    Tools that are currently off but may improve a follow-up answer (UI 'Agregar' buttons).
    """
    merged = merge_tool_sources(
        sanitize_tool_sources_from_llm((intent or {}).get("tool_sources")),
        infer_tool_sources_heuristic(question, intent),
    )
    low = (question or "").strip().lower()
    suggestions: list[str] = []

    def add(k: str) -> None:
        if eff.get(k):
            return
        if user is None and k in ("doctor_directory_mx", "allcan_mexico", "clinical_trials"):
            return
        if k not in suggestions:
            suggestions.append(k)

    for k in TOOL_KEYS:
        if merged.get(k):
            add(k)

    if re.search(
        r"\b(nom|norma|ley|pol[ií]tica|presupuesto|transparencia|instituto\s+nacional|secretar[ií]a|"
        r"oficial|gaceta|decreto|sistemas\s+de\s+informaci[oó]n)\b",
        low,
        re.I,
    ):
        add("ominis_rag")
    if re.search(
        r"\b(evidencia\s+cient[ií]fica|revisi[oó]n\s+sistem[aá]tica|meta[\s-]?an[aá]lisis|"
        r"literatura\s+acad[eé]mica|papers?|art[ií]culos?\s+acad[eé]micos)\b",
        low,
        re.I,
    ):
        add("openscholar")
    if re.search(r"\b(pubmed|pub\s*med|art[ií]culo(s)?\s+m[eé]dico)\b", low, re.I):
        add("pubmed")
    if re.search(r"\b(noticias?|actualidad|últim[oa]s?|202[4-9])\b", low, re.I):
        add("web")

    heur_for_order = infer_tool_sources_heuristic(question, intent)
    order = (
        (
            "clinical_trials",
            "web",
            "pubmed",
            "openscholar",
            "ominis_rag",
            "doctor_directory_mx",
            "allcan_mexico",
        )
        if heur_for_order.get("clinical_trials")
        else (
            "ominis_rag",
            "openscholar",
            "clinical_trials",
            "pubmed",
            "web",
            "doctor_directory_mx",
            "allcan_mexico",
        )
    )
    ordered = [k for k in order if k in suggestions][:6]
    return [{"id": k, "label": TOOL_SUGGESTION_UI_LABELS[k]} for k in ordered]


def _answer_suggests_insufficient(answer: str) -> bool:
    """Heuristic: model said it lacks data or only gave generic guidance."""
    if not (answer or "").strip() or len(answer.strip()) < 50:
        return False
    low = answer.lower()
    return bool(
        re.search(
            r"(no tengo acceso|no dispongo|no encontr[eé]|no hay datos|datos insuficientes|"
            r"no proporcionan|no aparece|las fuentes disponibles no|lamentablemente.{0,40}no|"
            r"no puedo (dar|proporcionar|ofrecer)|recomendar[íi]a consultar|"
            r"te recomendar[íi]a revisar|consulta.{0,30}(oficial|sitio|transparencia)|"
            r"bases\s+de\s+datos.{0,40}estudio|b[uú]squeda\s+m[aá]s\s+profunda|"
            r"registros?\s+de\s+investigaci[oó]n)",
            low,
            re.I,
        )
    )


def _question_needs_numeric_or_fiscal_evidence(question: str) -> bool:
    q = (question or "").lower()
    return bool(
        re.search(
            r"\b(compara|comparaci[oó]n|presupuesto|financ|millones|mdp|recursos|"
            r"ejercicio|aprobado|instituto\s+nacional|transparencia|d[áa]t[oa]s?\s+concret)\b",
            q,
            re.I,
        )
    )


def _question_is_clinical_trials_heavy(question: str, intent: dict[str, Any] | None) -> bool:
    """True when the query is about trials registry / sites / recruitment (ClinicalTrials.gov)."""
    if intent:
        ts = sanitize_tool_sources_from_llm(intent.get("tool_sources"))
        if ts.get("clinical_trials"):
            return True
    return bool(infer_tool_sources_heuristic(question, intent).get("clinical_trials"))


def suggest_tools_for_followup(
    question: str,
    answer: str,
    intent: dict[str, Any] | None,
    eff: dict[str, bool],
    *,
    user: Any | None,
) -> list[dict[str, Any]]:
    """
    UI buttons: (1) tools not yet enabled — «Agregar»;
    (2) tools already enabled but answer looks thin — «profundizar» (second pass, deeper retrieval).
    """
    add_items = suggest_tools_to_add(question, intent, eff, user=user)
    seen_ids = {x["id"] for x in add_items}
    out: list[dict[str, Any]] = [dict(x) for x in add_items]

    weak = _answer_suggests_insufficient(answer)
    fiscal = _question_needs_numeric_or_fiscal_evidence(question)
    heur = infer_tool_sources_heuristic(question, intent)
    ct_heavy = _question_is_clinical_trials_heavy(question, intent)

    if not weak and not fiscal:
        return out[:8]

    # Order: for trial questions, surface ClinicalTrials.gov before generic RAG
    extend_keys: list[str] = []
    if fiscal:
        for k in ("web", "openscholar", "ominis_rag"):
            if eff.get(k) and k not in seen_ids:
                extend_keys.append(k)
    elif ct_heavy:
        for k in ("clinical_trials", "web", "pubmed", "openscholar", "ominis_rag"):
            if eff.get(k) and k not in seen_ids:
                extend_keys.append(k)
    else:
        order = (
            "web",
            "openscholar",
            "ominis_rag",
            "pubmed",
            "clinical_trials",
            "doctor_directory_mx",
            "allcan_mexico",
        )
        for k in order:
            if eff.get(k) and heur.get(k) and k not in seen_ids:
                extend_keys.append(k)

    for k in extend_keys:
        base = TOOL_SUGGESTION_UI_LABELS.get(k, k)
        out.append(
            {
                "id": k,
                "label": f"{base} · profundizar",
                "extend": True,
            }
        )
        seen_ids.add(k)

    return out[:8]
