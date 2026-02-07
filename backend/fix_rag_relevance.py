#!/usr/bin/env python3
"""Fix RAG relevance by adding minimum score threshold"""

with open("/home/ubuntu/rag_api.py", "r") as f:
    content = f.read()

# Find and replace the tool_search_rag function
old_func = '''def tool_search_rag(query, k=5):
    chunks = load_chunks()
    query_lower = query.lower()
    query_words = set(query_lower.split())
    stop_words = {"el", "la", "los", "las", "de", "del", "en", "un", "una", "que", "es", "y", "a", "por", "para", "con", "se", "su", "al", "lo", "como", "the", "is", "are", "what", "how", "qué", "cómo", "méxico", "mexicano", "mexicana"}
    query_words = query_words - stop_words

    results = []
    for chunk in chunks:
        content = chunk.get("content", "").lower()
        title = chunk.get("metadata", {}).get("title", "").lower()
        full_text = f"{title} {content}"
        content_words = set(full_text.split()) - stop_words

        if not query_words:
            score = 0.0
        else:
            overlap = len(query_words & content_words)
            phrase_bonus = 0.5 if query_lower in full_text else 0.0
            title_bonus = 0.3 if any(w in title for w in query_words) else 0.0
            score = (overlap / len(query_words)) + phrase_bonus + title_bonus
        results.append((chunk, score))

    results.sort(key=lambda x: x[1], reverse=True)
    return results[:k]'''

new_func = '''def tool_search_rag(query, k=5, min_score=0.4):
    """Search RAG with minimum relevance threshold."""
    chunks = load_chunks()
    query_lower = query.lower()
    query_words = set(query_lower.split())
    
    # Common stop words
    stop_words = {"el", "la", "los", "las", "de", "del", "en", "un", "una", "que", "es", "y", "a", "por", "para", "con", "se", "su", "al", "lo", "como", "the", "is", "are", "what", "how", "qué", "cómo", "cuál", "cuáles", "cuántos", "cuántas", "hay", "tiene", "tienen"}
    
    # Generic health terms that shouldn't drive matching alone
    generic_terms = {"prevalencia", "incidencia", "tasa", "mortalidad", "morbilidad", "datos", "estadísticas", "información", "salud", "enfermedad", "pacientes", "casos", "mexico", "méxico", "mexicano", "mexicana", "nacional"}
    
    query_words = query_words - stop_words
    
    # Identify content-specific keywords (not generic terms)
    specific_keywords = query_words - generic_terms
    
    results = []
    for chunk in chunks:
        content = chunk.get("content", "").lower()
        title = chunk.get("metadata", {}).get("title", "").lower()
        full_text = f"{title} {content}"
        content_words = set(full_text.split()) - stop_words

        if not query_words:
            score = 0.0
        else:
            # Count overlapping words
            overlap = len(query_words & content_words)
            
            # Bonus for specific keyword matches (most important)
            specific_overlap = len(specific_keywords & content_words)
            specific_bonus = specific_overlap * 0.5 if specific_keywords else 0.0
            
            # Bonus for phrase match
            phrase_bonus = 0.5 if query_lower in full_text else 0.0
            
            # Bonus for title match on specific keywords
            title_bonus = 0.4 if any(w in title for w in specific_keywords) else 0.0
            
            # Base score
            base_score = overlap / len(query_words) if query_words else 0.0
            
            score = base_score + specific_bonus + phrase_bonus + title_bonus
            
        results.append((chunk, score))

    # Sort by score descending
    results.sort(key=lambda x: x[1], reverse=True)
    
    # Filter by minimum score threshold
    filtered = [(chunk, score) for chunk, score in results if score >= min_score]
    
    # If no results pass threshold, return top result only if score > 0.2
    if not filtered and results and results[0][1] > 0.2:
        filtered = [results[0]]
    
    print(f"[RAG] Query: '{query[:50]}...' | Found {len(filtered)}/{len(results)} above threshold {min_score}")
    if filtered:
        print(f"[RAG] Top result: {filtered[0][0].get('metadata', {}).get('title', '')[:60]}... (score: {filtered[0][1]:.2f})")
    
    return filtered[:k]'''

if old_func in content:
    content = content.replace(old_func, new_func)
    with open("/home/ubuntu/rag_api.py", "w") as f:
        f.write(content)
    print("RAG relevance fix applied - added minimum score threshold")
else:
    print("ERROR: Could not find target function")
