"""
URL scraper for bulk PDF discovery.

Given a webpage URL, scrapes it to find all linked PDF files,
extracts their titles (from surrounding context, not just the link text),
and returns structured results for indexing.
"""

import asyncio
import logging
import os
import re
import tempfile
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx

logger = logging.getLogger(__name__)

# When the server's CA bundle can't verify some targets (e.g. riisp.insp.mx), set SCRAPE_SSL_VERIFY=false
_SSL_VERIFY = os.environ.get("SCRAPE_SSL_VERIFY", "true").lower() not in ("0", "false", "no")

# Browser-like headers to avoid WAF blocks (Akamai, Cloudflare, datos.gob.mx 403, etc.)
BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "es-MX,es;q=0.9,es;q=0.8,en-US;q=0.5,en;q=0.3",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Sec-Ch-Ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Linux"',
}


def _headers_for_url(page_url: str) -> dict:
    """Browser-like headers plus Referer/Origin from page_url to avoid 403 on datos.gob.mx etc."""
    parsed = urlparse(page_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    # Referer as same-origin base often required by datos.gob.mx / historico.datos.gob.mx
    referer = f"{origin}/"
    return {
        **BROWSER_HEADERS,
        "Referer": referer,
        "Origin": origin,
    }

# Common user agent to avoid blocks
USER_AGENT = (
    "Mozilla/5.0 (compatible; OminisBot/1.0; +https://ominis.org)"
)

# Generic link labels that should NOT be used as titles
GENERIC_LABELS = {
    "descargar", "descargar documento", "download", "download document",
    "ver documento", "ver", "abrir", "open", "click here", "haz clic",
    "descargar pdf", "download pdf",
}


async def scrape_pdf_links(
    page_url: str,
    timeout: float = 30.0,
) -> list[dict]:
    """
    Scrape a webpage and find all PDF links with their titles.

    Returns a list of dicts:
    [
        {
            "title": "Document Title",
            "pdf_url": "https://example.com/doc.pdf",
            "source_page": "https://example.com/docs"
        },
        ...
    ]
    """
    headers = _headers_for_url(page_url)
    headers["User-Agent"] = USER_AGENT  # keep OminisBot for PDF scrape

    async with httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=True,
        headers=headers,
        verify=_SSL_VERIFY,
    ) as client:
        resp = await client.get(page_url)
        resp.raise_for_status()
        html = resp.text

    pdf_links = _extract_pdf_links(html, page_url)

    # Post-process: if most titles are identical (bad scrape), use filenames instead
    if len(pdf_links) > 1:
        titles = [p["title"] for p in pdf_links]
        most_common = max(set(titles), key=titles.count)
        if titles.count(most_common) > len(titles) * 0.5:
            # More than half have the same title — use filenames
            for p in pdf_links:
                if p["title"] == most_common:
                    p["title"] = _title_from_filename(p["pdf_url"])

    logger.info(f"Found {len(pdf_links)} PDF links on {page_url}")
    return pdf_links


def _extract_pdf_links(html: str, base_url: str) -> list[dict]:
    """
    Extract PDF links from HTML content with smart title detection.

    Strategy:
    1. Find all <a> tags linking to .pdf files
    2. For title, try (in order):
       a. Sibling/parent text (the label before "Descargar documento")
       b. The link text itself (if not generic like "Descargar")
       c. The PDF filename cleaned up
    3. Handle relative URLs
    """
    results = []
    seen_urls = set()

    # ── Phase 1: Find structured content blocks ──
    # Many government sites use a pattern like:
    #   <li>  Title Text \n <a href="...pdf">Descargar documento</a>  </li>
    # or separated by <hr> / --- :
    #   * Title Text \n  Descargar documento  (link)

    # Split by common block separators used on gob.mx-style pages
    block_pattern = re.compile(r'<hr\s*/?>|<li[^>]*>|---', re.IGNORECASE)
    blocks = block_pattern.split(html)

    a_tag_re = re.compile(
        r'<a\s[^>]*href\s*=\s*["\']([^"\']*\.pdf[^"\']*)["\'][^>]*>(.*?)</a>',
        re.IGNORECASE | re.DOTALL,
    )

    for block in blocks:
        for match in a_tag_re.finditer(block):
            href = match.group(1).strip()
            raw_link_text = match.group(2).strip()

            full_url = urljoin(base_url, href)
            if full_url in seen_urls:
                continue
            seen_urls.add(full_url)

            # Clean link text
            link_text = re.sub(r"<[^>]+>", "", raw_link_text).strip()
            link_text = re.sub(r"\s+", " ", link_text)

            # Try to get title from the block text *before* the link
            title = _extract_block_title(block, match.start())

            # Fallback chain
            if not title or title.lower().strip() in GENERIC_LABELS:
                if link_text and link_text.lower().strip() not in GENERIC_LABELS:
                    title = link_text
                else:
                    title = _title_from_filename(href)

            results.append({
                "title": title,
                "pdf_url": full_url,
                "source_page": base_url,
            })

    # ── Phase 2: Catch any PDF links missed by block splitting ──
    for match in a_tag_re.finditer(html):
        href = match.group(1).strip()
        full_url = urljoin(base_url, href)

        if full_url in seen_urls:
            continue
        seen_urls.add(full_url)

        raw_text = match.group(2).strip()
        link_text = re.sub(r"<[^>]+>", "", raw_text).strip()
        link_text = re.sub(r"\s+", " ", link_text)

        if link_text and link_text.lower().strip() not in GENERIC_LABELS:
            title = link_text
        else:
            title = _title_from_filename(href)

        results.append({
            "title": title,
            "pdf_url": full_url,
            "source_page": base_url,
        })

    return results


