#!/usr/bin/env python3
"""
MCP stdio server: Mexican doctor directory + All.Can México organization search.

Environment:
  OMINIS_BACKEND_URL — Haystack API base (default: https://api.ominis.org/v1)
  OMINIS_JWT — Valid Ominis user JWT (Bearer token)

Install: pip install -r requirements.txt
Cursor: add an MCP server with command:
  python /path/to/mcp_servers/ominis_directories/server.py
"""

from __future__ import annotations

import os

import httpx
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("ominis-directories")

BACKEND = os.environ.get("OMINIS_BACKEND_URL", "https://api.ominis.org/v1").rstrip("/")
TOKEN = os.environ.get("OMINIS_JWT", "").strip()


def _headers() -> dict[str, str]:
    if not TOKEN:
        raise RuntimeError("Set OMINIS_JWT to a valid Ominis API JWT (same token used for /v1 calls).")
    return {"Authorization": f"Bearer {TOKEN}"}


@mcp.tool()
async def search_doctor_directory_mexico(
    q: str = "",
    specialty: str = "",
    city: str = "",
    match_mode: str = "and",
    semantic: bool = True,
    limit: int = 20,
) -> dict:
    """
    Search the ingested Mexican doctor directory (sources such as Top Doctors México, Doctoralia, DoctorAnytime).
    When semantic is true (default), results are ranked by multilingual semantic similarity so queries like
    "Oncology" match Spanish specialties (e.g. Oncología) and related wording.
    """
    async with httpx.AsyncClient(timeout=120.0) as client:
        r = await client.get(
            f"{BACKEND}/doctor-directory/search",
            params={
                "q": q,
                "specialty": specialty,
                "city": city,
                "match_mode": match_mode,
                "semantic": semantic,
                "limit": limit,
            },
            headers=_headers(),
        )
        r.raise_for_status()
        return r.json()


@mcp.tool()
async def search_allcan_mexico(
    q: str = "",
    organization_type: str = "",
    state: str = "",
    specialty: str = "",
    city: str = "",
    page: int = 1,
    page_size: int = 24,
    semantic: bool = True,
) -> dict:
    """
    Search All.Can México organizations (patient groups, foundations, map directory).
    Uses the same semantic ranking as the web UI. Filter by organization_type using the Strapi "type" field.
    """
    async with httpx.AsyncClient(timeout=120.0) as client:
        r = await client.get(
            f"{BACKEND}/allcan-directory/search",
            params={
                "q": q,
                "type": organization_type,
                "state": state,
                "specialty": specialty,
                "city": city,
                "page": page,
                "page_size": page_size,
                "semantic": semantic,
            },
            headers=_headers(),
        )
        r.raise_for_status()
        return r.json()


if __name__ == "__main__":
    mcp.run()
