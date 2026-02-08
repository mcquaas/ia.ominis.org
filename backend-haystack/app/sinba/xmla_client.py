"""
XMLA Client for SINBA OLAP Cubes — connects to SQL Server Analysis Services.

Supports two connection strategies:
  1. Local .NET proxy — connects via the XMLA proxy service (localhost:5001)
     which uses ADOMD.NET for native SSAS TCP connections. This is the
     recommended approach for Linux/macOS.
  2. HTTP XMLA — connects via msmdpump.dll IIS endpoint (if available).

The client sends MDX queries and parses the responses.
"""

import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

# XMLA SOAP namespace constants
NS_SOAP = "http://schemas.xmlsoap.org/soap/envelope/"
NS_XMLA = "urn:schemas-microsoft-com:xml-analysis"
NS_ROWSET = "urn:schemas-microsoft-com:xml-analysis:rowset"
NS_MDDATASET = "urn:schemas-microsoft-com:xml-analysis:mddataset"

# Default SSAS ports
SSAS_DEFAULT_PORT = 2383
SSAS_BROWSER_PORT = 2382

# XMLA SOAP templates
XMLA_DISCOVER_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <Discover xmlns="urn:schemas-microsoft-com:xml-analysis">
      <RequestType>{request_type}</RequestType>
      <Restrictions>
        <RestrictionList>
          {restrictions}
        </RestrictionList>
      </Restrictions>
      <Properties>
        <PropertyList>
          {properties}
        </PropertyList>
      </Properties>
    </Discover>
  </soap:Body>
</soap:Envelope>"""

XMLA_EXECUTE_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <Execute xmlns="urn:schemas-microsoft-com:xml-analysis">
      <Command>
        <Statement>{mdx_query}</Statement>
      </Command>
      <Properties>
        <PropertyList>
          <Catalog>{catalog}</Catalog>
          <Format>Tabular</Format>
          {extra_properties}
        </PropertyList>
      </Properties>
    </Execute>
  </soap:Body>
</soap:Envelope>"""


@dataclass
class XmlaConnectionConfig:
    """Configuration for connecting to an SSAS instance via XMLA."""
    # HTTP XMLA endpoint (e.g., http://server/olap/msmdpump.dll)
    xmla_url: str = ""
    # Direct server hostname (for TCP fallback)
    server: str = ""
    port: int = SSAS_DEFAULT_PORT
    # Authentication
    username: str = ""
    password: str = ""
    # SSAS catalog (database)
    catalog: str = ""
    # Request timeout in seconds
    timeout: float = 30.0


@dataclass
class XmlaResult:
    """Result of an XMLA query."""
    success: bool = False
    columns: list[str] = field(default_factory=list)
    rows: list[dict[str, Any]] = field(default_factory=list)
    raw_xml: str = ""
    error: str = ""
    row_count: int = 0

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "columns": self.columns,
            "rows": self.rows[:1000],  # Cap at 1000 rows in API responses
            "row_count": self.row_count,
            "error": self.error,
        }


