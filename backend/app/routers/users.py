"""User management (admin only): list, invite, delete."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import func, select

from app.config import get_settings
from app.deps import AdminUser, SessionDep
from app.models.invite import Invite
from app.models.user import User, UserRole
from app.schemas.auth import UserOut
from app.schemas.user import InviteRequest, InviteResponse
from app.services.auth_service import generate_invite_token, hash_invite_token

router = APIRouter(prefix="/users", tags=["users"])

_INVITE_TTL = timedelta(days=7)


@router.get("", response_model=list[UserOut])
async def list_users(_: AdminUser, session: SessionDep) -> list[User]:
    result = await session.execute(select(User).order_by(User.created_at))
    return list(result.scalars().all())


@router.post("/invite", response_model=InviteResponse, status_code=status.HTTP_201_CREATED)
async def invite_user(
    payload: InviteRequest, admin: AdminUser, session: SessionDep
) -> InviteResponse:
    email = str(payload.email).lower()
    if await session.scalar(select(User).where(func.lower(User.email) == email)):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="An account with this email exists."
        )

    raw_token = generate_invite_token()
    expires_at = datetime.now(tz=UTC) + _INVITE_TTL
    invite = Invite(
        email=email,
        role=payload.role,
        token_hash=hash_invite_token(raw_token),
        invited_by=admin.id,
        expires_at=expires_at,
    )
    session.add(invite)
    await session.flush()

    base_url = get_settings().app_base_url.rstrip("/")
    return InviteResponse(
        invite_id=invite.id,
        email=payload.email,
        role=invite.role,
        expires_at=expires_at,
        invite_token=raw_token,
        accept_url=f"{base_url}/register?token={raw_token}",
    )


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: int, admin: AdminUser, session: SessionDep) -> Response:
    if user_id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="You cannot delete your own account."
        )
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    if user.role == UserRole.ADMIN:
        admin_count = await session.scalar(
            select(func.count()).select_from(User).where(User.role == UserRole.ADMIN)
        )
        if (admin_count or 0) <= 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot delete the last administrator.",
            )

    await session.delete(user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
