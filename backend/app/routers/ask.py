"""Turn a natural-language question into a previewable, read-only SQL SELECT."""

from __future__ import annotations

from fastapi import APIRouter

from app.deps import CurrentUser, SessionDep
from app.schemas.ask import AskRequest, AskResponse
from app.services.ask_flow import run_ask_flow

router = APIRouter(prefix="/ask", tags=["ask"])


@router.post("", response_model=AskResponse)
async def ask(payload: AskRequest, user: CurrentUser, session: SessionDep) -> AskResponse:
    # Stateless single question; conversational follow-ups live in /chats.
    return await run_ask_flow(session, user, payload.connection_id, payload.question)
