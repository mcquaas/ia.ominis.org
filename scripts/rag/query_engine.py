"""
RAG Query Engine for Ominis Health LLM
Retrieves relevant context and generates answers using LLM
"""

import os
import json
import boto3
from typing import List, Dict, Any, Optional, Tuple
import logging
import numpy as np

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class RAGQueryEngine:
    """RAG-based query engine for health questions"""
    
    def __init__(
        self,
        embeddings_bucket: str = 'ominis-health-embeddings',
        vector_prefix: str = 'vectors',
        region: str = 'us-east-2',
        use_sagemaker: bool = False,
        sagemaker_endpoint: str = 'ominis-biomistral-endpoint',
        use_bedrock: bool = True,
        bedrock_model: str = 'anthropic.claude-3-haiku-20240307-v1:0'
    ):
        """
        Initialize RAG query engine
        
        Args:
            embeddings_bucket: S3 bucket with vector store
            vector_prefix: S3 prefix for vector store
            region: AWS region
            use_sagemaker: Use SageMaker endpoint for LLM
            sagemaker_endpoint: SageMaker endpoint name
            use_bedrock: Use AWS Bedrock for LLM (recommended for MVP)
            bedrock_model: Bedrock model ID
        """
        self.region = region
        self.use_sagemaker = use_sagemaker
        self.use_bedrock = use_bedrock
        self.sagemaker_endpoint = sagemaker_endpoint
        self.bedrock_model = bedrock_model
        
        # Initialize clients
        if use_sagemaker:
            self.sagemaker = boto3.client('sagemaker-runtime', region_name=region)
        if use_bedrock:
            self.bedrock = boto3.client('bedrock-runtime', region_name=region)
        
        # Load vector store and embedder
        self.vector_store = None
        self.embedder = None
        self.embeddings_bucket = embeddings_bucket
        self.vector_prefix = vector_prefix
    
    def load_resources(self):
        """Load vector store and embedding model"""
        from vector_store import FAISSVectorStore
        from embedder import EmbeddingGenerator
        
        logger.info("Loading vector store from S3...")
        self.vector_store = FAISSVectorStore.load_from_s3(
            self.embeddings_bucket, 
            self.vector_prefix, 
            self.region
        )
        
        logger.info("Loading embedding model...")
        self.embedder = EmbeddingGenerator()
    
    def retrieve(self, query: str, k: int = 5) -> List[Tuple[Dict[str, Any], float]]:
        """
        Retrieve relevant documents for a query
        
        Args:
            query: User question
            k: Number of documents to retrieve
            
        Returns:
            List of (chunk, score) tuples
        """
        if self.embedder is None or self.vector_store is None:
            self.load_resources()
        
        # Generate query embedding
        query_embedding = self.embedder.embed_texts([query])[0]
        
        # Search vector store
        results = self.vector_store.search(query_embedding, k=k)
        
        return results
    
    def format_context(self, results: List[Tuple[Dict[str, Any], float]]) -> str:
        """
        Format retrieved chunks as context for the LLM
        
        Args:
            results: List of (chunk, score) tuples
            
        Returns:
            Formatted context string
        """
        context_parts = []
        
        for i, (chunk, score) in enumerate(results):
            source = chunk.get('metadata', {}).get('url', 'Unknown source')
            title = chunk.get('metadata', {}).get('title', 'Untitled')
            
            context_parts.append(f"""
[Fuente {i+1}]
Título: {title}
URL: {source}
Contenido:
{chunk['content']}
---""")
        
        return "\n".join(context_parts)
    
    def build_prompt(self, query: str, context: str) -> str:
        """
        Build the prompt for the LLM
        
        Args:
            query: User question
            context: Retrieved context
            
        Returns:
            Complete prompt
        """
        system_prompt = """Eres un asistente médico especializado de Ominis Health, respaldado por FUNSALUD. 
Tu objetivo es proporcionar información de salud precisa y útil basada en las fuentes proporcionadas.

INSTRUCCIONES:
1. Responde SOLO basándote en la información proporcionada en las fuentes.
2. Si las fuentes no contienen información suficiente, indícalo claramente.
3. Siempre cita las fuentes que uses (por número).
4. Usa un lenguaje claro y accesible.
5. No proporciones diagnósticos médicos. Recomienda consultar a un profesional cuando sea apropiado.
6. Responde en español."""

        user_prompt = f"""Pregunta del usuario: {query}

FUENTES DISPONIBLES:
{context}

Proporciona una respuesta completa basada en las fuentes anteriores. Incluye las referencias a las fuentes usadas."""

        return system_prompt, user_prompt
    
    def generate_with_bedrock(self, system_prompt: str, user_prompt: str) -> str:
        """
        Generate response using AWS Bedrock
        
        Args:
            system_prompt: System instructions
            user_prompt: User prompt with context
            
        Returns:
            Generated response
        """
        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 1024,
            "system": system_prompt,
            "messages": [
                {"role": "user", "content": user_prompt}
            ]
        })
        
        response = self.bedrock.invoke_model(
            modelId=self.bedrock_model,
            body=body,
            contentType='application/json',
            accept='application/json'
        )
        
        result = json.loads(response['body'].read())
        return result['content'][0]['text']
    
    def generate_with_sagemaker(self, system_prompt: str, user_prompt: str) -> str:
        """
        Generate response using SageMaker endpoint (BioMistral)
        
        Args:
            system_prompt: System instructions
            user_prompt: User prompt with context
            
        Returns:
            Generated response
        """
        prompt = f"""<s>[INST] {system_prompt}

{user_prompt} [/INST]"""

        payload = {
            "inputs": prompt,
            "parameters": {
                "max_new_tokens": 1024,
                "temperature": 0.7,
                "top_p": 0.9,
                "do_sample": True
            }
        }
        
        response = self.sagemaker.invoke_endpoint(
            EndpointName=self.sagemaker_endpoint,
            ContentType='application/json',
            Body=json.dumps(payload)
        )
        
        result = json.loads(response['Body'].read().decode())
        
        # Extract generated text
        if isinstance(result, list):
            return result[0].get('generated_text', '').split('[/INST]')[-1].strip()
        return result.get('generated_text', '').split('[/INST]')[-1].strip()
    
    def query(self, question: str, k: int = 5) -> Dict[str, Any]:
        """
        Process a health question and return answer with sources
        
        Args:
            question: User question
            k: Number of sources to retrieve
            
        Returns:
            Response with answer and sources
        """
        logger.info(f"Processing query: {question}")
        
        # Retrieve relevant context
        results = self.retrieve(question, k=k)
        
        if not results:
            return {
                'answer': 'Lo siento, no encontré información relevante para responder tu pregunta.',
                'sources': [],
                'query': question
            }
        
        # Format context
        context = self.format_context(results)
        
        # Build prompt
        system_prompt, user_prompt = self.build_prompt(question, context)
        
        # Generate answer
        if self.use_bedrock:
            answer = self.generate_with_bedrock(system_prompt, user_prompt)
        elif self.use_sagemaker:
            answer = self.generate_with_sagemaker(system_prompt, user_prompt)
        else:
            raise ValueError("No LLM backend configured")
        
        # Extract sources
        sources = [
            {
                'title': chunk.get('metadata', {}).get('title', 'Untitled'),
                'url': chunk.get('metadata', {}).get('url', ''),
                'score': float(score)
            }
            for chunk, score in results
        ]
        
        return {
            'answer': answer,
            'sources': sources,
            'query': question
        }


