"""
Ominis Health Query Lambda Handler with Authentication
This is an enhanced version that requires API key authentication.
"""

import os
import json
import time
import logging
from typing import Dict, Any

# Import the original handler functions
from handler import (
    search_chunks, 
    format_context, 
    generate_answer,
    logger
)

# Import authentication module
from auth import (
    require_auth,
    log_query_to_strapi,
    extract_api_key_from_event
)


@require_auth(endpoint='query')
def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Authenticated Lambda handler for Ominis Health queries.
    Requires valid API key with 'query' permission.
    """
    start_time = time.time()
    success = False
    error_type = None
    tokens_generated = 0
    sources_used = 0
    
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
        
        logger.info(f"Processing authenticated question: {question[:50]}...")
        
        # Search for relevant chunks
        results = search_chunks(question, k=k)
        sources_used = len(results)
        
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
            success = True
            return response
        
        # Format context and generate answer
        context = format_context(results)
        answer = generate_answer(question, context)
        
        # Estimate tokens (rough approximation)
        tokens_generated = len(answer.split()) * 1.3  # Rough token estimate
        
        # Format sources
        sources = [
            {
                'title': chunk.get('metadata', {}).get('title', 'Sin título'),
                'url': chunk.get('metadata', {}).get('url', ''),
                'score': round(score, 4)
            }
            for chunk, score in results
        ]
        
        success = True
        
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'POST, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type, X-API-Key'
            },
            'body': json.dumps({
                'answer': answer,
                'sources': sources,
                'query': question
            }, ensure_ascii=False)
        }
        
    except Exception as e:
        logger.error(f"Error: {str(e)}", exc_info=True)
        error_type = type(e).__name__
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({'error': str(e)})
        }
    
    finally:
        # Log the query asynchronously
        response_time_ms = int((time.time() - start_time) * 1000)
        api_key = extract_api_key_from_event(event)
        headers = event.get('headers', {}) or {}
        
        # Fire and forget - don't block the response
        try:
            log_query_to_strapi(
                api_key=api_key or '',
                endpoint='query',
                response_time_ms=response_time_ms,
                tokens_generated=int(tokens_generated),
                sources_used=sources_used,
                success=success,
                error_type=error_type,
                user_agent=headers.get('user-agent') or headers.get('User-Agent'),
                ip_address=event.get('requestContext', {}).get('identity', {}).get('sourceIp')
            )
        except:
            pass  # Don't fail if logging fails


@require_auth(endpoint='queryGpu')
def handler_gpu(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Authenticated Lambda handler for GPU-accelerated queries.
    Requires valid API key with 'queryGpu' permission.
    
    This is the same as the regular handler but requires higher permissions.
    """
    # Reuse the main handler logic
    # In production, this would route to the GPU server
    return handler(event, context)


# OPTIONS handler for CORS preflight
def options_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Handle CORS preflight requests"""
    return {
        'statusCode': 200,
        'headers': {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'POST, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type, X-API-Key, Authorization',
            'Access-Control-Max-Age': '86400',
        },
        'body': ''
    }


def main_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Main entry point that handles both authenticated and OPTIONS requests.
    """
    method = event.get('httpMethod', 'POST')
    
    if method == 'OPTIONS':
        return options_handler(event, context)
    
    return handler(event, context)
