"""
SINBA Cube HTML Parser — extracts OLAP cube metadata from SINBA HTML pages.

Parses the OWC (Office Web Components) embedded XML configuration
to extract connection strings, dimensions, measures, and hierarchies.
"""

import html
import logging
import re
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

SINBA_BASE_URL = "http://sinba08.salud.gob.mx/cubos/"
SINBA_INDEX_URL = "http://sinba08.salud.gob.mx/cubos/"

# Timeout for HTTP requests to SINBA
REQUEST_TIMEOUT = 15.0


@dataclass
class CubeDimension:
    """A dimension (field) in an OLAP cube."""
    name: str
    source_name: str  # e.g. [DClues2025].[Unidad Médica].[Entidad]
    orientation: str = ""  # Row, Column, Filter, Data
    hierarchy: str = ""
    number_format: str = ""


@dataclass
class CubeMeasure:
    """A measure in an OLAP cube."""
    name: str
    source_name: str  # e.g. [Measures].[Productos]
    number_format: str = ""


@dataclass
class CubeConnection:
    """SSAS connection details extracted from the cube HTML page."""
    provider: str = "MSOLAP"
    server: str = ""       # Data Source (SSAS server hostname)
    catalog: str = ""      # Initial Catalog (database name)
    user_id: str = ""
    password: str = ""
    extended_properties: str = ""


@dataclass
class CubeMetadata:
    """Complete metadata for a single SINBA OLAP cube."""
    cube_id: str                    # Internal ID (from HTML filename)
    name: str = ""                  # Cube name (from DataMember)
    title: str = ""                 # Page title
    category: str = ""              # Category (Egresos, Defunciones, etc.)
    year: str = ""                  # Year(s) covered
    url: str = ""                   # Source HTML page URL
    connection: CubeConnection = field(default_factory=CubeConnection)
    dimensions: list[CubeDimension] = field(default_factory=list)
    measures: list[CubeMeasure] = field(default_factory=list)
    owc_version: str = ""
    is_preliminary: bool = False
    publication_date: str = ""
    info_cutoff_date: str = ""

    def to_dict(self) -> dict:
        """Serialize to dict for API responses."""
        return {
            "cube_id": self.cube_id,
            "name": self.name,
            "title": self.title,
            "category": self.category,
            "year": self.year,
            "url": self.url,
            "is_preliminary": self.is_preliminary,
            "publication_date": self.publication_date,
            "info_cutoff_date": self.info_cutoff_date,
            "connection": {
                "server": self.connection.server,
                "catalog": self.connection.catalog,
            },
            "dimensions": [
                {
                    "name": d.name,
                    "source_name": d.source_name,
                    "orientation": d.orientation,
                }
                for d in self.dimensions
            ],
            "measures": [
                {
                    "name": m.name,
                    "source_name": m.source_name,
                    "number_format": m.number_format,
                }
                for m in self.measures
            ],
        }


def _unescape_owc_xml(raw: str) -> str:
    """
    Unescape the OWC XML data embedded in the HTML param tag.
    The XML is HTML-entity-encoded (sometimes double-encoded).
    """
    # First pass: unescape HTML entities
    text = html.unescape(raw)
    # Second pass for double-encoded entities
    text = html.unescape(text)
    return text


def _parse_connection_string(conn_str: str) -> CubeConnection:
    """Parse an MSOLAP connection string into a CubeConnection."""
    conn = CubeConnection()
    parts = conn_str.split(";")
    for part in parts:
        part = part.strip()
        if "=" not in part:
            continue
        key, _, value = part.partition("=")
        key_lower = key.strip().lower()
        value = value.strip().strip('"')

        if key_lower == "provider":
            conn.provider = value
        elif key_lower == "data source":
            conn.server = value
        elif key_lower == "initial catalog":
            conn.catalog = value
        elif key_lower == "user id":
            conn.user_id = value
        elif key_lower == "password":
            conn.password = value
        elif key_lower == "extended properties":
            conn.extended_properties = value

    return conn


def parse_cube_html(html_content: str, cube_id: str, url: str = "") -> Optional[CubeMetadata]:
    """
    Parse a SINBA cube HTML page and extract all OWC metadata.

    Args:
        html_content: Raw HTML content of the cube page.
        cube_id: Identifier derived from the filename.
        url: URL of the cube page.

    Returns:
        CubeMetadata if OWC data was found, None otherwise.
    """
    metadata = CubeMetadata(cube_id=cube_id, url=url)

    # Extract page title
    soup = BeautifulSoup(html_content, "html.parser")
    title_tag = soup.find("title")
    if title_tag:
        metadata.title = title_tag.get_text(strip=True)

    # Look for publication date and cutoff date in the page text
    text_content = soup.get_text()
    # Match various encodings of "PUBLICACIÓN" (UTF-8, windows-1252, etc.)
    pub_match = re.search(
        r"FECHA DE PUBLICACI.N\s*[:\s]*(.+?)(?:::|\n|$)",
        text_content,
        re.IGNORECASE,
    )
    if pub_match:
        metadata.publication_date = pub_match.group(1).strip()

    cutoff_match = re.search(
        r"Corte de informaci.n\s*[:\s]*(.+?)(?:::|\n|$)",
        text_content,
        re.IGNORECASE,
    )
    if cutoff_match:
        metadata.info_cutoff_date = cutoff_match.group(1).strip()

    if re.search(r"preliminar", text_content, re.IGNORECASE):
        metadata.is_preliminary = True

    # Extract the OWC XMLData param from the OBJECT tag
    # The XML is in a param named "XMLData" inside an OWC PivotTable object
    xml_data = ""

    # Method 1: Look for param tag with XMLData
    param_match = re.search(
        r'<param\s+name=["\']XMLData["\']\s+value="([^"]*)"',
        html_content,
        re.IGNORECASE | re.DOTALL,
    )
    if param_match:
        xml_data = _unescape_owc_xml(param_match.group(1))

    # Method 2: Look for inline OWC XML (alternative format)
    if not xml_data:
        owc_match = re.search(
            r'value="(&lt;xml[^"]*)"',
            html_content,
            re.IGNORECASE | re.DOTALL,
        )
        if owc_match:
            xml_data = _unescape_owc_xml(owc_match.group(1))

    if not xml_data:
        # Check if this is a frameset page — the OWC is in the inner frame
        frame_match = re.search(
            r'<frame\s+src=["\']([^"\']+)["\'].*?name=["\']mainFrame["\']',
            html_content,
            re.IGNORECASE,
        )
        if not frame_match:
            # Try alternative frame pattern (src after name)
            frame_match = re.search(
                r'<frame[^>]+src=["\']([^"\']+\.htm[l]?)["\']',
                html_content,
                re.IGNORECASE,
            )

        if frame_match:
            inner_filename = frame_match.group(1)
            metadata._inner_frame = inner_filename  # type: ignore[attr-defined]
            logger.debug(f"Cube {cube_id} uses frameset, inner frame: {inner_filename}")
            return metadata  # Return partial metadata; caller should fetch inner frame

        logger.debug(f"No OWC XML data found in cube {cube_id}")
        return None

    # Parse the OWC XML
    try:
        owc_soup = BeautifulSoup(xml_data, "html.parser")
    except Exception as e:
        logger.warning(f"Failed to parse OWC XML for cube {cube_id}: {e}")
        return None

    # OWC Version
    owc_ver = owc_soup.find("x:owcversion") or owc_soup.find("owcversion")
    if owc_ver:
        metadata.owc_version = owc_ver.get_text(strip=True)

    # Connection String
    conn_tag = owc_soup.find("x:connectionstring") or owc_soup.find("connectionstring")
    if conn_tag:
        conn_str = conn_tag.get_text(strip=True)
        metadata.connection = _parse_connection_string(conn_str)

    # Cube name (DataMember)
    dm_tag = owc_soup.find("x:datamember") or owc_soup.find("datamember")
    if dm_tag:
        metadata.name = dm_tag.get_text(strip=True)

    # Track seen measure source names to avoid duplicates
    seen_measure_sources: set[str] = set()

    # Parse PivotFields (dimensions and measures)
    pivot_fields = owc_soup.find_all("x:pivotfield") or owc_soup.find_all("pivotfield")
    for pf in pivot_fields:
        name_tag = pf.find("x:name") or pf.find("name")
        source_tag = pf.find("x:sourcename") or pf.find("sourcename")
        orient_tag = pf.find("x:orientation") or pf.find("orientation")
        fmt_tag = pf.find("x:numberformat") or pf.find("numberformat")
        parent_tag = pf.find("x:parentfield") or pf.find("parentfield")

        name = name_tag.get_text(strip=True) if name_tag else ""
        source = source_tag.get_text(strip=True) if source_tag else ""
        orientation = orient_tag.get_text(strip=True) if orient_tag else ""
        fmt = fmt_tag.get_text(strip=True) if fmt_tag else ""
        parent = parent_tag.get_text(strip=True) if parent_tag else ""

        if source and source.startswith("[Measures]"):
            if source not in seen_measure_sources:
                seen_measure_sources.add(source)
                metadata.measures.append(CubeMeasure(
                    name=name,
                    source_name=source,
                    number_format=fmt,
                ))
        elif orientation == "Data" and parent:
            # This is a data field bound to a measure — skip if already seen
            if parent not in seen_measure_sources:
                seen_measure_sources.add(parent)
                metadata.measures.append(CubeMeasure(
                    name=name,
                    source_name=parent,
                    number_format=fmt,
                ))
        elif source or orientation in ("Row", "Column", "Filter"):
            metadata.dimensions.append(CubeDimension(
                name=name,
                source_name=source,
                orientation=orientation,
                number_format=fmt,
            ))

    # Parse PLTotals (additional measures in some cube formats)
    pltotals = owc_soup.find_all("x:pltotal") or owc_soup.find_all("pltotal")
    for plt in pltotals:
        name_tag = plt.find("x:name") or plt.find("name")
        source_tag = plt.find("x:sourcename") or plt.find("sourcename")
        fmt_tag = plt.find("x:numberformat") or plt.find("numberformat")

        name = name_tag.get_text(strip=True) if name_tag else ""
        source = source_tag.get_text(strip=True) if source_tag else ""
        fmt = fmt_tag.get_text(strip=True) if fmt_tag else ""

        if source and source not in seen_measure_sources:
            seen_measure_sources.add(source)
            metadata.measures.append(CubeMeasure(
                name=name,
                source_name=source,
                number_format=fmt,
            ))

    # Extract year from cube_id or title
    year_match = re.search(r"(\d{4})", cube_id)
    if year_match:
        metadata.year = year_match.group(1)

    return metadata


