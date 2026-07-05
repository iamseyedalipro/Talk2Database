"""Answer analytical questions grounded in Clarity data and/or user databases."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.deps import CurrentUser, SessionDep
from app.schemas.analysis import AnalysisRequest, AnalysisResponse, AnalysisStepOut
from app.services.ai.base import AIProviderError
from app.services.ai.factory import get_ai_provider
from app.services.analysis.agent import run_analysis

router = APIRouter(prefix="/analysis", tags=["analysis"])


@router.post("", response_model=AnalysisResponse)
async def analyze(
    payload: AnalysisRequest, user: CurrentUser, session: SessionDep
) -> AnalysisResponse:
    try:
        outcome = await run_analysis(
            session,
            user,
            question=payload.question,
            connection_ids=payload.connection_ids,
            include_clarity=payload.include_clarity,
        )
    except AIProviderError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    provider = get_ai_provider()
    return AnalysisResponse(
        answer=outcome.answer,
        steps=[
            AnalysisStepOut(
                connection_id=step.connection_id,
                connection_name=step.connection_name,
                purpose=step.purpose,
                sql=step.sql,
                row_count=step.row_count,
                error=step.error,
            )
            for step in outcome.steps
        ],
        provider=provider.name,
        model=provider.model,
        warnings=outcome.warnings,
    )
