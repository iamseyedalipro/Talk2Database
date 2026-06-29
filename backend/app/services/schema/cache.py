"""Persisted schema snapshots — introspect once per import, reuse everywhere.

Rebuilding a snapshot happens only after an import/sync (or lazily on the first
question if none exists yet). Serving a question reads the latest stored snapshot
instead of touching the user-data database, so there is no per-question
introspection cost.
"""

from __future__ import annotations

from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.models.schema_snapshot import SchemaSnapshot
from app.services.schema.introspect import introspect_userdata
from app.services.schema.serialize import fingerprint, serialize_schema


async def get_current_snapshot(session: AsyncSession) -> SchemaSnapshot | None:
    """Return the latest snapshot, or ``None`` if nothing has been imported."""
    result = await session.execute(
        select(SchemaSnapshot).order_by(SchemaSnapshot.version.desc()).limit(1)
    )
    return result.scalar_one_or_none()


async def rebuild_snapshot(session: AsyncSession) -> SchemaSnapshot:
    """Introspect the user-data DB and store a new snapshot if the schema changed.

    If the structure is identical to the current snapshot (same fingerprint) the
    existing row is returned unchanged, avoiding churn.
    """
    schema = await run_in_threadpool(introspect_userdata)
    new_fingerprint = fingerprint(schema)

    current = await get_current_snapshot(session)
    if current is not None and current.fingerprint == new_fingerprint:
        return current

    snapshot = SchemaSnapshot(
        version=(current.version + 1) if current else 1,
        fingerprint=new_fingerprint,
        content_text=serialize_schema(schema),
        content_json=cast("dict[str, Any]", schema),
        table_count=len(schema["tables"]),
    )
    session.add(snapshot)
    await session.flush()
    return snapshot


async def ensure_snapshot(session: AsyncSession) -> SchemaSnapshot:
    """Return the current snapshot, building one on first use if needed."""
    current = await get_current_snapshot(session)
    if current is not None:
        return current
    return await rebuild_snapshot(session)
