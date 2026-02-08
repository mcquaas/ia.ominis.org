"""
PubMed search Haystack component using NCBI E-utilities API.
Returns search results as Haystack Document objects.

Includes automatic Spanish→English query translation and retry logic.
"""

import asyncio
import logging
import re
import xml.etree.ElementTree as ET
from typing import Optional

import httpx
from haystack import Document, component

logger = logging.getLogger(__name__)

ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

# Common Spanish→English medical term translations for better PubMed hits
_ES_EN_TERMS = {
    "insuficiencia cardíaca": "heart failure",
    "insuficiencia cardiaca": "heart failure",
    "diabetes mellitus": "diabetes mellitus",
    "diabetes tipo 2": "type 2 diabetes",
    "diabetes tipo 1": "type 1 diabetes",
    "hipertensión arterial": "arterial hypertension",
    "hipertensión": "hypertension",
    "cáncer": "cancer",
    "obesidad": "obesity",
    "mortalidad": "mortality",
    "morbilidad": "morbidity",
    "prevalencia": "prevalence",
    "incidencia": "incidence",
    "epidemiología": "epidemiology",
    "tratamiento": "treatment",
    "diagnóstico": "diagnosis",
    "guías clínicas": "clinical guidelines",
    "guía clínica": "clinical guideline",
    "ensayo clínico": "clinical trial",
    "revisión sistemática": "systematic review",
    "meta-análisis": "meta-analysis",
    "metaanálisis": "meta-analysis",
    "factores de riesgo": "risk factors",
    "enfermedad cardiovascular": "cardiovascular disease",
    "enfermedades cardiovasculares": "cardiovascular diseases",
    "enfermedad renal": "kidney disease",
    "enfermedad hepática": "liver disease",
    "salud pública": "public health",
    "salud mental": "mental health",
    "atención primaria": "primary care",
    "emergencias": "emergencies",
    "pediatría": "pediatrics",
    "geriatría": "geriatrics",
    "embarazo": "pregnancy",
    "vacuna": "vaccine",
    "vacunas": "vaccines",
    "antibióticos": "antibiotics",
    "resistencia antimicrobiana": "antimicrobial resistance",
    "México": "Mexico",
    "mexicano": "Mexican",
    "América Latina": "Latin America",
}


def _translate_query(query: str) -> str:
    """Best-effort Spanish→English translation for PubMed search."""
    result = query
    for es, en in sorted(_ES_EN_TERMS.items(), key=lambda x: -len(x[0])):
        result = re.sub(re.escape(es), en, result, flags=re.IGNORECASE)
    return result


# Words that indicate the user is searching for an author/person
_AUTHOR_CUES = re.compile(
    r"\b(trabajos?\s+de|artículos?\s+de|papers?\s+(by|from|de)|"
    r"publicaciones?\s+de|autor(es)?|investigador(es)?|"
    r"busca\w*\s+(a\s|en\s|de\s|por\s|artículos|trabajos|papers)|"
    r"encuentra\s|busca\w*\s.*(?:de|por|entre)\s)"
    r"", re.IGNORECASE,
)

# Stop words to exclude from name extraction
_STOP_WORDS = {
    "pubmed", "google", "scholar", "ominis", "mexico", "méxico",
    "busca", "dame", "encuentra", "muestra", "lista", "trabajos",
    "artículos", "papers", "publicaciones", "investigador",
    "investigaciones", "autor", "autores", "sobre", "acerca",
    "cardíaca", "cardiovascular", "salud", "medicina",
}


