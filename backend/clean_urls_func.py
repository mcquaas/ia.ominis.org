#!/usr/bin/env python3
"""Fix the clean_urls function directly"""

# Read current file
with open("/home/ubuntu/rag_api.py", "r") as f:
    lines = f.readlines()

# Find and remove the broken function (lines between def clean_urls... and next def or # ===)
start_idx = None
end_idx = None
for i, line in enumerate(lines):
    if "def clean_urls_from_answer" in line:
        start_idx = i
    elif start_idx is not None and (line.startswith("def ") or line.startswith("# ====")):
        end_idx = i
        break

if start_idx is not None and end_idx is not None:
    print(f"Found broken function from line {start_idx+1} to {end_idx}")
    # Remove the broken lines
    del lines[start_idx:end_idx]
    print("Removed broken function")
else:
    print("Could not find broken function boundaries")

# Write back
with open("/home/ubuntu/rag_api.py", "w") as f:
    f.writelines(lines)

# Now read again and insert proper function
with open("/home/ubuntu/rag_api.py", "r") as f:
    content = f.read()

# Insert the fixed function before the handler
fixed_function = '''
def clean_urls_from_answer(answer):
    """Remove any URLs that the LLM invented in its answer text."""
    import re
    
    # Find all URLs
    url_pattern = r'https?://[^\s<>"\')\]}\n]+'
    urls_found = re.findall(url_pattern, answer)
    
    if urls_found:
        print(f"[clean_urls] Removing {len(urls_found)} inline URLs from answer")
        for url in urls_found[:5]:  # Log first 5
            print(f"[clean_urls] Removed: {url[:60]}...")
    
    # Remove URLs and their prefixes
    result = answer
    for url in urls_found:
        # Remove URL with common prefixes
        result = result.replace(f"Available from: {url}", "")
        result = result.replace(f"Available at: {url}", "")
        result = result.replace(f"Disponible en: {url}", "")
        result = result.replace(f"Link: {url}", "")
        result = result.replace(f"URL: {url}", "")
        result = result.replace(url, "")
    
    # Clean up extra whitespace
    result = re.sub(r'  +', ' ', result)
    result = re.sub(r'\\n\\n\\n+', '\\n\\n', result)
    
    return result.strip()

'''

marker = "# ============ HTTP HANDLER ============"
if marker in content:
    content = content.replace(marker, fixed_function + marker)
    with open("/home/ubuntu/rag_api.py", "w") as f:
        f.write(content)
    print("Inserted fixed clean_urls_from_answer function")
else:
    print("Could not find marker to insert function")
