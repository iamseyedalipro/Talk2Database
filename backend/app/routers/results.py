"""AI-explained results: a one-line summary plus a suggested chart.

By default only column names/types and locally-computed aggregates are sent to
the model (the no-row-data promise). The result rows arrive from the user's own
browser; the backend strips them to statistics before calling the AI unless
``AI_ALLOW_SAMPLE_ROWS`` is enabled.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from starlette.concurrency import run_in_threadpool

from app.config import get_settings
from app.deps import CurrentUser
from app.schemas.results import SummarizeRequest
from app.services.ai.base import AIProviderError, ResultSummary
from app.services.ai.factory import get_ai_provider
from app.services.results_summary import build_summary_context, summary_system_prompt

router = APIRouter(prefix="/results", tags=["results"])


@router.post("/summarize", response_model=ResultSummary)
async def summarize(payload: SummarizeRequest, user: CurrentUser) -> ResultSummary:
    if not payload.columns or not payload.rows:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="There are no results to summarize.",
        )

    settings = get_settings()
    context = build_summary_context(
        question=payload.question,
        columns=payload.columns,
        rows=payload.rows,
        settings=settings,
    )

    provider = get_ai_provider()
    try:
        return await run_in_threadpool(
            provider.summarize_results,
            system_prompt=summary_system_prompt(),
            context=context,
        )
    except AIProviderError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
