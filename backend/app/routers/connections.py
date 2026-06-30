"""Manage data-source connections: create, list, edit, test, delete.

Connections are owned per user. Secrets are encrypted on the way in and never
returned. This router replaces the old import/upload flow — instead of copying a
database into the panel, a user points the panel at their own database.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

from app.deps import CurrentUser, SessionDep
from app.models.connection import Connection
from app.schemas.connections import (
    ConnectionCreate,
    ConnectionOut,
    ConnectionTestResult,
    ConnectionUpdate,
)
from app.schemas.schema import DbSchema
from app.services.connections import build_connector, get_owned_connection, load_connector
from app.services.crypto import SecretCryptoError, encrypt_secret
from app.services.schema.cache import ensure_snapshot, rebuild_snapshot

router = APIRouter(prefix="/connections", tags=["connections"])


@router.get("", response_model=list[ConnectionOut])
async def list_connections(user: CurrentUser, session: SessionDep) -> list[Connection]:
    result = await session.execute(
        select(Connection)
        .where(Connection.owner_id == user.id)
        .order_by(Connection.created_at.desc())
    )
    return list(result.scalars().all())


@router.post("", response_model=ConnectionOut, status_code=status.HTTP_201_CREATED)
async def create_connection(
    payload: ConnectionCreate, user: CurrentUser, session: SessionDep
) -> Connection:
    try:
        secret = encrypt_secret(payload.password)
    except SecretCryptoError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc
    connection = Connection(
        owner_id=user.id,
        name=payload.name,
        type=payload.type,
        host=payload.host,
        port=payload.port,
        database=payload.database,
        username=payload.username,
        secret_encrypted=secret,
        options=payload.options,
    )
    session.add(connection)
    try:
        await session.flush()
    except Exception as exc:  # unique (owner, name) violation, etc.
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A connection with that name already exists.",
        ) from exc
    return connection


@router.get("/{connection_id}", response_model=ConnectionOut)
async def get_connection(
    connection_id: int, user: CurrentUser, session: SessionDep
) -> Connection:
    return await get_owned_connection(session, connection_id, user)


@router.patch("/{connection_id}", response_model=ConnectionOut)
async def update_connection(
    connection_id: int,
    payload: ConnectionUpdate,
    user: CurrentUser,
    session: SessionDep,
) -> Connection:
    connection = await get_owned_connection(session, connection_id, user)
    data = payload.model_dump(exclude_unset=True)
    if "password" in data:
        password = data.pop("password")
        if password is not None:
            connection.secret_encrypted = encrypt_secret(password)
    for key, value in data.items():
        setattr(connection, key, value)
    await session.flush()
    return connection


@router.delete("/{connection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_connection(
    connection_id: int, user: CurrentUser, session: SessionDep
) -> Response:
    connection = await get_owned_connection(session, connection_id, user)
    await session.delete(connection)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{connection_id}/test", response_model=ConnectionTestResult)
async def test_connection(
    connection_id: int, user: CurrentUser, session: SessionDep
) -> ConnectionTestResult:
    connection = await get_owned_connection(session, connection_id, user)
    try:
        connector = build_connector(connection)
        ok = await run_in_threadpool(connector.reachable)
    except Exception as exc:
        return ConnectionTestResult(ok=False, message=str(exc))
    return ConnectionTestResult(
        ok=ok, message=None if ok else "Could not open a read-only connection."
    )


def _schema_error(connection: Connection, exc: Exception) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=f"Could not read the schema of '{connection.name}': {exc}",
    )


@router.get("/{connection_id}/schema", response_model=DbSchema)
async def get_connection_schema(
    connection_id: int, user: CurrentUser, session: SessionDep
) -> DbSchema:
    """Return the cached structural schema (tables/columns/keys) for a connection.

    Built lazily on first use; powers the schema browser. Never reads row data.
    """
    connection, connector = await load_connector(session, connection_id, user)
    try:
        snapshot = await ensure_snapshot(session, connection.id, connector)
    except Exception as exc:
        raise _schema_error(connection, exc) from exc
    return DbSchema.model_validate(snapshot.content_json)


@router.post("/{connection_id}/schema/refresh", response_model=DbSchema)
async def refresh_connection_schema(
    connection_id: int, user: CurrentUser, session: SessionDep
) -> DbSchema:
    """Re-introspect the connection and return the rebuilt schema (after a DDL change)."""
    connection, connector = await load_connector(session, connection_id, user)
    try:
        snapshot = await rebuild_snapshot(session, connection.id, connector)
    except Exception as exc:
        raise _schema_error(connection, exc) from exc
    return DbSchema.model_validate(snapshot.content_json)
