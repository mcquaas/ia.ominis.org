# OpenScholar 128K for Vast.ai — vLLM with 32K context (long-context research).
# Same model as EC2 deploy; use with: vastai create instance ... --image <this-image> --env '-p 8000:8000 --gpus all'
FROM vllm/vllm-openai:latest

# Default: serve OpenScholar with 32K context (alias 128K in product name).
ENV VLLM_MODEL="OpenSciLM/Llama-3.1_OpenScholar-8B"
ENV VLLM_SERVED_MODEL_NAME="openscholar"
ENV VLLM_MAX_MODEL_LEN="32768"

# Override entrypoint to pass model args (Vast can also pass --args)
ENTRYPOINT ["python3", "-m", "vllm.entrypoints.openai.api_server", \
  "--model", "OpenSciLM/Llama-3.1_OpenScholar-8B", \
  "--served-model-name", "openscholar", \
  "--host", "0.0.0.0", \
  "--port", "8000", \
  "--max-model-len", "32768", \
  "--gpu-memory-utilization", "0.9", \
  "--trust-remote-code"]
