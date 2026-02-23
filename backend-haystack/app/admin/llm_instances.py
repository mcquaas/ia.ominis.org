"""
EC2 start/stop and status for LLM GPU instances: ominis-2.0 (Qwen) and ominis-2.0-med (Med42-v2).
Both may share the same g4dn when ollama_med_instance_id is empty.
"""

import logging
from typing import Any, Literal, cast

from app.config import get_settings

logger = logging.getLogger(__name__)

LlmInstanceKey = Literal["ominis-2.0", "ominis-2.0-med"]

# Instance type -> GPU VRAM (GB) and system RAM (GB) for dashboard display
INSTANCE_SPECS: dict[str, dict[str, int]] = {
    "g4dn.xlarge": {"vram_gb": 16, "ram_gb": 16},
    "g4dn.2xlarge": {"vram_gb": 16, "ram_gb": 32},
    "g4dn.4xlarge": {"vram_gb": 16, "ram_gb": 64},
    "g5.xlarge": {"vram_gb": 24, "ram_gb": 16},
    "g5.2xlarge": {"vram_gb": 24, "ram_gb": 32},
    "g5.4xlarge": {"vram_gb": 24, "ram_gb": 64},
    "g5.8xlarge": {"vram_gb": 24, "ram_gb": 128},
    "p3.2xlarge": {"vram_gb": 16, "ram_gb": 61},
    "p4d.24xlarge": {"vram_gb": 40, "ram_gb": 1152},
}


def _get_instance_id(key: LlmInstanceKey) -> str | None:
    s = get_settings()
    if key == "ominis-2.0":
        return s.ollama_instance_id or None
    if key == "ominis-2.0-med":
        return (getattr(s, "ollama_med_instance_id", None) or "").strip() or s.ollama_instance_id or None
    return None


def _get_ec2_client():
    import boto3
    s = get_settings()
    kwargs = {"region_name": s.aws_region_gpu}
    if s.aws_access_key_id and s.aws_secret_access_key:
        kwargs["aws_access_key_id"] = s.aws_access_key_id
        kwargs["aws_secret_access_key"] = s.aws_secret_access_key
    return boto3.client("ec2", **kwargs)


def _model_info_llm(key: LlmInstanceKey) -> tuple[str, str]:
    """Return (model_base, model_description) for dashboard."""
    s = get_settings()
    if key == "ominis-2.0":
        return (s.ollama_model, "Uso general (Qwen)")
    if key == "ominis-2.0-med":
        return (getattr(s, "ollama_med_model", "med42") or "med42", "Modelo clínico Med42-v2 (M42 Health)")
    return ("", "")


def get_llm_instance_status() -> dict[str, Any]:
    """
    Return current EC2 state and details for each LLM instance.
    Top-level keys "ominis-2.0", "ominis-2.0-med" = state string.
    "details" = per-key dict with instanceId, instanceType, publicIp, state, vramGb, ramGb, modelBase, modelDescription.
    """
    result: dict[str, Any] = {"ominis-2.0": None, "details": {}}
    keys_order: list[str] = ["ominis-2.0"]
    s = get_settings()
    if (getattr(s, "ollama_med_model", None) or "").strip():
        keys_order.append("ominis-2.0-med")
        result["ominis-2.0-med"] = None
    keys_order = tuple(keys_order)
    key_to_id: dict[str, str] = {}
    for key in keys_order:
        iid = _get_instance_id(cast(LlmInstanceKey, key))
        if iid:
            key_to_id[key] = iid
        model_base, model_desc = _model_info_llm(cast(LlmInstanceKey, key))
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

    if not key_to_id:
        return result

    unique_ids = list(dict.fromkeys(key_to_id.values()))
    try:
        client = _get_ec2_client()
        resp = client.describe_instances(InstanceIds=unique_ids)
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
        for key, iid in key_to_id.items():
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
        logger.warning("Failed to get LLM instance status: %s", e)
        for key in key_to_id:
            result[key] = "error"
    return result


def start_llm_instance(key: LlmInstanceKey) -> dict[str, str]:
    """Start the given EC2 instance. Returns { "status": "ok"|"error", "message": "..." }."""
    iid = _get_instance_id(key)
    if not iid:
        return {"status": "error", "message": f"Instance ID for {key} not configured"}
    try:
        client = _get_ec2_client()
        client.start_instances(InstanceIds=[iid])
        return {"status": "ok", "message": "Instance starting"}
    except Exception as e:
        logger.exception("Start LLM instance %s failed", key)
        return {"status": "error", "message": str(e)}


def stop_llm_instance(key: LlmInstanceKey) -> dict[str, str]:
    """Stop the given EC2 instance. Returns { "status": "ok"|"error", "message": "..." }."""
    iid = _get_instance_id(key)
    if not iid:
        return {"status": "error", "message": f"Instance ID for {key} not configured"}
    try:
        client = _get_ec2_client()
        client.stop_instances(InstanceIds=[iid])
        return {"status": "ok", "message": "Instance stopping"}
    except Exception as e:
        logger.exception("Stop LLM instance %s failed", key)
        return {"status": "error", "message": str(e)}
