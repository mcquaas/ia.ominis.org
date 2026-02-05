# Ominis-2.0 Model Documentation

Technical specifications and architecture details for the Ominis-2.0 medical language model.

Released by [Fundación Mexicana para la Salud A.C.](https://funsalud.org.mx/) through [ai.ominis.org](https://ai.ominis.org)

## Table of Contents

- [Overview](#overview)
- [Model Architecture](#model-architecture)
- [Training Data](#training-data)
- [Model Specifications](#model-specifications)
- [Performance Characteristics](#performance-characteristics)
- [Deployment Configuration](#deployment-configuration)
- [Limitations](#limitations)

## Overview

Ominis-2.0 is a medical-focused large language model optimized for health information retrieval and question answering in Spanish. It is designed to provide accurate, sourced health information while maintaining 100% data residency in Mexico.

### Key Capabilities

- Medical terminology understanding
- Spanish language fluency
- Health education content generation
- Source-grounded responses
- Safe medical information guidance

## Model Architecture

### Base Architecture

Ominis-2.0 is built on a transformer-based architecture with the following characteristics:

| Specification | Value |
|---------------|-------|
| Architecture | Transformer (decoder-only) |
| Parameters | **7 billion** |
| Layers | 32 |
| Attention Heads | 32 |
| Hidden Dimension | 4,096 |
| Vocabulary Size | 32,000 tokens |
| Context Window | **32,768 tokens** |
| Precision | bfloat16 / float16 |

### Architectural Features

- **Grouped-Query Attention (GQA)**: Efficient attention mechanism with 8 key-value heads
- **Sliding Window Attention**: 4,096 token sliding window for efficient long-context processing
- **RoPE Embeddings**: Rotary Position Embeddings for position encoding
- **SiLU Activation**: Smooth activation function in feed-forward layers
- **RMSNorm**: Pre-normalization for training stability

### Model Hierarchy

```
┌─────────────────────────────────────────────────────────────────┐
│                        Ominis-2.0                                │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                  FUNSALUD Customization                    │  │
│  │  - Spanish system prompt                                  │  │
│  │  - Medical safety guidelines                              │  │
│  │  - Temperature optimization (0.3)                         │  │
│  └───────────────────────────────────────────────────────────┘  │
│                              ▲                                   │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │              Medical Domain Fine-tuning                    │  │
│  │  - PubMed Central corpus                                  │  │
│  │  - Medical terminology                                    │  │
│  │  - Clinical knowledge                                     │  │
│  └───────────────────────────────────────────────────────────┘  │
│                              ▲                                   │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │              Foundation Model (7B Transformer)             │  │
│  │  - General language understanding                         │  │
│  │  - Multilingual capabilities                              │  │
│  │  - Reasoning abilities                                    │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

## Training Data

### Medical Corpus Statistics

The medical domain knowledge was derived from extensive biomedical literature:

| Dataset | Documents | Tokens | Coverage |
|---------|-----------|--------|----------|
| PubMed Central Open Access | **~3,000,000** articles | ~14B tokens | Full-text biomedical |
| Medical Abstracts | ~30,000,000 | ~3B tokens | Research summaries |
| Clinical Guidelines | ~50,000 | ~500M tokens | Treatment protocols |

### Knowledge Domains

The model has been trained on content covering:

| Medical Domain | Coverage |
|----------------|----------|
| Internal Medicine | Comprehensive |
| Cardiology | Comprehensive |
| Endocrinology (Diabetes) | Comprehensive |
| Oncology | Comprehensive |
| Pediatrics | Comprehensive |
| Infectious Diseases | Comprehensive |
| Pharmacology | Comprehensive |
| Public Health | Comprehensive |
| Nutrition | Comprehensive |
| Mental Health | Moderate |

### Language Distribution

| Language | Percentage |
|----------|------------|
| English (medical literature) | 85% |
| Spanish | 10% |
| Other languages | 5% |

*Note: The model has strong Spanish generation capabilities through multilingual pre-training and prompt engineering.*

## Model Specifications

### Ominis-2.0 Configuration

```yaml
# Ominis-2.0 Modelfile
base_model: medical-7b-instruct
parameters:
  temperature: 0.3        # Lower for factual accuracy
  top_p: 0.9
  top_k: 40
  num_predict: 1024       # Max output tokens
  repeat_penalty: 1.1
  
system_prompt: |
  Eres un asistente médico especializado de Ominis Health, 
  respaldado por FUNSALUD. Tu objetivo es proporcionar 
  información de salud precisa y útil basada en fuentes 
  proporcionadas. Siempre responde en español y recomienda 
  consultar a un profesional médico cuando sea apropiado.
```

### Inference Requirements

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| RAM | 8 GB | 16 GB |
| VRAM (GPU) | N/A (CPU) | 8 GB |
| Storage | 5 GB | 10 GB |
| CPU | 8 cores | 16 cores |

### Supported Formats

| Format | Quantization | Size | Quality |
|--------|--------------|------|---------|
| Q4_K_M | 4-bit | ~4.1 GB | Good |
| Q5_K_M | 5-bit | ~4.8 GB | Better |
| Q6_K | 6-bit | ~5.5 GB | Best (CPU) |
| F16 | 16-bit | ~14 GB | Full |

## Performance Characteristics

### Response Quality

| Metric | Score | Benchmark |
|--------|-------|-----------|
| Medical QA Accuracy | 78% | MedQA |
| Spanish Fluency | 92% | Native evaluation |
| Source Attribution | 95% | RAG grounding |
| Safety Compliance | 98% | Medical safety |

### Latency (CPU Inference)

| Instance Type | Tokens/sec | First Token | Full Response |
|---------------|------------|-------------|---------------|
| c6i.xlarge (4 vCPU) | 8 t/s | 2s | 15s |
| c6i.2xlarge (8 vCPU) | 15 t/s | 1s | 8s |
| c6i.4xlarge (16 vCPU) | 25 t/s | 0.5s | 5s |

### Memory Usage

| Configuration | Idle | Peak (1K context) | Peak (8K context) |
|---------------|------|-------------------|-------------------|
| Q4_K_M | 4.5 GB | 5.5 GB | 8 GB |
| Q6_K | 6 GB | 7 GB | 10 GB |

## Deployment Configuration

### Production Settings (Ominis Health)

```bash
# Environment Variables
OLLAMA_MODEL=ominis-2.0
OLLAMA_HOST=0.0.0.0
OLLAMA_NUM_PARALLEL=4
OLLAMA_MAX_LOADED_MODELS=1

# Model Parameters (via Modelfile)
temperature=0.3    # Factual, consistent responses
num_predict=1024   # Adequate for medical explanations
num_ctx=4096       # Context for RAG chunks
```

### AWS Infrastructure

| Component | Specification | Region |
|-----------|---------------|--------|
| Instance | c6i.4xlarge | mx-central-1 |
| vCPUs | 16 | - |
| Memory | 32 GB | - |
| Storage | 100 GB gp3 | - |
| Network | Enhanced | VPC internal |

## Limitations

### Known Limitations

1. **Not a Medical Device**: Ominis-2.0 is an information system, not a diagnostic tool
2. **No Real-time Data**: Knowledge cutoff from training data
3. **Language Bias**: Primarily trained on English medical literature
4. **No Patient-Specific Advice**: Cannot provide personalized medical recommendations
5. **Hallucination Risk**: May occasionally generate plausible but incorrect information

### Safety Measures

The model includes built-in safety measures:

- **Disclaimer Generation**: Recommends professional consultation
- **Uncertainty Expression**: Acknowledges knowledge limits
- **Source Grounding**: RAG system reduces hallucinations
- **Temperature Control**: Lower temperature (0.3) for factual responses

### Use Case Restrictions

| Allowed | Not Allowed |
|---------|-------------|
| Health education | Medical diagnosis |
| General information | Treatment prescriptions |
| Wellness guidance | Emergency advice |
| Source-cited answers | Patient-specific care |

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| Ominis-2.0 | Feb 2026 | Initial release with FUNSALUD customization |

---

**Copyright 2026 Fundación Mexicana para la Salud A.C.**

Licensed under the Apache License, Version 2.0.
