#!/usr/bin/env python3
"""Rewrite normal question handler to Sources First architecture."""
import re

with open("/home/ubuntu/rag_api.py", "r") as f:
    content = f.read()

# 1. Update DIRECT_SYSTEM_PROMPT
old_ps = 'DIRECT_SYSTEM_PROMPT = """Eres OMINIS'
idx = content.find(old_ps)
if idx >= 0:
    end_triple = content.find('"""', idx + len(old_ps))
    if end_triple >= 0:
        old_block = content[idx:end_triple+3]
        new_block = 'DIRECT_SYSTEM_PROMPT = """Eres OMINIS, asistente de investigacion en salud de FUNSALUD para profesionales e investigadores en Mexico.\n\nINSTRUCCIONES:\n1. Responde usando la informacion de las FUENTES NUMERADAS proporcionadas.\n2. Cita usando SOLO [1], [2], [3], etc. correspondiendo EXACTAMENTE a las fuentes proporcionadas.\n3. NUNCA inventes fuentes, URLs, nombres de autores, ni referencias bibliograficas.\n4. NUNCA escribas Available from, Disponible en, doi, ni URLs en tu respuesta.\n5. Si las fuentes no cubren la pregunta, complementa con conocimiento general SIN inventar citas.\n6. Las fuentes se muestran automaticamente al usuario - NO las listes al final.\n7. Responde en espanol, de forma tecnica y directa.\n8. No repitas la pregunta ni des introducciones innecesarias.\n\nEJEMPLO CORRECTO: La diabetes tipo 2 afecta al 14% de la poblacion mexicana [1]. El tratamiento incluye metformina [2][3].\nEJEMPLO INCORRECTO: Segun la ADA (2021)... Available from: https://...\n\nCONTEXTO CONVERSACIONAL:\n- Si hay historial, usalo para entender el contexto.\n- Respuestas cortas del usuario son continuaciones del tema anterior."""'
        content = content.replace(old_block, new_block)
        print("1. Updated DIRECT_SYSTEM_PROMPT")
    else:
        print("1. Could not find end of DIRECT_SYSTEM_PROMPT")
else:
    print("1. Could not find DIRECT_SYSTEM_PROMPT")

# 2. Replace normal question flow
marker = "    # --- NORMAL QUESTION:"
idx_start = content.find(marker)
if idx_start >= 0:
    # Find the done yield
    done_pat = '    yield {"type": "done", "answer": cleaned_answer, "sources": all_sources, "mode": "direct"}'
    idx_done = content.find(done_pat, idx_start)
    if idx_done >= 0:
        idx_end = idx_done + len(done_pat)
        old_section = content[idx_start:idx_end]
        print(f"2. Found section ({len(old_section)} chars)")
        
        new_section = """    # --- NORMAL QUESTION: Sources First, Then Answer (Perplexity-style) ---
    
    # Phase 1: Gather ALL sources based on enabled toggles
    yield {"type": "status", "message": "Investigando fuentes..."}
    
    all_sources = []
    all_context_parts = []
    ref_num = 0
    
    # RAG search
    if rag_enabled:
        yield {"type": "status", "message": "Buscando en base de conocimiento..."}
        rag_results = tool_search_rag(question)
        if rag_results:
            rag_sources = rag_results_to_sources(rag_results)
            for i, (chunk, score) in enumerate(rag_results):
                ref_num += 1
                meta = chunk.get("metadata", {})
                title = meta.get("title", "Sin titulo")
                ctext = chunk.get("content", "")[:600]
                institution = meta.get("institution", "")
                sname = institution if institution else title[:50]
                all_context_parts.append("[" + str(ref_num) + "] " + sname + ": " + title + "\\n" + ctext)
                if i < len(rag_sources):
                    rag_sources[i]["ref_num"] = ref_num
            all_sources.extend(rag_sources)
    
    # PubMed search
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
            all_sources.extend(pm_sources)
    
    # Web search
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
            all_sources.extend(web_sources)
    
    # Send sources to frontend immediately
    if all_sources:
        yield {"type": "sources", "sources": all_sources}
    
    # Phase 2: Generate answer using ALL numbered sources
    yield {"type": "status", "message": "Generando respuesta..."}
    
    history_section = ""
    if history:
        hparts = []
        for m in history[-4:]:
            role = "Usuario" if m.get("role") == "user" else "OMINIS"
            hparts.append(role + ": " + m.get("content", "")[:300])
        history_section = "\\nHistorial:\\n" + "\\n".join(hparts) + "\\n\\n"
    
    image_section = ""
    if image_description:
        image_section = "\\n[IMAGEN ADJUNTA]\\nAnalisis: " + image_description + "\\n\\n"
    
    if all_context_parts:
        sources_text = "\\n\\n".join(all_context_parts)
        prompt = history_section + image_section + "FUENTES DISPONIBLES:\\n" + sources_text + "\\n\\nPregunta del usuario: " + question + "\\n\\nResponde usando las fuentes proporcionadas. Cita con [N] segun el numero de cada fuente. NO inventes URLs ni referencias adicionales."
    else:
        prompt = history_section + image_section + "Pregunta: " + question + "\\n\\nNo se encontraron fuentes especificas. Responde con tu conocimiento general. NO inventes citas ni URLs."
    
    full_answer = ""
    for token in stream_ollama(prompt, DIRECT_SYSTEM_PROMPT):
        full_answer += token
        yield {"type": "chunk", "text": token}
    
    # Phase 3: Clean and send done
    cleaned_answer = clean_urls_from_answer(full_answer)
    yield {"type": "done", "answer": cleaned_answer, "sources": all_sources, "mode": "direct"}"""
        
        content = content.replace(old_section, new_section)
        print("2. Replaced normal question flow")
    else:
        print("2. Could not find done yield")
else:
    print("2. Could not find NORMAL QUESTION marker")

# 3. Remove duplicate clean_urls_from_answer
matches = list(re.finditer(r'\ndef clean_urls_from_answer\(answer\):', content))
if len(matches) > 1:
    first_start = matches[0].start()
    second_start = matches[1].start()
    content = content[:first_start] + "\n" + content[second_start:]
    print("3. Removed duplicate clean_urls_from_answer")
else:
    print("3. Only one clean_urls found (OK)")

with open("/home/ubuntu/rag_api.py", "w") as f:
    f.write(content)

print("\nDone! Sources First architecture applied.")
