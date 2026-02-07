#!/usr/bin/env python3
"""
Fix search quality:
1. Better PubMed query building (use medical abbreviation expansion)
2. Better web search queries (clean up instructions, keep topic)
3. Post-retrieval relevance filtering for PubMed and Web
4. Limit to 3 sources per type (max 9 total, but filtered)
"""
import re

with open("/home/ubuntu/rag_api.py", "r") as f:
    content = f.read()

# 1. Fix build_pubmed_query to use medical abbreviations and better translations
old_build = content[content.find("def build_pubmed_query("):content.find("\n\ndef ", content.find("def build_pubmed_query("))+1]
print(f"Found build_pubmed_query ({len(old_build)} chars)")

new_build = '''def build_pubmed_query(spanish_text):
    """Convert Spanish medical text to English PubMed search terms."""
    text = spanish_text.lower().strip().rstrip("?\\u00bf!\\u00a1.")
    
    # First expand medical abbreviations
    words = text.split()
    expanded_words = list(words)
    for i, word in enumerate(words):
        if word in MEDICAL_ABBREVIATIONS:
            # Use first expansion (most common)
            expanded_words[i] = MEDICAL_ABBREVIATIONS[word][0]
    text = " ".join(expanded_words)

    # Additional medical translations
    extra_translations = {
        "novedoso": "novel", "novedosos": "novel", "nuevo": "new", "nuevos": "new",
        "reciente": "recent", "recientes": "recent", "actual": "current",
        "avanzado": "advanced", "emergente": "emerging",
        "eficaz": "effective", "seguro": "safe", "oral": "oral",
        "inyectable": "injectable", "combinado": "combination",
        "primera linea": "first line", "segunda linea": "second line",
        "guia clinica": "clinical guideline", "guia": "guideline",
        "revision sistematica": "systematic review", "metaanalisis": "meta-analysis",
        "ensayo clinico": "clinical trial", "estudio": "study",
        "mortalidad": "mortality", "morbilidad": "morbidity",
        "prevalencia": "prevalence", "incidencia": "incidence",
        "complicaciones": "complications", "pronostico": "prognosis",
        "fisiopatologia": "pathophysiology", "epidemiologia": "epidemiology",
    }

    # Try multi-word translations first
    result_terms = []
    remaining = text
    
    # Combine all translations
    all_trans = {}
    all_trans.update(_MEDICAL_TRANSLATIONS)
    all_trans.update(extra_translations)
    
    for es_term, en_term in sorted(all_trans.items(), key=lambda x: -len(x[0])):
        if es_term in remaining:
            result_terms.append(en_term)
            remaining = remaining.replace(es_term, " ")

    if result_terms:
        seen = set()
        unique = []
        for t in result_terms:
            if t.lower() not in seen:
                seen.add(t.lower())
                unique.append(t)
        query = " ".join(unique[:6])
        print(f"[build_pubmed_query] '{spanish_text[:50]}' -> '{query}'")
        return query

    # Fallback
    words = text.split()
    filtered = [w for w in words if w not in _SPANISH_STOPWORDS and len(w) > 2]
    query = " ".join(filtered[:6])
    print(f"[build_pubmed_query] '{spanish_text[:50]}' -> '{query}' (fallback)")
    return query

'''

content = content.replace(old_build, new_build)
print("1. Updated build_pubmed_query")


# 2. Add post-retrieval relevance filter function
relevance_filter = '''
def filter_relevant_results(sources, query, max_results=3):
    """Filter search results for relevance to the query topic."""
    if not sources:
        return []
    
    # Extract key terms from query (using medical abbreviation expansion)
    query_lower = query.lower()
    expanded = expand_medical_terms(query_lower)
    
    # Remove common stopwords
    stop = {"el", "la", "los", "las", "de", "del", "en", "un", "una", "que", "es", "y", "a",
            "por", "para", "con", "se", "su", "al", "lo", "como", "busca", "buscar", "dame",
            "encuentra", "investiga", "cuál", "cuáles", "qué", "cómo", "hay", "son", "the",
            "is", "are", "what", "how", "for", "and", "or", "in", "on", "to", "of", "with",
            "tratamiento", "treatment", "nuevo", "nuevos", "novedoso", "novedosos",
            "información", "datos", "salud", "health", "mexico", "méxico"}
    
    key_terms = expanded - stop
    if not key_terms:
        # If no specific terms, return top results as-is
        return sources[:max_results]
    
    scored = []
    for src in sources:
        title = src.get("title", "").lower()
        # Check how many key terms appear in the title
        matches = sum(1 for t in key_terms if t in title)
        if matches > 0:
            scored.append((src, matches))
    
    # Sort by match count descending
    scored.sort(key=lambda x: x[1], reverse=True)
    
    filtered = [s for s, _ in scored[:max_results]]
    
    if len(filtered) < len(sources):
        removed = len(sources) - len(filtered)
        print(f"[relevance_filter] Kept {len(filtered)}/{len(sources)} results ({removed} irrelevant removed)")
    
    return filtered

'''

