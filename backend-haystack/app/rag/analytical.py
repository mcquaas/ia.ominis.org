"""
Analytical layer for SAV/Parquet datasets.

When a .sav file is uploaded, microdata can be exported to Parquet (see config analytical_data_dir).
This module provides run_analytical_query() to compute weighted statistics over that Parquet
so the RAG + LLM can answer "what is the mean of X by group?" without hallucinating.
"""

import logging
from pathlib import Path
from typing import Any

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def _parquet_path(source_id: int) -> Path | None:
    base = (settings.analytical_data_dir or "").strip()
    if not base:
        return None
    path = Path(base) / f"{source_id}.parquet"
    return path if path.exists() else None


def save_sav_as_parquet(sav_path: str | Path, source_id: int) -> bool:
    """
    Read a .sav file and write microdata to Parquet under analytical_data_dir.
    Returns True on success. Caller must ensure analytical_data_dir is set.
    """
    base = (settings.analytical_data_dir or "").strip()
    if not base:
        logger.debug("analytical_data_dir not set; skipping Parquet export")
        return False
    try:
        import pyreadstat
    except ImportError as e:
        logger.warning(f"Parquet export skipped (missing pyreadstat): {e}")
        return False

    path = Path(sav_path)
    if path.suffix.lower() != ".sav":
        return False

    out_dir = Path(base)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{source_id}.parquet"

    try:
        df, _ = pyreadstat.read_sav(str(path))
        if df is None or df.empty:
            logger.warning(f"SAV file empty or unreadable: {path.name}")
            return False
        df.to_parquet(out_file, index=False)
        logger.info(f"Exported SAV to {out_file} for source_id={source_id}")
        return True
    except Exception as e:
        logger.error(f"Failed to export SAV to Parquet for source_id={source_id}: {e}", exc_info=True)
        return False


def run_analytical_query(
    source_id: int,
    variable: str,
    statistic: str = "mean",
    group_by: str | None = None,
    weight_var: str | None = None,
) -> dict[str, Any]:
    """
    Run a simple analytical query on the Parquet for this source.
    variable: column name (e.g. ICB, h0107).
    statistic: "mean", "sum", "count", "min", "max".
    group_by: optional column to group by (e.g. rural, entidad).
    weight_var: optional weight column (e.g. w_hogar); used for weighted mean/sum.

    Returns {"ok": true, "result": [...]} or {"ok": false, "error": "..."}.
    """
    parquet = _parquet_path(source_id)
    if not parquet:
        return {"ok": False, "error": "No analytical data for this source. Upload a .sav with analytical_data_dir set."}

    try:
        import duckdb
    except ImportError:
        return {"ok": False, "error": "DuckDB not installed."}

    # Normalize to safe column names (DuckDB/Parquet may have case/space)
    var = variable.strip()
    if not var:
        return {"ok": False, "error": "variable is required."}

    conn = duckdb.connect(":memory:")
    try:
        # Discover columns
        tbl = conn.execute(f"SELECT * FROM read_parquet(?) LIMIT 0", [str(parquet)]).fetchdf()
        columns = [c for c in tbl.columns]
        if var not in columns:
            return {"ok": False, "error": f"Variable '{var}' not found. Available: {', '.join(columns[:30])}{'...' if len(columns) > 30 else ''}."}

        stat = statistic.lower() if statistic else "mean"
        if stat not in ("mean", "sum", "count", "min", "max"):
            return {"ok": False, "error": "statistic must be one of: mean, sum, count, min, max."}

        group_col = group_by.strip() if group_by else None
        if group_col and group_col not in columns:
            return {"ok": False, "error": f"group_by column '{group_col}' not found."}

        weight_col = weight_var.strip() if weight_var else None
        if weight_col and weight_col not in columns:
            return {"ok": False, "error": f"weight_var '{weight_col}' not found."}

        # Build SQL
        if group_col:
            select_part = f'"{group_col}"'
            if stat == "count":
                agg = f'COUNT("{var}") AS value'
            elif stat == "mean" and weight_col:
                agg = f'SUM("{var}" * "{weight_col}") / NULLIF(SUM("{weight_col}"), 0) AS value'
            elif stat == "mean":
                agg = f'AVG("{var}") AS value'
            elif stat == "sum" and weight_col:
                agg = f'SUM("{var}" * "{weight_col}") AS value'
            elif stat == "sum":
                agg = f'SUM("{var}") AS value'
            elif stat == "min":
                agg = f'MIN("{var}") AS value'
            elif stat == "max":
                agg = f'MAX("{var}") AS value'
            else:
                agg = f'AVG("{var}") AS value'
            sql = f'SELECT {select_part}, {agg} FROM read_parquet(?) GROUP BY "{group_col}" ORDER BY "{group_col}"'
        else:
            if stat == "count":
                agg = f'COUNT("{var}") AS value'
            elif stat == "mean" and weight_col:
                agg = f'SUM("{var}" * "{weight_col}") / NULLIF(SUM("{weight_col}"), 0) AS value'
            elif stat == "mean":
                agg = f'AVG("{var}") AS value'
            elif stat == "sum" and weight_col:
                agg = f'SUM("{var}" * "{weight_col}") AS value'
            elif stat == "sum":
                agg = f'SUM("{var}") AS value'
            elif stat == "min":
                agg = f'MIN("{var}") AS value'
            elif stat == "max":
                agg = f'MAX("{var}") AS value'
            else:
                agg = f'AVG("{var}") AS value'
            sql = f"SELECT {agg} FROM read_parquet(?)"

        result = conn.execute(sql, [str(parquet)]).fetchdf()
        # Convert to list of dicts for JSON
        rows = result.to_dict(orient="records")
        # Convert any non-JSON-serializable types
        for r in rows:
            for k, v in r.items():
                if hasattr(v, "item"):
                    r[k] = v.item()
                elif hasattr(v, "isoformat"):
                    r[k] = v.isoformat()
        return {"ok": True, "statistic": stat, "variable": var, "group_by": group_col, "weight_var": weight_col, "result": rows}
    except Exception as e:
        logger.exception("Analytical query failed")
        return {"ok": False, "error": str(e)}
    finally:
        conn.close()
