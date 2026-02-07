#!/usr/bin/env python3
"""
Make RAG filtering MUCH stricter - only return truly relevant sources
"""

with open("/home/ubuntu/rag_api.py", "r") as f:
    content = f.read()

# Find and replace the entire tool_search_rag function
import re

# Find the function
pattern = r'def tool_search_rag\(query, k=5, min_score=0\.5\):.*?(?=\ndef |\nclass |\n# ====)'
match = re.search(pattern, content, re.DOTALL)

if match:
    old_func = match.group(0)
    print(f"Found tool_search_rag function ({len(old_func)} chars)")
    
    new_func = '''def tool_search_rag(query, k=3, min_score=0.8):
    """Search RAG with VERY strict relevance filtering. Returns ONLY truly relevant sources."""
    chunks = load_chunks()
    query_lower = query.lower()
    
    # Extract meaningful words (remove common words)
    stop_words = {
        # Spanish
        "el", "la", "los", "las", "de", "del", "en", "un", "una", "que", "es", "y", "a", 
        "por", "para", "con", "se", "su", "al", "lo", "como", "más", "pero", "sus", "le",
        "ya", "o", "este", "esta", "estos", "estas", "ser", "son", "fue", "han", "hay",
        "qué", "cómo", "cuál", "cuáles", "cuántos", "cuántas", "dónde", "cuándo",
        "tiene", "tienen", "puede", "pueden", "entre", "sobre", "cual", "cuando", "donde",
        # English
        "the", "is", "are", "what", "how", "which", "where", "when", "who", "why",
        "for", "and", "or", "in", "on", "to", "of", "with", "from", "by", "at", "as",
        "new", "about", "be", "been", "being", "have", "has", "had", "do", "does", "did",
        # Generic health terms (too broad to be useful for matching)
        "salud", "health", "datos", "data", "información", "information", "mexico", "méxico",
        "mexicano", "mexicana", "nacional", "enfermedad", "disease", "pacientes", "patients",
        "casos", "cases", "tratamiento", "treatment", "médico", "medical", "clínico", "clinical"
    }
    
    query_words = set(query_lower.split()) - stop_words
    
    # These are the KEY terms that MUST match for relevance
    key_terms = query_words.copy()
    
    if not key_terms:
        print(f"[RAG] No key terms extracted from query: '{query[:50]}...'")
        return []
    
    print(f"[RAG] Query: '{query[:60]}...' | Key terms: {key_terms}")
    
    results = []
    for chunk in chunks:
        content_text = chunk.get("content", "").lower()
        title = chunk.get("metadata", {}).get("title", "").lower()
        full_text = f"{title} {content_text}"
        
        # Count how many KEY terms appear in the document
        matching_terms = set()
        for term in key_terms:
            if term in full_text:
                matching_terms.add(term)
        
        if not matching_terms:
            continue  # Skip documents with ZERO key term matches
        
        # Calculate relevance score
        term_coverage = len(matching_terms) / len(key_terms)  # 0 to 1
        
        # Bonus for exact phrase match
        phrase_bonus = 0.3 if query_lower in full_text else 0.0
        
        # Bonus for key terms in title (more relevant)
        title_matches = sum(1 for t in key_terms if t in title)
        title_bonus = min(0.4, title_matches * 0.2)
        
        score = term_coverage + phrase_bonus + title_bonus
        
        results.append({
            "chunk": chunk,
            "score": score,
            "matching_terms": matching_terms,
            "term_coverage": term_coverage
        })
    
    # Sort by score descending
    results.sort(key=lambda x: x["score"], reverse=True)
    
    # STRICT filter: only return if score >= min_score AND has good term coverage
    filtered = []
    for r in results:
        if r["score"] >= min_score and r["term_coverage"] >= 0.5:
            filtered.append((r["chunk"], r["score"]))
    
    print(f"[RAG] Found {len(filtered)} sources above threshold {min_score} (from {len(results)} candidates)")
    
    if filtered:
        for i, (chunk, score) in enumerate(filtered[:k]):
            title = chunk.get("metadata", {}).get("title", "")[:50]
            print(f"[RAG] #{i+1}: {title}... (score: {score:.2f})")
    else:
        print(f"[RAG] No sources meet relevance threshold - returning empty")
    
    return filtered[:k]

'''
    
    content = content.replace(old_func, new_func)
    
    with open("/home/ubuntu/rag_api.py", "w") as f:
        f.write(content)
    
    print("Replaced tool_search_rag with stricter version")
else:
    print("Could not find tool_search_rag function")
