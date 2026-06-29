"""Tests for password hashing, JWT issuance and invite tokens."""

from __future__ import annotations

from app.services.auth_service import (
    create_access_token,
    decode_access_token,
    generate_invite_token,
    hash_invite_token,
    hash_password,
    verify_password,
)


def test_password_hash_roundtrip() -> None:
    hashed = hash_password("correct horse battery staple")
    assert hashed != "correct horse battery staple"
    assert verify_password("correct horse battery staple", hashed)
    assert not verify_password("wrong password", hashed)


def test_access_token_roundtrip() -> None:
    token, expires_in = create_access_token(user_id=42, role="admin")
    assert expires_in > 0
    payload = decode_access_token(token)
    assert payload["sub"] == "42"
    assert payload["role"] == "admin"


def test_invite_token_hash_is_deterministic_and_tokens_unique() -> None:
    raw = generate_invite_token()
    assert hash_invite_token(raw) == hash_invite_token(raw)
    assert hash_invite_token(raw) != raw
    assert generate_invite_token() != generate_invite_token()