class SINBAXmlaClient:
    """
    XMLA client for querying SINBA OLAP cubes via SOAP/HTTP.

    Usage:
        client = SINBAXmlaClient(config)
        result = await client.execute_mdx("SELECT ... FROM [CuboProductos2025]")
    """

    def __init__(self, config: XmlaConnectionConfig):
        self.config = config
        self._http_client: Optional[httpx.AsyncClient] = None

    async def _get_http_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client."""
        if self._http_client is None or self._http_client.is_closed:
            auth = None
            if self.config.username and self.config.password:
                auth = httpx.BasicAuth(
                    username=self.config.username,
                    password=self.config.password,
                )
            self._http_client = httpx.AsyncClient(
                timeout=self.config.timeout,
                auth=auth,
            )
        return self._http_client

    async def close(self):
        """Close the HTTP client."""
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()

    def _get_xmla_url(self) -> str:
        """Determine the XMLA endpoint URL."""
        if self.config.xmla_url:
            return self.config.xmla_url
        # Try to construct from server + common paths
        server = self.config.server
        if not server:
            raise ValueError("No XMLA URL or server configured")
        return f"http://{server}/olap/msmdpump.dll"

    def _build_properties_xml(self, extra: dict[str, str] | None = None) -> str:
        """Build the Properties XML block."""
        props = {}
        if self.config.catalog:
            props["Catalog"] = self.config.catalog
        if self.config.username:
            props["UserName"] = self.config.username
        if self.config.password:
            props["Password"] = self.config.password
        if extra:
            props.update(extra)
        return "\n".join(f"<{k}>{v}</{k}>" for k, v in props.items())

    async def _send_xmla_request(self, soap_body: str) -> str:
        """Send an XMLA SOAP request and return the raw XML response."""
        url = self._get_xmla_url()
        client = await self._get_http_client()

        headers = {
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": '"urn:schemas-microsoft-com:xml-analysis:Execute"',
        }

        try:
            resp = await client.post(url, content=soap_body, headers=headers)
            resp.raise_for_status()
            return resp.text
        except httpx.HTTPStatusError as e:
            logger.error(f"XMLA HTTP error {e.response.status_code}: {e.response.text[:500]}")
            raise
        except httpx.ConnectError as e:
            logger.error(f"Cannot connect to XMLA endpoint {url}: {e}")
            raise
        except Exception as e:
            logger.error(f"XMLA request failed: {e}")
            raise

    def _parse_tabular_response(self, xml_text: str) -> XmlaResult:
        """Parse a tabular (rowset) XMLA response."""
        result = XmlaResult(raw_xml=xml_text)

        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as e:
            result.error = f"XML parse error: {e}"
            return result

        # Check for SOAP Fault
        fault = root.find(f".//{{{NS_SOAP}}}Fault")
        if fault is not None:
            fault_string = fault.findtext("faultstring", "Unknown error")
            result.error = f"XMLA Fault: {fault_string}"
            return result

        # Find the rowset
        # Try different namespace patterns (SSAS can vary)
        rows_found = []
        columns = set()

        for ns in [NS_ROWSET, ""]:
            prefix = f"{{{ns}}}" if ns else ""
            for row in root.iter(f"{prefix}row"):
                row_dict = {}
                for child in row:
                    # Strip namespace from tag name
                    tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                    row_dict[tag] = child.text or ""
                    columns.add(tag)
                if row_dict:
                    rows_found.append(row_dict)

        if rows_found:
            result.success = True
            result.columns = sorted(columns)
            result.rows = rows_found
            result.row_count = len(rows_found)

        return result

    def _parse_multidimensional_response(self, xml_text: str) -> XmlaResult:
        """Parse a multidimensional (MDDataSet) XMLA response."""
        result = XmlaResult(raw_xml=xml_text)

        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as e:
            result.error = f"XML parse error: {e}"
            return result

        # Check for SOAP Fault
        fault = root.find(f".//{{{NS_SOAP}}}Fault")
        if fault is not None:
            fault_string = fault.findtext("faultstring", "Unknown error")
            result.error = f"XMLA Fault: {fault_string}"
            return result

        # Parse axes and cells from MDDataSet
        # This is a simplified parser - full MDDataSet parsing is complex
        cells = []
        for cell in root.iter(f"{{{NS_MDDATASET}}}Cell"):
            cell_data = {}
            for child in cell:
                tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                cell_data[tag] = child.text or ""
            if cell_data:
                cells.append(cell_data)

        if cells:
            result.success = True
            result.columns = sorted(set().union(*(c.keys() for c in cells)))
            result.rows = cells
            result.row_count = len(cells)

        return result

    # --- Public API ---

    async def test_connection(self) -> dict:
        """
        Test the XMLA connection by sending a DISCOVER_DATASOURCES request.
        Returns a dict with connection status and available data sources.
        """
        soap = XMLA_DISCOVER_TEMPLATE.format(
            request_type="DISCOVER_DATASOURCES",
            restrictions="",
            properties=self._build_properties_xml(),
        )

        try:
            response = await self._send_xmla_request(soap)
            result = self._parse_tabular_response(response)
            return {
                "connected": result.success,
                "datasources": result.rows,
                "error": result.error,
            }
        except Exception as e:
            return {
                "connected": False,
                "datasources": [],
                "error": str(e),
            }

    async def discover_cubes(self, catalog: str = "") -> XmlaResult:
        """Discover available cubes in the SSAS catalog."""
        restrictions = ""
        if catalog:
            restrictions = f"<CATALOG_NAME>{catalog}</CATALOG_NAME>"

        props = self._build_properties_xml()
        soap = XMLA_DISCOVER_TEMPLATE.format(
            request_type="MDSCHEMA_CUBES",
            restrictions=restrictions,
            properties=props,
        )

        response = await self._send_xmla_request(soap)
        return self._parse_tabular_response(response)

    async def discover_dimensions(self, catalog: str, cube_name: str) -> XmlaResult:
        """Discover dimensions for a specific cube."""
        restrictions = f"""
            <CATALOG_NAME>{catalog}</CATALOG_NAME>
            <CUBE_NAME>{cube_name}</CUBE_NAME>
        """
        props = self._build_properties_xml()
        soap = XMLA_DISCOVER_TEMPLATE.format(
            request_type="MDSCHEMA_DIMENSIONS",
            restrictions=restrictions,
            properties=props,
        )

        response = await self._send_xmla_request(soap)
        return self._parse_tabular_response(response)

    async def discover_measures(self, catalog: str, cube_name: str) -> XmlaResult:
        """Discover measures for a specific cube."""
        restrictions = f"""
            <CATALOG_NAME>{catalog}</CATALOG_NAME>
            <CUBE_NAME>{cube_name}</CUBE_NAME>
        """
        props = self._build_properties_xml()
        soap = XMLA_DISCOVER_TEMPLATE.format(
            request_type="MDSCHEMA_MEASURES",
            restrictions=restrictions,
            properties=props,
        )

        response = await self._send_xmla_request(soap)
        return self._parse_tabular_response(response)

    async def discover_hierarchies(
        self, catalog: str, cube_name: str, dimension: str = ""
    ) -> XmlaResult:
        """Discover hierarchies for a cube dimension."""
        restrictions = f"""
            <CATALOG_NAME>{catalog}</CATALOG_NAME>
            <CUBE_NAME>{cube_name}</CUBE_NAME>
        """
        if dimension:
            restrictions += f"<DIMENSION_UNIQUE_NAME>{dimension}</DIMENSION_UNIQUE_NAME>"

        props = self._build_properties_xml()
        soap = XMLA_DISCOVER_TEMPLATE.format(
            request_type="MDSCHEMA_HIERARCHIES",
            restrictions=restrictions,
            properties=props,
        )

        response = await self._send_xmla_request(soap)
        return self._parse_tabular_response(response)

    async def discover_members(
        self, catalog: str, cube_name: str, hierarchy: str, level: str = ""
    ) -> XmlaResult:
        """Discover members of a hierarchy (e.g., list all states)."""
        restrictions = f"""
            <CATALOG_NAME>{catalog}</CATALOG_NAME>
            <CUBE_NAME>{cube_name}</CUBE_NAME>
            <HIERARCHY_UNIQUE_NAME>{hierarchy}</HIERARCHY_UNIQUE_NAME>
        """
        if level:
            restrictions += f"<LEVEL_UNIQUE_NAME>{level}</LEVEL_UNIQUE_NAME>"

        props = self._build_properties_xml()
        soap = XMLA_DISCOVER_TEMPLATE.format(
            request_type="MDSCHEMA_MEMBERS",
            restrictions=restrictions,
            properties=props,
        )

        response = await self._send_xmla_request(soap)
        return self._parse_tabular_response(response)

    async def execute_mdx(self, mdx_query: str, catalog: str = "") -> XmlaResult:
        """
        Execute an MDX query against the SSAS cube.

        Args:
            mdx_query: The MDX query string.
            catalog: SSAS catalog (defaults to config catalog).

        Returns:
            XmlaResult with the query results.
        """
        cat = catalog or self.config.catalog
        if not cat:
            return XmlaResult(error="No catalog specified")

        extra_props = ""
        if self.config.username:
            extra_props += f"<UserName>{self.config.username}</UserName>\n"
        if self.config.password:
            extra_props += f"<Password>{self.config.password}</Password>\n"

        soap = XMLA_EXECUTE_TEMPLATE.format(
            mdx_query=_escape_xml(mdx_query),
            catalog=cat,
            extra_properties=extra_props,
        )

        try:
            response = await self._send_xmla_request(soap)
            # Try tabular first, then multidimensional
            result = self._parse_tabular_response(response)
            if not result.success and not result.error:
                result = self._parse_multidimensional_response(response)
            return result
        except Exception as e:
            return XmlaResult(error=str(e))

    async def execute_mdx_tabular(self, mdx_query: str, catalog: str = "") -> XmlaResult:
        """Execute MDX and return results in a flat tabular format."""
        return await self.execute_mdx(mdx_query, catalog)


def _escape_xml(text: str) -> str:
    """Escape special XML characters in text."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


