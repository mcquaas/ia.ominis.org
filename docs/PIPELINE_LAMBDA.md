# Pipeline con Lambda (auto-escalado por fuentes)

Permite que la ingesta escale con el número de fuentes: más fuentes → más invocaciones Lambda en paralelo, sin mantener un servidor siempre encendido.

## Límites de Lambda a tener en cuenta

| Límite | Valor | Impacto en el pipeline |
|--------|--------|-------------------------|
| Timeout | **15 min** máximo | Cada fase debe terminar en &lt; 15 min. |
| Memoria | 10 GB máximo | sentence-transformers cabe; batches grandes de embedding pueden necesitar 2–4 GB. |
| Payload (síncrono) | 6 MB | No pasar miles de chunks en el evento; usar S3. |
| Paquete (zip) | 250 MB descomprimido | sentence-transformers + torch suelen pasar; usar **imagen de contenedor** (hasta 10 GB) para la Lambda de embedding. |

## Arquitectura propuesta

```
[EventBridge / cron]
        │
        ▼
[Step 1: Lista de fuentes]  →  pubmed, url_list (N URLs), etc.
        │
        ▼
[Step 2: Map por fuente]    →  Lambda "ingest-one-source" por cada fuente (paralelo)
        │                         Event: { "source": "pubmed" } o { "source": "url_list", "urls": [...] }
        │                         Escribe: S3 raw_docs/YYYY-MM-DD/source_id.json
        ▼
[Step 3: Normalize + Chunk]  →  Lambda(es) leen S3, normalizan, chunkean, escriben S3 chunks/
        │                         Puede ser una Lambda por fuente o una que procese varios archivos.
        ▼
[Step 4: Map por batch de chunks]  →  Lambda "embed-batch" por cada lote de ~50–100 chunks (paralelo)
        │                         Event: { "s3_chunks_key": "chunks/xxx/batch_001.json" }
        │                         Escribe: S3 embeddings/xxx/batch_001.json
        ▼
[Step 5: Index / Merge]     →  Una Lambda o un job (Fargate/Batch) que:
                               - Lee todos los embeddings desde S3
                               - Construye FAISS, escribe health_chunks en PG, sube FAISS a S3, indexa OpenSearch
                               - Puede superar 15 min → mejor Fargate o Lambda con varias invocaciones “merge parcial” + una final.
```

**Auto-escalado:**

- **Más fuentes:** Step 2 es un Map sobre la lista de fuentes → una Lambda por fuente. Aumentar fuentes aumenta invocaciones en paralelo (respetando límites de concurrencia).
- **Más chunks:** Step 4 es un Map sobre batches de chunks → más chunks implica más Lambdas de embedding en paralelo.

## Opciones de despliegue

### A) Solo ingest en Lambda (recomendado para empezar)

- **Lambda “ingest-one-source”**: una por fuente (pubmed, url_list con N URLs). Escribe documentos crudos en S3.
- **Worker EC2 o Fargate** (cron o disparado por S3): lee desde S3, normaliza, chunkea, embebe, indexa (como hoy). Así se valida el flujo y se escala la parte más variable (fuentes) con Lambda.

### B) Ingest + Embed en Lambda; merge en un job

- Ingest: Lambda por fuente → S3.
- Normalize+Chunk: Lambda(es) que lean S3 y escriban chunks en S3 (o en RDS si se prefiere).
- Embed: Lambda **con imagen de contenedor** (sentence-transformers), una invocación por batch de chunks (p. ej. 64), evento con clave S3 del batch. Salida: embeddings en S3.
- Index/Merge: **Fargate** o **AWS Batch** (o una Lambda que solo haga merge si los datos caben en 15 min): lee embeddings de S3, construye FAISS, escribe PG/OpenSearch, sube FAISS a S3.

### C) Todo en Step Functions + Lambda (con restricción de tiempo)

- Cada fase en Lambda &lt; 15 min.
- La fase “index” (merge FAISS + PG + OpenSearch) puede partirse en “merge parcial” (varios Lambdas que generan índices parciales en S3) y una Lambda final que hace el merge definitivo y escribe PG/OpenSearch/S3, o delegar el merge final a Fargate/Batch.

