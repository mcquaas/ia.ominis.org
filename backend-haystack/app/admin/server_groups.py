"""
Aggregate LLM EC2 instances into a single "servers" list for the dashboard.
Only Ominis 2.0 and Ominis 2.0 Med are shown.
"""

import logging
from typing import Any

from app.config import get_settings
from app.admin.llm_instances import (
    _get_instance_id as _llm_instance_id,
    INSTANCE_SPECS,
    get_llm_instance_status,
    _model_info_llm,
)

# Approximate on-demand USD/month (24/7) for dashboard cost estimate — us-east-1, check AWS for current prices
INSTANCE_ESTIMATED_MONTHLY_USD: dict[str, int] = {
    "g4dn.xlarge": 380,
    "g4dn.2xlarge": 548,
    "g4dn.4xlarge": 986,
    "g5.xlarge": 525,
    "g5.2xlarge": 875,
    "g5.4xlarge": 1750,
    "g5.8xlarge": 3500,
    "p3.2xlarge": 918,
    "p4d.24xlarge": 32760,
}

logger = logging.getLogger(__name__)


def _get_ec2_client():
    import boto3
    s = get_settings()
    kwargs = {"region_name": s.aws_region_gpu}
    if s.aws_access_key_id and s.aws_secret_access_key:
        kwargs["aws_access_key_id"] = s.aws_access_key_id
        kwargs["aws_secret_access_key"] = s.aws_secret_access_key
    return boto3.client("ec2", **kwargs)


def _fetch_instance_type_specs(instance_types: list[str]) -> dict[str, dict[str, int]]:
    """Fetch RAM and VRAM per instance type from EC2 describe_instance_types (one source of truth per type)."""
    if not instance_types:
        return {}
    out: dict[str, dict[str, int]] = {}
    try:
        client = _get_ec2_client()
        spec_resp = client.describe_instance_types(InstanceTypes=instance_types)
        for it in spec_resp.get("InstanceTypes", []):
            itype = it.get("InstanceType")
            if not itype:
                continue
            ram_mib = None
            if it.get("MemoryInfo") and (it["MemoryInfo"] or {}).get("SizeInMiB") is not None:
                ram_mib = it["MemoryInfo"]["SizeInMiB"]
            vram_mib = None
            if it.get("GpuInfo") and (it["GpuInfo"] or {}).get("TotalGpuMemoryInMiB") is not None:
                vram_mib = it["GpuInfo"]["TotalGpuMemoryInMiB"]
            ram_gb = round(ram_mib / 1024) if ram_mib is not None else INSTANCE_SPECS.get(itype, {}).get("ram_gb")
            vram_gb = round(vram_mib / 1024) if vram_mib is not None else INSTANCE_SPECS.get(itype, {}).get("vram_gb")
            out[itype] = {"ram_gb": ram_gb, "vram_gb": vram_gb}
    except Exception as e:
        logger.warning("Failed to fetch instance type specs, using static map: %s", e)
    return out


def get_servers_status() -> dict[str, Any]:
    """
    Return a list of unique EC2 servers, each with instance details and the models that run on it.
    Used by dashboard to show one card per server with one on/off switch.
    """
    s = get_settings()
    # (key, instance_id, key_type "llm"|"research", label, model_base, model_description)
    key_to_server: list[tuple[str, str | None, str, str, str, str]] = []

    # LLM: ominis-2.0 (Ominis 2.0)
    iid = _llm_instance_id("ominis-2.0")  # type: ignore[arg-type]
    base, desc = _model_info_llm("ominis-2.0")  # type: ignore[arg-type]
    key_to_server.append(("ominis-2.0", iid, "llm", "Ominis 2.0", base, desc))

    # Ominis 2.0 Med: Med42-v2 (clinical). Same server as ominis-2.0 if no ollama_med_instance_id
    if (getattr(s, "ollama_med_model", None) or "").strip():
        med_iid = (getattr(s, "ollama_med_instance_id", None) or "").strip() or (s.ollama_instance_id or "").strip() or None
        med_model = (getattr(s, "ollama_med_model", "") or "").strip()
        key_to_server.append(("ominis-2.0-med", med_iid, "llm", "Ominis 2.0 Med", med_model, "Modelo clínico Med42-v2 (M42 Health)"))

    # Unique instance IDs that we have (exclude None)
    instance_ids = list(dict.fromkeys(iid for (_, iid, _, _, _, _) in key_to_server if iid))

    info_by_id: dict[str, dict] = {}
    if instance_ids:
        try:
            client = _get_ec2_client()
            resp = client.describe_instances(InstanceIds=instance_ids)
            types_seen: set[str] = set()
            for r in resp.get("Reservations", []):
                for inst in r.get("Instances", []):
                    iid = inst["InstanceId"]
                    itype = inst.get("InstanceType")
                    if itype:
                        types_seen.add(itype)
                    info_by_id[iid] = {
                        "state": inst["State"]["Name"],
                        "instanceType": itype,
                        "publicIp": (inst.get("PublicIpAddress") or "").strip() or None,
                        "vramGb": None,
                        "ramGb": None,
                    }
            type_specs = _fetch_instance_type_specs(list(types_seen))
            for iid, info in info_by_id.items():
                itype = info.get("instanceType")
                specs = (type_specs.get(itype) if itype else {}) or (INSTANCE_SPECS.get(itype, {}) if itype else {})
                info["vramGb"] = specs.get("vram_gb")
                info["ramGb"] = specs.get("ram_gb")
        except Exception as e:
            logger.warning("Failed to describe instances for server groups: %s", e)
            return {"servers": [], "error": str(e)[:200]}

    # Group by instance_id: server_id -> list of (key, key_type, label, modelBase, modelDescription)
    server_models: dict[str, list[tuple[str, str, str, str, str]]] = {}
    for key, iid, key_type, label, model_base, model_desc in key_to_server:
        if not iid:
            continue
        if iid not in server_models:
            server_models[iid] = []
        server_models[iid].append((key, key_type, label, model_base, model_desc))

    # Build response: one entry per server
    servers_out = []
    for iid in instance_ids:
        info = info_by_id.get(iid, {})
        models_list = server_models.get(iid, [])
        if not models_list:
            continue
        primary_key, primary_type, _, _, _ = models_list[0]
        models = [
            {"key": k, "label": lb, "modelBase": mb, "modelDescription": md}
            for k, _kt, lb, mb, md in models_list
        ]
        itype = info.get("instanceType")
        estimated_monthly_usd = INSTANCE_ESTIMATED_MONTHLY_USD.get(itype) if itype else None
        servers_out.append({
            "instanceId": iid,
            "instanceType": itype,
            "publicIp": info.get("publicIp"),
            "state": info.get("state") or "unknown",
            "vramGb": info.get("vramGb"),
            "ramGb": info.get("ramGb"),
            "estimatedMonthlyUsd": estimated_monthly_usd,
            "primaryKey": primary_key,
            "primaryKeyType": primary_type,
            "models": models,
        })

    return {"servers": servers_out}
