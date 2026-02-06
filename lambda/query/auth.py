"""
API Key Authentication Module for Ominis Health API
Validates API keys against the Strapi backend
"""

import os
import json
import urllib.request
import urllib.error
import logging
import time
from typing import Dict, Any, Optional, Tuple
from functools import lru_cache
import hashlib

logger = logging.getLogger()

# Configuration
STRAPI_URL = os.environ.get('STRAPI_URL', 'http://localhost:1337')
STRAPI_TIMEOUT = int(os.environ.get('STRAPI_TIMEOUT', '5'))
AUTH_CACHE_TTL = int(os.environ.get('AUTH_CACHE_TTL', '300'))  # 5 minutes

# In-memory cache for API key validation (reduces Strapi calls)
_auth_cache: Dict[str, Tuple[Dict, float]] = {}


def get_cache_key(api_key: str) -> str:
    """Create a cache key from API key (using hash for security)"""
    return hashlib.sha256(api_key.encode()).hexdigest()[:16]


def validate_api_key(api_key: str) -> Tuple[bool, Optional[Dict], Optional[str]]:
    """
    Validate an API key against the Strapi backend.
    
    Args:
        api_key: The API key to validate
        
    Returns:
        Tuple of (is_valid, key_info, error_message)
    """
    if not api_key:
        return False, None, "API key is required"
    
    # Check cache first
    cache_key = get_cache_key(api_key)
    if cache_key in _auth_cache:
        cached_info, cached_time = _auth_cache[cache_key]
        if time.time() - cached_time < AUTH_CACHE_TTL:
            logger.debug(f"Using cached auth for key prefix: {api_key[:12]}")
            return True, cached_info, None
    
    # Validate against Strapi
    try:
        payload = json.dumps({"apiKey": api_key}).encode('utf-8')
        
        req = urllib.request.Request(
            f"{STRAPI_URL}/api/api-keys/validate",
            data=payload,
            headers={'Content-Type': 'application/json'}
        )
        
        with urllib.request.urlopen(req, timeout=STRAPI_TIMEOUT) as response:
            result = json.loads(response.read().decode('utf-8'))
            
            if result.get('valid'):
                # Cache the successful validation
                key_info = {
                    'keyId': result.get('keyId'),
                    'owner': result.get('owner'),
                    'permissions': result.get('permissions', {}),
                    'rateLimit': result.get('rateLimit', 100),
                    'rateLimitWindow': result.get('rateLimitWindow', 'hour'),
                }
                _auth_cache[cache_key] = (key_info, time.time())
                return True, key_info, None
            else:
                reason = result.get('reason', 'invalid')
                return False, None, f"API key {reason}"
                
    except urllib.error.HTTPError as e:
        logger.error(f"HTTP error validating API key: {e.code}")
        return False, None, f"Authentication service error: {e.code}"
    except urllib.error.URLError as e:
        logger.error(f"URL error validating API key: {e}")
        # If Strapi is down, allow requests for 5 minutes using cache
        if cache_key in _auth_cache:
            cached_info, cached_time = _auth_cache[cache_key]
            # Extended grace period when Strapi is down
            if time.time() - cached_time < 3600:  # 1 hour grace
                logger.warning("Using stale cache due to Strapi unavailability")
                return True, cached_info, None
        return False, None, "Authentication service unavailable"
    except Exception as e:
        logger.error(f"Error validating API key: {e}")
        return False, None, f"Authentication error: {str(e)}"


def check_permission(key_info: Dict, permission: str) -> bool:
    """
    Check if an API key has a specific permission.
    
    Args:
        key_info: The key info from validation
        permission: The permission to check (e.g., 'query', 'queryGpu', 'sources')
        
    Returns:
        True if permission is granted
    """
    if not key_info:
        return False
    
    permissions = key_info.get('permissions', {})
    return permissions.get(permission, False)


