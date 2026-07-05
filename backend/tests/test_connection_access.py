"""Authorization tests for connection access helpers.

Mirrors the DB-free style used elsewhere in the suite: a tiny fake session
stands in for the real one so we exercise the access logic without Postgres.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from app.services.connections import get_accessible_connection, get_owned_connection
from fastapi import HTTPException


class _FakeSession:
    """Returns a fixed connection from ``get`` and a fixed grant from ``scalar``."""

    def __init__(self, conn: Any, grant: Any = None) -> None:
        self._conn = conn
        self._grant = grant

    async def get(self, _model: Any, _pk: Any) -> Any:
        return self._conn

    async def scalar(self, _stmt: Any) -> Any:
        return self._grant


def _conn(owner_id: int = 1) -> SimpleNamespace:
    return SimpleNamespace(id=7, owner_id=owner_id)


def _user(user_id: int, is_admin: bool = False) -> SimpleNamespace:
    return SimpleNamespace(id=user_id, is_admin=is_admin)


OWNER = _user(1)
OTHER = _user(2)
ADMIN = _user(3, is_admin=True)


async def test_accessible_owner() -> None:
    conn = _conn(owner_id=1)
    assert await get_accessible_connection(_FakeSession(conn), 7, OWNER) is conn


async def test_accessible_admin_sees_any() -> None:
    conn = _conn(owner_id=1)
    assert await get_accessible_connection(_FakeSession(conn), 7, ADMIN) is conn


async def test_accessible_granted_user() -> None:
    conn = _conn(owner_id=1)
    # A grant row exists (scalar returns its id) -> access allowed.
    session = _FakeSession(conn, grant=42)
    assert await get_accessible_connection(session, 7, OTHER) is conn


async def test_accessible_denied_without_grant() -> None:
    conn = _conn(owner_id=1)
    session = _FakeSession(conn, grant=None)
    with pytest.raises(HTTPException) as exc:
        await get_accessible_connection(session, 7, OTHER)
    assert exc.value.status_code == 404


async def test_accessible_missing_connection() -> None:
    with pytest.raises(HTTPException) as exc:
        await get_accessible_connection(_FakeSession(None), 7, ADMIN)
    assert exc.value.status_code == 404


async def test_owned_allows_owner_and_admin() -> None:
    conn = _conn(owner_id=1)
    assert await get_owned_connection(_FakeSession(conn), 7, OWNER) is conn
    assert await get_owned_connection(_FakeSession(conn), 7, ADMIN) is conn


async def test_owned_denies_granted_user() -> None:
    # A shared grantee may *use* a connection but never *manage* it.
    conn = _conn(owner_id=1)
    session = _FakeSession(conn, grant=42)
    with pytest.raises(HTTPException) as exc:
        await get_owned_connection(session, 7, OTHER)
    assert exc.value.status_code == 404
