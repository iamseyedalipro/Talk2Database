"""Schemas for the natural-language -> SQL generation step."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    connection_id: int
    question: str = Field(min_length=1, max_length=4000)


class SuggestedInterpretationOut(BaseModel):
    """A concrete rephrasing the user can click to re-ask with."""

    label: str
    description: str


class SuggestedQuestionsResponse(BaseModel):
    """Schema-derived example questions, cached per schema snapshot version."""

    questions: list[str] = Field(default_factory=list)


class AskResponse(BaseModel):
    history_id: int
    # "ok": generated_sql is ready to preview/run.
    # "needs_clarification": the question did not map to the schema; the UI shows
    #   clarification_question + suggested_interpretations as clickable options.
    # "unanswerable": no interpretation exists for this schema (see explanation).
    # "verification_failed": retries were exhausted and generated_sql still
    #   references identifiers that do not exist (listed in invalid_identifiers).
    status: Literal["ok", "needs_clarification", "unanswerable", "verification_failed"] = "ok"
    generated_sql: str | None = None
    explanation: str | None = None
    clarification_question: str | None = None
    suggested_interpretations: list[SuggestedInterpretationOut] = Field(default_factory=list)
    invalid_identifiers: list[str] = Field(default_factory=list)
    retry_count: int = 0
    dialect: str = "postgres"
    provider: str
    model: str
    # Non-fatal notes, e.g. "schema was trimmed to the most relevant tables".
    warnings: list[str] = Field(default_factory=list)
