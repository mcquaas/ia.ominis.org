#!/usr/bin/env python3
"""Fix source validation in rag_api.py"""

with open("/home/ubuntu/rag_api.py", "r") as f:
    content = f.read()

# 1. Update AGENT_SYSTEM_PROMPT to forbid invented URLs
old_prompt = '''AGENT_SYSTEM_PROMPT = """Eres OMINIS, agente de investigación en salud para profesionales en México.

HERRAMIENTAS:
1. pubmed_search: Para literatura médica. Usa términos en inglés ("semaglutide obesity", "diabetes treatment")
2. web_search: Para información actual en internet
3. fetch_source: Para contenido de una URL

FORMATO: {"action": "pubmed_search|web_search|fetch_source|answer", "input": "query o respuesta"}

CITACIÓN: Usa [N] para citar fuentes. NUNCA uses "1.", "2.". NUNCA menciones "RAG" ni "base de datos".
Responde en español, sé técnico y directo."""'''

new_prompt = '''AGENT_SYSTEM_PROMPT = """Eres OMINIS, agente de investigación en salud para profesionales en México.

HERRAMIENTAS:
1. pubmed_search: Para literatura médica. Usa términos en inglés ("semaglutide obesity", "diabetes treatment")
2. web_search: Para información actual en internet
3. fetch_source: Para contenido de una URL

FORMATO: {"action": "pubmed_search|web_search|fetch_source|answer", "input": "query o respuesta"}

REGLAS CRÍTICAS DE CITACIÓN:
- SOLO cita fuentes que aparecen en los resultados de las herramientas
- NUNCA inventes URLs ni nombres de documentos
- NUNCA cites fuentes que no hayas encontrado con las herramientas
- Usa [N] para citar (donde N es el número de la fuente en los resultados)
- NUNCA menciones "RAG", "base de datos" ni "sistema"
- Si no tienes fuentes, responde con tu conocimiento general SIN inventar citas

Responde en español, sé técnico y directo."""'''

content = content.replace(old_prompt, new_prompt)

# 2. Add URL validation function after imports
url_validator = '''

# ============ URL VALIDATION ============
_validated_urls = {}  # Cache for URL validation results

def validate_url(url, timeout=5):
    """Quick check if URL is accessible. Returns True/False."""
    if not url or not url.startswith("http"):
        return False
    
    # Check cache first
    if url in _validated_urls:
        return _validated_urls[url]
    
    try:
        req = urllib.request.Request(url, method="HEAD", headers={
            "User-Agent": "Mozilla/5.0 (compatible; OminisBot/1.0)"
        })
        with urllib.request.urlopen(req, timeout=timeout) as response:
            is_valid = response.status < 400
            _validated_urls[url] = is_valid
            return is_valid
    except Exception:
        # Try GET if HEAD fails (some servers dont support HEAD)
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (compatible; OminisBot/1.0)"
            })
            with urllib.request.urlopen(req, timeout=timeout) as response:
                is_valid = response.status < 400
                _validated_urls[url] = is_valid
                return is_valid
        except Exception:
            _validated_urls[url] = False
            return False


def filter_valid_sources(sources, validate=True):
    """Filter sources, optionally validating URLs."""
    if not sources:
        return []
    
    valid = []
    for src in sources:
        url = src.get("url", "")
        # Always include RAG sources (they come from our indexed data)
        if src.get("type") == "rag":
            valid.append(src)
        # For external sources, validate if requested
        elif url:
            if not validate or validate_url(url):
                valid.append(src)
            else:
                print(f"[filter_valid_sources] Invalid URL removed: {url}")
    return valid

'''

# Insert after the imports section
import_marker = "from bs4 import BeautifulSoup"
if import_marker in content:
    content = content.replace(import_marker, import_marker + url_validator)
    print("URL validation functions added")
else:
    print("Warning: Could not find import marker")

with open("/home/ubuntu/rag_api.py", "w") as f:
    f.write(content)

print("Sources validation fix applied successfully")
