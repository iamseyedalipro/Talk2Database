"""Resolve a stored :class:`Connection` into a ready-to-use connector.

This is the single place that decrypts a data-source secret, so plaintext stays
out of routers and logs.
"""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors import ConnectionConfig, Connector, get_connector
from app.models.connection import Connection
from app.models.connection_access import ConnectionAccess
from app.models.user import User
from app.services.crypto import decrypt_secret

_NOT_FOUND = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found")


async def get_owned_connection(session: AsyncSession, connection_id: int, user: User) -> Connection:
    """Return the connection for a caller allowed to **manage** it (else 404).

    Managing (edit settings, rotate password, delete) is limited to the owner
    and admins. Shared grantees cannot manage a connection — use
    :func:`get_accessible_connection` for read/use paths instead.
    """
    conn = await session.get(Connection, connection_id)
    if conn is None or not (conn.owner_id == user.id or user.is_admin):
        raise _NOT_FOUND
    return conn


async def get_accessible_connection(
    session: AsyncSession, connection_id: int, user: User
) -> Connection:
    """Return the connection for a caller allowed to **use** it (else 404).

    Use access covers the owner, any admin (admins see every connection), and
    any user explicitly granted access via :class:`ConnectionAccess`.
    """
    conn = await session.get(Connection, connection_id)
    if conn is None:
        raise _NOT_FOUND
    if conn.owner_id == user.id or user.is_admin:
        return conn
    granted = await session.scalar(
        select(ConnectionAccess.id).where(
            ConnectionAccess.connection_id == connection_id,
            ConnectionAccess.user_id == user.id,
        )
    )
    if granted is None:
        raise _NOT_FOUND
    return conn


def build_connector(connection: Connection) -> Connector:
    """Construct a connector from a stored connection (decrypting its secret)."""
    config = ConnectionConfig(
        type=str(connection.type),
        host=connection.host,
        port=connection.port,
        database=connection.database,
        username=connection.username,
        password=decrypt_secret(connection.secret_encrypted),
        options=connection.options or {},
    )
    return get_connector(config)


async def load_connector(
    session: AsyncSession, connection_id: int, user: User
) -> tuple[Connection, Connector]:
    """Resolve an accessible connection and its connector in one step."""
    connection = await get_accessible_connection(session, connection_id, user)
    return connection, build_connector(connection)
