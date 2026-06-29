"""Request/response schemas for user management."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr

from app.models.user import UserRole


class InviteRequest(BaseModel):
    email: EmailStr
    role: UserRole = UserRole.USER


class InviteResponse(BaseModel):
    invite_id: int
    email: EmailStr
    role: UserRole
    expires_at: datetime
    # The raw token is returned exactly once, embedded in the acceptance link.
    invite_token: str
    accept_url: str