def _extract_block_title(block_html: str, link_start_pos: int) -> str:
    """
    Extract a meaningful title from a content block, looking at text
    that appears before the PDF link position.
    """
    # Get text before the link
    before_link = block_html[:link_start_pos]

    # Strip HTML tags
    text = re.sub(r"<[^>]+>", " ", before_link)
    text = re.sub(r"\s+", " ", text).strip()

    # Remove common prefixes/markers (gob.mx uses symbols like *, /, +, etc.)
    text = re.sub(r'^[\s\*\/\\\+\-\>\<\[\]\|\~\^\u0178_\.]+', '', text).strip()
    # Also clean trailing markers
    text = re.sub(r'[\s\*\/\\\+\-\>\<\[\]\|\~\^_\.]+$', '', text).strip()

    # If there are multiple lines/sentences, take the last meaningful one
    parts = [p.strip() for p in re.split(r'[|\n]', text) if p.strip()]
    if parts:
        # Prefer the longest part that is not a generic label
        candidates = [p for p in parts if len(p) > 3 and p.lower().strip() not in GENERIC_LABELS]
        if candidates:
            return candidates[-1]  # Take the last (closest to the link)

    return text if len(text) > 3 else ""


def _title_from_filename(href: str) -> str:
    """Generate a readable title from a PDF filename."""
    filename = Path(urlparse(href).path).stem
    # Clean up common patterns
    title = filename.replace("-", " ").replace("_", " ")
    # Remove leading numbers like "03 "
    title = re.sub(r'^\d+\s*', '', title)
    # Title case
    title = title.strip().title() if title.strip() else "Documento PDF"
    return title


# ---------------------------------------------------------------------------
# Unified file link extraction (PDF, CSV, XLS, XLSX) for any webpage
# ---------------------------------------------------------------------------

# File extensions we can index from a scraped page
SCRAPE_FILE_EXTENSIONS = (".pdf", ".csv", ".xls", ".xlsx")


def _extract_file_links(
    html: str,
    base_url: str,
    extensions: tuple[str, ...] = SCRAPE_FILE_EXTENSIONS,
) -> list[dict]:
    """
    Extract links to PDF, CSV, XLS, XLSX (or any given extensions) from HTML
    with the same block/title logic as _extract_pdf_links.
    Returns list of { title, file_url, source_page, format }.
    """
    results = []
    seen_urls: set[str] = set()
    # Build regex: match any of the extensions (case-insensitive)
    ext_pattern = "|".join(re.escape(e) for e in extensions)
    a_tag_re = re.compile(
        rf'<a\s[^>]*href\s*=\s*["\']([^"\']*(?:{ext_pattern})[^"\']*)["\'][^>]*>(.*?)</a>',
        re.IGNORECASE | re.DOTALL,
    )

    block_pattern = re.compile(r'<hr\s*/?>|<li[^>]*>|---', re.IGNORECASE)
    blocks = block_pattern.split(html)

    for block in blocks:
        for match in a_tag_re.finditer(block):
            href = match.group(1).strip()
            raw_link_text = match.group(2).strip()
            full_url = urljoin(base_url, href)
            if full_url in seen_urls:
                continue
            seen_urls.add(full_url)
            fmt = _detect_format_from_url(full_url).lower() or "pdf"
            link_text = re.sub(r"<[^>]+>", "", raw_link_text).strip()
            link_text = re.sub(r"\s+", " ", link_text)
            title = _extract_block_title(block, match.start())
            if not title or title.lower().strip() in GENERIC_LABELS:
                if link_text and link_text.lower().strip() not in GENERIC_LABELS:
                    title = link_text
                else:
                    title = _title_from_filename(href) if fmt == "pdf" else _title_from_url_generic(href)
            results.append({
                "title": title,
                "file_url": full_url,
                "source_page": base_url,
                "format": fmt,
            })

    for match in a_tag_re.finditer(html):
        href = match.group(1).strip()
        full_url = urljoin(base_url, href)
        if full_url in seen_urls:
            continue
        seen_urls.add(full_url)
        fmt = _detect_format_from_url(full_url).lower() or "pdf"
        raw_text = match.group(2).strip()
        link_text = re.sub(r"<[^>]+>", "", raw_text).strip()
        link_text = re.sub(r"\s+", " ", link_text)
        if link_text and link_text.lower().strip() not in GENERIC_LABELS:
            title = link_text
        else:
            title = _title_from_filename(href) if fmt == "pdf" else _title_from_url_generic(href)
        results.append({
            "title": title,
            "file_url": full_url,
            "source_page": base_url,
            "format": fmt,
        })

    return results


