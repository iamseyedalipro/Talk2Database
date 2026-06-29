"""Password hashing, JWT issuance/verification, and invite tokens."""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from pwdlib import PasswordHash

from app.config import get_settings

_password_hasher = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return _password_hasher.verify(password, password_hash)


def create_access_token(*, user_id: int, role: str) -> tuple[str, int]:
    """Return a signed JWT and its lifetime in seconds."""
    settings = get_settings()
    expires_in = settings.jwt_expire_minutes * 60
    now = datetime.now(tz=UTC)
    payload = {
        "sub": str(user_id),
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=expires_in)).timestamp()),
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, expires_in


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and verify a JWT, raising ``jwt.PyJWTError`` if invalid/expired."""
    settings = get_settings()
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])


def generate_invite_token() -> str:
    """Return a fresh, URL-safe invite token (the raw value, shown once)."""
    return secrets.token_urlsafe(32)


def hash_invite_token(raw_token: str) -> str:
    """Hash an invite token for storage/lookup (never store the raw token)."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
