"""In-process scheduler for the end-of-day Clarity fetch.

An :class:`AsyncIOScheduler` lives for the lifetime of the FastAPI app (see the
lifespan in ``app.main``). The single cron job's time/timezone comes from the
admin-editable settings; saving new Clarity settings calls
:func:`reschedule_clarity_job` to apply them without a restart.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, tzinfo
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.db.panel import get_sessionmaker
from app.services.app_settings import DEFAULT_FETCH_TIME, DEFAULT_TIMEZONE, get_clarity_config
from app.services.clarity.fetcher import ClarityNotConfiguredError, run_fetch

logger = logging.getLogger(__name__)

CLARITY_JOB_ID = "clarity_daily_fetch"

_scheduler: AsyncIOScheduler | None = None


async def _clarity_job() -> None:
    """The scheduled end-of-day fetch. Owns its session and commit."""
    async with get_sessionmaker()() as session:
        try:
            await run_fetch(session, trigger="scheduled")
            await session.commit()
        except ClarityNotConfiguredError:
            logger.info("Scheduled Clarity fetch skipped: no API token configured.")
            await session.rollback()
        except Exception:
            logger.exception("Scheduled Clarity fetch failed.")
            await session.rollback()


def _parse_fetch_time(value: str) -> tuple[int, int]:
    hour_s, _, minute_s = value.partition(":")
    hour, minute = int(hour_s), int(minute_s or 0)
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(value)
    return hour, minute


def _build_trigger(fetch_time: str, timezone: str) -> CronTrigger:
    try:
        hour, minute = _parse_fetch_time(fetch_time)
    except ValueError:
        hour, minute = _parse_fetch_time(DEFAULT_FETCH_TIME)
    try:
        tz: tzinfo = ZoneInfo(timezone)
    except Exception:
        tz = ZoneInfo(DEFAULT_TIMEZONE)
    return CronTrigger(hour=hour, minute=minute, timezone=tz)


async def reschedule_clarity_job() -> None:
    """(Re)apply the configured fetch time/timezone to the cron job."""
    if _scheduler is None:
        return
    fetch_time, timezone = DEFAULT_FETCH_TIME, DEFAULT_TIMEZONE
    try:
        async with get_sessionmaker()() as session:
            config = await get_clarity_config(session)
            fetch_time, timezone = config.fetch_time, config.timezone
    except Exception:
        # e.g. the panel DB is not migrated yet - keep the default schedule.
        logger.warning("Could not read Clarity settings; scheduling at the default time.")
    _scheduler.add_job(
        _clarity_job,
        trigger=_build_trigger(fetch_time, timezone),
        id=CLARITY_JOB_ID,
        replace_existing=True,
        coalesce=True,
        misfire_grace_time=3600,
    )
    logger.info("Clarity daily fetch scheduled at %s (%s).", fetch_time, timezone)


def next_run_time() -> datetime | None:
    """When the daily fetch will next run (UTC), or None when not scheduled."""
    if _scheduler is None:
        return None
    job = _scheduler.get_job(CLARITY_JOB_ID)
    if job is None or job.next_run_time is None:
        return None
    next_run: datetime = job.next_run_time
    return next_run.astimezone(UTC)


async def start_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        return
    _scheduler = AsyncIOScheduler(timezone=UTC)
    _scheduler.start()
    await reschedule_clarity_job()


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
