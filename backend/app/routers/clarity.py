"""Admin endpoints for the Microsoft Clarity integration.

Settings (token, schedule, dimension combinations), manual fetch, run history
and budget status. ``/availability`` is the one non-admin endpoint - the
Analysis page uses it to decide whether the Clarity source can be selected.
"""

from __future__ import annotations

from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.deps import AdminUser, CurrentUser, SessionDep
from app.models.clarity import ClarityFetchRun, ClaritySnapshot
from app.schemas.clarity import (
    ClarityAvailabilityOut,
    ClarityRunOut,
    ClaritySettingsOut,
    ClaritySettingsUpdate,
    ClaritySnapshotOut,
    ClarityStatusOut,
)
from app.services.app_settings import (
    ALLOWED_DIMENSIONS,
    KEY_CLARITY_COMBOS,
    KEY_CLARITY_FETCH_TIME,
    KEY_CLARITY_PROJECT_ID,
    KEY_CLARITY_TIMEZONE,
    KEY_CLARITY_TOKEN,
    get_clarity_config,
    set_setting,
    validate_combos,
)
from app.services.clarity.fetcher import (
    DAILY_REQUEST_BUDGET,
    ClarityNotConfiguredError,
    requests_used_today,
    run_fetch,
)
from app.services.clarity.reader import clarity_availability
from app.services.crypto import SecretCryptoError, encrypt_secret
from app.services.scheduler import next_run_time, reschedule_clarity_job

router = APIRouter(prefix="/clarity", tags=["clarity"])


async def _settings_out(session: SessionDep) -> ClaritySettingsOut:
    config = await get_clarity_config(session)
    return ClaritySettingsOut(
        token_set=config.token is not None,
        project_id=config.project_id,
        fetch_time=config.fetch_time,
        timezone=config.timezone,
        dimension_combos=config.dimension_combos,
        allowed_dimensions=list(ALLOWED_DIMENSIONS),
        next_run_at=next_run_time(),
    )


@router.get("/settings", response_model=ClaritySettingsOut)
async def get_settings_endpoint(admin: AdminUser, session: SessionDep) -> ClaritySettingsOut:
    return await _settings_out(session)


@router.put("/settings", response_model=ClaritySettingsOut)
async def update_settings(
    payload: ClaritySettingsUpdate, admin: AdminUser, session: SessionDep
) -> ClaritySettingsOut:
    if payload.timezone is not None:
        try:
            ZoneInfo(payload.timezone)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Unknown timezone '{payload.timezone}'. Use an IANA name like 'UTC'.",
            ) from exc
        await set_setting(session, KEY_CLARITY_TIMEZONE, payload.timezone)

    if payload.dimension_combos is not None:
        try:
            validate_combos(payload.dimension_combos)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
            ) from exc
        await set_setting(session, KEY_CLARITY_COMBOS, payload.dimension_combos)

    if payload.fetch_time is not None:
        await set_setting(session, KEY_CLARITY_FETCH_TIME, payload.fetch_time)

    if payload.project_id is not None:
        await set_setting(session, KEY_CLARITY_PROJECT_ID, payload.project_id or None)

    if payload.api_token:  # empty string = keep the stored token
        try:
            encrypted = encrypt_secret(payload.api_token)
        except SecretCryptoError as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
            ) from exc
        await set_setting(session, KEY_CLARITY_TOKEN, encrypted)

    await session.commit()
    await reschedule_clarity_job()
    return await _settings_out(session)


@router.post("/fetch-now", response_model=ClarityRunOut)
async def fetch_now(admin: AdminUser, session: SessionDep) -> ClarityRunOut:
    try:
        run = await run_fetch(session, trigger="manual")
    except ClarityNotConfiguredError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return await _run_out(session, run)


async def _run_out(session: SessionDep, run: ClarityFetchRun) -> ClarityRunOut:
    snapshots = await session.execute(
        select(ClaritySnapshot)
        .where(ClaritySnapshot.fetch_run_id == run.id)
        .order_by(ClaritySnapshot.id)
    )
    return ClarityRunOut(
        id=run.id,
        trigger=run.trigger,
        data_date=run.data_date,
        status=run.status,
        requests_attempted=run.requests_attempted,
        requests_succeeded=run.requests_succeeded,
        created_at=run.created_at,
        finished_at=run.finished_at,
        error_summary=run.error_summary,
        snapshots=[
            ClaritySnapshotOut(
                combo_key=snap.combo_key,
                dimensions=list(snap.dimensions or []),
                status=snap.status,
                error=snap.error,
            )
            for snap in snapshots.scalars()
        ],
    )


@router.get("/runs", response_model=list[ClarityRunOut])
async def list_runs(admin: AdminUser, session: SessionDep, limit: int = 20) -> list[ClarityRunOut]:
    limit = max(1, min(limit, 100))
    runs = await session.execute(
        select(ClarityFetchRun).order_by(ClarityFetchRun.id.desc()).limit(limit)
    )
    return [await _run_out(session, run) for run in runs.scalars()]


@router.get("/status", response_model=ClarityStatusOut)
async def get_status(admin: AdminUser, session: SessionDep) -> ClarityStatusOut:
    config = await get_clarity_config(session)
    availability = await clarity_availability(session)
    return ClarityStatusOut(
        configured=config.token is not None,
        requests_used_today=await requests_used_today(session),
        daily_budget=DAILY_REQUEST_BUDGET,
        latest_data_date=availability["latest_data_date"],
        days_stored=availability["days_stored"],
        next_run_at=next_run_time(),
    )


@router.get("/availability", response_model=ClarityAvailabilityOut)
async def get_availability(user: CurrentUser, session: SessionDep) -> ClarityAvailabilityOut:
    availability = await clarity_availability(session)
    return ClarityAvailabilityOut(**availability)
