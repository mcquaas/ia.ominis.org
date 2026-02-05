"""
Ominis Health Query Lambda Handler (Lightweight version)
Uses Ollama on EC2 in Mexico - 100% data residency in Mexico
"""

import os
import json
import boto3
import logging
import urllib.request
import urllib.error
from typing import Dict, Any, List, Tuple
import math

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Environment variables
EMBEDDINGS_BUCKET = os.environ.get('EMBEDDINGS_BUCKET', 'ominis-health-embeddings-mx')
VECTOR_PREFIX = os.environ.get('VECTOR_PREFIX', 'vectors')
# Configuration
# ALL data and inference stays in mx-central-1 (Mexico)
# Using self-hosted Ollama on EC2 instead of Bedrock
OLLAMA_URL = os.environ.get('OLLAMA_URL', 'http://localhost:11434')
OLLAMA_MODEL = os.environ.get('OLLAMA_MODEL', 'ominis-2.0')  # Ominis Health medical LLM
AWS_REGION = os.environ.get('OMINIS_REGION', 'mx-central-1')

# Global cache
_chunks_cache = None
_embeddings_cache = None


def get_cached_data():
    """Load chunks and embeddings from S3 (cached for warm starts)"""
    global _chunks_cache, _embeddings_cache
    
    if _chunks_cache is not None and _embeddings_cache is not None:
        logger.info("Using cached data")
        return _chunks_cache, _embeddings_cache
    
    s3 = boto3.client('s3', region_name=AWS_REGION)
    
    # Load chunks
    response = s3.get_object(Bucket=EMBEDDINGS_BUCKET, Key=f"{VECTOR_PREFIX}/chunks.json")
    _chunks_cache = json.loads(response['Body'].read().decode('utf-8'))
    
    # Load embeddings from metadata or separate file
    try:
        response = s3.get_object(Bucket=EMBEDDINGS_BUCKET, Key=f"{VECTOR_PREFIX}/embeddings.json")
        _embeddings_cache = json.loads(response['Body'].read().decode('utf-8'))
    except:
        # If no embeddings file, we'll compute on the fly
        _embeddings_cache = None
    
    logger.info(f"Loaded {len(_chunks_cache)} chunks from S3")
    return _chunks_cache, _embeddings_cache


def simple_text_vector(text: str, vocab_size: int = 384) -> List[float]:
    """
    Create a simple text vector for similarity matching.
    Uses word hashing to create a fixed-size vector - no external API calls needed.
    All computation stays local in Mexico.
    """
    text = text.lower()
    words = text.split()
    vector = [0.0] * vocab_size
    
    for word in words:
        # Hash each word to a position in the vector
        idx = hash(word) % vocab_size
        vector[idx] += 1.0
    
    # Normalize
    magnitude = math.sqrt(sum(x * x for x in vector))
    if magnitude > 0:
        vector = [x / magnitude for x in vector]
    
    return vector


def cosine_similarity(a: List[float], b: List[float]) -> float:
    """Compute cosine similarity between two vectors"""
    dot_product = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    
    if norm_a == 0 or norm_b == 0:
        return 0.0
    
    return dot_product / (norm_a * norm_b)


def search_chunks(query: str, k: int = 5) -> List[Tuple[Dict, float]]:
    """
    Search for relevant chunks using local similarity matching.
    All computation stays in Mexico - no cross-region API calls.
    """
    chunks, stored_embeddings = get_cached_data()
    
    # Use keyword-based semantic matching (no external API calls)
    query_lower = query.lower()
    query_words = set(query_lower.split())
    
    # Remove common Spanish stop words
    stop_words = {'el', 'la', 'los', 'las', 'de', 'del', 'en', 'un', 'una', 'que', 'es', 'y', 'a', 'por', 'para', 'con', 'se', 'su', 'al', 'lo', 'como', 'más', 'pero', 'sus', 'le', 'ya', 'o', 'sin', 'sobre', 'todo', 'entre', 'hay', 'cuando', 'muy', 'ser', 'son', 'también'}
    query_words = query_words - stop_words
    
    results = []
    for chunk in chunks:
        content = chunk.get('content', '').lower()
        title = chunk.get('metadata', {}).get('title', '').lower()
        
        # Combine title and content for matching
        full_text = f"{title} {content}"
        content_words = set(full_text.split()) - stop_words
        
        # Calculate relevance score
        if not query_words:
            score = 0.0
        else:
            # Word overlap score
            overlap = len(query_words & content_words)
            
            # Boost for exact phrase matches
            phrase_bonus = 0.5 if query_lower in full_text else 0.0
            
            # Boost for title matches
            title_bonus = 0.3 if any(w in title for w in query_words) else 0.0
            
            score = (overlap / len(query_words)) + phrase_bonus + title_bonus
        
        results.append((chunk, score))
    
    # Sort by score and return top k
    results.sort(key=lambda x: x[1], reverse=True)
    return results[:k]


def format_context(results: List[Tuple[Dict, float]]) -> str:
    """Format chunks as context for LLM"""
    context_parts = []
    
    for i, (chunk, score) in enumerate(results):
        metadata = chunk.get('metadata', {})
        context_parts.append(f"""
[Fuente {i+1}]
Título: {metadata.get('title', 'Sin título')}
URL: {metadata.get('url', '')}
Contenido:
{chunk.get('content', '')}
---""")
    
    return "\n".join(context_parts)


def generate_answer(question: str, context: str) -> str:
    """Generate answer using Ollama on EC2 in Mexico (100% data residency)"""
    
    system_prompt = """Eres un asistente médico especializado de Ominis Health, respaldado por FUNSALUD. 
Tu objetivo es proporcionar información de salud precisa y útil basada en las fuentes proporcionadas.

INSTRUCCIONES:
1. Responde SOLO basándote en la información proporcionada en las fuentes.
2. Si las fuentes no contienen información suficiente, indícalo claramente.
3. Siempre cita las fuentes que uses (por número).
4. Usa un lenguaje claro y accesible.
5. No proporciones diagnósticos médicos. Recomienda consultar a un profesional cuando sea apropiado.
6. Responde en español."""

    user_prompt = f"""Pregunta del usuario: {question}

FUENTES DISPONIBLES:
{context}

Proporciona una respuesta completa basada en las fuentes anteriores. Incluye las referencias a las fuentes usadas."""

    # Full prompt for Ollama (Mistral format)
    full_prompt = f"""<s>[INST] {system_prompt}

{user_prompt} [/INST]"""

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


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Main Lambda handler"""
    try:
        # Parse request
        body = event.get('body', '{}')
        if isinstance(body, str):
            body = json.loads(body)
        
        question = body.get('question', '').strip()
        k = min(body.get('num_sources', 5), 10)
        
        if not question:
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({'error': 'Question is required'})
            }
        
        logger.info(f"Processing question: {question}")
        
        # Search for relevant chunks
        results = search_chunks(question, k=k)
        
        if not results:
            return {
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
        
        # Format context and generate answer
        context = format_context(results)
        answer = generate_answer(question, context)
        
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
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'POST, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type'
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
