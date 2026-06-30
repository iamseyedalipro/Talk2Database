"""System status: AI configuration, supported source types, connection count."""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import func, select

from app.config import get_settings
from app.connectors import supported_types
from app.deps import CurrentUser, SessionDep
from app.models.connection import Connection
from app.schemas.system import SystemStatus

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/status", response_model=SystemStatus)
async def system_status(user: CurrentUser, session: SessionDep) -> SystemStatus:
    settings = get_settings()
    count = await session.scalar(
        select(func.count()).select_from(Connection).where(Connection.owner_id == user.id)
    )
    return SystemStatus(
        provider=settings.ai_provider.value,
        model=settings.ai_model,
        connection_count=int(count or 0),
        supported_types=supported_types(),
    )
