"""System status: AI configuration, supported source types, connection count."""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import func, select

from app.config import get_settings
from app.connectors import supported_types
from app.deps import CurrentUser, SessionDep
from app.models.connection import Connection
from app.models.connection_access import ConnectionAccess
from app.schemas.system import SystemStatus

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/status", response_model=SystemStatus)
async def system_status(user: CurrentUser, session: SessionDep) -> SystemStatus:
    settings = get_settings()
    # Count the connections the caller can use: admins see all; others count
    # the ones they own plus any shared with them.
    query = select(func.count()).select_from(Connection)
    if not user.is_admin:
        query = query.where(
            (Connection.owner_id == user.id)
            | Connection.id.in_(
                select(ConnectionAccess.connection_id).where(ConnectionAccess.user_id == user.id)
            )
        )
    count = await session.scalar(query)
    return SystemStatus(
        provider=settings.ai_provider.value,
        model=settings.ai_model,
        connection_count=int(count or 0),
        supported_types=supported_types(),
    )
