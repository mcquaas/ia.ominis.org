# Arquitectura actual: qué está en uso y qué no

Este documento tiene diagramas para ver de un vistazo todos los componentes, en qué región viven y cuáles están en uso o son candidatos a eliminar.

---

## 1. Vista general (regiones e instancias)

```mermaid
flowchart TB
    subgraph users["👤 Usuarios"]
        U[ia.ominis.org / la.ominis.org / chat.ominis.org]
    end

    subgraph mx["🇲🇽 AWS mx-central-1 (México)"]
        FE["🟢 ominis-frontend-server<br/>t3.small · i-0efb1b3c28d64cdb5<br/><b>EN USO</b>"]
        BE["🟢 ominis-haystack-backend<br/>t3.large · i-04464c8355e364211<br/><b>EN USO</b>"]
        CHAT["🟢 ominis-chat-server<br/>t3.small · i-035b92e0a334cfc52<br/><b>EN USO</b>"]
        OLLAMA_T3["🟡 ominis-ollama-server<br/>t3.large · i-02264316b8b094bad<br/><b>REVISAR</b> · Sin GPU"]
    end

    subgraph us["🇺🇸 AWS us-east-1 (GPU)"]
        G5["🟢 ominis-falcon-gpu · g5.2xlarge<br/>i-00f7b0692c3219b46 · 18.235.182.22<br/><b>EN USO</b> · Ollama (OLLAMA_URL)"]
        G4["🟡 ominis-ollama-gpu · g4dn.xlarge<br/>i-067dd350739288262<br/><b>OPCIONAL</b> · Reserva"]
        OS8["🔴 ominis-openscholar · g5.2xlarge<br/>i-0bf5937dec0d1298f · 44.217.135.115<br/><b>CANDIDATO A QUITAR</b> · OpenScholar 8K"]
    end

    subgraph vast["☁️ Vast.ai"]
        M42["🟢 Med42 (A100)<br/>50.217.254.161:41474 → 8080<br/><b>EN USO</b> · Clinical Translator"]
        OS128["🟡 OpenScholar 128K<br/><b>POR DESPLEGAR</b> · 24e + 20a"]
        QVL["⚪ Qwen2.5-VL<br/><b>OPCIONAL</b>"]
        EMB["⚪ Embeddings (bge)<br/><b>OPCIONAL</b>"]
    end

    subgraph data["📦 Datos (mx-central-1)"]
        PG[(PostgreSQL + pgvector)]
        S3[(S3)]
    end

    U --> FE
    U --> CHAT
    FE --> BE
    CHAT --> BE
    BE --> G5
    BE --> G4
    BE --> OS8
    BE --> M42
    BE --> OS128
    BE --> QVL
    BE --> EMB
    BE --> PG
    BE --> S3
    BE -.-> OLLAMA_T3
```

**Leyenda**
- **🟢 EN USO** — Imprescindible hoy.
- **🟡 REVISAR / OPCIONAL** — Confirmar si se usa; si no, se puede apagar.
- **🔴 CANDIDATO A QUITAR** — Se puede eliminar cuando el reemplazo en Vast esté estable.
- **⚪ OPCIONAL** — Pensado para más adelante (fase experimental).

---

## 2. Flujo de inferencia: qué modelo usa cada ruta

```mermaid
flowchart LR
    subgraph frontend["Frontend"]
        UI[Chat / Modo Investigación]
    end

    subgraph backend["Haystack Backend"]
        RAG[RAG + Agentes]
    end

    subgraph chat["Chat normal"]
        OLLAMA["Ollama (g5)<br/>Qwen, BioMistral, MinicPM-V, Qwen3"]
    end

    subgraph research["Modo Investigación"]
        QWEN_AG["Qwen (g5)<br/>Evidence Extractor · Bias Auditor"]
        OS128K["OpenScholar 128K<br/>Vast o EC2"]
        MED42["Med42<br/>Vast"]
    end

    subgraph vision["Visión (imagen)"]
        V_OLLAMA[MinicPM-V · Ollama g5]
        V_QVL[Qwen2.5-VL · Vast]
    end

    UI --> RAG
    RAG --> OLLAMA
    RAG --> QWEN_AG
    RAG --> OS128K
    RAG --> MED42
    RAG --> V_OLLAMA
    RAG --> V_QVL
```

| Ruta | Origen actual | En uso / Candidato |
|------|----------------|--------------------|
| Chat (Ominis 2.0, Med, Clinic, Open, Power) | Ollama g5 / vLLM EC2 | g5 **en uso** |
| Modo Investigación (síntesis) | OpenScholar 8K (EC2) o 128K (Vast) | 8K EC2 **candidato a quitar** si 128K en Vast |
| Clinical Translator (tras reporte) | Med42 Vast | **En uso** (configurar `MED42_API_URL`) |
| Evidence Extractor / Bias Auditor | Qwen en g5 | **En uso** |
| Análisis de imagen | MinicPM-V (g5) o Qwen2.5-VL (Vast) | g5 **en uso**; Qwen-VL **opcional** |
| Embeddings (RAG) | In-process (SentenceTransformers) o bge Vast | In-process **en uso**; bge **opcional** |

---

## 3. Tabla resumen: instancias y decisión

| Instancia | Región | Tipo | Rol | Decisión |
|-----------|--------|------|-----|----------|
| ominis-frontend-server | mx-central-1 | t3.small | UI | **Mantener** |
| ominis-haystack-backend | mx-central-1 | t3.large | API RAG/agentes | **Mantener** |
| ominis-chat-server | mx-central-1 | t3.small | Chat | **Mantener** |
| ominis-ollama-server | mx-central-1 | t3.large | Sin GPU | **Revisar** → candidata a quitar |
| ominis-falcon-gpu | us-east-1 | g5.2xlarge | Ollama (OLLAMA_URL) | **Mantener** (chat + visión) |
| ominis-ollama-gpu | us-east-1 | g4dn.xlarge | Ollama reserva | **Opcional** → quitar si no se usa |
| ominis-openscholar | us-east-1 | g5.2xlarge | OpenScholar 8K | **Quitar** cuando 128K en Vast esté estable |
| Med42 | Vast.ai | A100 | Clinical Translator | **En uso** |
| OpenScholar 128K | Vast.ai | A100 | Modo Investigación largo | **Desplegar** (24e + 20a) |

---

## 4. Cómo ver los diagramas Mermaid

- **GitHub**: al abrir este `.md` en el repo, GitHub renderiza los bloques `mermaid`.
- **VS Code / Cursor**: extensión "Mermaid" o vista previa con Mermaid.
- **Online**: copiar el bloque de código en [mermaid.live](https://mermaid.live) y ver/exportar el diagrama.

Si quieres, el siguiente paso puede ser dejar este doc como referencia única y enlazarlo desde `ARCHITECTURE.md` y `VAST_DEPLOY_AND_EC2_CLEANUP.md`.
