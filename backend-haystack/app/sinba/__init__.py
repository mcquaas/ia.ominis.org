"""
SINBA Cubes Agent — connects to Mexico's SINBA OLAP health data cubes.

SINBA (Sistema Nacional de Información Básica en Salud) provides OLAP cubes
with health statistics from Mexico's Secretaría de Salud, covering:
  - Hospital discharges (egresos hospitalarios)
  - Mortality and fetal deaths
  - Birth certificates (SINAC)
  - Health services (SIS)
  - CONAPO population projections
  - Health expenditure (Cuentas en Salud)
  - Medical resources and infrastructure

Architecture:
  - cube_parser.py   — Parses SINBA HTML pages to extract OWC/OLAP metadata
  - xmla_client.py   — XMLA SOAP client for querying SSAS cubes
  - mdx_builder.py   — LLM-powered natural language → MDX query builder
  - schemas.py       — Pydantic request/response models
  - router.py        — FastAPI endpoints

SSAS Connection:
  The cubes run on SQL Server Analysis Services (SSAS) 2008+ on servers:
    - pwidgis03.salud.gob.mx (newer cubes: 2016, 2025)
    - cubosdgis.salud.gob.mx (older cubes: 2014-2015)

  SSAS port 2383 is open on both servers but they do NOT expose an HTTP
  XMLA endpoint (msmdpump.dll). To query cubes from Python/Linux, you need
  an XMLA HTTP proxy. Options:

  1. Deploy msmdpump.dll on a Windows IIS server with access to SSAS.
     Set SINBA_XMLA_URL=http://your-proxy/olap/msmdpump.dll

  2. Use a .NET Core microservice with Microsoft.AnalysisServices.AdomdClient:
     - The AdomdClient NuGet package works on Linux via .NET 6+
     - Create a small REST API that proxies XMLA/MDX requests
     - Run as a sidecar container alongside the Python backend

  3. For development/testing, the cube parser and MDX builder work offline
     (no SSAS connection needed for metadata discovery and query generation).
"""
