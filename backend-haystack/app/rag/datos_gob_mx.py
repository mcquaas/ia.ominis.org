"""
datos.gob.mx — CKAN API client for open datasets (metadata-only RAG indexing).

Uses the official CKAN API (no HTML scraping). Datasets are indexed as text describing
title, institution, license, tags, and resource download URLs — not the CSV bytes.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

BASE = "https://www.datos.gob.mx"
API = f"{BASE}/api/3/action/package_search"
USER_AGENT = "OminisBot/1.0 (+https://ominis.org)"


def portal_dataset_url(pkg: dict[str, Any]) -> str:
    name = (pkg.get("name") or "").strip()
    if name:
        return f"{BASE}/dataset/{name}"
    return BASE


def build_index_text(pkg: dict[str, Any]) -> str:
    """Spanish plain-text blob for embedding (metadata + resource links)."""
    lines: list[str] = []
    title = (pkg.get("title") or "").strip() or (pkg.get("name") or "Sin título")
    name = (pkg.get("name") or "").strip()
    lines.append(f"Conjunto de datos: {title}")
    lines.append("Fuente: Portal nacional de datos abiertos de México (datos.gob.mx), API CKAN.")
    lines.append("Tipo: metadatos de base de datos abierta (no se indexó el contenido fila a fila).")
    if name:
        lines.append(f"Página oficial del conjunto: {portal_dataset_url(pkg)}")
    notes = (pkg.get("notes") or "").strip()
    if notes:
        lines.append(f"Descripción: {notes}")
    org = pkg.get("organization") or {}
    if org.get("title"):
        lines.append(f"Institución publicadora: {org['title']}")
    if pkg.get("maintainer"):
        lines.append(f"Responsable (metadato CKAN): {pkg['maintainer']}")
    lic_title = (pkg.get("license_title") or "").strip()
    lic_id = (pkg.get("license_id") or "").strip()
    if lic_title or lic_id:
        lines.append(f"Licencia: {lic_title or lic_id}")
    if pkg.get("metadata_created"):
        lines.append(f"Metadatos creados: {pkg['metadata_created']}")
    if pkg.get("metadata_modified"):
        lines.append(f"Última modificación de metadatos: {pkg['metadata_modified']}")
    tags = pkg.get("tags") or []
    if tags:
        tnames = [str(t.get("display_name") or t.get("name") or "").strip() for t in tags]
        tnames = [t for t in tnames if t]
        if tnames:
            lines.append(f"Etiquetas: {', '.join(tnames)}")
    groups = pkg.get("groups") or []
    if groups:
        gtitles = [str(g.get("title") or g.get("name") or "").strip() for g in groups]
        gtitles = [g for g in gtitles if g]
        if gtitles:
            lines.append(f"Grupos CKAN: {', '.join(gtitles)}")
    resources = pkg.get("resources") or []
    lines.append(f"Recursos publicados ({len(resources)}):")
    for i, res in enumerate(resources, 1):
        rname = (res.get("name") or f"recurso_{i}").strip()
        fmt = (res.get("format") or "").strip().upper() or "—"
        url = (res.get("url") or "").strip()
        desc = (res.get("description") or res.get("resource_subtitle") or "").strip()
        mime = (res.get("mimetype") or "").strip()
        parts = [f"  {i}. {rname} ({fmt})"]
        if mime:
            parts.append(f"mimetype: {mime}")
        if desc:
            parts.append(f"— {desc}")
        lines.append(" ".join(parts))
        if url:
            lines.append(f"     URL de descarga / acceso: {url}")
        if res.get("datastore_active"):
            lines.append("     (Datastore CKAN activo: consulta vía API del portal.)")
    lines.append(
        "Para obtener el archivo: usar la URL de descarga indicada o la página del conjunto en datos.gob.mx."
    )
    return "\n".join(lines)


def _count_formats(resources: list[dict[str, Any]]) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in resources:
        fmt = (r.get("format") or "unknown").strip().upper() or "UNKNOWN"
        out[fmt] = out.get(fmt, 0) + 1
    return dict(sorted(out.items(), key=lambda x: (-x[1], x[0])))


async def fetch_packages_for_group(
    group_name: str = "salud",
    *,
    max_items: Optional[int] = None,
    rows_per_page: int = 100,
) -> list[dict[str, Any]]:
    """
    Paginate CKAN package_search with fq=groups:{group_name}.
    """
    out: list[dict[str, Any]] = []
    start = 0
    async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
        while True:
            params: dict[str, Any] = {
                "fq": f"groups:{group_name}",
                "rows": rows_per_page,
                "start": start,
            }
            r = await client.get(API, params=params, headers={"User-Agent": USER_AGENT})
            r.raise_for_status()
            data = r.json()
            if not data.get("success"):
                err = data.get("error", {})
                raise RuntimeError(f"CKAN error: {err}")
            result = data.get("result") or {}
            batch = result.get("results") or []
            total = int(result.get("count") or 0)
            out.extend(batch)
            if max_items is not None and len(out) >= max_items:
                return out[:max_items]
            if not batch or start + len(batch) >= total:
                break
            start += rows_per_page
    return out


async def preview_group(
    group_name: str = "salud",
    sample_size: int = 8,
) -> dict[str, Any]:
    """Counts + sample titles + resource format histogram (first page only for speed)."""
    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
        r = await client.get(
            API,
            params={"fq": f"groups:{group_name}", "rows": min(100, max(1, sample_size)), "start": 0},
            headers={"User-Agent": USER_AGENT},
        )
        r.raise_for_status()
        data = r.json()
        if not data.get("success"):
            raise RuntimeError(data.get("error", {}))
        result = data.get("result") or {}
        total = int(result.get("count") or 0)
        results = result.get("results") or []
    sample_titles = [str(p.get("title") or p.get("name") or "") for p in results[:sample_size]]
    total_resources = 0
    fmt_hist: dict[str, int] = {}
    for p in results:
        res = p.get("resources") or []
        total_resources += len(res)
        for k, v in _count_formats(res).items():
            fmt_hist[k] = fmt_hist.get(k, 0) + v
    group_title = "Salud"
    if results and results[0].get("groups"):
        for g in results[0]["groups"]:
            if (g.get("name") or "") == group_name:
                group_title = str(g.get("title") or group_title)
                break
    return {
        "totalPackages": total,
        "groupName": group_name,
        "groupTitle": group_title,
        "totalResourcesSample": total_resources,
        "resourceFormatsSample": fmt_hist,
        "sampleTitles": [t for t in sample_titles if t],
    }
