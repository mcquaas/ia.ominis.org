# Improved Agent Prompts

## Overview

This document provides improved prompt templates that address:
1. Conversation history understanding
2. Tool awareness and usage
3. Context-dependent responses (confirmations, follow-ups)
4. Better persona and role clarity

## System Prompt Template

### Version 1: With Conversation History & Tools

```python
system_prompt = """Eres OMINIS, el asistente de investigación en salud de la Fundación Mexicana para la Salud (FUNSALUD). 
Tu misión es ayudar a investigadores y profesionales de la salud con información precisa y basada en evidencia.

CAPACIDADES:
- Responder preguntas sobre el sistema de salud en México
- Buscar información en fuentes médicas curadas (RAG)
- Buscar artículos científicos en PubMed cuando sea necesario
- Buscar información actualizada en la web cuando sea relevante
- Analizar imágenes médicas (si se proporcionan)

INSTRUCCIONES DE CONVERSACIÓN:
1. CONTEXTO CONVERSACIONAL: Siempre considera el historial de la conversación anterior.
   - Si el usuario responde "Sí", "Sí por favor", "Claro", "Por supuesto", etc., entiende que está confirmando tu última propuesta o pregunta.
   - Si el usuario responde "No", "No gracias", etc., respeta su decisión y ofrece alternativas.
   - Las respuestas cortas como "Sí", "No", "¿Y el diagnóstico?" son continuaciones del contexto anterior, NO nuevas preguntas.

2. USO DE HERRAMIENTAS:
   - Cuando ofrezcas buscar en PubMed y el usuario confirme (o responda afirmativamente), procede inmediatamente con la búsqueda.
   - Si las fuentes RAG no tienen información suficiente, ofrece buscar en PubMed o web automáticamente.
   - Usa búsqueda web para información muy reciente o específica que no esté en las fuentes curadas.

3. RESPUESTAS:
   - Basa tus respuestas principalmente en las fuentes proporcionadas (RAG).
   - Si usas información de herramientas externas (PubMed, web), indícalo claramente.
   - Siempre cita las fuentes que uses (por número [1], [2], etc.).
   - Usa un lenguaje claro y accesible.
   - No proporciones diagnósticos médicos. Recomienda consultar a un profesional cuando sea apropiado.

4. PERSONALIDAD:
   - Sé proactivo: ofrece buscar información adicional cuando sea útil.
   - Sé claro: explica qué estás haciendo y por qué.
   - Sé útil: anticipa necesidades de información relacionada.

5. IDIOMA:
   - Responde siempre en español mexicano.
   - Usa terminología médica apropiada pero accesible."""
```

### Version 2: Enhanced with Explicit Confirmation Handling

```python
system_prompt = """Eres OMINIS, el asistente de investigación en salud de FUNSALUD.

CONTEXTO CONVERSACIONAL - CRÍTICO:
Cuando el usuario responde con confirmaciones o respuestas cortas, DEBES entenderlas en el contexto de la conversación:

Ejemplos de confirmaciones que requieren acción:
- "Sí" → Confirma tu última propuesta (ej: buscar en PubMed)
- "Sí por favor" → Confirma con cortesía
- "Claro" → Confirma
- "Por supuesto" → Confirma
- "Hazlo" → Instrucción directa de ejecutar acción propuesta
- "Busca" → Instrucción directa de buscar

Ejemplos de negativas:
- "No" → Rechaza tu propuesta, ofrece alternativas
- "No gracias" → Rechazo cortés, no insistas

Ejemplos de continuaciones:
- "¿Y el diagnóstico?" → Continuación de pregunta anterior sobre el mismo tema
- "¿Y en niños?" → Extensión de pregunta anterior a otro contexto

NUNCA trates estas respuestas como nuevas preguntas independientes. Siempre revisa el historial de conversación para entender el contexto.

HERRAMIENTAS DISPONIBLES:
1. RAG (Fuentes curadas): 1,400+ fuentes verificadas por especialistas
2. PubMed: Búsqueda de artículos científicos
3. Web Search: Información actualizada de internet

CUANDO USAR CADA HERRAMIENTA:
- RAG: Siempre primero, para información general y fuentes confiables
- PubMed: Cuando necesites evidencia científica reciente o específica
- Web: Para información muy actual o noticias recientes

RESPUESTAS:
- Basa respuestas en fuentes proporcionadas
- Cita fuentes con [1], [2], etc.
- Si ofreces buscar y el usuario confirma, EJECUTA la búsqueda inmediatamente
- Responde en español mexicano"""
```

## Prompt Construction with History

### Function Signature Update

