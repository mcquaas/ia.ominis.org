# LLM GPU Infrastructure (AWS)

Summary of EC2 instances used for Ollama (Ominis 2.0, Ominis 2.0 Clinic, and optional Ominis 2.0 Open).

## Instances (us-east-1)

| Purpose | Instance ID | Type | GPU / VRAM | Public IP | Config / Key |
|--------|-------------|------|------------|-----------|--------------|
| **Ollama g4dn** (Qwen + BioMistral) | i-067dd350739288262 | **g4dn.xlarge** | T4 **16 GB** | 3.213.91.241 | `config/ollama_gpu_server.txt`, key: `ominis-ollama-gpu-key.pem` |
| **Falcon / repurposed Ollama** | i-00f7b0692c3219b46 | **g5.2xlarge** | A10G **24 GB** | 18.235.182.22 | `config/falcon_gpu_server.txt`, key: `ominis-falcon-gpu-key.pem` |

- **g4dn.xlarge**: 16 GB VRAM — fits Qwen 2.5 14B, BioMistral 7B, Qwen 3 14B. Dashboard start/stop (20e) uses this instance ID.
- **g5.2xlarge**: 24 GB VRAM — fits the above plus larger models; production may use this as `OLLAMA_URL` (see dashboard “Estado real de cada servidor Ollama”).

Which host the backend uses is set by `OLLAMA_URL` in the backend `.env` (on the Haystack server). Install new models (e.g. for Ominis 2.0 Open) on **that** host.

**Production (as of 2026-02):** Backend `OLLAMA_URL` points to **g5** (18.235.182.22). On that host we have: `qwen2.5:14b`, `ominis-2.0:latest`, `minicpm-v:latest`, `qwen3:14b` (Ominis 2.0 Open), and `cniongolo/biomistral:latest` (Ominis 2.0 Clinic). Set `OLLAMA_CLINIC_MODEL=cniongolo/biomistral` in backend .env (run `./infrastructure/20l-update-backend-env-clinic-model.sh`).

## Can we run Qwen 3.5?

- **qwen3.5:cloud** / **qwen3.5:397b-cloud**: Very large (397B params); not suitable for 16–24 GB VRAM. Use only if Ollama offers smaller variants later (e.g. qwen3.5:14b).
- **qwen3:14b**: Fits on both g4dn (16 GB) and g5.2xlarge (24 GB). Recommended for **Ominis 2.0 Open** today.

## Commands (AWS CLI)

```bash
# Describe g4dn (Ollama)
aws ec2 describe-instances --instance-ids i-067dd350739288262 --region us-east-1 --query 'Reservations[*].Instances[*].[InstanceType,State.Name,PublicIpAddress]' --output table

# Describe g5 (Falcon / Ollama)
aws ec2 describe-instances --instance-ids i-00f7b0692c3219b46 --region us-east-1 --query 'Reservations[*].Instances[*].[InstanceType,State.Name,PublicIpAddress]' --output table
```

## Install Ominis 2.0 Open

1. SSH to the Ollama server that matches your backend `OLLAMA_URL` (e.g. 3.213.91.241 or 18.235.182.22).
2. Run: `ollama pull qwen3:14b` (and `ollama list` to confirm).
3. On the backend server, set `OLLAMA_OPEN_MODEL=qwen3:14b` in `.env` and restart (or run `./infrastructure/20k-update-backend-env-open-model.sh`).
