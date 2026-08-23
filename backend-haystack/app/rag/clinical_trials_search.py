"""
ClinicalTrials.gov (Mexico) — keyword extraction + API fetch → Haystack Documents.
Shared by query-stream and /clinical-trials/assist.
"""

import json
import logging
import re

import httpx
from haystack import Document
from haystack.dataclasses import ChatMessage

logger = logging.getLogger(__name__)

CT_API = "https://clinicaltrials.gov/api/v2/studies"
MAX_KEYWORD_CHARS = 220

KEYWORD_SYSTEM = """Eres un asistente técnico interno (el usuario NO ve tu salida).
El usuario escribe en ESPAÑOL sobre ensayos clínicos o investigación en salud en México.

Tu única tarea: devolver un JSON válido para la API de ClinicalTrials.gov (parámetro query.term en INGLÉS).

Formato EXACTO (una sola línea, sin markdown):
{"keywords":"texto en inglés"}

Reglas:
- "keywords": 2 a 14 palabras en inglés: enfermedad, fármaco, dispositivo, tipo de intervención o población, según la pregunta.
- Sin saltos de línea dentro del string. Escapa comillas internas si las hubiera (mejor evítalas).
- Si la pregunta es muy amplia, elige términos que maximicen resultados relevantes en ensayos clínicos.
- Si no es sobre salud/ensayos, usa igualmente términos en inglés relacionados con lo preguntado para intentar una búsqueda útil."""


