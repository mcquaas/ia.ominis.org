"""
EC2 start/stop and status for LLM GPU instances: ominis-2.0 (Qwen) and ominis-2.0-clinic (BioMistral).
Both typically use the same g4dn instance; dashboard shows two switches for clarity.
"""

import logging
from typing import Literal

from app.config import get_settings

logger = logging.getLogger(__name__)

LlmInstanceKey = Literal["ominis-2.0", "ominis-2.0-clinic"]


def _get_instance_id(key: LlmInstanceKey) -> str | None:
    s = get_settings()
    if key == "ominis-2.0":
        return s.ollama_instance_id or None
    if key == "ominis-2.0-clinic":
        return s.ollama_clinic_instance_id or s.ollama_instance_id or None
    return None


def _get_ec2_client():
    import boto3
    s = get_settings()
    kwargs = {"region_name": s.aws_region_gpu}
    if s.aws_access_key_id and s.aws_secret_access_key:
        kwargs["aws_access_key_id"] = s.aws_access_key_id
        kwargs["aws_secret_access_key"] = s.aws_secret_access_key
    return boto3.client("ec2", **kwargs)


def get_llm_instance_status() -> dict[str, str | None]:
    """
    Return current EC2 state for each LLM instance.
    Keys: "ominis-2.0", "ominis-2.0-clinic".
    Values: "running" | "stopped" | "pending" | "error" | None (not configured).
    """
    result: dict[str, str | None] = {"ominis-2.0": None, "ominis-2.0-clinic": None}
    keys_order = ("ominis-2.0", "ominis-2.0-clinic")
    key_to_id: dict[str, str] = {}
    for key in keys_order:
        iid = _get_instance_id(key)
        if iid:
            key_to_id[key] = iid

    if not key_to_id:
        return result

    # Deduplicate instance IDs so we only call AWS once per unique ID
    unique_ids = list(dict.fromkeys(key_to_id.values()))
    try:
        client = _get_ec2_client()
        resp = client.describe_instances(InstanceIds=unique_ids)
        state_by_id = {}
        for r in resp.get("Reservations", []):
            for inst in r.get("Instances", []):
                state_by_id[inst["InstanceId"]] = inst["State"]["Name"]
        for key, iid in key_to_id.items():
            result[key] = state_by_id.get(iid, "unknown")
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
