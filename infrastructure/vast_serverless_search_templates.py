#!/usr/bin/env python3
"""
List Vast templates (GET /api/v0/template/) and filter by name/tag for Serverless workergroup setup.

  export VAST_API_KEY=...
  python3 infrastructure/vast_serverless_search_templates.py
  python3 infrastructure/vast_serverless_search_templates.py --name-contains vLLM
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request

CONSOLE = os.environ.get("VAST_CONSOLE_URL", "https://console.vast.ai")


def _get(path: str, params: dict, api_key: str) -> dict:
    parts = []
    for k, v in params.items():
        if v is None:
            continue
        val = json.dumps(v) if isinstance(v, (dict, list)) else str(v)
        parts.append(f"{urllib.parse.quote(k, safe='')}={urllib.parse.quote(val, safe='')}")
    qs = "&".join(parts)
    url = CONSOLE.rstrip("/") + path + ("?" + qs if qs else "")
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        raw = resp.read().decode("utf-8")
        return json.loads(raw) if raw else {}


def main() -> None:
    p = argparse.ArgumentParser(description="Search Vast templates")
    p.add_argument("--api-key", default=os.environ.get("VAST_API_KEY", ""))
    p.add_argument("--name-contains", default="", help="Case-insensitive substring filter on template name")
    p.add_argument("--limit", type=int, default=80, help="Max rows after filter")
    args = p.parse_args()
    api_key = (args.api_key or "").strip()
    if not api_key:
        print("Set VAST_API_KEY", file=sys.stderr)
        sys.exit(1)

    # Broad fetch; filter client-side (API has no ILIKE for name)
    body = _get(
        "/api/v0/template/",
        {
            "select_cols": json.dumps(["id", "name", "hash_id", "tag", "image", "recommended"]),
        },
        api_key,
    )
    if not body.get("success"):
        print(json.dumps(body, indent=2))
        sys.exit(1)

    rows = body.get("templates") or []
    needle = (args.name_contains or "").strip().lower()
    out = []
    for t in rows:
        name = (t.get("name") or "") + " " + (t.get("tag") or "")
        if needle and needle not in name.lower():
            continue
        out.append(
            {
                "id": t.get("id"),
                "name": t.get("name"),
                "hash_id": t.get("hash_id"),
                "tag": t.get("tag"),
                "image": (t.get("image") or "")[:80],
            }
        )
        if len(out) >= args.limit:
            break

    print(json.dumps({"templates_found": len(out), "templates": out}, indent=2))


if __name__ == "__main__":
    main()
