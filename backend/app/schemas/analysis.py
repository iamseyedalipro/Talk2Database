"""Schemas for the data-analysis section."""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class AnalysisRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    connection_ids: list[int] = Field(default_factory=list, max_length=5)
    include_clarity: bool = False

    @model_validator(mode="after")
    def _at_least_one_source(self) -> AnalysisRequest:
        if not self.connection_ids and not self.include_clarity:
            raise ValueError("Select at least one data source (Clarity or a connection).")
        return self


class AnalysisStepOut(BaseModel):
    connection_id: int | None = None
    connection_name: str | None = None
    purpose: str | None = None
    sql: str
    row_count: int | None = None
    error: str | None = None


class AnalysisResponse(BaseModel):
    answer: str
    steps: list[AnalysisStepOut] = Field(default_factory=list)
    provider: str
    model: str
    warnings: list[str] = Field(default_factory=list)
