#!/usr/bin/env python3
"""
Create multiple Vast Serverless endpoints + workergroups from a JSON manifest.

  export VAST_API_KEY=...
  cp config/vast_serverless_manifest.example.json config/vast_serverless_manifest.json
  # Edit: set template_id or template_hash per workload
  python3 infrastructure/vast_serverless_provision_manifest.py --manifest config/vast_serverless_manifest.json

Reuses POST logic from vast_serverless_provision.py (inline).
"""

from __future__ import annotations

import argparse
import json
import os
import sys

# Import shared HTTP from sibling script pattern
import urllib.error
import urllib.request

CONSOLE = os.environ.get("VAST_CONSOLE_URL", "https://console.vast.ai")


def _headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _post(path: str, body: dict, api_key: str) -> dict:
    url = CONSOLE.rstrip("/") + path
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=_headers(api_key), method="POST")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code} {path}: {err[:2000]}") from e


def provision_one(
    api_key: str,
    endpoint_name: str,
    template_id: int | None,
    template_hash: str | None,
    defaults: dict,
) -> tuple[int | None, dict]:
    body = {
        "endpoint_name": endpoint_name,
        "min_load": defaults.get("min_load", 0),
        "target_util": defaults.get("target_util", 0.9),
        "cold_mult": defaults.get("cold_mult", 2.0),
        "cold_workers": defaults.get("cold_workers", 0),
        "max_workers": defaults.get("max_workers", 12),
    }
    print(f"\n=== Endpoint {endpoint_name} ===\nCreate endpoint:", json.dumps(body, indent=2))
    out = _post("/api/v0/endptjobs/", body, api_key)
    print("Response:", json.dumps(out, indent=2))
    endpoint_id = out.get("result") or out.get("id") or out.get("endpoint_id")
    if endpoint_id is not None:
        endpoint_id = int(endpoint_id)

    wg: dict = {
        "endpoint_name": endpoint_name,
        "min_load": defaults.get("min_load", 0),
        "target_util": defaults.get("target_util", 0.9),
        "cold_mult": defaults.get("cold_mult", 2.0),
        "cold_workers": defaults.get("cold_workers", 0),
        "max_workers": defaults.get("max_workers", 12),
        "gpu_ram": defaults.get("gpu_ram", 24),
        "search_params": defaults.get("search_params", "verified=true rentable=true"),
    }
    if template_hash:
        wg["template_hash"] = str(template_hash)
    elif template_id:
        wg["template_id"] = int(template_id)
    else:
        raise ValueError(f"{endpoint_name}: set template_id or template_hash in manifest")
    if endpoint_id is not None:
        wg["endpoint_id"] = endpoint_id

    print("Create workergroup:", json.dumps(wg, indent=2))
    out2 = _post("/api/v0/workergroups/", wg, api_key)
    print("Response:", json.dumps(out2, indent=2))
    return endpoint_id, out2


def main() -> None:
    p = argparse.ArgumentParser(description="Provision Vast Serverless from JSON manifest")
    p.add_argument("--manifest", required=True, help="Path to vast_serverless_manifest.json")
    p.add_argument("--api-key", default=os.environ.get("VAST_API_KEY", ""))
    p.add_argument("--dry-run", action="store_true", help="Print planned actions only")
    args = p.parse_args()

    api_key = (args.api_key or "").strip()
    if not api_key:
        print("Set VAST_API_KEY", file=sys.stderr)
        sys.exit(1)

    with open(args.manifest, encoding="utf-8") as f:
        manifest = json.load(f)

    defaults = manifest.get("defaults") or {}
    workloads = manifest.get("workloads") or []

    env_lines: list[str] = ["# Add to backend .env (with VAST_API_KEY):\n"]
    for w in workloads:
        name = w.get("endpoint_name")
        if not name:
            continue
        tid = w.get("template_id")
        th = (w.get("template_hash") or "").strip() or None
        if tid in (None, "null"):
            tid = None
        else:
            tid = int(tid)
        bk = w.get("backend_env_key") or ""
        if args.dry_run:
            print(f"Would provision {name} template_id={tid} template_hash={th}")
        else:
            if not tid and not th:
                print(f"SKIP {name}: no template_id or template_hash", file=sys.stderr)
                continue
            try:
                provision_one(api_key, name, tid, th, defaults)
            except Exception as e:
                print(f"ERROR {name}: {e}", file=sys.stderr)
                continue
        if bk:
            env_lines.append(f"{bk}={name}\n")

    print("\n--- Suggested .env lines ---\n")
    print("".join(env_lines))
    print("VAST_API_KEY=(your key)")
    print("\nWait for workers at https://cloud.vast.ai/serverless/ then deploy backend.")


if __name__ == "__main__":
    main()
