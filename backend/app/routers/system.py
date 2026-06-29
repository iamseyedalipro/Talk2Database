"""System status: data mode, AI configuration, connectivity, schema size."""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

from app.config import get_settings
from app.db.userdata import userdata_reachable
from app.deps import CurrentUser, SessionDep
from app.models.import_run import ImportRun
from app.schemas.imports import ImportRunOut, SystemStatus
from app.services.schema.cache import get_current_snapshot

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/status", response_model=SystemStatus)
async def system_status(_: CurrentUser, session: SessionDep) -> SystemStatus:
    settings = get_settings()
    snapshot = await get_current_snapshot(session)
    last_import = await session.scalar(
        select(ImportRun).order_by(ImportRun.started_at.desc()).limit(1)
    )
    connected = await run_in_threadpool(userdata_reachable)

    return SystemStatus(
        import_mode=settings.import_mode.value,
        provider=settings.ai_provider.value,
        model=settings.ai_model,
        userdata_connected=connected,
        schema_table_count=snapshot.table_count if snapshot else 0,
        schema_version=snapshot.version if snapshot else None,
        last_import=ImportRunOut.model_validate(last_import) if last_import else None,
    )
