"""
Chart generation utilities for Haystack chat responses.

Generates chart specs via the LLM (JSON-only) and renders PNG charts
inline using matplotlib.
"""

from __future__ import annotations

import base64
import io
import json
import logging
import re
import uuid
from typing import Optional

from haystack.dataclasses import ChatMessage, Document

logger = logging.getLogger(__name__)

CHART_KEYWORDS = (
    "grafica",
    "gráfica",
    "grafico",
    "gráfico",
    "chart",
    "plot",
    "bar",
    "barra",
    "barras",
    "linea",
    "línea",
    "lineas",
    "líneas",
    "pie",
    "pastel",
    "torta",
)

SUPPORTED_CHART_TYPES = {"bar", "line", "pie"}


def _contains_table(text: str) -> bool:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if any(line.startswith("|") and line.endswith("|") for line in lines):
        return True
    if any(re.match(r"^\|[\s\-:|]+\|$", line) for line in lines):
        return True
    # CSV-like: at least 2 comma-separated lines with numbers
    csv_lines = [line for line in lines if "," in line]
    if len(csv_lines) >= 2 and any(re.search(r"\d", line) for line in csv_lines):
        return True
    return False


def looks_like_chart_request(text: str) -> bool:
    lowered = text.lower()
    if any(k in lowered for k in CHART_KEYWORDS):
        return True
    return _contains_table(text)


def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rstrip() + "…"


def _extract_json_object(text: str) -> dict | None:
    """Extract the first JSON object from a text blob."""
    try:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        return json.loads(text[start : end + 1])
    except Exception:
        return None


def _collect_data_snippet(question: str) -> str:
    lines = question.splitlines()
    if not lines:
        return ""
    data_lines: list[str] = []
    for line in lines:
        if "|" in line or "," in line or re.search(r"\d", line):
            data_lines.append(line)
    snippet = "\n".join(data_lines)
    return _truncate(snippet, 1500)


def _build_chart_messages(
    question: str,
    answer: str,
    documents: list[Document],
    history: list[dict] | None = None,
    for_research_report: bool = False,
) -> list[ChatMessage]:
    system = (
        "Eres un analista de visualización. Tu tarea es proponer datos para gráficas. "
        "Devuelve SOLO JSON válido sin texto extra. "
        "Si no hay datos claros o la gráfica no sería relevante para la pregunta, responde con {\"charts\": []}.\n"
        "Solo propón una gráfica cuando los datos apoyen directamente la respuesta y la visualización aporte valor (comparaciones, tendencias, proporciones). Si los datos son genéricos o no encajan, devuelve {\"charts\": []}.\n"
    )
    if for_research_report:
        system += (
            "En reportes de investigación: solo propón una gráfica si la respuesta contiene números EXPLÍCITOS de las fuentes (prevalencia %, N, sensibilidad, especificidad, valores de corte). "
            "NUNCA propongas gráficas con categorías genéricas (ej. Sí/No, Diagnóstico vs Enfermedad) sin datos reales; en ese caso devuelve {\"charts\": []}.\n"
        )
    system += (
        "Formato JSON:\n"
        "{"
        "\"charts\": ["
        "{"
        "\"type\": \"bar|line|pie\", "
        "\"title\": \"...\", "
        "\"x_label\": \"...\", "
        "\"y_label\": \"...\", "
        "\"series\": [{\"name\": \"...\", \"data\": [{\"x\": \"...\", \"y\": 0}]}], "
        "\"labels\": [\"...\"], "
        "\"values\": [0]"
        "}"
        "]"
        "}\n"
        "Reglas:\n"
        "- x_label = eje horizontal (categorías: Año, Tipo, Tratamiento, etc.).\n"
        "- y_label = eje vertical (magnitud: Número de estudios, Prevalencia (%), Proporción, etc.). NUNCA pongas \"Año\" en y_label si los valores en Y son números; y_label debe describir qué mide ese número.\n"
        "- Usa SOLO datos explícitos en la pregunta, respuesta o fuentes.\n"
        "- Máximo 12 puntos por serie. Para pie: labels/values; para bar/line: series. Números reales (no texto)."
    )

    user_parts: list[str] = []
    data_snippet = _collect_data_snippet(question)
    if data_snippet:
        user_parts.append(f"DATOS DETECTADOS:\n{data_snippet}")

    if documents:
        source_text = "FUENTES DISPONIBLES:\n"
        for i, doc in enumerate(documents[:2], 1):
            title = doc.meta.get("title", "Sin título")
            url = doc.meta.get("url", "")
            content = (doc.content or "")[:700]
            source_text += f"\n[{i}] {title}\nURL: {url}\nContenido: {content}\n---"
        user_parts.append(source_text)

    if history:
        recent = history[-4:]
        hist_text = "\n".join([f"{m.get('role')}: {m.get('content')}" for m in recent])
        user_parts.append(f"HISTORIAL RECIENTE:\n{_truncate(hist_text, 1200)}")

    user_parts.append(f"PREGUNTA DEL USUARIO:\n{_truncate(question, 1200)}")
    user_parts.append(f"RESPUESTA DEL ASISTENTE:\n{_truncate(answer, 1200)}")

    return [
        ChatMessage.from_system(system),
        ChatMessage.from_user("\n\n".join(user_parts)),
    ]


