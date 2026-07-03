"""Admin audit feed: who asked what, across all users (privacy-gated).

Builds on ``query_history``. Only questions, generated SQL and execution status
are exposed — never row data, which the panel never stores. The feed can be
turned off entirely with ``ADMIN_AUDIT_ENABLED=false``.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.config import get_settings
from app.deps import AdminUser, SessionDep
from app.models.query_history import QueryHistory, QueryStatus
from app.models.user import User
from app.schemas.audit import AuditItem

router = APIRouter(prefix="/admin/audit", tags=["admin"])


@router.get("", response_model=list[AuditItem])
async def list_audit(
    _admin: AdminUser,
    session: SessionDep,
    user_id: int | None = Query(default=None),
    connection_id: int | None = Query(default=None),
    status_filter: QueryStatus | None = Query(default=None, alias="status"),
    q: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[AuditItem]:
    if not get_settings().admin_audit_enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="The audit feed is disabled."
        )

    stmt = select(QueryHistory, User.email).join(User, User.id == QueryHistory.user_id)
    if user_id is not None:
        stmt = stmt.where(QueryHistory.user_id == user_id)
    if connection_id is not None:
        stmt = stmt.where(QueryHistory.connection_id == connection_id)
    if status_filter is not None:
        stmt = stmt.where(QueryHistory.last_status == status_filter)
    if q:
        stmt = stmt.where(QueryHistory.question.ilike(f"%{q}%"))
    stmt = stmt.order_by(QueryHistory.created_at.desc()).limit(limit).offset(offset)

    result = await session.execute(stmt)
    items: list[AuditItem] = []
    for history, email in result.all():
        item = AuditItem.model_validate(history, from_attributes=True)
        item.user_email = email
        items.append(item)
    return items
