"""Turn a natural-language question into a previewable, read-only SQL SELECT.

This is the HTTP fallback transport; the same flow streams progress events over
``/api/ask/ws`` (see :mod:`app.routers.ask_ws`). Both delegate to
:func:`app.services.ask_flow.run_ask_flow`.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.deps import CurrentUser, SessionDep
from app.schemas.ask import AskRequest, AskResponse
from app.services.ask_flow import AskFlowError, run_ask_flow

router = APIRouter(prefix="/ask", tags=["ask"])


@router.post("", response_model=AskResponse)
async def ask(payload: AskRequest, user: CurrentUser, session: SessionDep) -> AskResponse:
    try:
        outcome = await run_ask_flow(
            session,
            user,
            connection_id=payload.connection_id,
            question=payload.question,
        )
    except AskFlowError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    return outcome.response
