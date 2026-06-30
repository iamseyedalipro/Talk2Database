"""Persisted schema snapshots — introspect once per connection, reuse everywhere.

A snapshot is built by introspecting a connection's live data source and stored
per connection. Serving a question reads the latest stored snapshot for that
connection instead of re-introspecting, so there is no per-question
introspection cost. Snapshots rebuild on demand (lazily on first use, or when a
caller explicitly refreshes after a schema change).
"""

from __future__ import annotations

from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.connectors import Connector
from app.models.schema_snapshot import SchemaSnapshot
from app.services.schema.serialize import fingerprint, serialize_schema


async def get_current_snapshot(
    session: AsyncSession, connection_id: int
) -> SchemaSnapshot | None:
    """Return the latest snapshot for a connection, or ``None`` if none exists."""
    result = await session.execute(
        select(SchemaSnapshot)
        .where(SchemaSnapshot.connection_id == connection_id)
        .order_by(SchemaSnapshot.version.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def rebuild_snapshot(
    session: AsyncSession, connection_id: int, connector: Connector
) -> SchemaSnapshot:
    """Introspect the connection and store a new snapshot if the schema changed.

    If the structure is identical to the current snapshot (same fingerprint) the
    existing row is returned unchanged, avoiding churn.
    """
    schema = await run_in_threadpool(connector.introspect)
    new_fingerprint = fingerprint(schema)

    current = await get_current_snapshot(session, connection_id)
    if current is not None and current.fingerprint == new_fingerprint:
        return current

    snapshot = SchemaSnapshot(
        connection_id=connection_id,
        version=(current.version + 1) if current else 1,
        fingerprint=new_fingerprint,
        content_text=serialize_schema(schema),
        content_json=cast("dict[str, Any]", schema),
        table_count=len(schema["tables"]),
    )
    session.add(snapshot)
    await session.flush()
    return snapshot


async def ensure_snapshot(
    session: AsyncSession, connection_id: int, connector: Connector
) -> SchemaSnapshot:
    """Return the current snapshot for a connection, building one on first use."""
    current = await get_current_snapshot(session, connection_id)
    if current is not None:
        return current
    return await rebuild_snapshot(session, connection_id, connector)