def _extract_author_query(query: str) -> str | None:
    """
    If the query looks like an author search, extract name(s) and format
    them for PubMed's [Author] field syntax.
    Returns None if this doesn't look like an author search.
    """
    has_cue = bool(_AUTHOR_CUES.search(query))

    # Heuristic: short query with capitalized words that look like a name
    # e.g. "Gustavo Ross PubMed" or "Gustavo Ross"
    if not has_cue:
        words = query.split()
        # Check if query is mostly a proper name (short, capitalized words)
        name_words = [w for w in words if w[0:1].isupper() and w.lower() not in _STOP_WORDS and len(w) > 1]
        noise_words = [w for w in words if w.lower() in _STOP_WORDS or w.lower() in ("en", "a", "el", "la", "los", "las", "y", "and")]
        if len(name_words) >= 2 and len(name_words) + len(noise_words) >= len(words) - 1:
            has_cue = True

    if not has_cue:
        return None

    # Remove common prefixes/noise to isolate names
    # e.g. "busca en PubMed trabajos de Atamañuk y Gustavo Ross"
    # → after removing noise → "Atamañuk y Gustavo Ross"
    cleaned = re.sub(
        r"(?i)\b(busca|en|pubmed|google|scholar|trabajos?|artículos?|"
        r"papers?|publicaciones?|de|del|por|and|the|sobre|acerca)\b",
        " ", query
    )

    # Split by conjunctions: "y", "and", ","
    segments = re.split(r"\s+(?:y|and|,|&)\s+", cleaned, flags=re.IGNORECASE)

    authors: list[str] = []
    for seg in segments:
        # Extract words that look like names (capitalized, or contain ñ/accents)
        words = seg.split()
        name_words = []
        for w in words:
            w_clean = w.strip(".,;:()\"'")
            if not w_clean:
                continue
            # A name word: starts with uppercase, or contains special chars like ñ
            if (
                w_clean[0].isupper()
                or any(c in w_clean for c in "ñÑáéíóúÁÉÍÓÚ")
            ) and w_clean.lower() not in _STOP_WORDS:
                name_words.append(w_clean)

        if name_words:
            author_str = " ".join(name_words)
            authors.append(author_str)

    if not authors:
        return None

    # Build PubMed query: each author as [Author] tag, joined with OR
    # Using OR because we want articles by ANY of the named authors
    parts = [f"{a}[Author]" for a in authors]

    # If multiple authors, also try the AND version as first query
    if len(parts) > 1:
        return " AND ".join(parts)
    return parts[0]


@component
class PubMedSearchComponent:
    """
    Haystack component that searches PubMed via NCBI E-utilities.
    Returns a list of Documents with source_type="pubmed".
    """

    @component.output_types(documents=list[Document])
    def run(self, query: str, top_k: int = 5) -> dict:
        """Search PubMed synchronously and return Documents."""
        import asyncio

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # We're inside an async context; run in a new loop via thread
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    docs = pool.submit(
                        lambda: asyncio.run(_search_pubmed_async(query, top_k))
                    ).result()
            else:
                docs = asyncio.run(_search_pubmed_async(query, top_k))
            return {"documents": docs}
        except Exception as e:
            logger.error(f"PubMed search error: {e}", exc_info=True)
            return {"documents": []}


