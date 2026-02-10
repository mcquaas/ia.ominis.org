# Plan de acción: Agente de investigación mejorado

## Objetivos

1. **Proceso de pensamiento visible**: Mostrar qué está investigando el agente en cada paso y por qué decidió buscar en cada fuente.
2. **Seguimiento del plan**: El agente debe seguir el plan de investigación con la retroalimentación del usuario.
3. **Notas de investigación**: Tomar notas relevantes en cada lectura para elaborar documentos más completos con citas científicas.
4. **Nombre del modelo**: Cambiar a `ominis-2.0-research` cuando se especifique o muestre en el frontend.

---

## 1. Proceso de pensamiento en el panel de actividad

### Estado actual
- Cada paso tiene: `action`, `detail`, `url`, `result`, `elapsed`
- El panel muestra: "Buscando: Cáncer en PubMed" → "Resultados: 30 fuentes"
- Falta el *razonamiento*: por qué busca ahí, qué espera encontrar, qué encontró de relevante

### Propuesta
Añadir un campo **`reasoning`** (o `thought`) a cada paso, con frases como:

| Acción | Ejemplo de reasoning |
|--------|----------------------|
| plan | "Definiendo el plan de investigación para abordar: {focus}. Consultas iniciales: {n}." |
| search | "Buscaré en {fuente} información sobre: {query}. Es relevante para el tema de {focus}." |
| search_result | "Encontré {n} fuentes. Algunas parecen prometedoras para el reporte. Identificando cuáles profundizar." |
| refine | "Refinando con lo que el usuario especificó: {resumen}. Ajustando consultas para {focus}." |
| read | "Leyendo: {título} para extraer datos relevantes sobre {topic}." |
| read_done | "Hallazgo clave: {preview breve}. Tomando nota para citar en el reporte." |
| read_fail | "No pude extraer contenido útil de esta fuente. Continuando con otras." |
| filter | "Filtrando {n} candidatas a {m} únicas para enfocar el análisis." |
| relevance | "Evaluando cuáles de {n} fuentes son más relevantes para el tema del usuario." |
| complete | "Consolidando {found} fuentes encontradas y {read} leídas para el reporte final." |
| sources | "Generando reporte con {n} fuentes seleccionadas y citas." |

### Implementación
- **Backend**: Extender `emit_step(action, detail, url, result, reasoning="")` con frases de plantilla según `action`.
- **Frontend**: Mostrar `step.reasoning` en el panel, debajo o junto a `detail` y `result`.

---

## 2. Notas de investigación

### Flujo actual
- Se leen fuentes → se guardan en `documents` → se pasan al LLM para el reporte
- El contenido se trunca por límite de contexto

### Propuesta
- **Acumulador de notas**: Lista `research_notes: list[str]` que se va llenando durante la lectura.
- **Por cada `read_done`**: Añadir una nota breve (1–2 frases) con datos clave:
  - Ejemplo: "Fuente [3]: INCan como principal fuente de información sobre cáncer en México; datos epidemiológicos 2020–2024."
- **Paso al reporte**: Incluir `research_notes` en el prompt del reporte final:

  ```
  NOTAS DE INVESTIGACIÓN (hallazgos clave por fuente):
  - [1] ...
  - [2] ...
  ```

  Así el modelo puede usar estas notas para estructurar el reporte y citar correctamente.

### Opciones de implementación

| Opción | Pros | Contras |
|--------|------|---------|
| A) LLM por fuente | notas precisas y resumidas | más latencia y costo |
| B) Plantilla desde extracto | sin latencia extra | notas menos ricas |
| C) Solo extracto de texto | implementación simple | puede ser redundante con el contenido |

**Recomendación**: Empezar con **B)** (extracto de texto como “nota”) y mejorar si hace falta:
- En `read_done` usar `result` con un preview más largo (ej. 200–300 chars).
- Emitir ese preview como “nota” y acumularlo en `research_notes`.
- A futuro: evaluar si se puede añadir una llamada LLM ligera para resumir por fuente.

---

## 3. Seguimiento del plan y retroalimentación del usuario

### Estado actual
- El plan incluye: `focus`, `queries`, `sections`
- El usuario responde las preguntas (ej. "prefiero cáncer de mama, pulmón, ovarios")
- El flujo de refinamiento ya usa esas respuestas

### Propuesta
- **Explicitar el plan en el prompt**: Añadir en el prompt final:
  ```
  PLAN DE INVESTIGACIÓN (con retroalimentación del usuario):
  - Focus: {focus}
  - Qué incluir: {user_specs}
  - Qué no hacer: {user_exclusions si existen}
  ```

- **Campo `excluded_sources`**: Ya existe; el usuario puede desmarcar fuentes.
- **Revisar que el prompt incluya el plan**: Verificar que `build_academic_messages` reciba y use bien el plan y las especificaciones del usuario.

---

## 4. Reportes más completos y citas científicas

### Mejoras en el prompt

1. **Formato de citas**: Incluir en el prompt:
   - Ejemplo: "Citar como: [N] Autor(es). Título. Fuente, año. URL."
   - Exigir que cada afirmación tenga un `[N]` que remita a la fuente.

2. **Secciones obligatorias**:
   - Resumen ejecutivo
   - Contexto
   - Hallazgos principales (con citas)
   - Análisis detallado
   - Discusión
   - Limitaciones
   - Conclusiones
   - Referencias (formato completo)

3. **Notas de investigación**: Añadir el bloque `NOTAS DE INVESTIGACIÓN` al prompt del reporte para que el modelo se base en ellas.

4. **Límite de contexto**: Mantener el balance actual entre truncar y enviar suficiente evidencia para citas detalladas.

