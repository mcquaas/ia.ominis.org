"""
Improved Ominis Health Query Handler with Conversation History Support
This is a reference implementation showing how to fix the "Sí" confirmation issue.
"""

import os
import json
import logging
import urllib.request
import urllib.error
from typing import Dict, Any, List, Tuple, Optional

logger = logging.getLogger()
logger.setLevel(logging.INFO)

OLLAMA_URL = os.environ.get('OLLAMA_URL', 'http://localhost:11434')
OLLAMA_MODEL = os.environ.get('OLLAMA_MODEL', 'ominis-2.0')


def detect_confirmation(question: str, history: List[Dict[str, str]]) -> Tuple[bool, Optional[str]]:
    """
    Detect if current question is a confirmation of previous conversation.
    
    Returns:
        (is_confirmation, context_hint) tuple
    """
    question_lower = question.lower().strip()
    
    # Common confirmation patterns
    confirmations = [
        "sí", "si", "sí por favor", "si por favor", 
        "claro", "por supuesto", "hazlo", "busca",
        "ok", "okay", "de acuerdo", "perfecto",
        "adelante", "procede", "haz la búsqueda"
    ]
    
    is_confirmation = question_lower in confirmations
    
    # Get context from last assistant message
    context_hint = None
    if is_confirmation and history:
        for msg in reversed(history):
            if msg.get("role") == "assistant":
                content = msg.get("content", "")
                if "buscar" in content.lower() or "búsqueda" in content.lower() or "pubmed" in content.lower():
                    context_hint = content
                    break
    
    return is_confirmation, context_hint


def build_system_prompt() -> str:
    """Build improved system prompt with conversation awareness"""
    return """Eres OMINIS, el asistente de investigación en salud de la Fundación Mexicana para la Salud (FUNSALUD). 
Tu misión es ayudar a investigadores y profesionales de la salud con información precisa y basada en evidencia.

CAPACIDADES:
- Responder preguntas sobre el sistema de salud en México
- Buscar información en fuentes médicas curadas (RAG)
- Buscar artículos científicos en PubMed cuando sea necesario
- Buscar información actualizada en la web cuando sea relevante

INSTRUCCIONES DE CONVERSACIÓN - CRÍTICO:
1. CONTEXTO CONVERSACIONAL: Siempre considera el historial de la conversación anterior.
   - Si el usuario responde "Sí", "Sí por favor", "Claro", "Por supuesto", etc., entiende que está confirmando tu última propuesta o pregunta.
   - Si el usuario responde "No", "No gracias", respeta su decisión y ofrece alternativas.
   - Las respuestas cortas como "Sí", "No", "¿Y el diagnóstico?" son continuaciones del contexto anterior, NO nuevas preguntas independientes.

2. USO DE HERRAMIENTAS:
   - Cuando ofrezcas buscar en PubMed y el usuario confirme (o responda afirmativamente), procede inmediatamente con la búsqueda.
   - Si las fuentes RAG no tienen información suficiente, ofrece buscar en PubMed o web automáticamente.

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
   - Responde siempre en español mexicano."""


def build_prompt_with_history(
    question: str,
    context: str,
    history: List[Dict[str, str]] = None,
    tools_enabled: Dict[str, bool] = None
) -> str:
    """
    Build prompt including conversation history.
    
    Args:
        question: Current user question
        context: RAG context from sources
        history: Previous conversation messages [{"role": "user/assistant", "content": "..."}]
        tools_enabled: Dict with "web_search", "pubmed_search" flags
    """
    system_prompt = build_system_prompt()
    
    history = history or []
    tools_enabled = tools_enabled or {}
    
    # Build conversation history section
    history_section = ""
    if len(history) > 0:
        history_section = "\n\nHISTORIAL DE CONVERSACIÓN (últimos mensajes):\n"
        for msg in history[-4:]:  # Last 4 messages for context
            role_name = "Usuario" if msg.get("role") == "user" else "Asistente"
            content = msg.get("content", "")
            history_section += f"{role_name}: {content}\n"
        history_section += "\n"
    
    # Detect if current question is a confirmation
    is_confirmation, context_hint = detect_confirmation(question, history)
    
    # Build context-aware user prompt
    if is_confirmation and context_hint:
        user_prompt = f"""El usuario ha confirmado tu propuesta anterior.

ÚLTIMO MENSAJE DEL ASISTENTE (lo que propusiste):
{context_hint}

ACCIÓN REQUERIDA: El usuario respondió "{question}" confirmando tu propuesta. 
Procede inmediatamente con la acción que propusiste (ej: realizar la búsqueda en PubMed).
NO respondas con otra pregunta, EJECUTA la acción que ofreciste."""
    
    elif is_confirmation:
        user_prompt = f"""El usuario ha respondido "{question}" confirmando algo de la conversación anterior.

{history_section}

INTERPRETA esta respuesta en el contexto anterior y responde apropiadamente.
Si ofreciste realizar una búsqueda o acción, procede con ella ahora."""
    
    else:
        user_prompt = f"""Pregunta actual del usuario: {question}

{history_section if history_section else ""}

FUENTES DISPONIBLES (RAG):
{context}

Proporciona una respuesta completa basada en las fuentes y el contexto de la conversación.
Si la información no es suficiente, ofrece buscar en PubMed o web."""
    
    # Full prompt for Ollama (Mistral format)
    full_prompt = f"""<s>[INST] {system_prompt}

{user_prompt} [/INST]"""
    
    return full_prompt