# Lambda handler for AWS Lambda deployment
def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    AWS Lambda handler for RAG queries
    
    Args:
        event: Lambda event with 'question' field
        context: Lambda context
        
    Returns:
        API Gateway response
    """
    try:
        # Parse request
        body = event.get('body', '{}')
        if isinstance(body, str):
            body = json.loads(body)
        
        question = body.get('question', '')
        k = body.get('num_sources', 5)
        
        if not question:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'Question is required'})
            }
        
        # Initialize engine (will be cached in warm starts)
        engine = RAGQueryEngine(use_bedrock=True)
        
        # Process query
        result = engine.query(question, k=k)
        
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps(result, ensure_ascii=False)
        }
        
    except Exception as e:
        logger.error(f"Error processing query: {e}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }


if __name__ == '__main__':
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python query_engine.py '<question>'")
        sys.exit(1)
    
    question = sys.argv[1]
    
    engine = RAGQueryEngine(use_bedrock=True)
    engine.load_resources()
    
    result = engine.query(question)
    
    print("\n" + "=" * 60)
    print("QUERY RESULT")
    print("=" * 60)
    print(f"\nQuestion: {result['query']}")
    print(f"\nAnswer:\n{result['answer']}")
    print(f"\nSources:")
    for i, source in enumerate(result['sources']):
        print(f"  {i+1}. {source['title']} ({source['score']:.2f})")
        print(f"     {source['url']}")
