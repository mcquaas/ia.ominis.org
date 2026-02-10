#!/usr/bin/env python3
"""
Query each Ollama server (from config files or env) with /api/tags (same info as `ollama list`)
and print model names so we can align backend routing (OLLAMA_FAST_MODEL, etc.).

Usage:
  # From repo root, using config/*.txt URLs:
  python infrastructure/check-ollama-servers.py

  # With env vars (e.g. backend .env) to also show what the backend actually uses:
  OLLAMA_URL=http://3.213.91.241:11434 OLLAMA_FAST_URL= FALCON_OLLAMA_URL=http://18.235.182.22:11434 \
    python infrastructure/check-ollama-servers.py
"""

import os
import re
import sys
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = REPO_ROOT / "config"
TIMEOUT = 10


def parse_config_url(path: Path, var_name: str) -> str | None:
    if not path.exists():
        return None
    text = path.read_text()
    m = re.search(rf"^{var_name}=(.+)$", text, re.MULTILINE)
    if not m:
        return None
    return m.group(1).strip() or None


def get_servers_from_config() -> list[tuple[str, str | None]]:
    """(label, url) from config files. g4dn runs both Ominis 2.0 (Qwen) and Ominis 2.0 Clinic (BioMistral)."""
    servers = []
    gpu = CONFIG_DIR / "ollama_gpu_server.txt"
    url = parse_config_url(gpu, "GPU_OLLAMA_API_URL")
    servers.append(("g4dn (Ominis 2.0 + Ominis 2.0 Clinic)", url))
    return servers


def get_servers_from_env() -> list[tuple[str, str | None]]:
    """(label, url) from env vars (what the backend actually uses)."""
    return [
        ("OLLAMA_URL (ominis-2.0 / vision)", os.environ.get("OLLAMA_URL", "").strip() or None),
        ("OLLAMA_CLINIC_URL (ominis-2.0-clinic)", (os.environ.get("OLLAMA_CLINIC_URL") or "").strip() or None),
    ]


def fetch_tags(url: str) -> tuple[bool, list[str], str | None]:
    """Return (reachable, model_names, error_message)."""
    import json
    req = urllib.request.Request(f"{url.rstrip('/')}/api/tags")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            data = json.load(r)
            models = [m.get("name", "") for m in data.get("models", []) if m.get("name")]
            return True, models, None
    except Exception as e:
        return False, [], str(e)[:80]


def main():
    use_env = "OLLAMA_URL" in os.environ or "OLLAMA_CLINIC_URL" in os.environ
    if use_env:
        servers = get_servers_from_env()
        print("Using OLLAMA_* URLs from environment (backend config):\n")
    else:
        servers = get_servers_from_config()
        print("Using URLs from config/ollama_gpu_server.txt and config/falcon_gpu_server.txt:\n")

    seen_urls = set()
    rows = []
    for label, url in servers:
        if not url:
            rows.append((label, url, False, [], "not set"))
            continue
        if url in seen_urls:
            rows.append((label, url, None, [], "same URL as above"))
            continue
        seen_urls.add(url)
        reachable, models, err = fetch_tags(url)
        rows.append((label, url, reachable, models, err))

    # Print table
    max_label = max(len(r[0]) for r in rows)
    for label, url, reachable, models, err in rows:
        url_s = url or "—"
        status = "✓ reachable" if reachable is True else ("—" if reachable is None else f"✗ {err or 'unreachable'}")
        print(f"  {label:<{max_label}}  {url_s}")
        print(f"  {'':<{max_label}}  {status}")
        if models:
            for name in sorted(models):
                print(f"  {'':<{max_label}}    → {name}")
        elif reachable is True:
            print(f"  {'':<{max_label}}    → (no models listed)")
        print()

    # Routing checklist
    print("--- Routing checklist (backend .env) ---")
    print("• ominis-2.0       → backend sends OLLAMA_MODEL (e.g. qwen2.5:14b) to OLLAMA_URL.")
    print("• ominis-2.0-clinic → backend sends OLLAMA_CLINIC_MODEL (default 'biomistral') to OLLAMA_CLINIC_URL or OLLAMA_URL.")
    print("• If OLLAMA_CLINIC_URL is empty, both models use OLLAMA_URL (same g4dn); that server must have both model names.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