def _title_from_url_generic(href: str) -> str:
    """Readable title from any file URL (CSV, XLS, etc.)."""
    path = urlparse(href).path
    filename = Path(path).stem if path else "document"
    title = filename.replace("-", " ").replace("_", " ")
    title = re.sub(r'^\d+\s*', '', title)
    return title.strip().title() if title.strip() else "Documento"


async def scrape_file_links(
    page_url: str,
    extensions: tuple[str, ...] = SCRAPE_FILE_EXTENSIONS,
    timeout: float = 30.0,
) -> list[dict]:
    """
    Scrape a webpage and find all links to PDF, CSV, XLS, XLSX (or given extensions).
    Returns list of { title, file_url, source_page, format }.
    """
    headers = _headers_for_url(page_url)
    headers["User-Agent"] = USER_AGENT
    parsed = urlparse(page_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"

    async with httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=True,
        headers=headers,
        verify=_SSL_VERIFY,
        cookies=httpx.Cookies(),
    ) as client:
        if "datos.gob.mx" in origin:
            try:
                await client.get(origin + "/", headers={**headers, "Referer": origin + "/"})
            except Exception:
                pass
        resp = await client.get(page_url)
        resp.raise_for_status()
        html = resp.text

    file_links = _extract_file_links(html, page_url, extensions)

    if len(file_links) > 1:
        titles = [f["title"] for f in file_links]
        most_common = max(set(titles), key=titles.count)
        if titles.count(most_common) > len(titles) * 0.5:
            for f in file_links:
                if f["title"] == most_common:
                    f["title"] = _title_from_url_generic(f["file_url"])

    logger.info(
        f"Found {len(file_links)} file links (PDF/CSV/XLS) on {page_url}"
    )
    return file_links


# ---------------------------------------------------------------------------
# Dataset page scraper (CKAN / datos.gob.mx style)
# ---------------------------------------------------------------------------

async def scrape_dataset_resources(
    page_url: str, timeout: float = 30.0
) -> dict:
    """
    Scrape a dataset page (CKAN / datos.gob.mx style) for downloadable
    resources (CSV, XLS, PDF, etc.) and page-level metadata.

    For historico.datos.gob.mx and similar sites that return 403 without a session,
    we first request the origin to obtain cookies, then request the dataset page.
    """
    parsed = urlparse(page_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    headers = _headers_for_url(page_url)

    async with httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=True,
        headers=headers,
        verify=_SSL_VERIFY,
        cookies=httpx.Cookies(),  # persist cookies across requests
    ) as client:
        # First hit the origin to get any session/WAF cookies (reduces 403 on historico.datos.gob.mx)
        if "datos.gob.mx" in origin or "historico.datos" in origin:
            try:
                await client.get(origin + "/", headers={**headers, "Referer": origin + "/"})
            except Exception:
                pass  # ignore; we still try the actual page
        resp = await client.get(page_url)
        resp.raise_for_status()
        html = resp.text

    return _extract_dataset_resources(html, page_url)


def _extract_dataset_resources(html: str, page_url: str) -> dict:
    """Parse dataset page HTML for resources and metadata."""
    base_url = f"{urlparse(page_url).scheme}://{urlparse(page_url).netloc}"

    # --- Page-level metadata ---
    # Prefer dataset-specific title over generic site title
    page_title = ""
    # Try og:title first (usually most specific)
    og_title = re.search(
        r'<meta[^>]*property="og:title"[^>]*content="([^"]*)"', html
    )
    if og_title:
        page_title = og_title.group(1).strip()
        # Remove site suffix like " - datos.gob.mx/busca"
        page_title = re.sub(r"\s*[-–|]\s*datos\.gob\.mx.*$", "", page_title).strip()

    if not page_title:
        # Try all H1 tags, prefer the last non-generic one
        h1_matches = re.findall(r"<h1[^>]*>(.*?)</h1>", html, re.DOTALL)
        for h in reversed(h1_matches):
            cleaned = re.sub(r"<[^>]+>", "", h).strip()
            if cleaned and cleaned.lower() not in ("datos abiertos", "open data"):
                page_title = cleaned
                break
        if not page_title and h1_matches:
            page_title = re.sub(r"<[^>]+>", "", h1_matches[0]).strip()

    if not page_title:
        title_tag = re.search(r"<title>(.*?)</title>", html, re.DOTALL)
        if title_tag:
            page_title = title_tag.group(1).strip()

    # Extract metadata table (CKAN "Más información" / "Additional Information")
    page_metadata: dict[str, str] = {}
    rows = re.findall(
        r"<th[^>]*>\s*(.*?)\s*</th>\s*<td[^>]*>\s*(.*?)\s*</td>",
        html,
        re.DOTALL,
    )
    for key, val in rows:
        k = re.sub(r"<[^>]+>", "", key).strip()
        k = re.sub(r"\s+", " ", k).strip()
        v = re.sub(r"<[^>]+>", "", val).strip()
        v = re.sub(r"\s+", " ", v).strip()
        if k and v and k not in ("Campo", "Valor", "Field", "Value"):
            # Skip the composite header row that CKAN sometimes generates
            if len(k) > 60 or "\n" in k:
                continue
            # Skip keys that contain the header labels merged
            if "Campo" in k and "Valor" in k:
                # Extract just the actual key after the header noise
                # Pattern: "Campo Valor <actual_key>"
                actual = re.sub(r"^Campo\s+Valor\s+", "", k).strip()
                if actual and actual != k:
                    k = actual
                else:
                    continue
            page_metadata[k] = v

    # --- Resources ---
    # Pattern 1: CKAN download buttons with data-name (datos.gob.mx)
    resources: list[dict] = []
    seen_urls: set[str] = set()

    ckan_resources = re.findall(
        r'<a[^>]*href="([^"]*)"[^>]*'
        r'data-id="([^"]*)"[^>]*'
        r'data-name="([^"]*)"[^>]*'
        r'data-slug="([^"]*)"',
        html,
        re.DOTALL,
    )

    # Build a description map from nearby text
    desc_map: dict[str, str] = {}
    for m in re.finditer(
        r'data-id="([^"]*)".*?<p class="description">\s*(.*?)\s*</p>',
        html,
        re.DOTALL,
    ):
        rid = m.group(1)
        desc = re.sub(r"<[^>]+>", "", m.group(2)).strip()
        desc_map[rid] = desc

    for url, rid, name, slug in ckan_resources:
        if not url.startswith("http"):
            url = urljoin(base_url, url)
        if url in seen_urls:
            continue
        seen_urls.add(url)

        ext = _detect_format_from_url(url)
        resources.append(
            {
                "title": name,
                "description": desc_map.get(rid, ""),
                "url": url,
                "format": ext,
                "resource_id": rid,
                "source_page": page_url,
            }
        )

    # Pattern 2: Generic link extraction + NADA-style (download/catalog URLs)
    indexable_exts = (".csv", ".xls", ".xlsx", ".pdf", ".json", ".xml", ".zip", ".txt")
    all_links = re.findall(
        r'<a\s([^>]*)href="([^"]*)"([^>]*)>(.*?)</a>', html, re.DOTALL
    )
    for before, href, after, text in all_links:
        if not href.startswith("http"):
            href = urljoin(base_url, href)
        if href in seen_urls:
            continue
        full_tag = (before + " " + after).lower()
        text_clean = re.sub(r"<[^>]+>", "", text).strip()

        ext = _detect_format_from_url(href)
        if not ext and ("download" in href.lower() or "catalog" in href.lower() or "nada" in href.lower()):
            from urllib.parse import parse_qs, urlparse
            parsed = urlparse(href)
            qs = parse_qs(parsed.query)
            ext = (qs.get("format") or qs.get("type") or [""])[0].lower()[:5]
            if not ext and text_clean:
                if "csv" in text_clean.lower():
                    ext = "csv"
                elif "excel" in text_clean.lower() or "xls" in text_clean.lower():
                    ext = "xlsx"
                elif "pdf" in text_clean.lower():
                    ext = "pdf"
        if not ext:
            continue
        if ext == "dataset":
            continue
        # Add if direct file URL or we inferred format (e.g. NADA)
        if any(href.lower().endswith(e) for e in indexable_exts) or ext in ("csv", "xls", "xlsx", "pdf", "json"):
            seen_urls.add(href)
            resources.append(
                {
                    "title": text_clean or _title_from_url_generic(href),
                    "description": "",
                    "url": href,
                    "format": ext.upper() if len(ext) <= 5 else ext,
                    "resource_id": "",
                    "source_page": page_url,
                }
            )

    logger.info(
        f"Scraped dataset page '{page_url}': {len(resources)} resources, "
        f"{len(page_metadata)} metadata fields"
    )

    return {
        "page_title": page_title,
        "page_metadata": page_metadata,
        "resources": resources,
    }


