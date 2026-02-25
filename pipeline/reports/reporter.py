"""Write quality report JSON and summary MD."""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from pipeline import config as pipeline_config
from pipeline.quality.metrics import compute_quality_metrics

logger = logging.getLogger(__name__)


def write_report() -> tuple[Path, Path]:
    """Write reports/YYYY-MM-DD_report.json and reports/YYYY-MM-DD_summary.md. Returns (json_path, md_path)."""
    metrics = compute_quality_metrics()
    date_str = datetime.utcnow().strftime("%Y-%m-%d")
    reports_dir = pipeline_config.REPORTS_DIR
    json_path = reports_dir / f"{date_str}_report.json"
    md_path = reports_dir / f"{date_str}_summary.md"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2, ensure_ascii=False)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(f"# Health Datastore Report — {date_str}\n\n")
        f.write(f"- **Documents:** {metrics.get('num_documents', 0)}\n")
        f.write(f"- **Chunks:** {metrics.get('num_chunks', 0)}\n")
        f.write(f"- **%% Mexican chunks:** {metrics.get('pct_chunks_mexican', 0)}\n")
        f.write(f"- **Avg evidence age (years):** {metrics.get('avg_evidence_age_years', 'N/A')}\n\n")
        f.write("## By document type\n\n")
        for k, v in (metrics.get("by_document_type") or {}).items():
            f.write(f"- {k}: {v}\n")
        f.write("\n## By institution\n\n")
        for k, v in (metrics.get("by_institution") or {}).items():
            f.write(f"- {k}: {v}\n")
    logger.info("Wrote %s and %s", json_path, md_path)
    return json_path, md_path
