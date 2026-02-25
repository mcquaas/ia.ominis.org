# Embeddings preentrenados para PubMed y papers científicos (MED42 / OpenScholar)

## ¿Hay índices pre-indexados que se puedan usar?

**En la práctica: no** hay un índice público de PubMed (o literatura científica) con embeddings listos que podamos usar como “caja negra” con MED42/OpenScholar. Lo que sí hay son:

- **APIs de búsqueda** (PubMed E-utilities, Semantic Scholar, PubTator3): devuelven papers por términos o entidades, pero no búsqueda por similitud vectorial expuesta de forma directa y gratuita para nuestro flujo.
- **Trabajos de investigación** que describen sistemas con embeddings precomputados a escala PubMed (p. ej. vectores int8 para ~40M registros), pero sin API pública reutilizable.
- **Modelos preentrenados** para texto científico/biomédico: no son “índices”, pero permiten que **nosotros** indexemos (y consultemos) con embeddings mucho más adecuados que un modelo generalista.

Para MED42 y OpenScholar lo relevante es **qué contexto les pasamos**: si ese contexto sale de una búsqueda sobre papers, usar un **modelo de embeddings científico** mejora la recuperación y por tanto la calidad del contexto. Sigue siendo “nosotros indexamos”, pero con un modelo ya entrenado para ese dominio.

## Modelos que sí puedes usar (sin índice externo)

### 1. SPECTER2 (Allen AI) – papers científicos

- **Qué es:** Modelo de embeddings para documentos científicos (título + resumen). Entrenado con citaciones sobre millones de papers.
- **Dónde:** Hugging Face `allenai/specter2` (y variantes con adapters por tarea).
- **Dimensión:** 768.
- **Uso:** Sustituir en el pipeline el modelo de embeddings por SPECTER2 para la fuente “PubMed” (o cualquier chunk que sea título+abstract). El backend debe usar el **mismo modelo** para embeber la query y comparar con FAISS.
- **Compatibilidad:** Funciona con el flujo actual (pipeline embebe chunks → FAISS; backend embebe query → búsqueda). Solo hay que cambiar `HEALTH_EMBEDDING_MODEL` (y `HEALTH_EMBEDDING_DIM=768`) y re-indexar. Si el modelo no está en la API de Sentence Transformers, puede hacer falta cargarlo con `transformers` y hacer mean pooling sobre el último hidden state (el pipeline y el backend tendrían que usar la misma lógica).

### 2. MedCPT (NCBI) – biomédico / PubMed

- **Qué es:** Encoders (consulta y artículo) para retrieval biomédico, entrenados con pares query–artículo de logs de búsqueda de PubMed.
- **Dónde:** NCBI en GitHub/Hugging Face (`ncbi/MedCPT`, etc.). Incluye cross-encoder para reranking.
- **Uso:** Usar el **article encoder** para embeber abstracts/chunks de PubMed y el **query encoder** en el backend para la consulta. Misma idea: un solo modelo (o par query/doc) en pipeline y backend, re-indexar con ese modelo.
- **Nota:** La API de uso puede ser Transformers (no solo Sentence Transformers); el pipeline y el backend tendrían que cargar MedCPT de la misma forma.

### 3. Sentence Transformers generalistas (actual)

- **all-MiniLM-L6-v2** (384 dim): Lo que usas ahora. Sirve para texto general y URLs institucionales; para papers científicos SPECTER2 o MedCPT suelen dar mejor resultado.

## Cómo encaja con MED42 y OpenScholar

- **MED42 / OpenScholar** reciben **contexto** (párrafos o resúmenes) que tú les pasas. No “leen” un índice externo; ese contexto suele salir de tu RAG (p. ej. FAISS + health datastore).
- Si la fuente es **PubMed / papers**: indexar (y consultar) con **SPECTER2 o MedCPT** mejora la relevancia de lo que recuperas y, por tanto, la calidad del contexto que llega a MED42/OpenScholar.
- No hace falta un “índice pre-indexado” externo: el “pre-indexado” es el **modelo preentrenado** (SPECTER2/MedCPT); el índice lo construyes tú con ese modelo.

## Opción práctica: un solo modelo científico para todo el health datastore

Si la mayoría del contenido es PubMed/papers o texto biomédico:

1. En **pipeline** y **backend**:
   - `HEALTH_EMBEDDING_MODEL=allenai/specter2` (o el MedCPT article encoder, según disponibilidad en Hugging Face).
   - `HEALTH_EMBEDDING_DIM=768`.
2. Re-ejecutar el pipeline de ingesta para re-indexar con el nuevo modelo (FAISS + PG + OpenSearch).
3. El backend ya usa el mismo modelo para la query (en `health_datastore/retriever.py`); con la misma dimensión, FAISS y el modelo de query siguen siendo compatibles.

Si mezclas **muchas** URLs institucionales (gob.mx, etc.) y **muchos** papers, en teoría podrías tener dos índices (uno con MiniLM para URLs y otro con SPECTER2 para PubMed) y fusionar resultados en el backend; es más complejo y normalmente no necesario para empezar.

## Resumen

| Pregunta | Respuesta |
|----------|-----------|
| ¿Índice pre-indexado de PubMed listo para usar? | No, no hay uno público que se enchiufe directo. |
| ¿Modelos preentrenados para papers/PubMed? | Sí: **SPECTER2** (Allen AI) y **MedCPT** (NCBI). |
| ¿Compatible con MED42/OpenScholar? | Sí: ellos consumen contexto; si ese contexto se obtiene con SPECTER2/MedCPT, la recuperación para papers mejora. |
| ¿Qué cambiar en el repo? | `HEALTH_EMBEDDING_MODEL` + `HEALTH_EMBEDDING_DIM` y re-indexar; opcionalmente adaptar el embedder si el modelo usa API de Transformers en lugar de Sentence Transformers. |