def generate_answer(
    question: str, 
    context: str,
    history: Optional[List[Dict[str, str]]] = None,
    tools_enabled: Optional[Dict[str, bool]] = None
) -> str:
    """
    Generate answer using Ollama with conversation history support.
    
    Args:
        question: Current user question
        context: RAG context from sources
        history: Previous conversation messages [{"role": "user/assistant", "content": "..."}]
        tools_enabled: Dict with "web_search", "pubmed_search" flags
    """
    history = history or []
    tools_enabled = tools_enabled or {}
    
    # Build prompt with history
    full_prompt = build_prompt_with_history(
        question=question,
        context=context,
        history=history,
        tools_enabled=tools_enabled
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
    
    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/generate",
        data=payload,
        headers={'Content-Type': 'application/json'}
    )
    
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            result = json.loads(response.read().decode('utf-8'))
            return result.get('response', 'No se pudo generar respuesta.')
    except urllib.error.URLError as e:
        logger.error(f"Error connecting to Ollama: {e}")
        raise Exception(f"Error connecting to LLM server: {e}")


def format_context(results: List[Tuple[Dict, float]]) -> str:
    """Format chunks as context for LLM"""
    context_parts = []
    
    for i, (chunk, score) in enumerate(results):
        metadata = chunk.get('metadata', {})
        title = metadata.get('title', 'Sin título')
        url = metadata.get('url', '')
        
        context_parts.append(f"""
[Fuente {i+1}]
Título: {title}
URL: {url}
Contenido:
{chunk.get('content', '')}
---""")
    
    return "\n".join(context_parts)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Main Lambda handler with conversation history support.
    
    Expected event body:
    {
        "question": "user question",
        "history": [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}],
        "num_sources": 5,
        "web_search": true,
        "pubmed_search": false
    }
    """
    try:
        # Parse request
        body = event.get('body', '{}')
        if isinstance(body, str):
            body = json.loads(body)
        
        question = body.get('question', '').strip()
        history = body.get('history', [])  # NEW: Get history
        k = min(body.get('num_sources', 5), 10)
        tools_enabled = {
            'web_search': body.get('web_search', False),
            'pubmed_search': body.get('pubmed_search', False)
        }
        
        if not question:
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({'error': 'Question is required'})
            }
        
        logger.info(f"Processing question: {question[:50]}... (history: {len(history)} messages)")
        
        # TODO: Implement search_chunks function (from original handler)
        # For now, this is a placeholder
        # results = search_chunks(question, k=k)
        results = []  # Placeholder
        
        if not results:
            response = {
                'statusCode': 200,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({
                    'answer': 'Lo siento, no encontré información relevante.',
                    'sources': [],
                    'query': question
                }, ensure_ascii=False)
            }
            return response
        
        # Format context
        context_str = format_context(results)
        
        # Generate answer with history support
        answer = generate_answer(
            question=question,
            context=context_str,
            history=history,  # NEW: Pass history
            tools_enabled=tools_enabled  # NEW: Pass tools
        )
        
        # Format sources
        sources = [
            {
                'title': chunk.get('metadata', {}).get('title', 'Sin título'),
                'url': chunk.get('metadata', {}).get('url', ''),
                'score': round(score, 4)
            }
            for chunk, score in results
        ]
        
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'answer': answer,
                'sources': sources,
                'query': question
            }, ensure_ascii=False)
        }
        
    except Exception as e:
        logger.error(f"Error: {str(e)}", exc_info=True)
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({'error': str(e)})
        }