def log_query_to_strapi(
    api_key: str,
    endpoint: str,
    response_time_ms: int,
    tokens_generated: int = 0,
    sources_used: int = 0,
    success: bool = True,
    error_type: str = None,
    user_agent: str = None,
    ip_address: str = None
) -> bool:
    """
    Log a query to Strapi for analytics.
    This is fire-and-forget - doesn't block the response.
    
    Args:
        api_key: The API key used
        endpoint: The endpoint called ('query' or 'query-gpu')
        response_time_ms: Response time in milliseconds
        tokens_generated: Number of tokens generated
        sources_used: Number of sources used
        success: Whether the query was successful
        error_type: Error type if failed
        user_agent: User agent string
        ip_address: IP address (will be hashed)
        
    Returns:
        True if logging succeeded
    """
    try:
        # Hash the query and IP for privacy
        query_hash = hashlib.sha256(api_key.encode()).hexdigest()[:32]
        ip_hash = hashlib.sha256((ip_address or '').encode()).hexdigest()[:32] if ip_address else None
        
        # Get API key ID from cache if available
        cache_key = get_cache_key(api_key)
        api_key_id = None
        if cache_key in _auth_cache:
            key_info, _ = _auth_cache[cache_key]
            api_key_id = key_info.get('keyId')
        
        payload = json.dumps({
            "data": {
                "queryHash": query_hash,
                "endpoint": endpoint,
                "responseTimeMs": response_time_ms,
                "tokensGenerated": tokens_generated,
                "sourcesUsed": sources_used,
                "success": success,
                "errorType": error_type,
                "apiKey": api_key_id,
                "userAgent": user_agent[:255] if user_agent else None,
                "ipHash": ip_hash,
            }
        }).encode('utf-8')
        
        # Get internal API token from environment
        internal_token = os.environ.get('STRAPI_API_TOKEN')
        headers = {'Content-Type': 'application/json'}
        if internal_token:
            headers['Authorization'] = f'Bearer {internal_token}'
        
        req = urllib.request.Request(
            f"{STRAPI_URL}/api/query-logs",
            data=payload,
            headers=headers
        )
        
        with urllib.request.urlopen(req, timeout=STRAPI_TIMEOUT) as response:
            return response.status == 200
            
    except Exception as e:
        # Don't fail the main request if logging fails
        logger.error(f"Failed to log query to Strapi: {e}")
        return False


def create_auth_error_response(message: str, status_code: int = 401) -> Dict[str, Any]:
    """Create a standardized authentication error response"""
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'WWW-Authenticate': 'ApiKey',
        },
        'body': json.dumps({
            'error': {
                'status': status_code,
                'name': 'UnauthorizedError' if status_code == 401 else 'ForbiddenError',
                'message': message,
            }
        })
    }


def extract_api_key_from_event(event: Dict[str, Any]) -> Optional[str]:
    """Extract API key from request headers"""
    headers = event.get('headers', {}) or {}
    
    # Try different header formats (case-insensitive)
    for key in ['x-api-key', 'X-API-Key', 'X-Api-Key', 'authorization', 'Authorization']:
        if key in headers:
            value = headers[key]
            # Handle Bearer token format
            if value.startswith('Bearer '):
                value = value[7:]
            return value
    
    return None


def require_auth(endpoint: str = 'query'):
    """
    Decorator to require API key authentication on a handler.
    
    Args:
        endpoint: The endpoint name for permission checking ('query', 'queryGpu', 'sources')
    """
    def decorator(func):
        def wrapper(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
            # Extract API key
            api_key = extract_api_key_from_event(event)
            
            if not api_key:
                return create_auth_error_response("API key is required. Include X-API-Key header.")
            
            # Validate API key
            is_valid, key_info, error = validate_api_key(api_key)
            
            if not is_valid:
                return create_auth_error_response(error or "Invalid API key")
            
            # Check permission
            if not check_permission(key_info, endpoint):
                return create_auth_error_response(
                    f"API key does not have permission for {endpoint}",
                    status_code=403
                )
            
            # Add auth info to event for handler use
            event['auth'] = {
                'apiKey': api_key,
                'keyInfo': key_info,
            }
            
            return func(event, context)
        
        return wrapper
    return decorator
