"""Admin endpoints for the Ask analysis mode toggle and exploratory row cap.

Both values live in the ``app_settings`` key/value table so they take effect
immediately without a restart. When analysis mode is ON, every Ask runs the
agentic investigation loop (table discovery + bounded read-only exploratory
queries whose sampled rows are sent to the AI provider).
"""

from __future__ import annotations

from fastapi import APIRouter

from app.deps import AdminUser, SessionDep
from app.schemas.ask_settings import AskSettingsOut, AskSettingsUpdate
from app.services.app_settings import (
    KEY_ASK_ANALYSIS_MODE,
    KEY_ASK_ANALYSIS_ROW_CAP,
    get_ask_runtime_settings,
    set_setting,
)

router = APIRouter(prefix="/admin/ask-settings", tags=["ask-settings"])


async def _current(session: SessionDep) -> AskSettingsOut:
    analysis_mode, row_cap = await get_ask_runtime_settings(session)
    return AskSettingsOut(analysis_mode=analysis_mode, row_cap=row_cap)


@router.get("", response_model=AskSettingsOut)
async def get_ask_settings(admin: AdminUser, session: SessionDep) -> AskSettingsOut:
    return await _current(session)


@router.put("", response_model=AskSettingsOut)
async def update_ask_settings(
    payload: AskSettingsUpdate, admin: AdminUser, session: SessionDep
) -> AskSettingsOut:
    await set_setting(session, KEY_ASK_ANALYSIS_MODE, payload.analysis_mode)
    await set_setting(session, KEY_ASK_ANALYSIS_ROW_CAP, payload.row_cap)
    return await _current(session)
