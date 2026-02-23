# Vast.ai Deployments & EC2 Cleanup

## 1. Med42 (ya en Vast) — Solo configurar backend

Med42 ya está desplegado en Vast. Con la info de **IP & Port Info** (ej. internal **8080** → external **41474** en **50.217.254.161**):

1. **Configurar backend** para que el paso "Clinical Translator" en Modo Investigación use Med42:
   ```bash
   ./infrastructure/20b-vast-update-backend-env-med42.sh http://50.217.254.161:41474
   ```
   O crea `config/med42_vast.txt` con:
   ```bash
   MED42_API_URL=http://50.217.254.161:41474
   ```
   y ejecuta:
   ```bash
   ./infrastructure/20b-vast-update-backend-env-med42.sh
   ```

2. El backend añade `/v1` si hace falta; el endpoint debe ser OpenAI-compatible (`/v1/chat/completions`).

---

## 2. Qué montar después en Vast

| Orden | Servicio | Script / Acción | Puerto interno | Uso |
|-------|----------|------------------|----------------|-----|
| 1 | **OpenScholar 128K** | `./infrastructure/24e-vast-ai-create-openscholar-128k.sh` | **8000** | Modo Investigación (síntesis larga). Luego: IP & Port Info → mapping **8000/tcp** → `OPENSCHOLAR_128K_API_URL` y `./infrastructure/20a-vast-update-backend-env-openscholar-128k.sh` |
| 2 | **Ollama Qwen3 + Qwen2.5-VL** | `./infrastructure/24f-vast-ai-create-ollama-qwen-vl.sh` | **11434** | Chat general (Qwen3) + visión (Qwen2.5-VL). Luego: pull models, `config/ollama_qwen_vast.txt`, `./infrastructure/20c-vast-update-backend-env-ollama-qwen-vl.sh`. Ver [VAST_OLLAMA_QWEN_VL.md](VAST_OLLAMA_QWEN_VL.md). |
| 3 (opcional) | **Embeddings (bge)** | Microservicio en Vast (RTX 4090/L4), endpoint `/embed` con `{"texts": [...]}` → `{"embeddings": [...]}` | 8080 u otro | Backend: `EMBEDDING_SERVICE_URL=http://IP:PORT` |

**Resumen:** Con Med42 ya en Vast, los siguientes pasos recomendados son **OpenScholar 128K** (24e + 20a) y **Ollama Qwen3 + Qwen2.5-VL** (24f + 20c). Embeddings es opcional para la fase experimental.

---

## 3. EC2 que se pueden eliminar (una vez Vast estable)

Después de **validar** que Med42 y OpenScholar 128K en Vast responden bien:

| EC2 (Instance ID) | Config | Uso actual | Acción |
|-------------------|--------|------------|--------|
| **i-0bf5937dec0d1298f** | `config/openscholar_server.txt` | OpenScholar **8K** (g5.2xlarge), Modo Investigación corto | **Apagar / terminar** si solo usas OpenScholar **128K** en Vast. |
| **i-0c44f34ab8b001d5a** | `config/openscholar_128k_server.txt` | OpenScholar **128K** en EC2 | **Apagar / terminar** cuando OpenScholar 128K en Vast (24e) esté en uso y estable. |

**No eliminar (aún):**

| EC2 | Uso | Motivo |
|-----|-----|--------|
| **i-00f7b0692c3219b46** (g5.2xlarge) | Ollama: Qwen, BioMistral, MinicPM-V, Qwen3 | Backend usa este como `OLLAMA_URL` para chat y visión. **Se puede apagar** cuando Ollama Qwen+VL en Vast (24f + 20c) esté en uso. |
| **i-067dd350739288262** (g4dn) | Ollama alternativo (g4dn) | Reserva / otro modelo; ver dashboard "Estado real de cada servidor Ollama". |
| **i-04464c8355e364211** | Haystack backend | Servidor de la API. |
| **i-0efb1b3c28d64cdb5** | Frontend | App web. |
| **i-035b92e0a334cfc52** | Chat | Si usas chat.ominis.org. |
| **i-02122ca56de796e2e** | XMLA proxy | SINBA/OLAP. |

**Resumen EC2 a eliminar (cuando Vast esté validado):**

1. **OpenScholar 8K** (i-0bf5937dec0d1298f) — si solo usas 128K en Vast.  
2. **OpenScholar 128K en EC2** (i-0c44f34ab8b001d5a) — cuando 24e + 20a en Vast estén en producción.

Antes de terminar instancias: hacer snapshot o backup si lo necesitas, y quitar cualquier referencia en scripts/dashboard (start/stop por instance ID) para esas instancias.
