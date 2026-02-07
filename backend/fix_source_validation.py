#!/usr/bin/env python3
"""
Fix source handling:
1. Remove LLM URL extraction (causes hallucinated links)
2. Re-enable URL validation with fast timeout
3. Only trust sources from actual tool results
"""

with open("/home/ubuntu/rag_api.py", "r") as f:
    content = f.read()

# 1. Remove the extract_urls_from_response call from the main flow
old_extraction = '''    # Phase 3b: Extract URLs from LLM response and merge into sources
    extracted_url_sources = extract_urls_from_response(full_answer)
    if extracted_url_sources:
        existing_urls = {s.get("url", "") for s in all_sources}
        for ext_src in extracted_url_sources:
            if ext_src["url"] not in existing_urls:
                all_sources.append(ext_src)
        # Send sources if we found new ones from the LLM text'''

new_extraction = '''    # NOTE: We do NOT extract URLs from LLM text to avoid hallucinated links
    # Sources only come from RAG, PubMed, or Web search tools'''

if old_extraction in content:
    content = content.replace(old_extraction, new_extraction)
    print("1. Removed LLM URL extraction")
else:
    print("1. Could not find URL extraction code (may already be removed)")

# 2. Re-enable URL validation with fast timeout
old_validate1 = 'event["sources"] = filter_valid_sources(event["sources"], validate=False)  # Validation disabled temporarily'
new_validate1 = 'event["sources"] = filter_valid_sources(event["sources"], validate=True)'

old_validate2 = 'final_sources = filter_valid_sources(final_sources, validate=False)  # Validation disabled temporarily'
new_validate2 = 'final_sources = filter_valid_sources(final_sources, validate=True)'

if old_validate1 in content:
    content = content.replace(old_validate1, new_validate1)
    print("2. Re-enabled streaming validation")
else:
    print("2. Streaming validation code not found")

if old_validate2 in content:
    content = content.replace(old_validate2, new_validate2)
    print("3. Re-enabled non-streaming validation")
else:
    print("3. Non-streaming validation code not found")

# 3. Update validate_url to be faster (2 second timeout) and skip RAG URLs
old_validate_func = '''def validate_url(url, timeout=5):
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
            return False'''

new_validate_func = '''def validate_url(url, timeout=3):
    """Quick check if URL is accessible. Returns True/False."""
    if not url or not url.startswith("http"):
        return False
    
    # Always trust our own ominis.org URLs (they're from RAG)
    if "ominis.org" in url:
        return True
    
    # Always trust pubmed URLs (they're from our PubMed tool)
    if "pubmed.ncbi.nlm.nih.gov" in url or "ncbi.nlm.nih.gov" in url:
        return True
    
    # Check cache first
    if url in _validated_urls:
        return _validated_urls[url]
    
    try:
        req = urllib.request.Request(url, method="HEAD", headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        with urllib.request.urlopen(req, timeout=timeout) as response:
            is_valid = response.status < 400
            _validated_urls[url] = is_valid
            return is_valid
    except Exception:
        # Try GET if HEAD fails
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            })
            with urllib.request.urlopen(req, timeout=timeout) as response:
                is_valid = response.status < 400
                _validated_urls[url] = is_valid
                return is_valid
        except Exception as e:
            print(f"[validate_url] Failed: {url} - {str(e)[:50]}")
            _validated_urls[url] = False
            return False'''

if old_validate_func in content:
    content = content.replace(old_validate_func, new_validate_func)
    print("4. Updated validate_url with faster timeout and trusted domains")
else:
    print("4. Could not find validate_url function")

with open("/home/ubuntu/rag_api.py", "w") as f:
    f.write(content)

print("\nSource validation fixes applied!")