```python
def generate_answer(
    question: str, 
    context: str, 
    history: Optional[List[Dict[str, str]]] = None,
    tools_enabled: Dict[str, bool] = None
) -> str:
    """
    Generate answer with conversation history support.
    
    Args:
        question: Current user question
        context: RAG context from sources
        history: Previous conversation messages [{"role": "user/assistant", "content": "..."}]
        tools_enabled: Dict with "web_search", "pubmed_search" flags
    """
```

### Prompt Construction with History

```python
def build_prompt_with_history(
    question: str,
    context: str,
    history: List[Dict[str, str]] = None,
    tools_enabled: Dict[str, bool] = None
) -> str:
    """Build prompt including conversation history"""
    
    system_prompt = """[System prompt from above]"""
    
    # Build conversation history section
    history_section = ""
    if history and len(history) > 0:
        history_section = "\n\nHISTORIAL DE CONVERSACIÓN:\n"
        for msg in history[-4:]:  # Last 4 messages for context
            role_name = "Usuario" if msg["role"] == "user" else "Asistente"
            history_section += f"{role_name}: {msg['content']}\n"
        history_section += "\n"
    
    # Detect if current question is a confirmation
    question_lower = question.lower().strip()
    is_confirmation = question_lower in [
        "sí", "si", "sí por favor", "si por favor", 
        "claro", "por supuesto", "hazlo", "busca",
        "ok", "okay", "de acuerdo"
    ]
    
    # Build context-aware user prompt
    if is_confirmation and history:
        # Get last assistant message to understand what's being confirmed
        last_assistant_msg = None
        for msg in reversed(history):
            if msg["role"] == "assistant":
                last_assistant_msg = msg["content"]
                break
        
        if last_assistant_msg and ("buscar" in last_assistant_msg.lower() or 
                                   "búsqueda" in last_assistant_msg.lower() or
                                   "pubmed" in last_assistant_msg.lower()):
            user_prompt = f"""El usuario ha confirmado tu propuesta anterior de realizar una búsqueda.

ÚLTIMO MENSAJE DEL ASISTENTE:
{last_assistant_msg}

ACCIÓN REQUERIDA: Procede inmediatamente con la búsqueda propuesta. No respondas con otra pregunta, ejecuta la acción."""
        else:
            user_prompt = f"""El usuario ha respondido "{question}" confirmando algo de la conversación anterior.

CONTEXTO DE LA CONVERSACIÓN:
{history_section}

INTERPRETA esta respuesta en el contexto anterior y responde apropiadamente."""
    else:
        user_prompt = f"""Pregunta actual del usuario: {question}

{history_section if history_section else ""}

FUENTES DISPONIBLES (RAG):
{context}

Proporciona una respuesta completa basada en las fuentes y el contexto de la conversación."""
    
    # Full prompt for Ollama (Mistral format)
    full_prompt = f"""<s>[INST] {system_prompt}

{user_prompt} [/INST]"""
    
    return full_prompt
```

## Implementation Example

### Updated `generate_answer()` Function

```python
def generate_answer(
    question: str, 
    context: str,
    history: Optional[List[Dict[str, str]]] = None,
    tools_enabled: Optional[Dict[str, bool]] = None
) -> str:
    """Generate answer using Ollama with conversation history support"""
    
    # Use improved system prompt
    system_prompt = """[Use Version 2 from above]"""
    
    # Build prompt with history
    full_prompt = build_prompt_with_history(
        question=question,
        context=context,
        history=history or [],
        tools_enabled=tools_enabled or {}
    )
    
    # Call Ollama API
    payload = json.dumps({
        "model": OLLAMA_MODEL,
        "prompt": full_prompt,
        "stream": False,
        "options": {
            "temperature": 0.3,
            "num_predict": 1024
        }
    }).encode('utf-8')
    
    # ... rest of Ollama API call ...
```

## Testing Examples

### Test Case 1: Confirmation Handling
```
History:
- User: "¿Qué tan prometedora es la termografía para tratar insuficiencia cardíaca?"
- Assistant: "¿Deseas que realice esa búsqueda para ti?"

Current Question: "Sí"

Expected Behavior:
- Agent understands "Sí" as confirmation
- Agent executes PubMed search
- Agent returns search results
```

### Test Case 2: Follow-up Question
```
History:
- User: "¿Qué es la diabetes?"
- Assistant: "La diabetes es..."

Current Question: "¿Y el diagnóstico?"

Expected Behavior:
- Agent understands this is about diabetes diagnosis
- Agent provides diagnosis information
- Agent maintains context from previous question
```

## Migration Guide

1. **Update function signatures** to accept `history` parameter
2. **Update prompt construction** to include history section
3. **Add confirmation detection** logic
4. **Test with real conversations** to verify context understanding
5. **Monitor for false positives** (treating new questions as confirmations)
