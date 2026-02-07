#!/usr/bin/env python3
"""Improve RAG relevance - require key terms in results"""

with open("/home/ubuntu/rag_api.py", "r") as f:
    content = f.read()

# Find the current function
old_func = '''def tool_search_rag(query, k=5, min_score=0.4):
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

new_func = '''def tool_search_rag(query, k=5, min_score=0.5):
    """Search RAG with strict relevance filtering."""
    chunks = load_chunks()
    query_lower = query.lower()
    query_words = set(query_lower.split())
    
    # Common stop words (Spanish and English)
    stop_words = {"el", "la", "los", "las", "de", "del", "en", "un", "una", "que", "es", "y", "a", "por", "para", "con", "se", "su", "al", "lo", "como", "the", "is", "are", "what", "how", "qué", "cómo", "cuál", "cuáles", "cuántos", "cuántas", "hay", "tiene", "tienen", "for", "and", "or", "in", "on", "to", "of", "with", "new", "about"}
    
    # Generic terms that shouldn't drive matching alone
    generic_terms = {"prevalencia", "incidencia", "tasa", "mortalidad", "morbilidad", "datos", "estadísticas", "información", "salud", "enfermedad", "pacientes", "casos", "mexico", "méxico", "mexicano", "mexicana", "nacional", "treatment", "treatments", "data", "information", "health", "disease", "patients", "cases"}
    
    query_words = query_words - stop_words
    
    # Identify content-specific keywords (most important for relevance)
    specific_keywords = query_words - generic_terms
    
    results = []
    for chunk in chunks:
        content_text = chunk.get("content", "").lower()
        title = chunk.get("metadata", {}).get("title", "").lower()
        full_text = f"{title} {content_text}"
        content_words = set(full_text.split()) - stop_words

        if not query_words:
            score = 0.0
            has_key_term = False
        else:
            # Check if ANY specific keyword appears in the content
            specific_overlap = len(specific_keywords & content_words)
            has_key_term = specific_overlap > 0 or not specific_keywords
            
            # Base overlap score
            overlap = len(query_words & content_words)
            base_score = overlap / len(query_words) if query_words else 0.0
            
            # Bonus for specific keyword matches
            specific_bonus = specific_overlap * 0.6 if specific_keywords else 0.0
            
            # Bonus for exact phrase match
            phrase_bonus = 0.5 if query_lower in full_text else 0.0
            
            # Bonus for key terms in title
            title_bonus = 0.5 if any(w in title for w in specific_keywords) else 0.0
            
            score = base_score + specific_bonus + phrase_bonus + title_bonus
            
            # Penalty if no specific keywords match (relevance penalty)
            if specific_keywords and specific_overlap == 0:
                score = score * 0.3  # Heavy penalty for missing key terms
            
        results.append((chunk, score, has_key_term))

    # Sort by score descending
    results.sort(key=lambda x: x[1], reverse=True)
    
    # Filter: must have score >= min_score AND ideally have key terms
    filtered = []
    for chunk, score, has_key_term in results:
        if score >= min_score:
            # Prefer results with key terms
            if has_key_term or len(filtered) < 2:  # Allow top 2 even without key terms
                filtered.append((chunk, score))
    
    # If nothing passes, only return if genuinely relevant
    if not filtered and results:
        top_chunk, top_score, top_has_key = results[0]
        if top_score > 0.3 and top_has_key:
            filtered = [(top_chunk, top_score)]
    
    print(f"[RAG] Query: '{query[:50]}...' | Specific keywords: {specific_keywords}")
    print(f"[RAG] Found {len(filtered)}/{len(results)} above threshold {min_score}")
    if filtered:
        print(f"[RAG] Top result: {filtered[0][0].get('metadata', {}).get('title', '')[:60]}... (score: {filtered[0][1]:.2f})")
    else:
        print(f"[RAG] No relevant results found")
    
    return filtered[:k]'''

if old_func in content:
    content = content.replace(old_func, new_func)
    with open("/home/ubuntu/rag_api.py", "w") as f:
        f.write(content)
    print("RAG relevance v2 fix applied")
else:
    print("ERROR: Could not find target function - may have different content")
    # Show what we have
    import subprocess
    result = subprocess.run(["grep", "-n", "def tool_search_rag", "/home/ubuntu/rag_api.py"], capture_output=True, text=True)
    print(f"Current function location: {result.stdout}")
