"""Request/response schemas for user management."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr

from app.models.user import UserRole


class InviteRequest(BaseModel):
    email: EmailStr
    role: UserRole = UserRole.USER


class UserSelfUpdate(BaseModel):
    """Fields a user may change on their own account."""

    language: Literal["en", "fa"] | None = None


class UserDirectoryEntry(BaseModel):
    """Minimal user identity for share pickers (available to any signed-in user)."""

    id: int
    email: str


class InviteResponse(BaseModel):
    invite_id: int
    email: EmailStr
    role: UserRole
    expires_at: datetime
    # The raw token is returned exactly once, embedded in the acceptance link.
    invite_token: str
    accept_url: str