async def fetch_cube_page(cube_filename: str) -> Optional[str]:
    """Fetch a cube HTML page from SINBA, handling windows-1252/iso-8859-1 encoding."""
    url = urljoin(SINBA_BASE_URL, cube_filename)
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            resp = await client.get(url, follow_redirects=True)
            resp.raise_for_status()
            # SINBA pages use windows-1252 or iso-8859-1 encoding (declared in
            # HTML meta tags, not HTTP headers). httpx defaults to the HTTP
            # Content-Type header which often says text/html without charset,
            # falling back to UTF-8 which corrupts accented characters.
            raw = resp.content
            for encoding in ("windows-1252", "iso-8859-1", "utf-8"):
                try:
                    return raw.decode(encoding)
                except (UnicodeDecodeError, LookupError):
                    continue
            return raw.decode("utf-8", errors="replace")
    except Exception as e:
        logger.warning(f"Failed to fetch cube page {url}: {e}")
        return None


async def discover_cube_pages() -> list[dict]:
    """
    Parse the SINBA index page to discover all available cube pages.

    Returns a list of dicts with keys:
      - filename: HTML filename
      - label: Display label
      - category: Category (Defunciones, Egresos, etc.)
    """
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            resp = await client.get(SINBA_INDEX_URL, follow_redirects=True)
            resp.raise_for_status()
            # SINBA index page uses iso-8859-1 encoding
            raw = resp.content
            html_content = raw.decode("windows-1252", errors="replace")
    except Exception as e:
        logger.error(f"Failed to fetch SINBA index: {e}")
        return []

    soup = BeautifulSoup(html_content, "html.parser")
    cubes = []
    current_category = "General"

    # The index page has section headers (h2/h3/bold text) followed by links
    for element in soup.find_all(["a", "h2", "h3", "b", "strong"]):
        if element.name in ("h2", "h3", "b", "strong"):
            text = element.get_text(strip=True)
            if text and len(text) > 3:
                current_category = text

        if element.name == "a":
            href = element.get("href", "")
            label = element.get_text(strip=True)

            # Extract filename from JavaScript new_window('filename.html') or direct href
            js_match = re.search(r"new_window\(['\"]([^'\"]+\.html)['\"]", href)
            if js_match:
                filename = js_match.group(1)
            elif href.endswith(".html") and "salud.gob.mx" not in href:
                filename = href
            else:
                continue

            # Skip non-cube links (metadata pages, help files, etc.)
            if any(
                skip in filename.lower()
                for skip in ("metadatos", "metadata", "manual", "ayuda", "help")
            ):
                continue

            cubes.append({
                "filename": filename,
                "label": label,
                "category": current_category,
            })

    logger.info(f"Discovered {len(cubes)} cube pages from SINBA index")
    return cubes


