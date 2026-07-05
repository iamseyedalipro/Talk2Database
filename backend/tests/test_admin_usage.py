"""Integration tests for token-usage recording and the admin usage report.

Uses an in-memory SQLite async engine so the aggregation SQL runs for real
(``func.sum`` / ``func.date`` grouping), rather than mocking the query layer.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from app.db.base import Base
from app.deps import require_admin
from app.models.connection import Connection, DataSourceType
from app.models.token_usage import TokenUsageRecord
from app.models.user import User, UserRole
from app.routers import admin_usage
from app.services.ai.base import TokenUsage
from app.services.token_usage import record_usage
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


@pytest_asyncio.fixture()
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


async def _seed_users(session: AsyncSession) -> tuple[User, User]:
    alice = User(email="alice@x.com", password_hash="h", role=UserRole.ADMIN)
    bob = User(email="bob@x.com", password_hash="h", role=UserRole.USER)
    session.add_all([alice, bob])
    await session.flush()
    return alice, bob


async def test_record_usage_writes_row(session: AsyncSession) -> None:
    alice, _bob = await _seed_users(session)
    await record_usage(
        session,
        user_id=alice.id,
        connection_id=None,
        operation="generate_sql",
        provider="anthropic",
        model="claude",
        usage=TokenUsage(input_tokens=10, output_tokens=4, cache_read_tokens=2),
    )
    rows = (await session.execute(TokenUsageRecord.__table__.select())).all()
    assert len(rows) == 1
    assert rows[0].total_tokens == 16


async def test_record_usage_skips_zero(session: AsyncSession) -> None:
    alice, _bob = await _seed_users(session)
    await record_usage(
        session,
        user_id=alice.id,
        connection_id=None,
        operation="generate_sql",
        provider="anthropic",
        model="claude",
        usage=TokenUsage(),
    )
    rows = (await session.execute(TokenUsageRecord.__table__.select())).all()
    assert rows == []


async def test_usage_report_aggregates(session: AsyncSession) -> None:
    alice, bob = await _seed_users(session)
    conn = Connection(
        owner_id=alice.id,
        name="db",
        type=DataSourceType.POSTGRES,
        host="h",
        port=5432,
        database="d",
        username="u",
        secret_encrypted="s",
    )
    session.add(conn)
    await session.flush()

    # Alice: two anthropic calls; Bob: one openai call.
    await record_usage(
        session,
        user_id=alice.id,
        connection_id=conn.id,
        operation="generate_sql",
        provider="anthropic",
        model="claude",
        usage=TokenUsage(input_tokens=100, output_tokens=20),
    )
    await record_usage(
        session,
        user_id=alice.id,
        connection_id=conn.id,
        operation="summarize_results",
        provider="anthropic",
        model="claude",
        usage=TokenUsage(input_tokens=10, output_tokens=5),
    )
    await record_usage(
        session,
        user_id=bob.id,
        connection_id=None,
        operation="generate_sql",
        provider="openai",
        model="gpt",
        usage=TokenUsage(input_tokens=50, cache_read_tokens=10),
    )

    report = await admin_usage.usage_report(
        _admin=alice, session=session, date_from=None, date_to=None
    )

    assert report.totals.total_tokens == 100 + 20 + 10 + 5 + 50 + 10
    assert report.totals.call_count == 3
    assert report.totals.cache_read_tokens == 10

    # by_user ordered by total desc: Alice (135) before Bob (60).
    assert [u.label for u in report.by_user] == ["alice@x.com", "bob@x.com"]
    assert report.by_user[0].total_tokens == 135
    assert report.by_user[0].call_count == 2

    providers = {p.label: p.total_tokens for p in report.by_provider}
    assert providers == {"anthropic": 135, "openai": 60}

    models = {m.label for m in report.by_model}
    assert models == {"claude", "gpt"}

    # All rows share one day (created_at server default) -> a single daily point.
    assert len(report.daily) == 1
    assert report.daily[0].total_tokens == report.totals.total_tokens


async def test_usage_report_window_filters(session: AsyncSession) -> None:
    alice, _bob = await _seed_users(session)
    await record_usage(
        session,
        user_id=alice.id,
        connection_id=None,
        operation="generate_sql",
        provider="anthropic",
        model="claude",
        usage=TokenUsage(input_tokens=100),
    )
    # A window entirely in the future excludes today's row.
    future = datetime(2999, 1, 1, tzinfo=UTC)
    report = await admin_usage.usage_report(
        _admin=alice, session=session, date_from=future, date_to=None
    )
    assert report.totals.call_count == 0
    assert report.by_user == []
    assert report.daily == []


async def test_usage_endpoint_requires_admin() -> None:
    admin = User(email="a@x.com", password_hash="h", role=UserRole.ADMIN)
    normal = User(email="n@x.com", password_hash="h", role=UserRole.USER)
    assert await require_admin(user=admin) is admin
    with pytest.raises(HTTPException) as excinfo:
        await require_admin(user=normal)
    assert excinfo.value.status_code == 403