def _normalize_chart(chart: dict) -> Optional[dict]:
    if not isinstance(chart, dict):
        return None
    ctype = str(chart.get("type", "")).lower().strip()
    if ctype not in SUPPORTED_CHART_TYPES:
        return None
    title = str(chart.get("title", "")).strip()
    x_label = str(chart.get("x_label", "")).strip()
    y_label = str(chart.get("y_label", "")).strip()

    if ctype == "pie":
        labels = chart.get("labels") or []
        values = chart.get("values") or []
        if not isinstance(labels, list) or not isinstance(values, list):
            return None
        pairs = []
        for label, value in zip(labels, values):
            try:
                val = float(value)
            except Exception:
                continue
            label_str = str(label).strip()
            if label_str:
                pairs.append((label_str, val))
        if len(pairs) < 2:
            return None
        labels, values = zip(*pairs)
        return {
            "id": uuid.uuid4().hex,
            "type": ctype,
            "title": title,
            "x_label": "",
            "y_label": "",
            "labels": list(labels)[:12],
            "values": list(values)[:12],
            "series": [],
        }

    series = chart.get("series") or []
    if not isinstance(series, list) or len(series) == 0:
        return None
    normalized_series = []
    for s in series:
        if not isinstance(s, dict):
            continue
        name = str(s.get("name", "")).strip() or "Serie"
        data = s.get("data") or []
        if not isinstance(data, list):
            continue
        points = []
        for point in data:
            if not isinstance(point, dict):
                continue
            x_val = str(point.get("x", "")).strip()
            try:
                y_val = float(point.get("y"))
            except Exception:
                continue
            if x_val:
                points.append((x_val, y_val))
        if len(points) >= 2:
            normalized_series.append({"name": name, "data": points[:12]})
    if not normalized_series:
        return None
    return {
        "id": uuid.uuid4().hex,
        "type": ctype,
        "title": title,
        "x_label": x_label,
        "y_label": y_label,
        "labels": [],
        "values": [],
        "series": normalized_series,
    }


async def generate_chart_specs(
    question: str,
    answer: str,
    documents: list[Document],
    history: list[dict] | None,
    generator,
    force: bool = False,
) -> list[dict]:
    """Generate chart specs from question/answer/documents. If force=True (e.g. research report), skip the question-based gate."""
    if not force and not looks_like_chart_request(question):
        return []

    messages = _build_chart_messages(
        question=question,
        answer=answer,
        documents=documents,
        history=history,
        for_research_report=force,
    )

    try:
        import asyncio

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: generator.run(messages=messages),
        )
        replies = result.get("replies", [])
        text = replies[0].text if replies else ""
    except Exception as exc:
        logger.error("Chart spec generation failed: %s", exc, exc_info=True)
        return []

    spec = _extract_json_object(text) or {}
    charts_raw = spec.get("charts") if isinstance(spec.get("charts"), list) else []

    normalized: list[dict] = []
    for chart in charts_raw:
        norm = _normalize_chart(chart)
        if norm:
            normalized.append(norm)
    return normalized[:3]