async def _search_pubmed_async(query: str, max_results: int = 5) -> list[Document]:
    """
    Search PubMed using NCBI E-utilities.
    Two-step process: esearch (find IDs) → efetch (get details).
    Automatically translates Spanish queries to English for better results.
    Includes retry logic for rate-limited requests (429).
    """
    # Build list of queries to try (best → fallback)
    queries_to_try: list[str] = []

    # 1. If it looks like an author search, try [Author] syntax first
    author_query = _extract_author_query(query)
    _raw_author_names: list[str] = []
    if author_query:
        queries_to_try.append(author_query)
        # Also try individual authors with [Author] tag
        if " AND " in author_query:
            for part in author_query.split(" AND "):
                part = part.strip()
                queries_to_try.append(part)
                # Extract raw name (without [Author] tag) for abstract fallback
                raw = part.replace("[Author]", "").strip()
                if raw:
                    _raw_author_names.append(raw)
        else:
            raw = author_query.replace("[Author]", "").strip()
            if raw:
                _raw_author_names.append(raw)

    # 2. Translated query (Spanish → English)
    en_query = _translate_query(query)
    if en_query not in queries_to_try:
        queries_to_try.append(en_query)

    # 3. Original query as fallback (if different from translated)
    if en_query.lower() != query.lower() and query not in queries_to_try:
        queries_to_try.append(query)

    # 4. If author search: add raw names as plain text queries (searches
    #    titles + abstracts + all fields) — catches mentions even if
    #    the person isn't a PubMed-indexed author
    for name in _raw_author_names:
        if name not in queries_to_try:
            queries_to_try.append(name)

    all_ids: list[str] = []
    seen_ids: set[str] = set()

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Step 1: Search for article IDs (try translated first, then original)
            for q in queries_to_try:
                if len(all_ids) >= max_results:
                    break

                for attempt in range(3):
                    try:
                        search_params = {
                            "db": "pubmed",
                            "term": q,
                            "retmax": str(max_results),
                            "retmode": "json",
                            "sort": "relevance",
                        }
                        search_resp = await client.get(ESEARCH_URL, params=search_params)
                        if search_resp.status_code == 429:
                            await asyncio.sleep(1.0 * (attempt + 1))
                            continue
                        search_resp.raise_for_status()
                        break
                    except httpx.HTTPStatusError as e:
                        if e.response.status_code == 429 and attempt < 2:
                            await asyncio.sleep(1.0 * (attempt + 1))
                            continue
                        raise
                else:
                    continue

                search_data = search_resp.json()
                id_list = search_data.get("esearchresult", {}).get("idlist", [])
                for pid in id_list:
                    if pid not in seen_ids:
                        seen_ids.add(pid)
                        all_ids.append(pid)

                # Small delay between queries to avoid rate limiting
                if len(queries_to_try) > 1:
                    await asyncio.sleep(0.4)

            if not all_ids:
                logger.info(f"PubMed search for '{query[:50]}' returned 0 results")
                return []

            # Limit to max_results
            all_ids = all_ids[:max_results]

            # Step 2: Fetch article details (with retry)
            for attempt in range(3):
                try:
                    fetch_params = {
                        "db": "pubmed",
                        "id": ",".join(all_ids),
                        "rettype": "abstract",
                        "retmode": "xml",
                    }
                    await asyncio.sleep(0.4)  # Respect rate limit
                    fetch_resp = await client.get(EFETCH_URL, params=fetch_params)
                    if fetch_resp.status_code == 429:
                        await asyncio.sleep(1.5 * (attempt + 1))
                        continue
                    fetch_resp.raise_for_status()
                    break
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 429 and attempt < 2:
                        await asyncio.sleep(1.5 * (attempt + 1))
                        continue
                    raise
            else:
                logger.warning("PubMed efetch failed after 3 retries (rate limited)")
                return []

            documents = _parse_pubmed_xml(fetch_resp.text)
            logger.info(
                f"PubMed search for '{query[:50]}' -> '{en_query[:50]}' returned {len(documents)} articles"
            )
            return documents

    except Exception as e:
        logger.error(f"PubMed search error: {e}", exc_info=True)
        return []


def _parse_pubmed_xml(xml_text: str) -> list[Document]:
    """Parse PubMed XML response into Haystack Documents."""
    documents = []

    try:
        root = ET.fromstring(xml_text)

        for article_el in root.findall(".//PubmedArticle"):
            pmid_el = article_el.find(".//PMID")
            pmid = pmid_el.text if pmid_el is not None else ""

            title_el = article_el.find(".//ArticleTitle")
            title = title_el.text if title_el is not None else "Sin título"

            # Build abstract text
            abstract_parts = []
            for abs_el in article_el.findall(".//AbstractText"):
                label = abs_el.get("Label", "")
                text = abs_el.text or ""
                if label:
                    abstract_parts.append(f"{label}: {text}")
                else:
                    abstract_parts.append(text)
            abstract = "\n".join(abstract_parts)

            if not abstract:
                abstract = title or ""

            # Authors — show ALL authors so the LLM can identify them
            authors = []
            for author_el in article_el.findall(".//Author"):
                last = author_el.findtext("LastName", "")
                first = author_el.findtext("ForeName", "")
                if last:
                    authors.append(f"{last} {first}".strip())
            author_str = ", ".join(authors)

            # Journal and year
            journal_el = article_el.find(".//Journal/Title")
            journal = journal_el.text if journal_el is not None else ""
            year_el = article_el.find(".//PubDate/Year")
            year = year_el.text if year_el is not None else ""

            # Build URL and citation
            url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else ""
            citation = ""
            if author_str:
                citation = f"{author_str}. "
            if title:
                citation += f"{title}. "
            if journal:
                citation += f"{journal}"
            if year:
                citation += f" ({year})"
            citation = citation.strip().rstrip(".")

            doc = Document(
                content=abstract,
                meta={
                    "title": title or "Sin título",
                    "url": url,
                    "source_type": "pubmed",
                    "pmid": pmid,
                    "authors": author_str,
                    "journal": journal,
                    "year": year,
                    "citation": citation,
                },
            )
            documents.append(doc)

    except ET.ParseError as e:
        logger.error(f"Failed to parse PubMed XML: {e}")

    return documents


# Convenience async wrapper for use in the router
async def search_pubmed(query: str, max_results: int = 5) -> list[Document]:
    """Async wrapper for PubMed search."""
    return await _search_pubmed_async(query, max_results)
