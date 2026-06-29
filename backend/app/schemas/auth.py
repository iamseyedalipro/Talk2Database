"""Request/response schemas for authentication."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.user import UserRole


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class BootstrapRequest(BaseModel):
    """Create the very first (admin) account while no users exist."""

    email: EmailStr
    password: str = Field(min_length=8, max_length=256)


class RegisterRequest(BaseModel):
    """Accept an invitation and create the account."""

    invite_token: str = Field(min_length=1)
    email: EmailStr
    password: str = Field(min_length=8, max_length=256)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    role: UserRole
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut
