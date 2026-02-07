"""
Pydantic schemas for API key management.
Matches the frontend's expected types (ApiKey, CreateApiKeyData, CreateApiKeyResponse).
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class APIKeyPermissions(BaseModel):
    query: bool = True
    queryGpu: bool = True
    sources: bool = False


class APIKeyOut(BaseModel):
    """Matches frontend's ApiKey type."""
    id: int
    name: str
    keyPrefix: str
    status: str
    permissions: APIKeyPermissions
    rateLimit: int = 100
    rateLimitWindow: str = "minute"
    requestsCount: str = "0"
    lastUsedAt: Optional[str] = None
    expiresAt: Optional[str] = None
    createdAt: str

    model_config = {"from_attributes": True}


class CreateAPIKeyRequest(BaseModel):
    """Matches frontend's CreateApiKeyData."""
    name: str
    description: Optional[str] = None
    permissions: Optional[APIKeyPermissions] = None
    rateLimit: Optional[int] = 100
    rateLimitWindow: Optional[str] = "minute"
    expiresAt: Optional[str] = None


class CreateAPIKeyResponse(BaseModel):
    """Matches frontend's CreateApiKeyResponse."""
    data: APIKeyOut
    apiKey: str  # Full key, shown only once
    message: str
