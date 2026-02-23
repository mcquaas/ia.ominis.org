"""
EC2 start/stop and status for research GPU instances (OpenScholar 8K and 128K).
Used by admin dashboard and by RAG router to choose which research endpoint to use.
"""

import logging
import threading
import time
from typing import Any, Literal

from app.config import get_settings

logger = logging.getLogger(__name__)

ResearchInstanceKey = Literal["openscholar", "openscholar_128k"]

# Instance type -> GPU VRAM (GB) and system RAM (GB) for dashboard display
INSTANCE_SPECS: dict[str, dict[str, int]] = {
    "g4dn.xlarge": {"vram_gb": 16, "ram_gb": 16},
    "g4dn.2xlarge": {"vram_gb": 16, "ram_gb": 32},
    "g5.xlarge": {"vram_gb": 24, "ram_gb": 16},
    "g5.2xlarge": {"vram_gb": 24, "ram_gb": 32},
    "g5.4xlarge": {"vram_gb": 24, "ram_gb": 64},
    "g5.8xlarge": {"vram_gb": 24, "ram_gb": 128},
    "p3.2xlarge": {"vram_gb": 16, "ram_gb": 61},
}

# Model base and description per research key
RESEARCH_MODEL_INFO: dict[str, tuple[str, str]] = {
    "openscholar": ("OpenScholar 8K", "vLLM, contexto 8K"),
    "openscholar_128k": ("OpenScholar 128K", "vLLM, contexto 128K (se apaga a los 60 min)"),
}

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


def get_research_instance_status() -> dict[str, Any]:
    """
    Return current EC2 state and details for each research instance.
    Top-level keys "openscholar", "openscholar_128k" = state string (backward compat).
    "details" = per-key dict with instanceId, instanceType, publicIp, state, vramGb, ramGb, modelBase, modelDescription.
    """
    result: dict[str, Any] = {"openscholar": None, "openscholar_128k": None, "details": {}}
    keys_order = ("openscholar", "openscholar_128k")
    ids: dict[str, str] = {}
    for key in keys_order:
        iid = _get_instance_id(key)
        if iid:
            ids[key] = iid
        model_base, model_desc = RESEARCH_MODEL_INFO.get(key, ("", ""))
        result["details"][key] = {
            "instanceId": iid,
            "instanceType": None,
            "publicIp": None,
            "state": None,
            "vramGb": None,
            "ramGb": None,
            "modelBase": model_base,
            "modelDescription": model_desc,
        }

    if not ids:
        return result

    try:
        client = _get_ec2_client()
        resp = client.describe_instances(InstanceIds=list(ids.values()))
        info_by_id: dict[str, dict] = {}
        for r in resp.get("Reservations", []):
            for inst in r.get("Instances", []):
                iid = inst["InstanceId"]
                itype = inst.get("InstanceType")
                specs = INSTANCE_SPECS.get(itype or "", {}) if itype else {}
                info_by_id[iid] = {
                    "state": inst["State"]["Name"],
                    "instanceType": itype,
                    "publicIp": (inst.get("PublicIpAddress") or "").strip() or None,
                    "privateIp": (inst.get("PrivateIpAddress") or "").strip() or None,
                    "vramGb": specs.get("vram_gb"),
                    "ramGb": specs.get("ram_gb"),
                }
        for key, iid in ids.items():
            info = info_by_id.get(iid, {})
            state = info.get("state") or "unknown"
            result[key] = state
            result["details"][key].update({
                "instanceId": iid,
                "instanceType": info.get("instanceType"),
                "publicIp": info.get("publicIp"),
                "state": state,
                "vramGb": info.get("vramGb"),
                "ramGb": info.get("ramGb"),
            })
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
