"""Provider-agnostic interface for natural-language -> SQL generation."""

from __future__ import annotations

from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field

ChartType = Literal["bar", "line", "table", "none"]


class GeneratedSQL(BaseModel):
    """Structured result returned by every provider."""

    sql: str = Field(description="A single, read-only SELECT statement.")
    explanation: str | None = Field(
        default=None, description="A short, plain-language description of what the query does."
    )


class ResultSummary(BaseModel):
    """An AI-written one-line summary plus a suggested visualization."""

    summary: str = Field(description="A one or two sentence summary of the result set.")
    chart_type: ChartType = Field(default="none", description="The best chart for these results.")
    x_column: str | None = Field(
        default=None, description="Column for the chart X axis (a label/category/time)."
    )
    y_column: str | None = Field(default=None, description="Numeric column for the chart Y axis.")


class AIProviderError(RuntimeError):
    """Raised when the provider call fails or returns an unusable result."""


# JSON schema used to constrain provider output to {sql, explanation}.
SQL_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "sql": {
            "type": "string",
            "description": "A single read-only SELECT statement.",
        },
        "explanation": {
            "type": "string",
            "description": "A short, plain-language summary of the query.",
        },
    },
    "required": ["sql", "explanation"],
    "additionalProperties": False,
}


# JSON schema used to constrain provider output to a result summary + chart hint.
RESULT_SUMMARY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "summary": {
            "type": "string",
            "description": "A one or two sentence plain-language summary of the results.",
        },
        "chart_type": {
            "type": "string",
            "enum": ["bar", "line", "table", "none"],
            "description": "The best chart type for these results.",
        },
        "x_column": {
            "type": ["string", "null"],
            "description": "Column name for the chart X axis, or null.",
        },
        "y_column": {
            "type": ["string", "null"],
            "description": "Numeric column name for the chart Y axis, or null.",
        },
    },
    "required": ["summary", "chart_type", "x_column", "y_column"],
    "additionalProperties": False,
}


class LLMProvider(Protocol):
    """Generates SQL from a question and a (cacheable) schema block.

    The caller (a connector) supplies the dialect-specific ``system_prompt`` and
    the already-wrapped ``schema_block`` so the provider stays source-agnostic.
    """

    name: str
    model: str

    def generate_sql(self, *, question: str, system_prompt: str, schema_block: str) -> GeneratedSQL:
        """Return SQL answering ``question`` grounded in ``schema_block``.

        Implementations MUST place ``schema_block`` as a stable leading prefix so
        provider prompt caching applies across repeated questions.
        """
        ...

    def summarize_results(self, *, system_prompt: str, context: str) -> ResultSummary:
        """Summarize a result set and suggest a chart from a prepared ``context``.

        The caller builds ``context`` from column names/types and locally-computed
        aggregates (plus an optional opted-in row sample), so the provider never
        sees raw row data unless the deployment enabled it.
        """
        ...
