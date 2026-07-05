"""Admin endpoints for editing the AI prompts used by Ask and Analysis."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.deps import AdminUser, SessionDep
from app.schemas.prompts import PromptOut, PromptUpdate
from app.services.ai.prompts import DEFAULT_PROMPTS
from app.services.prompt_store import (
    ASK_PROMPT_KEY,
    PROMPT_KEYS,
    get_prompt,
    reset_prompt,
    set_prompt,
)

router = APIRouter(prefix="/prompts", tags=["prompts"])

_META: dict[str, tuple[str, str]] = {
    ASK_PROMPT_KEY: (
        "Ask (natural language to SQL)",
        "System prompt for the Ask page. Must keep the {label} placeholder - it is "
        "replaced with the SQL dialect (e.g. PostgreSQL). Escape literal braces as {{ and }}.",
    ),
    "analysis_system": (
        "Analysis",
        "System prompt for the Analysis page. Sets how the AI investigates and answers "
        "using Clarity metrics and read-only SQL queries.",
    ),
}


def _check_key(key: str) -> None:
    if key not in PROMPT_KEYS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown prompt '{key}'")


async def _prompt_out(session: SessionDep, key: str) -> PromptOut:
    content, is_customized = await get_prompt(session, key)
    title, description = _META.get(key, (key, ""))
    return PromptOut(
        key=key,
        title=title,
        description=description,
        content=content,
        default_content=DEFAULT_PROMPTS[key],
        is_customized=is_customized,
    )


@router.get("", response_model=list[PromptOut])
async def list_prompts(admin: AdminUser, session: SessionDep) -> list[PromptOut]:
    return [await _prompt_out(session, key) for key in sorted(PROMPT_KEYS)]


@router.put("/{key}", response_model=PromptOut)
async def update_prompt(
    key: str, payload: PromptUpdate, admin: AdminUser, session: SessionDep
) -> PromptOut:
    _check_key(key)
    if key == ASK_PROMPT_KEY:
        try:
            payload.content.format(label="PostgreSQL")
        except (KeyError, IndexError, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "The template failed to render: check that it uses {label} (and only "
                    "{label}) as a placeholder, and that literal braces are escaped as "
                    "{{ and }}."
                ),
            ) from exc
    await set_prompt(session, key, payload.content)
    return await _prompt_out(session, key)


@router.post("/{key}/reset", response_model=PromptOut)
async def reset_prompt_endpoint(key: str, admin: AdminUser, session: SessionDep) -> PromptOut:
    _check_key(key)
    await reset_prompt(session, key)
    return await _prompt_out(session, key)