---

## 5. Nombre del modelo: ominis-2.0-research

### Cambios en código

| Archivo | Cambio |
|---------|--------|
| `backend-haystack/app/rag/router.py` | `ACADEMIC_MODEL_ID = "ominis-2.0-research"` |
| `frontend/src/components/MainLayout.tsx` | Reemplazar `ominis-2.0` por `ominis-2.0-research` donde se muestra el modelo de investigación |
| Footer, modelo page, etc. | Mantener `ominis-2.0` como modelo general; usar `ominis-2.0-research` solo en el contexto de Investigación |

---

## Orden de implementación sugerido

1. **Fase 1 – Quick wins** (menos cambios)
   - Cambiar nombre del modelo a `ominis-2.0-research` en backend y frontend.
   - Añadir `reasoning` a cada paso con plantillas de texto.

2. **Fase 2 – Notas de investigación**
   - Añadir acumulador de notas.
   - Emitir notas en `read_done` usando el extracto de texto.
   - Pasar `research_notes` al prompt del reporte.

3. **Fase 3 – Mejoras de reporte** ✅ IMPLEMENTADO
   - Formato de citas y secciones obligatorias en prompt; plan explícito (Focus, Qué incluir, Qué no hacer).

4. **Fase 4 – Opcional**
   - LLM extra por fuente: no implementado. Exclusiones temáticas: excluded_topics en ResearchRequest.

5. **Decisiones tabla y gráfica** ✅ IMPLEMENTADO
   - Tabla: el agente decide si incluir tabla; elige columnas y datos e incluye tabla en markdown en el reporte.
   - Gráfica: decide si una gráfica ayuda; puede emitir bloque ```chart con JSON para renderizar; o en Phase 2 se llama al generador de gráficas (force=True). El bloque ```chart se elimina del texto enviado al cliente.

---

## 6. Maximizar contexto y longitud del reporte (sin sacrificar velocidad)

**Situación actual:** Modelo 8K contexto; input (fuentes + plan + notas) compite con output. Ya usamos `max_tokens` dinámico para no exceder 8K.

### Técnicas que no cambian el modelo

| Técnica | Qué hace | Velocidad | Completitud |
|--------|----------|-----------|-------------|
| **max_tokens dinámico** | Ajustar salida al espacio libre (ya implementado). | Igual | Aprovecha todo el hueco disponible. |
| **Comprimir input** | Reducir evidencia por documento (resúmenes por fuente, menos chars por doc). | Igual o mejor | Menos detalle en input; el modelo puede citar menos fino. |
| **Priorizar evidencia** | Enviar solo los N fragmentos más relevantes (relevance scoring ya existe); el resto en `research_notes` resumido. | Igual | Reporte basado en lo más relevante; se pierde el resto. |
| **Reporte por partes (chunked)** | Generar el reporte en 2–3 llamadas: por ejemplo Resumen+Contexto+Hallazgos, luego Análisis+Discusión, luego Limitaciones+Conclusiones+Referencias. Cada llamada con su subconjunto de fuentes y un resumen de lo anterior. | Más latencia (varias llamadas) | Reporte más largo y completo; mejor uso del contexto por sección. |

### Mezcla de modelos (model mix)

- **Idea:** Un modelo pequeño y rápido (p. ej. 7B, 8K) para plan, refinamiento y pasos intermedios; un modelo con contexto grande (p. ej. 32K–128K) solo para la generación del reporte final.
- **Ventajas:** Velocidad en la mayoría de pasos; una sola llamada “cara” con mucho contexto y salida larga.
- **Desventajas:** Necesitas desplegar o acceder a un segundo modelo (vLLM/Ollama) con contexto largo; coste y operación.
- **Recomendación:** Si tienes o puedes tener un modelo 32K (o más) en la misma API (p. ej. vLLM con `max_model_len=32768`), usarlo solo para la llamada de reporte y dejar el resto en el modelo actual.

### Reporte por partes (recomendado para reportes más largos)

1. **Dividir secciones:** Definir bloques, p. ej. [Resumen ejecutivo, Contexto, Hallazgos], [Análisis detallado, Discusión], [Limitaciones, Conclusiones, Referencias].
2. **Por cada bloque:** Una llamada al LLM con (i) instrucción para esa sección, (ii) subconjunto de fuentes más relevante para esa sección (o resumen de fuentes), (iii) “Resumen de lo ya escrito” (1–2 párrafos) para coherencia.
3. **Concatenar:** Unir las salidas en un solo markdown y enviar al cliente (y a PDF).
4. **Velocidad:** Puedes ejecutar en secuencia (más simple) o, si las secciones son independientes, en paralelo (más rápido, pero peor coherencia).

### Modelo con contexto más grande

- Si el mismo modelo (u otro en la misma stack) está disponible con **32K o 128K** de contexto, subir `MODEL_CTX_LIMIT` y el presupuesto de input en `openscholar` (p. ej. más tokens por documento) permite reportes más largos en una sola llamada sin cambiar el flujo.
- Velocidad: las llamadas con ventanas muy grandes suelen ser más lentas y costosas; conviene medir en tu entorno.

### Resumen de prioridades

1. **Corto plazo (ya hecho):** max_tokens dinámico; priorizar evidencia y notas para no llenar el contexto de ruido.
2. **Medio plazo:** Implementar **reporte por partes** (2–3 llamadas por secciones) para reportes más largos sin cambiar de modelo.
3. **Si hay presupuesto/ops:** Añadir un **modelo de contexto largo** solo para la generación del reporte, o migrar el reporte a un modelo 32K/128K.
