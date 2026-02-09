"""
Taxonomy for RAG document classification — researcher-oriented categories.

All documents in the RAG system should be tagged with these dimensions
to enable filtering and discovery by researchers.
"""

from typing import TypedDict

# Valid values for each taxonomy dimension
RAG_TAXONOMY = {
    "institucion": [
        "SSA",
        "IMSS",
        "IMSS-Bienestar",
        "ISSSTE",
        "Servicios Estatales de Salud",
        "COFEPRIS",
        "OSC",
        "Privado",
        "Internacional",
    ],
    "tipo_documento": [
        "ley",
        "norma",
        "politica_publica",
        "programa",
        "guia_clinica",
        "protocolo",
        "informe",
        "evaluacion",
        "manual",
        "articulo_cientifico",
        "base_datos",
    ],
    "marco_normativo": [
        "constitucional",
        "ley_general",
        "nom",
        "reglamento",
        "lineamiento",
        "acuerdo",
        "no_aplica",
    ],
    "funcion_salud": [
        "promocion",
        "prevencion",
        "diagnostico",
        "tratamiento",
        "rehabilitacion",
        "cuidados_paliativos",
        "vigilancia",
        "regulacion",
        "financiamiento",
        "investigacion",
    ],
    "dominio_salud": [
        "salud_publica",
        "enfermedades_cronicas",
        "enfermedades_transmisibles",
        "salud_mental",
        "salud_materna_infantil",
        "cancer",
        "nutricion",
        "adicciones",
        "discapacidad",
        "determinantes_sociales",
    ],
    "poblacion_objetivo": [
        "poblacion_general",
        "sin_seguridad_social",
        "derechohabientes",
        "personal_salud",
        "mujeres",
        "infancia",
        "adolescentes",
        "personas_mayores",
        "pueblos_indigenas",
    ],
    "nivel_atencion": [
        "primaria",
        "secundaria",
        "terciaria",
        "comunitaria",
        "hospitalaria",
        "ambulatoria",
    ],
    "territorio": [
        "nacional",
        "estatal",
        "municipal",
        "local",
        "rural",
        "urbano",
    ],
    "financiamiento": [
        "publico",
        "federal",
        "estatal",
        "mixto",
        "privado",
        "no_especificado",
    ],
    "tecnologia_insumos": [
        "medicamentos",
        "vacunas",
        "dispositivos_medicos",
        "cuadro_basico",
        "abasto",
        "evaluacion_tecnologias",
        "no_aplica",
    ],
    "datos_digital": [
        "sistemas_informacion",
        "expediente_clinico",
        "interoperabilidad",
        "analitica",
        "inteligencia_artificial",
        "proteccion_datos",
        "no_aplica",
    ],
    "vigencia": [
        "vigente",
        "historico",
        "transitorio",
        "emergencia_sanitaria",
    ],
}


class TaxonomyDict(TypedDict, total=False):
    """Typed structure for taxonomy JSON."""

    institucion: list[str]
    tipo_documento: list[str]
    marco_normativo: list[str]
    funcion_salud: list[str]
    dominio_salud: list[str]
    poblacion_objetivo: list[str]
    nivel_atencion: list[str]
    territorio: list[str]
    financiamiento: list[str]
    tecnologia_insumos: list[str]
    datos_digital: list[str]
    vigencia: list[str]


def validate_taxonomy_value(dimension: str, value: str) -> bool:
    """Check if a value is valid for the given taxonomy dimension."""
    allowed = RAG_TAXONOMY.get(dimension, [])
    return value in allowed


def filter_valid_taxonomy_values(dimension: str, values: list[str]) -> list[str]:
    """Filter a list to only include valid values for the dimension."""
    allowed = set(RAG_TAXONOMY.get(dimension, []))
    return [v for v in values if v in allowed]


def sanitize_taxonomy(taxonomy: dict) -> dict:
    """
    Ensure all taxonomy values are valid. Invalid values are dropped.
    Returns a clean taxonomy dict suitable for storage.
    """
    result: dict = {}
    for dimension, allowed in RAG_TAXONOMY.items():
        vals = taxonomy.get(dimension)
        if not vals:
            continue
        if isinstance(vals, str):
            vals = [vals]
        filtered = [v for v in vals if isinstance(v, str) and v in allowed]
        if filtered:
            result[dimension] = filtered
    return result
