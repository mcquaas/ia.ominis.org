#!/usr/bin/env python3
"""
Local test script for Ominis Health RAG Query
Tests the full pipeline locally with Ollama (100% Mexico data residency)
"""

import sys
import os
import json
import urllib.request
import urllib.error

# Add paths
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'rag'))

from vector_store import FAISSVectorStore
from embedder import EmbeddingGenerator
from chunker import DocumentChunker

# Configuration
EMBEDDINGS_BUCKET = 'ominis-health-embeddings-mx'
VECTOR_PREFIX = 'vectors'
REGION = 'mx-central-1'

# Ollama configuration (self-hosted in Mexico)
OLLAMA_URL = os.environ.get('OLLAMA_URL', 'http://localhost:11434')
OLLAMA_MODEL = os.environ.get('OLLAMA_MODEL', 'ominis-2.0')


def load_resources():
    """Load vector store and embedder"""
    print("Loading embedding model...")
    embedder = EmbeddingGenerator()
    
    print("Loading vector store from S3...")
    store = FAISSVectorStore.load_from_s3(EMBEDDINGS_BUCKET, VECTOR_PREFIX, REGION)
    print(f"  Loaded {len(store.chunks)} chunks")
    
    return embedder, store


def search(query: str, embedder, store, k: int = 5):
    """Search for relevant documents"""
    # Generate query embedding
    query_embedding = embedder.embed_texts([query])[0]
    
    # Search
    results = store.search(query_embedding, k=k)
    
    return results


def format_results(results):
    """Format search results for display"""
    print("\n" + "=" * 60)
    print("SEARCH RESULTS")
    print("=" * 60)
    
    for i, (chunk, score) in enumerate(results):
        print(f"\n[{i+1}] Score: {score:.4f}")
        print(f"    Title: {chunk.get('metadata', {}).get('title', 'N/A')}")
        print(f"    URL: {chunk.get('metadata', {}).get('url', 'N/A')}")
        print(f"    Content: {chunk['content'][:200]}...")


def call_ollama(prompt: str) -> str:
    """Call Ollama API for LLM inference (self-hosted in Mexico)"""
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


def test_with_ollama(query: str, results):
    """Test full RAG with Ollama LLM (self-hosted in Mexico)"""
    print("\n" + "=" * 60)
    print("TESTING WITH OLLAMA (Self-hosted in Mexico)")
    print("=" * 60)
    print(f"URL: {OLLAMA_URL}")
    print(f"Model: {OLLAMA_MODEL}")
    
    # Format context
    context_parts = []
    for i, (chunk, score) in enumerate(results):
        metadata = chunk.get('metadata', {})
        context_parts.append(f"""
[Fuente {i+1}]
Título: {metadata.get('title', 'Untitled')}
URL: {metadata.get('url', '')}
Contenido:
{chunk['content']}
---""")
    
    context = "\n".join(context_parts)
    
    system_prompt = """Eres un asistente médico especializado de Ominis Health, respaldado por FUNSALUD. 
Tu objetivo es proporcionar información de salud precisa y útil basada en las fuentes proporcionadas.

INSTRUCCIONES:
1. Responde SOLO basándote en la información proporcionada en las fuentes.
2. Si las fuentes no contienen información suficiente, indícalo claramente.
3. Siempre cita las fuentes que uses (por número).
4. Usa un lenguaje claro y accesible.
5. Responde en español."""

    user_prompt = f"""Pregunta del usuario: {query}

FUENTES DISPONIBLES:
{context}

Proporciona una respuesta basada en las fuentes anteriores."""

    # Build Mistral format prompt
    full_prompt = f"""<s>[INST] {system_prompt}

{user_prompt} [/INST]"""

    try:
        print("\nCalling Ollama LLM...")
        answer = call_ollama(full_prompt)
        
        print("\n" + "-" * 60)
        print("RESPUESTA:")
        print("-" * 60)
        print(answer)
        
        return answer
        
    except Exception as e:
        print(f"\nOllama error: {e}")
        print("\nNote: Make sure Ollama is running and accessible at", OLLAMA_URL)
        print("You can set OLLAMA_URL environment variable to point to your server")
        return None


def main():
    if len(sys.argv) < 2:
        # Default test query
        query = "¿Qué es la diabetes?"
    else:
        query = " ".join(sys.argv[1:])
    
    print(f"\n{'=' * 60}")
    print(f"OMINIS HEALTH RAG TEST (100% Mexico)")
    print(f"{'=' * 60}")
    print(f"\nQuery: {query}")
    
    # Load resources
    embedder, store = load_resources()
    
    # Search
    print(f"\nSearching for relevant documents...")
    results = search(query, embedder, store, k=5)
    
    if not results:
        print("No results found!")
        return
    
    # Display search results
    format_results(results)
    
    # Test with Ollama
    print("\n\nDo you want to test with Ollama LLM? (y/n): ", end="")
    try:
        response = input().strip().lower()
        if response == 'y':
            test_with_ollama(query, results)
    except EOFError:
        # Non-interactive mode, skip LLM test
        print("(skipping LLM test in non-interactive mode)")


if __name__ == '__main__':
    main()
