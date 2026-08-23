#!/usr/bin/env python3
"""
Create Vast.ai Serverless endpoint + workergroup via HTTPS API.

Requires VAST_API_KEY (or --api-key). You must supply a template_hash or template_id from the
Vast dashboard (Serverless → create workergroup → template) or from `vastai` CLI if available.

Examples:
  export VAST_API_KEY=...
  python3 infrastructure/vast_serverless_provision.py \\
    --endpoint-name ominis-vllm-power \\
    --template-hash YOUR_TEMPLATE_HASH \\
    --min-load 0 --cold-workers 0 --max-workers 8

Then set backend env (see docs/VAST_SERVERLESS.md):
  vast_serverless_power_endpoint=ominis-vllm-power
"""

from __future__ import annotations

import argparse
import json
import os
import sys
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


def main() -> None:
    p = argparse.ArgumentParser(description="Create Vast Serverless endpoint + workergroup")
    p.add_argument("--api-key", default=os.environ.get("VAST_API_KEY", ""), help="Defaults to VAST_API_KEY")
    p.add_argument("--endpoint-name", required=True, help="Unique endpoint name (matches backend *endpoint* env)")
    p.add_argument("--template-hash", default="", help="Workergroup template hash from Vast UI")
    p.add_argument("--template-id", type=int, default=0, help="Or numeric template id")
    p.add_argument("--min-load", type=float, default=0.0)
    p.add_argument("--target-util", type=float, default=0.9)
    p.add_argument("--cold-mult", type=float, default=2.0)
    p.add_argument("--cold-workers", type=int, default=0)
    p.add_argument("--max-workers", type=int, default=12)
    p.add_argument("--gpu-ram", type=int, default=24)
    p.add_argument(
        "--search-params",
        default="verified=true rentable=true",
        help="GPU marketplace filter for workers (if not using template_hash)",
    )
    p.add_argument("--skip-endpoint", action="store_true", help="Only create workergroup (endpoint must exist)")
    args = p.parse_args()

    api_key = (args.api_key or "").strip()
    if not api_key:
        print("Set VAST_API_KEY or pass --api-key", file=sys.stderr)
        sys.exit(1)

    endpoint_id: int | None = None
    if not args.skip_endpoint:
        body = {
            "endpoint_name": args.endpoint_name,
            "min_load": args.min_load,
            "target_util": args.target_util,
            "cold_mult": args.cold_mult,
            "cold_workers": args.cold_workers,
            "max_workers": args.max_workers,
        }
        print("Creating endpoint:", json.dumps(body, indent=2))
        out = _post("/api/v0/endptjobs/", body, api_key)
        print("Response:", json.dumps(out, indent=2))
        endpoint_id = (out.get("result") or out.get("id")) if isinstance(out, dict) else None
        if endpoint_id is None and isinstance(out, dict):
            endpoint_id = out.get("endpoint_id")
    else:
        print("Skipping endpoint creation (--skip-endpoint)")

    wg: dict = {
        "endpoint_name": args.endpoint_name,
        "min_load": args.min_load,
        "target_util": args.target_util,
        "cold_mult": args.cold_mult,
        "cold_workers": args.cold_workers,
        "max_workers": args.max_workers,
        "gpu_ram": args.gpu_ram,
        "search_params": args.search_params,
    }
    if args.template_hash:
        wg["template_hash"] = args.template_hash
    elif args.template_id:
        wg["template_id"] = args.template_id
    else:
        print(
            "ERROR: Provide --template-hash or --template-id (from Vast Serverless UI / docs).",
            file=sys.stderr,
        )
        sys.exit(2)
    if endpoint_id is not None:
        wg["endpoint_id"] = int(endpoint_id)

    print("Creating workergroup:", json.dumps(wg, indent=2))
    out2 = _post("/api/v0/workergroups/", wg, api_key)
    print("Response:", json.dumps(out2, indent=2))
    print("\nNext: wait for workers in https://cloud.vast.ai/serverless/ then set backend env vars.")


if __name__ == "__main__":
    main()