def parse_keywords_json(text: str) -> str:
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```\w*\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            kw = data.get("keywords") or data.get("query") or ""
            return str(kw).strip()[:MAX_KEYWORD_CHARS]
    except json.JSONDecodeError:
        pass
    m = re.search(r'"keywords"\s*:\s*"([^"]*)"', text or "")
    if m:
        return m.group(1).strip()[:MAX_KEYWORD_CHARS]
    return ""


def _mexico_locations_summary(locations: list) -> str:
    parts: list[str] = []
    for loc in locations or []:
        if not isinstance(loc, dict):
            continue
        c = (loc.get("country") or "").lower()
        if "mexico" not in c and "méxico" not in c:
            continue
        city = (loc.get("city") or "").strip()
        st = (loc.get("state") or "").strip()
        fac = (loc.get("facility") or "").strip()
        bits = ", ".join(x for x in [city, st] if x)
        if bits and fac:
            parts.append(f"{bits} — {fac[:72]}")
        elif bits:
            parts.append(bits)
        elif fac:
            parts.append(fac[:80])
    if parts:
        return "; ".join(parts[:4])
    # Fallback: any location (trial may list non-MX sites first)
    for loc in (locations or [])[:3]:
        if not isinstance(loc, dict):
            continue
        city = (loc.get("city") or "").strip()
        st = (loc.get("state") or "").strip()
        country = (loc.get("country") or "").strip()
        bits = ", ".join(x for x in [city, st, country] if x)
        if bits:
            parts.append(bits)
    return "; ".join(parts[:3]) if parts else ""


def _overall_status_es(status: str) -> str:
    """Map CT.gov overallStatus (English) to Spanish for LLM-facing content."""
    s = (status or "").strip().upper()
    mapping = {
        "RECRUITING": "En reclutamiento",
        "NOT_YET_RECRUITING": "Aún no recluta",
        "ACTIVE_NOT_RECRUITING": "Activo, sin reclutar",
        "COMPLETED": "Completado",
        "TERMINATED": "Terminado antes de tiempo",
        "WITHDRAWN": "Retirado",
        "SUSPENDED": "Suspendido",
        "ENROLLING_BY_INVITATION": "Inscripción por invitación",
        "AVAILABLE": "Disponible",
        "NO_LONGER_AVAILABLE": "Ya no disponible",
        "APPROVED_FOR_MARKETING": "Aprobado para comercialización",
        "UNKNOWN": "Desconocido",
    }
    return mapping.get(s, status or "no indicado")


def study_json_to_document(study: dict) -> Document:
    ps = study.get("protocolSection") or {}
    idm = ps.get("identificationModule") or {}
    nct = (idm.get("nctId") or "").strip()
    title = (idm.get("briefTitle") or "Sin título").strip()
    org = ((idm.get("organization") or {}).get("fullName") or "").strip()
    sm = ps.get("statusModule") or {}
    status_raw = (sm.get("overallStatus") or "").strip()
    status_es = _overall_status_es(status_raw)
    start_struct = sm.get("startDateStruct") or {}
    start_date = (start_struct.get("date") or "").strip()
    year_from_start = start_date[:4] if start_date and len(start_date) >= 4 and start_date[:4].isdigit() else ""

    loc_mod = ps.get("contactsLocationsModule") or {}
    locations = loc_mod.get("locations") or []
    if not isinstance(locations, list):
        locations = []
    loc_summary = _mexico_locations_summary(locations)

    dm = ps.get("descriptionModule") or {}
    brief = (dm.get("briefSummary") or "").strip()[:1600]
    cond_mod = ps.get("conditionsModule") or {}
    conds = cond_mod.get("conditions") or []
    if isinstance(conds, list):
        cond_str = ", ".join(str(c) for c in conds[:10])
    else:
        cond_str = ""
    arm = ps.get("armsInterventionsModule") or {}
    interventions = arm.get("interventions") or []
    intr_bits = []
    if isinstance(interventions, list):
        for it in interventions[:6]:
            if isinstance(it, dict):
                nm = (it.get("name") or "").strip()
                typ = (it.get("type") or "").strip()
                if nm:
                    intr_bits.append(f"{nm} ({typ})" if typ else nm)
    intr_str = "; ".join(intr_bits)

    parts = [
        f"NCT ID: {nct}",
        f"Título (registro, puede estar en inglés): {title}",
        f"Estado del estudio: {status_es}"
        + (f" (código en registro: {status_raw})" if status_raw and status_raw.upper() != status_es.upper() else ""),
        f"Fecha de inicio (registro): {start_date or 'no indicada'}",
        f"Sitios en o relacionados con México (si constan): {loc_summary or 'ver registro en ClinicalTrials.gov'}",
        f"Organización (registro): {org}",
    ]
    if cond_str:
        parts.append(f"Condiciones: {cond_str}")
    if intr_str:
        parts.append(f"Intervenciones: {intr_str}")
    if brief:
        parts.append(f"Resumen breve (puede estar en inglés en el registro): {brief}")

    content = "\n".join(parts)
    url = f"https://clinicaltrials.gov/study/{nct}" if nct else "https://clinicaltrials.gov/"
    fallback_search = f"https://clinicaltrials.gov/search?term={nct}" if nct else ""
    classic_show = f"https://clinicaltrials.gov/ct2/show/{nct}" if nct else ""
    display_title = f"{title} ({nct})" if nct else title
    return Document(
        content=content,
        meta={
            "title": display_title,
            "url": url,
            "ct_fallback_search_url": fallback_search,
            "ct_classic_show_url": classic_show,
            "source_type": "clinicaltrials",
            "nct_id": nct,
            "ct_start_date": start_date,
            "ct_locations_summary": loc_summary,
            "year": year_from_start or None,
        },
    )


def extract_keywords_sync(question: str, generator) -> str:
    messages = [
        ChatMessage.from_system(KEYWORD_SYSTEM),
        ChatMessage.from_user(f"Pregunta del usuario:\n{question.strip()}\n\nDevuelve solo el JSON."),
    ]
    try:
        kw_result = generator.run(messages=messages)
        kw_replies = kw_result.get("replies", [])
        kw_text = kw_replies[0].text if kw_replies else ""
        return parse_keywords_json(kw_text)
    except Exception as e:
        logger.warning("clinical_trials keyword extraction failed: %s", e)
        return ""


async def fetch_studies_http(keywords: str, page_size: int) -> tuple[list[dict], int]:
    params: dict[str, str] = {
        "query.locn": "Mexico",
        "pageSize": str(page_size),
    }
    if keywords:
        params["query.term"] = keywords
    async with httpx.AsyncClient(timeout=90.0) as client:
        r = await client.get(CT_API, params=params)
        r.raise_for_status()
        data = r.json()
    studies = data.get("studies") or []
    return studies, len(studies)


async def fetch_clinical_trials_documents(
    question: str,
    manager,
    model_id: str,
    max_results: int = 20,
) -> tuple[list[Document], str]:
    """
    LLM keywords (English) + ClinicalTrials.gov API → Documents with ct_* meta for UI.
    """
    generator = manager.get_generator(model_id)
    keywords_used = extract_keywords_sync(question, generator)
    if not keywords_used:
        keywords_used = "clinical trial health"

    studies, _n = await fetch_studies_http(keywords_used, min(max_results, 24))
    docs = [study_json_to_document(s) for s in studies if s]
    for d in docs:
        if d.meta is not None:
            d.meta["ct_search_keywords"] = keywords_used
    return docs, keywords_used
