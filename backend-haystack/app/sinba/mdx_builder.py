"""
MDX Query Builder — translates natural language questions to MDX queries.

Uses the project's LLM (via Ollama) to interpret user questions in the
context of a specific OLAP cube's structure (dimensions, measures, hierarchies)
and generate appropriate MDX (Multidimensional Expressions) queries.
"""

import json
import logging
import re
from typing import Optional

from haystack.dataclasses import ChatMessage

from app.sinba.cube_parser import CubeMetadata

logger = logging.getLogger(__name__)

# System prompt for MDX generation
MDX_SYSTEM_PROMPT = """Eres un experto en MDX (Multidimensional Expressions) para SQL Server Analysis Services.
Tu tarea es traducir preguntas en lenguaje natural sobre datos de salud de México a consultas MDX válidas.

REGLAS IMPORTANTES:
1. Genera SOLO la consulta MDX, sin explicaciones ni texto adicional.
2. Usa la sintaxis MDX correcta para SSAS.
3. Los nombres de dimensiones, jerarquías y medidas DEBEN coincidir exactamente con los del cubo.
4. Para filtrar por entidad federativa, usa WHERE o FILTER con la dimensión correspondiente.
5. Usa NON EMPTY para evitar filas/columnas vacías.
6. Para totales nacionales, no filtres por entidad.
7. Los miembros se referencian como [Dimensión].[Jerarquía].[Nivel].&[Valor]
8. Responde SOLO con el MDX query, nada más."""

# Template for providing cube context to the LLM
CUBE_CONTEXT_TEMPLATE = """CUBO OLAP: {cube_name}
CATÁLOGO: {catalog}

DIMENSIONES DISPONIBLES:
{dimensions}

MEDIDAS DISPONIBLES:
{measures}

NOTAS:
- Las entidades federativas de México se representan en la dimensión de unidad médica.
- Los años pueden estar en una dimensión temporal o ser parte del nombre del cubo.
- Las medidas numéricas comunes incluyen: conteo de egresos, días de estancia, productos.
"""


def _format_cube_context(metadata: CubeMetadata) -> str:
    """Format cube metadata into a context string for the LLM."""
    dims = []
    for d in metadata.dimensions:
        dims.append(f"  - {d.name}: {d.source_name} (orientación: {d.orientation})")

    measures = []
    for m in metadata.measures:
        measures.append(f"  - {m.name}: {m.source_name}")

    return CUBE_CONTEXT_TEMPLATE.format(
        cube_name=metadata.name,
        catalog=metadata.connection.catalog,
        dimensions="\n".join(dims) if dims else "  (no se encontraron dimensiones explícitas)",
        measures="\n".join(measures) if measures else "  (no se encontraron medidas explícitas)",
    )


def build_mdx_prompt(question: str, metadata: CubeMetadata) -> list[ChatMessage]:
    """
    Build chat messages for LLM-powered MDX generation.

    Args:
        question: Natural language question about the health data.
        metadata: Cube metadata with dimensions and measures.

    Returns:
        List of ChatMessage objects ready for the OllamaChatGenerator.
    """
    cube_context = _format_cube_context(metadata)

    messages = [
        ChatMessage.from_system(MDX_SYSTEM_PROMPT),
        ChatMessage.from_user(
            f"Contexto del cubo OLAP:\n{cube_context}\n\n"
            f"Pregunta: {question}\n\n"
            f"Genera la consulta MDX:"
        ),
    ]

    return messages


def extract_mdx_from_response(response_text: str) -> str:
    """
    Extract the MDX query from the LLM response.
    Handles cases where the LLM wraps it in code blocks or adds extra text.
    """
    text = response_text.strip()

    # Try to extract from markdown code block
    code_match = re.search(r"```(?:mdx|sql)?\s*\n(.*?)\n```", text, re.DOTALL | re.IGNORECASE)
    if code_match:
        return code_match.group(1).strip()

    # If the response starts with SELECT or WITH, it's likely the raw MDX
    if text.upper().startswith(("SELECT", "WITH")):
        return text

    # Try to find a SELECT statement anywhere in the text
    select_match = re.search(
        r"((?:WITH\s+.+?\s+)?SELECT\s+.+?FROM\s+\[.+?\](?:\s+WHERE\s+.+?)?)\s*$",
        text,
        re.DOTALL | re.IGNORECASE,
    )
    if select_match:
        return select_match.group(1).strip()

    # Return as-is if nothing else matched
    return text


# --- Predefined MDX templates for common queries ---

MDX_TEMPLATES = {
    "total_by_state": """
SELECT
  NON EMPTY {{[Measures].[{measure}]}} ON COLUMNS,
  NON EMPTY {{{dimension}.Members}} ON ROWS
FROM [{cube}]
""",
    "top_n": """
SELECT
  NON EMPTY {{[Measures].[{measure}]}} ON COLUMNS,
  NON EMPTY TopCount({{{dimension}.Members}}, {n}, [Measures].[{measure}]) ON ROWS
FROM [{cube}]
""",
    "total": """
SELECT
  NON EMPTY {{[Measures].[{measure}]}} ON COLUMNS
FROM [{cube}]
""",
    "cross_tab": """
SELECT
  NON EMPTY {{[Measures].[{measure}]}} ON COLUMNS,
  NON EMPTY CrossJoin({{{dim1}.Members}}, {{{dim2}.Members}}) ON ROWS
FROM [{cube}]
""",
}


def build_template_mdx(
    template_name: str,
    cube_name: str,
    params: dict[str, str],
) -> Optional[str]:
    """
    Build an MDX query from a predefined template.

    Args:
        template_name: Name of the template (e.g., 'total_by_state').
        cube_name: Name of the OLAP cube.
        params: Template parameters (measure, dimension, n, etc.).

    Returns:
        Formatted MDX query string, or None if template not found.
    """
    template = MDX_TEMPLATES.get(template_name)
    if not template:
        return None

    params["cube"] = cube_name
    try:
        return template.format(**params).strip()
    except KeyError as e:
        logger.warning(f"Missing template parameter: {e}")
        return None