## Código de referencia en el repo

- **`lambda/pipeline/ingest/handler.py`**: Lambda “ingest-one-source”. Evento: `{"source": "pubmed"}` o `{"source": "url_list", "urls": [...]}`. Escribe en S3 y devuelve manifest (bucket, key, doc_count).
- **`lambda/pipeline/embed_batch/handler.py`**: Lambda “embed-batch”. Evento: `{"s3_bucket", "s3_key"}` de un JSON con lista de chunks. Carga el modelo, embebe, escribe resultado en S3. Desplegar con **imagen de contenedor** (`lambda/pipeline/embed_batch/Dockerfile`).

La orquestación (Step Functions Map por fuente / por batch) y la fase de merge/index (FAISS + PG + OpenSearch) se pueden añadir después usando estos handlers como contrato.

## Cuándo usar Lambda vs worker EC2

| Criterio | Lambda | EC2 worker |
|----------|--------|------------|
| Coste con pocas ejecuciones | Bajo (pago por invocación) | Fijo por horas encendido |
| Auto-escalar por fuentes/chunks | Sí (Map por fuente/batch) | No (un proceso secuencial) |
| Tiempo máximo por paso | 15 min | Sin límite |
| Complejidad operativa | Step Functions + permisos IAM | Un servidor + cron |
| Embedding (modelo grande) | Imagen de contenedor o Layer grande | Venv en el servidor |

Recomendación: empezar con **ingest en Lambda** (escalado por fuentes) y el resto en el worker actual; después mover **embed** a Lambda por batches si se necesita más paralelismo.

## Desplegar ingest Lambda (prueba rápida)

1. Empaquetar: `cd lambda/pipeline/ingest && pip install -r requirements.txt -t . && zip -r ../ingest.zip .`
2. Crear función Lambda (runtime Python 3.12), subir `ingest.zip`, timeout 5 min, memoria 512 MB.
3. Variables de entorno: `PIPELINE_RAW_BUCKET` (o `HEALTH_FAISS_S3_BUCKET`), opcional `PIPELINE_RAW_PREFIX`.
4. Invocar con evento de prueba: `{"source": "url_list", "urls": ["https://www.gob.mx/salud"]}` → debe escribir en S3 y devolver `bucket`, `key`, `doc_count`.

**Despliegue con script (recomendado):**

```bash
./infrastructure/29i-deploy-pipeline-ingest-lambda.sh
```

Esto crea/actualiza la función `ominis-ingestion` (o `LAMBDA_FUNCTION_INGESTION`), timeout 5 min, escribe en `PIPELINE_RAW_BUCKET`/`pipeline/raw_docs`.

**Iniciar ingesta con Lambdas y luego pipeline:**

1. Invocar Lambdas (una por fuente: pubmed, url_list) para que escriban documentos crudos en S3.
2. En el worker (o backend) ejecutar el pipeline en modo **--from-s3** para leer esos JSON de S3, normalizar, chunquear, embeber e indexar (FAISS + OpenSearch + PostgreSQL).

```bash
./infrastructure/29j-trigger-lambda-ingest-and-pipeline.sh
```

Ese script: invoca las dos Lambdas (pubmed + url_list con URLs mexicanas), luego hace SSH al worker (si existe `config/pipeline_worker.txt`) o al backend y ejecuta `python -m pipeline.nightly_pipeline --from-s3`. Si no hay worker ni backend configurado, imprime las órdenes para ejecutar `--from-s3` a mano.

**Pipeline --from-s3:** El pipeline acepta `--from-s3`: lista todos los JSON bajo `s3://PIPELINE_RAW_BUCKET/PIPELINE_RAW_PREFIX/`, los carga, calcula `content_hash` si falta (para dedup), y sigue con normalize → chunk → embed → index. Así la ingesta escala con Lambdas (más fuentes = más invocaciones) y el worker solo hace el trabajo pesado de embedding e indexación.