def _detect_format_from_url(url: str) -> str:
    """Detect file format from URL."""
    path = urlparse(url).path.lower()
    last = path.split("/")[-1]
    if "." in last:
        ext = last.rsplit(".", 1)[-1]
        if len(ext) <= 5:
            return ext.upper()
    return ""


# ---------------------------------------------------------------------------
# File download utilities
# ---------------------------------------------------------------------------


async def download_pdf(
    pdf_url: str,
    timeout: float = 180.0,
    max_retries: int = 2,
) -> tuple[Path, int]:
    """
    Download a PDF to a temporary file.
    Returns (temp_file_path, file_size_bytes).
    Retries on truncated response (peer closed connection), common with gob.mx.
    """
    headers = {"User-Agent": USER_AGENT}
    last_error = None

    for attempt in range(max_retries + 1):
        try:
            async with httpx.AsyncClient(
                timeout=timeout,
                follow_redirects=True,
                headers=headers,
                verify=_SSL_VERIFY,
            ) as client:
                resp = await client.get(pdf_url)
                resp.raise_for_status()
                content = resp.content
            break
        except Exception as e:
            last_error = e
            if attempt < max_retries and "peer closed connection" in str(e).lower():
                logger.warning("PDF download truncated (attempt %s/%s), retrying: %s", attempt + 1, max_retries + 1, e)
                await asyncio.sleep(2.0 * (attempt + 1))
                continue
            raise

    # Save to temp file
    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    tmp.write(content)
    tmp.close()

    return Path(tmp.name), len(content)


async def download_file(
    url: str,
    timeout: float = 120.0,
) -> tuple[Path, int, str]:
    """
    Download any file to a temp path. Returns (path, size, extension).
    Detects extension from URL or content-type.
    """
    async with httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=True,
        headers=BROWSER_HEADERS,
        verify=_SSL_VERIFY,
    ) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        content = resp.content
        content_type = resp.headers.get("content-type", "")

    # Determine extension
    ext = _detect_format_from_url(url).lower()
    if not ext:
        if "csv" in content_type:
            ext = "csv"
        elif "spreadsheet" in content_type or "xlsx" in content_type:
            ext = "xlsx"
        elif "ms-excel" in content_type:
            ext = "xls"
        elif "pdf" in content_type:
            ext = "pdf"
        elif "html" in content_type:
            ext = "html"
        elif "json" in content_type:
            ext = "json"
        else:
            ext = "txt"

    # Detect if we got an HTML error page instead of the expected file
    # (WAFs like Incapsula/Imperva return HTML with 200 status)
    if ext in ("csv", "xlsx", "xls", "pdf", "json", "xml"):
        first_bytes = content[:500]
        try:
            text_start = first_bytes.decode("utf-8", errors="replace").strip().lower()
        except Exception:
            text_start = ""
        if text_start.startswith(("<!doctype", "<html", "<?xml")) and ext != "html":
            if "incapsula" in text_start or "access denied" in text_start or "<iframe" in text_start:
                raise RuntimeError(
                    f"Download blocked by WAF (Incapsula/Imperva). "
                    f"The server returned an HTML error page instead of the {ext.upper()} file."
                )

    suffix = f".{ext}"
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    tmp.write(content)
    tmp.close()

    return Path(tmp.name), len(content), ext
