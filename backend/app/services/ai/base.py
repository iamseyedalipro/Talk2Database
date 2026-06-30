"""Provider-agnostic interface for natural-language -> SQL generation."""

from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel, Field


class GeneratedSQL(BaseModel):
    """Structured result returned by every provider."""

    sql: str = Field(description="A single, read-only SELECT statement.")
    explanation: str | None = Field(
        default=None, description="A short, plain-language description of what the query does."
    )


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
