"""
EC2 start/stop and status for research GPU instances (OpenScholar 8K and 128K).
Used by admin dashboard and by RAG router to choose which research endpoint to use.
"""

import logging
import threading
import time
from typing import Literal

from app.config import get_settings

logger = logging.getLogger(__name__)

ResearchInstanceKey = Literal["openscholar", "openscholar_128k"]

# When 128k instance was started (unix timestamp); stop it after auto_stop_minutes
_128k_started_at: float | None = None
_lock = threading.Lock()


def _get_instance_id(key: ResearchInstanceKey) -> str | None:
    s = get_settings()
    if key == "openscholar":
        return s.openscholar_instance_id or None
    if key == "openscholar_128k":
        return s.openscholar_128k_instance_id or None
    return None


def _get_ec2_client():
    import boto3
    s = get_settings()
    kwargs = {"region_name": s.aws_region_gpu}
    if s.aws_access_key_id and s.aws_secret_access_key:
        kwargs["aws_access_key_id"] = s.aws_access_key_id
        kwargs["aws_secret_access_key"] = s.aws_secret_access_key
    return boto3.client("ec2", **kwargs)


def get_research_instance_status() -> dict[str, str | None]:
    """
    Return current EC2 state for each research instance.
    Keys: "openscholar", "openscholar_128k".
    Values: "running" | "stopped" | "pending" | "error" (ID set but AWS call failed) | None (not configured).
    """
    result: dict[str, str | None] = {"openscholar": None, "openscholar_128k": None}
    ids = {}
    for key in ("openscholar", "openscholar_128k"):
        iid = _get_instance_id(key)
        if iid:
            ids[key] = iid

    if not ids:
        return result

    try:
        client = _get_ec2_client()
        resp = client.describe_instances(InstanceIds=list(ids.values()))
        state_by_id = {}
        for r in resp.get("Reservations", []):
            for inst in r.get("Instances", []):
                state_by_id[inst["InstanceId"]] = inst["State"]["Name"]
        for key, iid in ids.items():
            result[key] = state_by_id.get(iid, "unknown")
    except Exception as e:
        logger.warning("Failed to get research instance status: %s", e)
        for key in ids:
            result[key] = "error"
    return result


def start_research_instance(key: ResearchInstanceKey) -> dict[str, str]:
    """Start the given EC2 instance. Returns { "status": "ok"|"error", "message": "..." }."""
    iid = _get_instance_id(key)
    if not iid:
        return {"status": "error", "message": f"Instance ID for {key} not configured"}
    try:
        client = _get_ec2_client()
        client.start_instances(InstanceIds=[iid])
        if key == "openscholar_128k":
            with _lock:
                global _128k_started_at
                _128k_started_at = time.time()
            minutes = get_settings().openscholar_128k_auto_stop_minutes
            t = threading.Thread(target=_auto_stop_128k_after, args=(minutes,), daemon=True)
            t.start()
            logger.info("Scheduled auto-stop of 128k instance in %s minutes", minutes)
        return {"status": "ok", "message": "Instance starting"}
    except Exception as e:
        logger.exception("Start instance %s failed", key)
        return {"status": "error", "message": str(e)}


def _auto_stop_128k_after(minutes: int) -> None:
    time.sleep(minutes * 60)
    with _lock:
        global _128k_started_at
        _128k_started_at = None
    stop_research_instance("openscholar_128k")
    logger.info("Auto-stopped 128k research instance after %s minutes", minutes)


def stop_research_instance(key: ResearchInstanceKey) -> dict[str, str]:
    """Stop the given EC2 instance. Returns { "status": "ok"|"error", "message": "..." }."""
    iid = _get_instance_id(key)
    if not iid:
        return {"status": "error", "message": f"Instance ID for {key} not configured"}
    try:
        client = _get_ec2_client()
        client.stop_instances(InstanceIds=[iid])
        if key == "openscholar_128k":
            with _lock:
                global _128k_started_at
                _128k_started_at = None
        return {"status": "ok", "message": "Instance stopping"}
    except Exception as e:
        logger.exception("Stop instance %s failed", key)
        return {"status": "error", "message": str(e)}


def get_active_research_key() -> Literal["openscholar_128k", "openscholar"] | None:
    """
    Return which research instance to use: 128k if running, else 8K if running, else None.
    Used by RAG router to pick generator and model id.
    """
    status = get_research_instance_status()
    if status.get("openscholar_128k") == "running":
        return "openscholar_128k"
    if status.get("openscholar") == "running":
        return "openscholar"
    return None