# Pattern for fenced block: ```chart or ```json followed by content and closing ```
_CHART_BLOCK_RE = re.compile(
    r"```(?:chart|json)\s*\n(.*?)```",
    re.DOTALL | re.IGNORECASE,
)


def parse_chart_specs_from_text(text: str) -> list[dict]:
    """
    Parse embedded chart spec from report text. Looks for ```chart or ```json
    block containing {"charts": [...]}. Returns list of normalized chart dicts
    (empty if none or invalid).
    """
    if not text or not text.strip():
        return []
    normalized: list[dict] = []
    for match in _CHART_BLOCK_RE.finditer(text):
        block = match.group(1).strip()
        spec = _extract_json_object(block)
        if not spec:
            continue
        charts_raw = spec.get("charts") if isinstance(spec.get("charts"), list) else []
        for chart in charts_raw:
            norm = _normalize_chart(chart)
            if norm:
                normalized.append(norm)
        if normalized:
            break  # Use first valid block only
    return normalized[:3]


def strip_chart_block_from_text(text: str) -> str:
    """Remove the first ```chart or ```json block from text (so the report does not show raw JSON)."""
    if not text:
        return text
    return _CHART_BLOCK_RE.sub("", text, count=1).strip()


def render_chart_images(charts: list[dict]) -> list[dict]:
    if not charts:
        return []

    try:
        import matplotlib.pyplot as plt
    except Exception as exc:
        logger.error("matplotlib is required for chart rendering: %s", exc)
        return []

    images: list[dict] = []
    for chart in charts:
        try:
            plt.close("all")
            try:
                plt.style.use("seaborn-v0_8-darkgrid")
            except Exception:
                plt.style.use("default")

            fig, ax = plt.subplots(figsize=(6.2, 4.2), dpi=160)
            ctype = chart.get("type")

            if ctype == "pie":
                labels = chart.get("labels") or []
                values = chart.get("values") or []
                ax.pie(values, labels=labels, autopct="%1.1f%%", startangle=90)
                ax.axis("equal")
            else:
                series = chart.get("series") or []
                x_labels = [x for x, _ in series[0]["data"]]
                x_positions = list(range(len(x_labels)))
                width = 0.8 / max(1, len(series))

                for idx, s in enumerate(series):
                    xs = x_positions
                    ys = [y for _, y in s["data"]]
                    if ctype == "bar":
                        offset = (idx - (len(series) - 1) / 2) * width
                        ax.bar(
                            [x + offset for x in xs],
                            ys,
                            width=width,
                            label=s["name"],
                        )
                    else:
                        ax.plot(xs, ys, marker="o", linewidth=2, label=s["name"])

                ax.set_xticks(x_positions)
                ax.set_xticklabels(x_labels, rotation=30, ha="right")
                if chart.get("x_label"):
                    ax.set_xlabel(chart.get("x_label"))
                if chart.get("y_label"):
                    ax.set_ylabel(chart.get("y_label"))
                if len(series) > 1:
                    ax.legend(loc="best", fontsize="small")

            if chart.get("title"):
                ax.set_title(chart.get("title"))

            fig.tight_layout()
            buf = io.BytesIO()
            fig.savefig(buf, format="png", bbox_inches="tight")
            buf.seek(0)
            img_b64 = base64.b64encode(buf.read()).decode("utf-8")
            data_uri = f"data:image/png;base64,{img_b64}"

            images.append(
                {
                    "id": chart.get("id") or uuid.uuid4().hex,
                    "type": chart.get("type"),
                    "title": chart.get("title"),
                    "image": data_uri,
                }
            )
        except Exception as exc:
            logger.error("Chart rendering failed: %s", exc, exc_info=True)
            continue

    return images
