# Agregar más documentos al pipeline RAG

El backend usa **RDS** y **pgvector**; los documentos ya migrados están en la base. Para **juntar más documentos** no hace falta reindexar lo existente; solo agregar fuentes nuevas por cualquiera de estas vías.

## Resumen rápido

| Método | Dónde | Uso típico |
|--------|--------|-------------|
| **Subir archivo** | Dashboard o API | PDF, DOCX, TXT, HTML, CSV, XLS/XLSX, SAV (SPSS) |
| **URL directa** | Dashboard o API | Una página o PDF por URL |
| **Scrape + index** | Dashboard o API | Una URL: se buscan PDFs/CSV/XLS en la página y se indexan |
| **Dataset (CSV/Excel)** | Dashboard o API | Tabla con columnas: título, URL o contenido, categoría, etc. |
| **Tainacan** | Dashboard o API | Importar colección 97 de Tainacan (ominis.org) |

Formatos aceptados para **upload**: `.pdf`, `.docx`, `.txt`, `.html`, `.htm`, `.csv`, `.xlsx`, `.xls`, `.sav`. Máximo **50 MB** por archivo.

---

## 1. Desde el dashboard (recomendado)

1. Entra al **dashboard** (admin) con usuario admin/developer.
2. **Fuentes RAG** → "Nueva fuente" o "Subir archivo".
3. **Subir archivo**: elige el archivo, título, categoría e idioma → se indexa en segundo plano.
4. **Por URL**: crea una fuente con "URL de la fuente" y opcionalmente contenido; se indexa desde la URL.
5. **Scrape**: en la opción de scrape, pega la URL de una página; el sistema lista PDFs/CSV/XLS y puedes elegir cuáles indexar.
6. **Dataset**: pega o sube CSV/Excel con columnas (título, URL o contenido, categoría…) y se crean fuentes e indexación en lote.
7. **Tainacan**: importar desde colección 97; se crean fuentes y se indexan en segundo plano.

Todo lo que agregues se escribe en **RDS** (pgvector) automáticamente.

---

## 2. Por API (con token admin/developer)

Base URL del backend: `https://api.ominis.org` (o `http://78.12.33.205:8000` si pruebas directo). Incluye el header:

```
Authorization: Bearer <JWT>
```

### Subir un archivo

```bash
curl -X POST "https://api.ominis.org/v1/api/rag-sources/upload" \
  -H "Authorization: Bearer YOUR_JWT" \
  -F "file=@/ruta/al/documento.pdf" \
  -F "title=Mi documento" \
  -F "category=Protocolos" \
  -F "language=es"
```

### Crear fuente con URL (para indexar una sola URL)

```bash
curl -X POST "https://api.ominis.org/v1/api/rag-sources" \
  -H "Authorization: Bearer YOUR_JWT" \
  -H "Content-Type: application/json" \
  -d '{"title": "Título", "sourceUrl": "https://ejemplo.gob.mx/documento.pdf", "category": "Normatividad", "language": "es"}'
```

### Scrape + index (PDFs/CSV/XLS en una página)

```bash
curl -X POST "https://api.ominis.org/v1/api/rag-sources/scrape-index" \
  -H "Authorization: Bearer YOUR_JWT" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://ejemplo.gob.mx/recursos", "category": "Datos", "language": "es"}'
```

### Importar desde Tainacan (colección 97)

```bash
curl -X POST "https://api.ominis.org/v1/api/rag-sources/tainacan-import" \
  -H "Authorization: Bearer YOUR_JWT" \
  -H "Content-Type: application/json" \
  -d '{"skipExisting": true, "category": "tainacan", "language": "es"}'
```

### Batch reindex (solo si quieres refrescar fuentes ya existentes)

Para propagar taxonomía o reindexar fuentes que fallaron o quedaron "stuck":

```bash
curl -X POST "https://api.ominis.org/v1/api/rag-sources/batch-reindex" \
  -H "Authorization: Bearer YOUR_JWT" \
  -H "Content-Type: application/json" \
  -d '{"onlyWithTaxonomy": false}'
```

---

## 3. Scripts locales (`scripts/ingestion/`)

Hay scripts que descargan o preparan datos (p. ej. Tainacan a S3, fuentes mexicanas). El backend actual **no lee S3 para RAG**; el pipeline de documentos es: API → backend → pgvector en RDS.

Para juntar más documentos usa el **dashboard** o la **API** (upload, scrape-index, tainacan-import, dataset-index). El endpoint **tainacan-import** ya trae la colección 97 y indexa contra RDS.

---

## 4. Límites y Nginx

- **Tamaño máximo de subida**: 50 MB. Si Nginx devuelve 413, en el servidor backend configura `client_max_body_size 50M` (ver `infrastructure/20g-backend-nginx-upload-size.sh`).
- **CORS**: `ALLOWED_ORIGINS` en el `.env` del backend debe incluir el origen del frontend (p. ej. `https://ia.ominis.org`).

---

## ¿Hace falta reindexar?

- **No** para empezar a juntar más documentos: solo agrega fuentes nuevas.
- **Sí** solo si quieres actualizar fuentes ya existentes, propagar taxonomía a los chunks, o reintentar fuentes en error. Usa **batch-reindex** desde el dashboard o la API.
