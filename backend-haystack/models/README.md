# LLM Models for Ominis Health

This directory contains Ollama Modelfiles for the LLM models used by the backend.

## Available Models

### 1. ominis-2.0 (BioMistral) — Default
- **Base**: BioMistral-7B (`cniongolo/biomistral`)
- **Parameters**: 7B
- **VRAM**: ~6GB (quantized)
- **Strength**: Medical/health domain specialization, Spanish language
- **Already deployed** on the existing Ollama instance

### 2. falcon-40b-instruct (Falcon) — New
- **Base**: Falcon-40B-Instruct by TII (Technology Innovation Institute)
- **Parameters**: 40B
- **VRAM**: ~24GB (Q4_K_M quantized) / ~80GB (FP16)
- **Strength**: Strong general reasoning, multilingual, instruction-following

## Setup

### Pull and create the Falcon model

```bash
# Option A: Pull the pre-built model from Ollama library
ollama pull falcon:40b-instruct

# Then create the customized version with our system prompt:
ollama create falcon-40b-instruct -f models/falcon-40b-instruct.Modelfile

# Option B: If falcon:40b-instruct is not in the Ollama library,
# use a quantized GGUF from HuggingFace:
# 1. Download: https://huggingface.co/TheBloke/falcon-40b-instruct-GGUF
# 2. Update the FROM line in the Modelfile to point to the .gguf file
# 3. Run: ollama create falcon-40b-instruct -f models/falcon-40b-instruct.Modelfile
```

### Verify both models are available

```bash
ollama list
# Should show both:
#   ominis-2.0        ...
#   falcon-40b-instruct  ...

# Quick test
ollama run ominis-2.0 "Hola, ¿qué es la diabetes?"
ollama run falcon-40b-instruct "Hola, ¿qué es la diabetes?"
```

## Adding new models

1. Create a Modelfile in this directory
2. Add the model to `MODEL_REGISTRY` in `app/config.py`
3. Restart the backend — the new pipeline is built automatically at startup
4. The frontend model selector picks up new models via `GET /v1/models`
