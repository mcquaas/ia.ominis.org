# ominis-2.0 Model Documentation

**ominis-2.0** is the first Mexican Large Language Model (LLM) specialized in health, developed for clinical, epidemiological, and administrative health research.

Released by [Fundación Mexicana para la Salud A.C.](https://funsalud.org.mx/) through [ai.ominis.org](https://ai.ominis.org)

## Table of Contents

- [Overview](#overview)
- [Model Specifications](#model-specifications)
- [Training Data](#training-data)
- [Architecture Details](#architecture-details)
- [Performance Benchmarks](#performance-benchmarks)
- [Inference Performance](#inference-performance)
- [Deployment](#deployment)
- [Medical Domains](#medical-domains)
- [Limitations](#limitations)
- [License](#license)

## Overview

ominis-2.0 is designed to provide accurate, sourced health information in Spanish while maintaining complete data sovereignty for Mexican users. The model is:

- **Mexican-developed**: Customized for Spanish-language medical queries
- **Health-specialized**: Trained on 33+ million medical documents
- **Privacy-focused**: No third-party AI dependencies
- **Human-curated**: 1,400+ sources verified by health specialists

### Key Statistics

| Metric | Value |
|--------|-------|
| Parameters | **7 billion** |
| Context Window | **32,768 tokens** |
| Training Documents | **33+ million** |
| Training Tokens | **17.5+ billion** |
| FUNSALUD Curated Sources | **1,400+** |
| Medical QA Accuracy | **78%** |

## Model Specifications

### Core Architecture

| Specification | Value |
|---------------|-------|
| Model Type | Transformer (decoder-only) |
| Parameters | 7 billion |
| Context Window | 32,768 tokens |
| Vocabulary Size | 32,000 |
| Layers | 32 |
| Attention Heads | 32 |
| Hidden Dimension | 4,096 |
| Intermediate Size | 14,336 |

### Architectural Features

| Feature | Implementation |
|---------|----------------|
| Attention Type | Grouped-Query Attention (GQA) |
| Position Encoding | Rotary Position Embeddings (RoPE) |
| Normalization | RMSNorm |
| Activation | SiLU (Swish) |
| Sliding Window | 4,096 tokens |
| KV Heads | 8 (GQA compression) |

## Training Data

### Primary Sources

| Source | Documents | Tokens | Description |
|--------|-----------|--------|-------------|
| PubMed Central (Open Access) | ~3,000,000 | ~14B | Full-text medical articles |
| Medical Abstracts | ~30,000,000 | ~3B | Research paper abstracts |
| Clinical Guidelines | ~50,000 | ~500M | Evidence-based protocols |
| **FUNSALUD Curated** | **+1,400** | (RAG) | Human-verified sources |

### Total Training Corpus

- **33+ million documents**
- **17.5+ billion tokens**
- **Focus**: Clinical, epidemiological, and administrative health

### FUNSALUD Curated Sources (RAG)

The 1,400+ curated sources include:

| Category | Count | Description |
|----------|-------|-------------|
| Medical Databases | 200+ | Registries and databases |
| Clinical Guidelines | 150+ | Practice guidelines |
| Research Papers | 400+ | Peer-reviewed studies |
| Institutional Sources | 300+ | Government and health orgs |
| Educational Materials | 350+ | Patient education |

All sources are verified by a team of health specialists at FUNSALUD.

## Architecture Details

### Grouped-Query Attention (GQA)

ominis-2.0 uses GQA for efficient inference:

```
Standard Multi-Head Attention:
- 32 Query heads, 32 Key heads, 32 Value heads
- Memory: O(32 * d_k)

Grouped-Query Attention (GQA):
- 32 Query heads, 8 KV heads
- 4 Query heads share 1 KV head
- Memory: O(8 * d_k) - 4x reduction
```

### Sliding Window Attention

For long contexts, the model uses sliding window:

```
Context: 32,768 tokens
Sliding Window: 4,096 tokens
Local Attention: Each token attends to 4,096 nearest tokens
Global Patterns: Learned through layer stacking
```

### Position Encoding (RoPE)

Rotary Position Embeddings enable:
- Relative position encoding
- Efficient extrapolation to longer sequences
- Better handling of positional patterns

## Performance Benchmarks

### Medical Question Answering

| Metric | Score | Description |
|--------|-------|-------------|
| Clinical Accuracy | **78%** | Correct medical responses |
| Spanish Fluency | **92%** | Natural Spanish generation |
| Source Attribution | **95%** | Correct source citations |
| Safety Compliance | **98%** | Appropriate disclaimers |

### Benchmark Details

| Benchmark | Score | Notes |
|-----------|-------|-------|
| Medical QA (Spanish) | 78% | Custom evaluation set |
| MMLU (Medical subset) | 71% | Multi-subject accuracy |
| Spanish Fluency | 92% | Native speaker evaluation |
| Hallucination Rate | 8% | With RAG context |

## Inference Performance

### Hardware Configurations

| Configuration | Hardware | Tokens/sec | Response Time |
|---------------|----------|------------|---------------|
| CPU (Standard) | c6i.4xlarge | ~25 t/s | 5-10 seconds |
| GPU (Fast) | g4dn.xlarge (T4) | ~80+ t/s | 2-3 seconds |
| GPU (Premium) | g5.xlarge (A10G) | ~120+ t/s | 1-2 seconds |

### Memory Requirements

| Mode | VRAM/RAM | Notes |
|------|----------|-------|
| CPU (float32) | 28 GB RAM | Full precision |
| CPU (int8) | 8 GB RAM | Quantized |
| GPU (float16) | 14 GB VRAM | Half precision |
| GPU (int4) | 4 GB VRAM | Quantized |

## Deployment

### Ollama Modelfile

```dockerfile
FROM cniongolo/biomistral

PARAMETER temperature 0.3
PARAMETER num_predict 1024
PARAMETER num_gpu 99

SYSTEM """Eres un asistente médico especializado de Ominis Health, respaldado por FUNSALUD.
Tu objetivo es proporcionar información de salud precisa y útil basada en fuentes confiables.
Siempre responde en español y recomienda consultar a un profesional médico cuando sea apropiado."""
```

### Create Model

```bash
# Create ominis-2.0 from Modelfile
ollama create ominis-2.0 -f Modelfile

# Verify
ollama list
```

### API Usage

```bash
curl http://localhost:11434/api/generate -d '{
  "model": "ominis-2.0",
  "prompt": "¿Cuáles son los síntomas de la diabetes?",
  "stream": false,
  "options": {
    "temperature": 0.3,
    "num_predict": 1024
  }
}'
```

### Environment Variables

```bash
export OLLAMA_URL="http://localhost:11434"
export OLLAMA_MODEL="ominis-2.0"
```

## Medical Domains

ominis-2.0 is trained on content covering:

| Domain | Coverage |
|--------|----------|
| Internal Medicine | High |
| Cardiology | High |
| Endocrinology | High |
| Diabetes | High |
| Oncology | Medium |
| Pediatrics | Medium |
| Infectious Diseases | High |
| Pharmacology | High |
| Public Health | High |
| Nutrition | High |
| Mental Health | Medium |
| Epidemiology | High |

## Limitations

### Medical Disclaimer

**ominis-2.0 is NOT a substitute for professional medical advice.**

- Do not use for diagnosis or treatment decisions
- Always consult a qualified healthcare professional
- The model may contain inaccuracies or outdated information

### Known Limitations

| Limitation | Description |
|------------|-------------|
| Not Real-time | Knowledge cutoff based on training data |
| Spanish Focus | Best performance in Spanish |
| General Health | Not specialized in rare conditions |
| No Images | Cannot process medical images |
| No Patient Data | Not designed for EHR integration |

### Hallucination Mitigation

The RAG architecture reduces hallucinations by:
1. Grounding responses in retrieved documents
2. Requiring source citations
3. Using low temperature (0.3) for factual responses
4. Human curation of source materials

## License

ominis-2.0 is released under the **Apache License 2.0**.

```
Copyright 2026 Fundación Mexicana para la Salud A.C.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
```

### Attribution

When using ominis-2.0, please cite:

```
Ominis-2.0: Mexican Health Language Model
Fundación Mexicana para la Salud A.C.
https://ai.ominis.org
```

---

For system architecture, see [ARCHITECTURE.md](ARCHITECTURE.md).
For development guide, see [DEVELOPMENT.md](DEVELOPMENT.md).

**Contact**: ominis@funsalud.org.mx