class SINBAProxyClient:
    """
    Client that connects to SSAS via the local .NET XMLA proxy service.

    The proxy runs on localhost:5001 and uses ADOMD.NET for native TCP
    connections to SSAS. This is the recommended approach for Linux/macOS.

    Usage:
        client = SINBAProxyClient(proxy_url="http://127.0.0.1:5001")
        result = await client.execute_mdx(
            query="SELECT ... FROM [CuboProductos2025]",
            server="pwidgis03.salud.gob.mx",
            catalog="EGRESOS2025",
            username="DGIS15",
            password="Temp123!",
        )
    """

    def __init__(self, proxy_url: str = "http://127.0.0.1:5001"):
        self.proxy_url = proxy_url.rstrip("/")
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=120.0)
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def health_check(self) -> dict:
        """Check if the XMLA proxy is running."""
        try:
            client = await self._get_client()
            resp = await client.get(f"{self.proxy_url}/health")
            return resp.json()
        except Exception as e:
            return {"status": "unavailable", "error": str(e)}

    async def execute_mdx(
        self,
        query: str,
        server: str = "pwidgis03.salud.gob.mx",
        catalog: str = "",
        username: str = "",
        password: str = "",
        timeout: int = 120,
    ) -> XmlaResult:
        """Execute an MDX query via the .NET proxy."""
        client = await self._get_client()

        payload = {
            "server": server,
            "catalog": catalog,
            "username": username,
            "password": password,
            "query": query,
            "timeout": timeout,
        }

        try:
            resp = await client.post(f"{self.proxy_url}/mdx", json=payload)
            data = resp.json()

            return XmlaResult(
                success=data.get("success", False),
                columns=data.get("columns", []),
                rows=data.get("rows", []),
                row_count=data.get("rowCount", data.get("row_count", 0)),
                error=data.get("error", ""),
            )
        except httpx.ConnectError:
            return XmlaResult(
                error="XMLA proxy not running. Start it with: cd xmla-proxy && dotnet run"
            )
        except Exception as e:
            return XmlaResult(error=f"Proxy request failed: {e}")

    async def discover(
        self,
        discover_type: str,
        server: str = "pwidgis03.salud.gob.mx",
        catalog: str = "",
        username: str = "",
        password: str = "",
        cube_name: str = "",
        dimension_name: str = "",
        hierarchy_name: str = "",
    ) -> XmlaResult:
        """Discover schema metadata via the .NET proxy."""
        client = await self._get_client()

        payload = {
            "server": server,
            "catalog": catalog,
            "username": username,
            "password": password,
            "type": discover_type,
            "cubeName": cube_name,
            "dimensionName": dimension_name,
            "hierarchyName": hierarchy_name,
        }

        try:
            resp = await client.post(f"{self.proxy_url}/discover", json=payload)
            data = resp.json()

            return XmlaResult(
                success=data.get("success", False),
                columns=data.get("columns", []),
                rows=data.get("rows", []),
                row_count=data.get("row_count", 0),
                error=data.get("error", ""),
            )
        except httpx.ConnectError:
            return XmlaResult(
                error="XMLA proxy not running. Start it with: cd xmla-proxy && dotnet run"
            )
        except Exception as e:
            return XmlaResult(error=f"Proxy discover failed: {e}")


def build_client_from_connection(
    server: str,
    catalog: str,
    username: str = "",
    password: str = "",
    xmla_url: str = "",
) -> SINBAXmlaClient:
    """
    Factory to create an XMLA client from cube connection details.

    If xmla_url is empty, constructs the default msmdpump.dll URL.
    """
    config = XmlaConnectionConfig(
        xmla_url=xmla_url,
        server=server,
        catalog=catalog,
        username=username,
        password=password,
    )
    return SINBAXmlaClient(config)


def build_proxy_client(proxy_url: str = "") -> SINBAProxyClient:
    """Create a client that uses the local .NET XMLA proxy service."""
    url = proxy_url or "http://127.0.0.1:5001"
    return SINBAProxyClient(proxy_url=url)
