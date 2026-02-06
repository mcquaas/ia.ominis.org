# Data Privacy & Residency

This document describes how data is handled, stored, and processed in the Ominis Health LLM system.

## Table of Contents

- [Overview](#overview)
- [Infrastructure](#infrastructure)
- [Data Classification](#data-classification)
- [Data Residency](#data-residency)
- [User Data Handling](#user-data-handling)
- [Authentication & API Keys](#authentication--api-keys)
- [Third-Party Services](#third-party-services)
- [Human Curation](#human-curation)
- [Security Measures](#security-measures)
- [Compliance](#compliance)

## Overview

Ominis Health LLM is designed with data sovereignty as a core principle:

- **All stored data remains in Mexico** (AWS mx-central-1, Querétaro datacenter)
- **No third-party AI models** — uses ominis-2.0 exclusively
- **User queries are not stored** — processed transiently
- **Human-curated sources** — verified by health specialists
- **FUNSALUD-managed infrastructure** — complete control over data flow

## Infrastructure

All infrastructure is owned and managed by Fundación Mexicana para la Salud A.C.:

| Component | Location | Purpose |
|-----------|----------|---------|
| S3 Storage | Mexico (Querétaro) | All data storage |
| PostgreSQL | Mexico (Querétaro) | Strapi user database |
| CPU Inference | Mexico (Querétaro) | Default LLM inference |
| GPU Inference | US (Virginia) | Optional fast inference |
| Frontend | Global (CDN) | Web delivery |

**Important**: Even when GPU inference runs in the US, the server is owned and managed by FUNSALUD. No data is shared with third-party AI providers.

## Data Classification

### Content Data (Health Sources)

| Category | Description | Location | Retention |
|----------|-------------|----------|-----------|
| Raw Content | WordPress/Tainacan/IMSS/ISSSTE | Mexico S3 | Indefinite |
| Processed Chunks | Chunked documents | Mexico S3 | Indefinite |
| Embeddings | Vector representations | Mexico S3 | Indefinite |
| FAISS Index | Searchable index | Mexico S3 | Indefinite |

### User Account Data

| Category | Description | Location | Retention |
|----------|-------------|----------|-----------|
| User profiles | Email, username | Mexico PostgreSQL | Until deletion |
| API keys | Hashed keys | Mexico PostgreSQL | Until revoked |
| Roles | Permission levels | Mexico PostgreSQL | Until deletion |

### Operational Data

| Category | Description | Location | Retention |
|----------|-------------|----------|-----------|
| CloudWatch Logs | API logs | Mexico | 30 days |
| Query Logs | Aggregated stats | Mexico PostgreSQL | 90 days |
| Access Logs | S3 access | Mexico | 90 days |

### User Query Data

| Category | Description | Stored? | Location |
|----------|-------------|---------|----------|
| Query text | Questions asked | **No** | N/A |
| Session history | Chat history | **No** | N/A |
| Response text | Generated answers | **No** | N/A |

## Data Residency

### Primary Data Location: Mexico (100%)

All persistent data is stored in AWS Mexico Region (mx-central-1):

```
AWS mx-central-1 (Querétaro, Mexico)
├── S3 Buckets
│   ├── ominis-health-raw-data-mx
│   ├── ominis-health-processed-data-mx
│   ├── ominis-health-embeddings-mx
│   └── ominis-health-models-mx
├── RDS PostgreSQL
│   └── ominis-strapi-db (users, API keys, sources)
├── EC2 Instances
│   ├── ominis-strapi (admin backend)
│   ├── ominis-frontend
│   └── ominis-ollama (CPU inference)
└── CloudWatch Logs
```

### Inference Options

#### Option 1: 100% Mexico (CPU)

All processing stays in Mexico:
- Response time: 5-10 seconds
- Complete data residency

#### Option 2: Hybrid (GPU in US)

For faster inference:
- Response time: 2-3 seconds
- Only query text travels to US (transient)
- No data stored in US
- Server managed by FUNSALUD

## User Data Handling

### Query Processing

```
┌─────────────────────────────────────────────────────────┐
│                   Query Lifecycle                        │
├─────────────────────────────────────────────────────────┤
│ 1. User submits question                                │
│ 2. Optional API key validation                          │
│ 3. Question processed in memory                         │
│ 4. Vector similarity search                             │
│ 5. ominis-2.0 generates response                        │
│ 6. Response returned to user                            │
│ 7. Query discarded (not stored)                         │
└─────────────────────────────────────────────────────────┘
```

### What We DON'T Collect

- ❌ Health records or medical history
- ❌ Query text or chat history
- ❌ Personal health information
- ❌ Tracking cookies or analytics

### What We DO Collect

For registered users only:
- ✓ Email address (for authentication)
- ✓ Username (for identification)
- ✓ Password hash (bcrypt, never plain text)
- ✓ API key usage counts (aggregated)

## Authentication & API Keys

### User Authentication

- **Method**: JWT tokens
- **Expiration**: 7 days (configurable)
- **Storage**: Token in localStorage (client-side)
- **Password**: bcrypt hashed with salt

### API Keys

| Aspect | Implementation |
|--------|----------------|
| Format | `ominis_` prefix + 64 char random |
| Storage | bcrypt hashed, only prefix stored |
| Display | Shown once on creation |
| Revocation | Immediate effect |
| Rate limits | Per-key configurable |

### Role-Based Access

| Role | Capabilities |
|------|-------------|
| Researcher | Use API, manage own keys |
| Admin | + View stats, manage sources |
| SuperAdmin | + Manage users and roles |

## Third-Party Services

### AI Models

| Provider | Usage |
|----------|-------|
| OpenAI | **Not used** |
| Google (Gemini) | **Not used** |
| Anthropic (Claude) | **Not used** |
| Meta (Llama) | **Not used** |
| AWS Bedrock | **Not used** |

**All inference via self-hosted ominis-2.0.**

### Search Services (Optional)

| Service | Usage | Data Sent |
|---------|-------|-----------|
| Web Search | Optional toggle | Query text only |
| PubMed | Optional toggle | Query text only |

Users can disable these via toggles in the chat interface.

### AWS Services

| Service | Region | Purpose |
|---------|--------|---------|
| S3 | mx-central-1 | Data storage |
| EC2 | mx-central-1 / us-east-1 | Compute |
| RDS | mx-central-1 | PostgreSQL |
| CloudFront | Global | CDN |

## Human Curation

All 1,400+ sources are curated by health specialists:

### Curation Process

1. **Identification**: Health experts identify sources
2. **Review**: Medical accuracy verification
3. **Categorization**: Proper metadata
4. **Quality Assurance**: Regular updates

### Source Types

| Type | Count |
|------|-------|
| IMSS Guidelines | 200+ |
| ISSSTE Guidelines | 100+ |
| Tainacan Collections | 400+ |
| Institutional Sources | 300+ |
| Educational Materials | 400+ |

## Security Measures

### Encryption

| Layer | Method |
|-------|--------|
| In Transit | TLS 1.2+ |
| At Rest | S3/RDS encryption (AES-256) |
| Passwords | bcrypt |
| API Keys | bcrypt |

### Access Control

| Control | Implementation |
|---------|----------------|
| Authentication | JWT tokens |
| Authorization | Role-based policies |
| API Access | API keys with permissions |
| Rate Limiting | Per-key limits |

### Monitoring

| System | Purpose |
|--------|---------|
| CloudWatch | Metrics and alerts |
| Status Watchdog | Health checks |
| Query Logs | Usage aggregation |

## Compliance

### Mexican Data Protection

The system is designed to comply with:

- **LFPDPPP** (Ley Federal de Protección de Datos Personales)
- **Aviso de Privacidad** requirements

### Healthcare Information

- Provides **general health information only**
- Not a substitute for medical advice
- Not designed for PHI storage

### User Rights

For registered users:
- **Access**: View profile via `/profile`
- **Correction**: Update profile information
- **Deletion**: Request account deletion

For anonymous users:
- No personal data collected
- Nothing to access, correct, or delete

## Summary

| Aspect | Status |
|--------|--------|
| Data Storage | 100% Mexico |
| Third-Party AI | None |
| User Queries | Not stored |
| Personal Data | Minimal (email, username) |
| Passwords | Hashed (bcrypt) |
| API Keys | Hashed, shown once |
| Human Curation | 1,400+ verified sources |

---

For technical details, see [ARCHITECTURE.md](ARCHITECTURE.md).
For API documentation, see [API_STRAPI.md](API_STRAPI.md).

**Contact**: ominis@funsalud.org.mx
