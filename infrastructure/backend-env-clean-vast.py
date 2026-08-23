#!/usr/bin/env python3
"""Remove duplicate Vast/Ollama/Power/Med/OpenScholar lines from .env. Run on backend with .env path as first arg."""
import re
import sys

path = sys.argv[1] if len(sys.argv) > 1 else ".env"
# Keys we want to dedupe (only first occurrence kept, then we append fresh block)
DROP_KEYS = (
    r"^OLLAMA_URL=",
    r"^OLLAMA_MODEL=",
    r"^VISION_MODEL=",
    r"^OLLAMA_MED_",
    r"^POWER_",
    r"^OPENSCHOLAR_128K_",
    r"^MED42_API_URL=",
)
DROP_COMMENT = re.compile(
    r"^\s*#.*(Ollama \(Vast|GPT \(gpt-oss|Ominis 2.0 Med|OpenScholar|Med42|Si POWER)",
    re.I,
)
KEY_PAT = re.compile("|".join(f"({k})" for k in DROP_KEYS))

with open(path) as f:
    lines = f.readlines()

kept = []
for line in lines:
    if KEY_PAT.match(line.strip()) or DROP_COMMENT.match(line.strip()):
        continue
    kept.append(line)

with open(path, "w") as f:
    f.writelines(kept)

print("Removed duplicate Vast/Ollama/Power/Med/OpenScholar lines.")