async def catalog_all_cubes(max_cubes: int = 0) -> list[CubeMetadata]:
    """
    Discover and parse all available SINBA cubes.

    Args:
        max_cubes: Maximum number of cubes to parse (0 = all).

    Returns:
        List of CubeMetadata for successfully parsed cubes.
    """
    pages = await discover_cube_pages()
    if max_cubes > 0:
        pages = pages[:max_cubes]

    results: list[CubeMetadata] = []

    for page_info in pages:
        filename = page_info["filename"]
        cube_id = filename.replace(".html", "")
        url = urljoin(SINBA_BASE_URL, filename)

        html_content = await fetch_cube_page(filename)
        if not html_content:
            continue

        metadata = parse_cube_html(html_content, cube_id, url)
        if metadata:
            metadata.category = page_info.get("category", "")
            if not metadata.year:
                # Try to extract year from label
                year_match = re.search(r"(\d{4})", page_info.get("label", ""))
                if year_match:
                    metadata.year = year_match.group(1)
            results.append(metadata)

    logger.info(f"Successfully parsed {len(results)} cubes out of {len(pages)} pages")
    return results


async def get_cube_metadata(cube_id: str) -> Optional[CubeMetadata]:
    """Fetch and parse metadata for a specific cube, following framesets."""
    filename = f"{cube_id}.html"
    html_content = await fetch_cube_page(filename)
    if not html_content:
        return None

    url = urljoin(SINBA_BASE_URL, filename)
    metadata = parse_cube_html(html_content, cube_id, url)

    if metadata is None:
        return None

    # If the page is a frameset, fetch the inner frame for OWC data
    inner_frame = getattr(metadata, "_inner_frame", None)
    if inner_frame and not metadata.name:
        inner_html = await fetch_cube_page(inner_frame)
        if inner_html:
            inner_meta = parse_cube_html(inner_html, cube_id, url)
            if inner_meta and inner_meta.name:
                # Merge: keep title from outer page, take OWC data from inner
                inner_meta.title = metadata.title or inner_meta.title
                inner_meta.url = url
                return inner_meta

        # If inner frame couldn't be fetched or parsed, return None
        # (partial frameset metadata without OWC data isn't useful)
        return None

    return metadata
