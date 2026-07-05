"""Read stored Clarity snapshots back out: analysis context and availability."""

from __future__ import annotations

import json
from datetime import date
from typing import Any, TypedDict

from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.clarity import ClaritySnapshot


class ClarityAvailability(TypedDict):
    available: bool
    latest_data_date: str | None
    days_stored: int


async def clarity_availability(session: AsyncSession) -> ClarityAvailability:
    """Whether any Clarity data exists, and how fresh it is."""
    result = await session.execute(
        select(
            func.max(ClaritySnapshot.data_date),
            func.count(distinct(ClaritySnapshot.data_date)),
        ).where(ClaritySnapshot.status == "success")
    )
    latest, days = result.one()
    return ClarityAvailability(
        available=latest is not None,
        latest_data_date=latest.isoformat() if isinstance(latest, date) else None,
        days_stored=int(days or 0),
    )


async def load_clarity_context(
    session: AsyncSession, *, days: int = 7, max_chars: int = 12_000
) -> str | None:
    """Serialize the most recent stored Clarity metrics for the LLM.

    Newest days first so truncation drops the oldest data. Returns ``None``
    when nothing is stored yet.
    """
    date_rows = await session.execute(
        select(ClaritySnapshot.data_date)
        .where(ClaritySnapshot.status == "success")
        .distinct()
        .order_by(ClaritySnapshot.data_date.desc())
        .limit(days)
    )
    dates = list(date_rows.scalars())
    if not dates:
        return None

    sections: list[str] = []
    used = 0
    truncated = False
    for day in dates:
        snap_rows = await session.execute(
            select(ClaritySnapshot)
            .where(
                ClaritySnapshot.data_date == day,
                ClaritySnapshot.status == "success",
            )
            .order_by(ClaritySnapshot.combo_key)
        )
        lines = [f"## {day.isoformat()}"]
        for snap in snap_rows.scalars():
            payload: Any = snap.payload
            lines.append(f"- {snap.combo_key}: {json.dumps(payload, separators=(',', ':'))}")
        section = "\n".join(lines)
        if used + len(section) > max_chars:
            truncated = True
            break
        sections.append(section)
        used += len(section)

    if not sections:
        # Even the newest day alone exceeds the cap - include it hard-truncated.
        sections = [section[:max_chars]]
        truncated = True

    header = (
        "Microsoft Clarity metrics (aggregated per day; each line is one dimension "
        "breakdown as raw JSON):"
    )
    footer = "\n(older days omitted to fit the context budget)" if truncated else ""
    return header + "\n\n" + "\n\n".join(sections) + footer
