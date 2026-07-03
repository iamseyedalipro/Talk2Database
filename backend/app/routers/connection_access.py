"""Admin connection-access manager: grant users access to connections.

A connection is owned by one user; these admin-only endpoints let an admin share
a connection with additional users (read/use access — see
``get_accessible_connection``). The UI is user-first: pick a user, then choose
which connections they can reach.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import delete, select

from app.deps import AdminUser, SessionDep
from app.models.connection import Connection
from app.models.connection_access import ConnectionAccess
from app.models.user import User
from app.schemas.connection_access import ConnectionAccessOut, ConnectionAccessUpdate

router = APIRouter(prefix="/admin/users/{user_id}/connection-access", tags=["admin"])


async def _require_user(session: SessionDep, user_id: int) -> User:
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    return user


@router.get("", response_model=ConnectionAccessOut)
async def get_user_access(user_id: int, _: AdminUser, session: SessionDep) -> ConnectionAccessOut:
    """List the connection ids explicitly granted to a user (excludes owned)."""
    await _require_user(session, user_id)
    rows = await session.scalars(
        select(ConnectionAccess.connection_id).where(ConnectionAccess.user_id == user_id)
    )
    return ConnectionAccessOut(connection_ids=list(rows.all()))


@router.put("", response_model=ConnectionAccessOut)
async def set_user_access(
    user_id: int,
    payload: ConnectionAccessUpdate,
    admin: AdminUser,
    session: SessionDep,
) -> ConnectionAccessOut:
    """Replace a user's full grant set.

    Connection ids that don't exist, or that the user already owns (access there
    is implicit), are silently ignored.
    """
    target = await _require_user(session, user_id)

    requested = set(payload.connection_ids)
    if requested:
        # Keep only real connections that the target user does not already own.
        valid_rows = await session.execute(
            select(Connection.id, Connection.owner_id).where(Connection.id.in_(requested))
        )
        desired = {cid for cid, owner_id in valid_rows.all() if owner_id != target.id}
    else:
        desired = set()

    existing_rows = await session.scalars(
        select(ConnectionAccess.connection_id).where(ConnectionAccess.user_id == user_id)
    )
    existing = set(existing_rows.all())

    to_remove = existing - desired
    to_add = desired - existing

    if to_remove:
        await session.execute(
            delete(ConnectionAccess).where(
                ConnectionAccess.user_id == user_id,
                ConnectionAccess.connection_id.in_(to_remove),
            )
        )
    for connection_id in to_add:
        session.add(
            ConnectionAccess(connection_id=connection_id, user_id=user_id, granted_by=admin.id)
        )
    await session.flush()

    return ConnectionAccessOut(connection_ids=sorted(desired))
