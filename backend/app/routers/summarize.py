"""Natural-language answer summaries for executed query results.

This endpoint sends a **capped sample of result rows** to the AI provider — a
deliberate, opt-in exception to the panel's "schema only, never row data" rule.
It is disabled unless ``ANSWER_SUMMARY_ENABLED=true``, the client must call it
explicitly, and the sample is truncated server-side to the configured
row/column/cell limits before anything leaves the panel. See docs/security.md.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from starlette.concurrency import run_in_threadpool

from app.config import get_settings
from app.deps import CurrentUser, SessionDep
from app.models.query_history import QueryHistory
from app.schemas.summarize import SummarizeRequest, SummarizeResponse
from app.services.ai.base import AIProviderError
from app.services.ai.factory import get_ai_provider
from app.services.ai.prompts import build_summary_system_prompt, build_summary_user_prompt
from app.services.connections import get_owned_connection

router = APIRouter(prefix="/summarize", tags=["summarize"])


def _render_sample(
    columns: list[str],
    rows: list[list[object]],
    *,
    max_rows: int,
    max_columns: int,
    max_cell_chars: int,
) -> tuple[str, bool]:
    """Render a size-capped plain-text table; returns (text, was_truncated_here)."""
    kept_columns = columns[:max_columns]
    kept_rows = rows[:max_rows]
    truncated_here = len(columns) > len(kept_columns) or len(rows) > len(kept_rows)

    def cell(value: object) -> str:
        text = "" if value is None else str(value)
        return text[:max_cell_chars]

    lines = [" | ".join(kept_columns)]
    for row in kept_rows:
        lines.append(" | ".join(cell(v) for v in row[: len(kept_columns)]))
    return "\n".join(lines), truncated_here


@router.post("", response_model=SummarizeResponse)
async def summarize(
    payload: SummarizeRequest, user: CurrentUser, session: SessionDep
) -> SummarizeResponse:
    settings = get_settings()
    if not settings.answer_summary_enabled:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Answer summaries are disabled. Set ANSWER_SUMMARY_ENABLED=true to enable.",
        )

    # Ownership check — the summary is scoped to a connection the user owns.
    await get_owned_connection(session, payload.connection_id, user)

    sample_text, truncated_here = _render_sample(
        payload.columns,
        payload.rows,
        max_rows=settings.answer_summary_max_rows,
        max_columns=settings.answer_summary_max_columns,
        max_cell_chars=settings.answer_summary_max_cell_chars,
    )
    truncated_note = " — sample truncated" if (payload.truncated or truncated_here) else ""

    provider = get_ai_provider()
    try:
        summary = await run_in_threadpool(
            provider.summarize,
            system_prompt=build_summary_system_prompt(),
            user_prompt=build_summary_user_prompt(
                question=payload.question,
                sql=payload.sql,
                table_text=sample_text,
                row_count=payload.row_count,
                truncated_note=truncated_note,
            ),
        )
    except AIProviderError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    if payload.history_id is not None:
        history = await session.get(QueryHistory, payload.history_id)
        if history is not None and history.user_id == user.id:
            history.summary_text = summary
            await session.flush()

    return SummarizeResponse(summary=summary)
