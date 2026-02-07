"""
Pydantic schemas for authentication requests and responses.
Matches the frontend's expected API contract (Strapi-compatible format).
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


# --- Role schema (matches frontend User.role) ---

class RoleOut(BaseModel):
    id: int
    name: str
    type: str


# --- User schemas ---

class UserOut(BaseModel):
    """User response matching frontend's User type."""
    id: int
    username: str
    email: str
    role: RoleOut
    confirmed: bool = True
    blocked: bool = False
    createdAt: str
    updatedAt: str

    model_config = {"from_attributes": True}


class AuthResponse(BaseModel):
    """Login/register response matching frontend's AuthResponse type."""
    jwt: str
    user: UserOut


# --- Request schemas ---

class LoginRequest(BaseModel):
    """Login request matching frontend's LoginCredentials type."""
    identifier: str  # email or username
    password: str


class RegisterRequest(BaseModel):
    """Register request matching frontend's RegisterData type."""
    username: str = Field(..., min_length=3, max_length=100)
    email: EmailStr
    password: str = Field(..., min_length=8)


class ChangePasswordRequest(BaseModel):
    currentPassword: str
    password: str
    passwordConfirmation: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    code: str
    password: str
    passwordConfirmation: str


class UpdateUserRequest(BaseModel):
    username: Optional[str] = None
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    institution: Optional[str] = None
    bio: Optional[str] = None
    blocked: Optional[bool] = None
    role: Optional[str] = None  # superadmin only
