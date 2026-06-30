"""Resolve a stored :class:`Connection` into a ready-to-use connector.

This is the single place that decrypts a data-source secret, so plaintext stays
out of routers and logs.
"""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors import ConnectionConfig, Connector, get_connector
from app.models.connection import Connection
from app.models.user import User
from app.services.crypto import decrypt_secret


async def get_owned_connection(session: AsyncSession, connection_id: int, user: User) -> Connection:
    """Return the connection if it exists and belongs to ``user`` (else 404)."""
    conn = await session.get(Connection, connection_id)
    if conn is None or conn.owner_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found")
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
    """Resolve an owned connection and its connector in one step."""
    connection = await get_owned_connection(session, connection_id, user)
    return connection, build_connector(connection)
