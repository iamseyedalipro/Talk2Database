"""Persistence helper for LLM token-usage records.

Recording usage must never break the user's request, so callers wrap this in a
try/except (or rely on the swallowed-error behaviour here) and the panel session
is left usable even when a write fails.
"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.token_usage import TokenUsageRecord
from app.services.ai.base import TokenUsage

logger = logging.getLogger(__name__)


async def record_usage(
    session: AsyncSession,
    *,
    user_id: int,
    connection_id: int | None,
    operation: str,
    provider: str | None,
    model: str | None,
    usage: TokenUsage,
) -> None:
    """Insert one token-usage row. No-op when the call reported zero tokens."""
    if usage.total <= 0:
        return
    record = TokenUsageRecord(
        user_id=user_id,
        connection_id=connection_id,
        operation=operation,
        provider=provider,
        model=model,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        cache_read_tokens=usage.cache_read_tokens,
        cache_write_tokens=usage.cache_write_tokens,
        total_tokens=usage.total,
    )
    session.add(record)
    await session.flush()
