"""Authentication: login, first-admin bootstrap, invite registration."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select

from app.deps import CurrentUser, SessionDep
from app.models.invite import Invite
from app.models.user import User, UserRole
from app.schemas.auth import (
    BootstrapRequest,
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserOut,
)
from app.services.auth_service import (
    create_access_token,
    hash_invite_token,
    hash_password,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _token_response(user: User) -> TokenResponse:
    token, expires_in = create_access_token(user_id=user.id, role=user.role.value)
    return TokenResponse(
        access_token=token,
        expires_in=expires_in,
        user=UserOut.model_validate(user),
    )


async def _user_count(session: SessionDep) -> int:
    return await session.scalar(select(func.count()).select_from(User)) or 0


@router.get("/bootstrap-available")
async def bootstrap_available(session: SessionDep) -> dict[str, bool]:
    """Whether the first-admin bootstrap is still open (no users exist yet)."""
    return {"available": (await _user_count(session)) == 0}


@router.post("/bootstrap", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def bootstrap(payload: BootstrapRequest, session: SessionDep) -> TokenResponse:
    """Create the very first account as admin. Disabled once any user exists."""
    if await _user_count(session) > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Bootstrap is closed; an account already exists.",
        )
    user = User(
        email=str(payload.email).lower(),
        password_hash=hash_password(payload.password),
        role=UserRole.ADMIN,
    )
    session.add(user)
    await session.flush()
    return _token_response(user)


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, session: SessionDep) -> TokenResponse:
    """Accept an invitation and create the account."""
    email = str(payload.email).lower()
    token_hash = hash_invite_token(payload.invite_token)
    invite = await session.scalar(select(Invite).where(Invite.token_hash == token_hash))

    now = datetime.now(tz=UTC)
    if (
        invite is None
        or invite.accepted_at is not None
        or invite.expires_at < now
        or invite.email.lower() != email
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid, expired, or already-used invitation.",
        )

    if await session.scalar(select(User).where(func.lower(User.email) == email)):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="An account with this email exists."
        )

    user = User(
        email=email,
        password_hash=hash_password(payload.password),
        role=invite.role,
    )
    session.add(user)
    invite.accepted_at = now
    await session.flush()
    return _token_response(user)


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, session: SessionDep) -> TokenResponse:
    email = str(payload.email).lower()
    user = await session.scalar(select(User).where(func.lower(User.email) == email))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password."
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="This account is disabled."
        )
    user.last_login_at = datetime.now(tz=UTC)
    await session.flush()
    return _token_response(user)


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)