# Insert before handle_stream
marker = "# ============ MAIN STREAMING HANDLER ============"
if marker in content:
    content = content.replace(marker, relevance_filter + "\n" + marker)
    print("2. Added filter_relevant_results function")
else:
    print("2. Could not find marker")


# 3. Update normal question flow to filter results and limit per source
# Fix PubMed section
old_pm = '''    # PubMed search
    if pubmed_enabled:
        yield {"type": "status", "message": "Buscando en PubMed..."}
        pubmed_query = build_pubmed_query(question)
        pm_text, pm_sources = tool_pubmed_search(pubmed_query)
        if pm_sources:
            pm_articles = pm_text.split("\\n\\n") if pm_text else []
            for i, src in enumerate(pm_sources):
                ref_num += 1
                art = pm_articles[i][:400] if i < len(pm_articles) else src.get("title", "")
                all_context_parts.append("[" + str(ref_num) + "] PubMed: " + src.get("title", "") + "\\n" + art)
                src["ref_num"] = ref_num
            all_sources.extend(pm_sources)'''

new_pm = '''    # PubMed search
    if pubmed_enabled:
        yield {"type": "status", "message": "Buscando en PubMed..."}
        pubmed_query = build_pubmed_query(question)
        pm_text, pm_sources = tool_pubmed_search(pubmed_query, max_results=5)
        if pm_sources:
            # Filter for relevance
            pm_sources = filter_relevant_results(pm_sources, question, max_results=3)
            pm_articles = pm_text.split("\\n\\n") if pm_text else []
            for i, src in enumerate(pm_sources):
                ref_num += 1
                # Find matching article text
                art = ""
                for pa in pm_articles:
                    if src.get("title", "XXX")[:30].lower() in pa.lower():
                        art = pa[:400]
                        break
                if not art:
                    art = src.get("title", "")
                all_context_parts.append("[" + str(ref_num) + "] PubMed: " + src.get("title", "") + "\\n" + art)
                src["ref_num"] = ref_num
            all_sources.extend(pm_sources)'''

if old_pm in content:
    content = content.replace(old_pm, new_pm)
    print("3. Updated PubMed section with relevance filter")
else:
    print("3. Could not find PubMed section")


# Fix Web section
old_web = '''    # Web search
    if web_enabled:
        yield {"type": "status", "message": "Buscando en internet..."}
        web_text, web_sources = tool_web_search(question)
        if web_sources:
            web_articles = web_text.split("\\n\\n") if web_text else []
            for i, src in enumerate(web_sources):
                ref_num += 1
                art = web_articles[i][:400] if i < len(web_articles) else src.get("title", "")
                all_context_parts.append("[" + str(ref_num) + "] Web: " + src.get("title", "") + "\\n" + art)
                src["ref_num"] = ref_num
            all_sources.extend(web_sources)'''

new_web = '''    # Web search
    if web_enabled:
        yield {"type": "status", "message": "Buscando en internet..."}
        # Clean the question for web search (remove instruction words)
        web_query = question
        for prefix in ["busca ", "buscar ", "investiga ", "dame ", "encuentra "]:
            if web_query.lower().startswith(prefix):
                web_query = web_query[len(prefix):]
        web_text, web_sources = tool_web_search(web_query)
        if web_sources:
            # Filter for relevance
            web_sources = filter_relevant_results(web_sources, question, max_results=3)
            web_articles = web_text.split("\\n\\n") if web_text else []
            for i, src in enumerate(web_sources):
                ref_num += 1
                art = ""
                for wa in web_articles:
                    if src.get("title", "XXX")[:30].lower() in wa.lower():
                        art = wa[:400]
                        break
                if not art:
                    art = src.get("title", "")
                all_context_parts.append("[" + str(ref_num) + "] Web: " + src.get("title", "") + "\\n" + art)
                src["ref_num"] = ref_num
            all_sources.extend(web_sources)'''

if old_web in content:
    content = content.replace(old_web, new_web)
    print("4. Updated Web section with relevance filter")
else:
    print("4. Could not find Web section")


with open("/home/ubuntu/rag_api.py", "w") as f:
    f.write(content)

print("\nSearch quality improvements applied!")
