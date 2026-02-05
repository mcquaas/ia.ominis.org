#!/usr/bin/env python3
"""
Full RAG test with Ollama (100% Mexico data residency)
"""

import sys
import os
import json
import urllib.request
import urllib.error

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'rag'))

from vector_store import FAISSVectorStore
from embedder import EmbeddingGenerator

EMBEDDINGS_BUCKET = 'ominis-health-embeddings-mx'
VECTOR_PREFIX = 'vectors'
REGION = 'mx-central-1'

# Ollama configuration (self-hosted in Mexico)
OLLAMA_URL = os.environ.get('OLLAMA_URL', 'http://localhost:11434')
OLLAMA_MODEL = os.environ.get('OLLAMA_MODEL', 'ominis-2.0')


def call_ollama(prompt: str) -> str:
    """Call Ollama API for LLM inference"""
    payload = json.dumps({
        "model": OLLAMA_MODEL,
        "prompt": prompt,
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
        with urllib.request.urlopen(req, timeout=120) as response:
            result = json.loads(response.read().decode('utf-8'))
            return result.get('response', 'No response generated.')
    except urllib.error.URLError as e:
        return f"Error connecting to Ollama: {e}"


def main():
    query = sys.argv[1] if len(sys.argv) > 1 else "¿Qué es la diabetes?"
    
    print(f"Query: {query}\n")
    print(f"Using Ollama at: {OLLAMA_URL}")
    print(f"Model: {OLLAMA_MODEL}\n")
    
    # Load resources
    print("Loading resources...")
    embedder = EmbeddingGenerator()
    store = FAISSVectorStore.load_from_s3(EMBEDDINGS_BUCKET, VECTOR_PREFIX, REGION)
    
    # Search
    print("Searching...")
    query_embedding = embedder.embed_texts([query])[0]
    results = store.search(query_embedding, k=3)
    
    # Format context
    context_parts = []
    for i, (chunk, score) in enumerate(results):
        metadata = chunk.get('metadata', {})
        context_parts.append(f"""
[Fuente {i+1}]
Título: {metadata.get('title', 'Untitled')}
URL: {metadata.get('url', '')}
Contenido: {chunk['content']}
---""")
    
    context = "\n".join(context_parts)
    
    # Build prompt for Ollama (Mistral format)
    system_prompt = """Eres un asistente médico de Ominis Health (FUNSALUD). 
Responde basándote SOLO en las fuentes proporcionadas. Cita las fuentes por número. Responde en español."""
    
    full_prompt = f"""<s>[INST] {system_prompt}

Pregunta: {query}

FUENTES:
{context}

Responde basándote en las fuentes. [/INST]"""
    
    # Call Ollama
    print("Calling Ollama LLM (self-hosted in Mexico)...")
    answer = call_ollama(full_prompt)
    
    print("\n" + "=" * 60)
    print("RESPUESTA:")
    print("=" * 60)
    print(answer)
    
    print("\n" + "=" * 60)
    print("FUENTES:")
    print("=" * 60)
    for i, (chunk, score) in enumerate(results):
        print(f"[{i+1}] {chunk.get('metadata', {}).get('title', 'N/A')}")
        print(f"    {chunk.get('metadata', {}).get('url', 'N/A')}")


if __name__ == '__main__':
    main()
