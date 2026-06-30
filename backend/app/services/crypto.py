"""Symmetric encryption for data-source secrets stored in the panel database.

Connection passwords are encrypted at rest with Fernet (AES-128-CBC + HMAC)
using ``CONNECTIONS_SECRET_KEY`` from the environment. Plaintext secrets never
touch the database and are never returned by the API.
"""

from __future__ import annotations

from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings


class SecretCryptoError(RuntimeError):
    """Raised when secrets cannot be encrypted/decrypted (missing/invalid key)."""


@lru_cache
def _fernet() -> Fernet:
    key = get_settings().connections_secret_key
    if not key:
        raise SecretCryptoError(
            "CONNECTIONS_SECRET_KEY is not set. Generate one with "
            "`python -c \"from cryptography.fernet import Fernet; "
            'print(Fernet.generate_key().decode())"` and add it to .env.'
        )
    try:
        return Fernet(key.encode("utf-8"))
    except (ValueError, TypeError) as exc:  # malformed key
        raise SecretCryptoError(f"CONNECTIONS_SECRET_KEY is invalid: {exc}") from exc


def encrypt_secret(plaintext: str) -> str:
    """Return a Fernet token (str) for ``plaintext``."""
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_secret(token: str) -> str:
    """Return the plaintext for a Fernet ``token``."""
    try:
        return _fernet().decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise SecretCryptoError(
            "Could not decrypt a stored secret. The CONNECTIONS_SECRET_KEY may have changed."
        ) from exc
