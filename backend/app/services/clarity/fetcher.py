"""End-of-day Clarity fetch: spend the 10-requests/day budget and store results.

A run fetches yesterday's data (``numOfDays=1``, relative to the configured
timezone) once per configured dimension combination, storing each raw response
as a :class:`~app.models.clarity.ClaritySnapshot` under one
:class:`~app.models.clarity.ClarityFetchRun`. The caller owns the commit.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta, tzinfo
from zoneinfo import ZoneInfo

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.clarity import ClarityFetchRun, ClaritySnapshot
from app.services.app_settings import ClarityConfig, combo_key, get_clarity_config
from app.services.clarity.client import ClarityAPIError, fetch_insights

logger = logging.getLogger(__name__)

DAILY_REQUEST_BUDGET = 10


class ClarityNotConfiguredError(RuntimeError):
    """No usable Clarity API token has been configured."""


def plan_combos(
    combos: list[list[str]], requests_used: int, budget: int = DAILY_REQUEST_BUDGET
) -> list[list[str]]:
    """Truncate the configured combos to what the remaining budget allows."""
    remaining = max(0, budget - requests_used)
    return combos[:remaining]


async def requests_used_today(session: AsyncSession) -> int:
    """API requests attempted during the current UTC day.

    Summed from the (never-deleted) fetch-run log, so refetches that replace a
    day's snapshots still count. We assume Clarity's daily limit resets on UTC
    day boundaries; the sum is our best local approximation of the budget.
    """
    day_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    result = await session.execute(
        select(func.coalesce(func.sum(ClarityFetchRun.requests_attempted), 0)).where(
            ClarityFetchRun.created_at >= day_start
        )
    )
    return int(result.scalar_one())


def _data_date(config: ClarityConfig) -> date:
    try:
        tz: tzinfo = ZoneInfo(config.timezone)
    except Exception:
        tz = UTC
    return (datetime.now(tz) - timedelta(days=1)).date()


async def run_fetch(session: AsyncSession, *, trigger: str) -> ClarityFetchRun:
    """Execute one fetch run; returns the (flushed, uncommitted) run row."""
    config = await get_clarity_config(session)
    if not config.token:
        raise ClarityNotConfiguredError(
            "Clarity is not configured. Save an API token in the admin panel first."
        )

    data_date = _data_date(config)
    used = await requests_used_today(session)
    planned = plan_combos(config.dimension_combos, used)

    run = ClarityFetchRun(
        trigger=trigger,
        data_date=data_date,
        status="running",
        requests_attempted=0,
        requests_succeeded=0,
    )
    session.add(run)
    await session.flush()

    if not planned:
        run.status = "failed"
        run.finished_at = datetime.now(UTC)
        run.error_summary = (
            f"Daily Clarity request budget exhausted ({used}/{DAILY_REQUEST_BUDGET} "
            "requests already used today)."
        )
        await session.flush()
        return run

    skipped = len(config.dimension_combos) - len(planned)
    errors: list[str] = []
    if skipped:
        errors.append(
            f"{skipped} combination(s) skipped: only {len(planned)} of the "
            f"{DAILY_REQUEST_BUDGET}-request daily budget remained."
        )

    abort = False
    for dimensions in planned:
        key = combo_key(dimensions)
        run.requests_attempted += 1

        # A refetch for the same day replaces the previous snapshot.
        await session.execute(
            delete(ClaritySnapshot).where(
                ClaritySnapshot.data_date == data_date,
                ClaritySnapshot.combo_key == key,
            )
        )

        snapshot = ClaritySnapshot(
            fetch_run_id=run.id,
            data_date=data_date,
            combo_key=key,
            dimensions=list(dimensions),
            num_of_days=1,
        )
        try:
            snapshot.payload = await fetch_insights(config.token, dimensions=dimensions)
            snapshot.status = "success"
            run.requests_succeeded += 1
        except ClarityAPIError as exc:
            snapshot.status = "error"
            snapshot.error = str(exc)
            errors.append(f"{key}: {exc}")
            # Auth failures and rate limits will fail every remaining request
            # too - stop instead of burning budget.
            abort = exc.is_auth_error or exc.is_rate_limited
        session.add(snapshot)
        await session.flush()
        if abort:
            errors.append("Remaining combinations skipped after a fatal error.")
            break

    if run.requests_succeeded == 0:
        run.status = "failed"
    elif run.requests_succeeded < len(config.dimension_combos):
        run.status = "partial"
    else:
        run.status = "success"
    run.finished_at = datetime.now(UTC)
    run.error_summary = "\n".join(errors) or None
    await session.flush()
    logger.info(
        "Clarity fetch (%s) for %s finished: %s (%d/%d succeeded)",
        trigger,
        data_date,
        run.status,
        run.requests_succeeded,
        run.requests_attempted,
    )
    return run
