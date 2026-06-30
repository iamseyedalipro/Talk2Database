"""Tests for at-rest encryption of connection secrets."""

from __future__ import annotations

import pytest
from cryptography.fernet import Fernet


@pytest.fixture
def crypto_with_key(monkeypatch: pytest.MonkeyPatch):
    """Provide the crypto module wired to a fresh Fernet key."""
    from app.config import get_settings
    from app.services import crypto

    key = Fernet.generate_key().decode()
    monkeypatch.setenv("CONNECTIONS_SECRET_KEY", key)
    get_settings.cache_clear()
    crypto._fernet.cache_clear()
    yield crypto
    get_settings.cache_clear()
    crypto._fernet.cache_clear()


def test_encrypt_decrypt_roundtrip(crypto_with_key) -> None:
    token = crypto_with_key.encrypt_secret("hunter2")
    assert token != "hunter2"
    assert crypto_with_key.decrypt_secret(token) == "hunter2"


def test_missing_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.config import get_settings
    from app.services import crypto

    monkeypatch.setenv("CONNECTIONS_SECRET_KEY", "")
    get_settings.cache_clear()
    crypto._fernet.cache_clear()
    try:
        with pytest.raises(crypto.SecretCryptoError):
            crypto.encrypt_secret("x")
    finally:
        get_settings.cache_clear()
        crypto._fernet.cache_clear()
