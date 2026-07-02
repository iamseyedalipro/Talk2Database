"""Provider-agnostic interface for natural-language -> SQL generation."""

from __future__ import annotations

from typing import Any, Literal, Protocol, TypedDict

from pydantic import BaseModel, Field, model_validator


class ChatMessage(TypedDict):
    """One turn of the generation conversation (plain text, provider-agnostic)."""

    role: Literal["user", "assistant"]
    content: str


class SuggestedInterpretation(BaseModel):
    """A concrete rephrasing the user can pick when their question is ambiguous."""

    label: str = Field(description="Short button text, e.g. 'Total completed payments'.")
    description: str = Field(
        description="A complete, self-contained question answerable from the schema."
    )


class SqlGenerationResult(BaseModel):
    """Structured result returned by every provider."""

    status: Literal["ok", "needs_clarification", "unanswerable"]
    sql: str | None = Field(
        default=None, description="A single, read-only SELECT statement (status 'ok' only)."
    )
    explanation: str | None = Field(
        default=None, description="A short, plain-language description of what the query does."
    )
    clarification_question: str | None = Field(
        default=None, description="The question to ask the user back (needs_clarification only)."
    )
    suggested_interpretations: list[SuggestedInterpretation] | None = None

    @model_validator(mode="after")
    def _check_status_fields(self) -> SqlGenerationResult:
        if self.status == "ok" and not (self.sql or "").strip():
            raise ValueError("status 'ok' requires a non-empty sql")
        if self.status == "needs_clarification" and not (self.clarification_question or "").strip():
            raise ValueError("status 'needs_clarification' requires a clarification_question")
        return self


class AIProviderError(RuntimeError):
    """Raised when the provider call fails or returns an unusable result."""


# JSON schema used to constrain provider structured output. Written in OpenAI
# strict mode form (every property required, nullability via type unions),
# which Anthropic tool input schemas accept unchanged.
SQL_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "status": {
            "type": "string",
            "enum": ["ok", "needs_clarification", "unanswerable"],
            "description": (
                "'ok' when the question maps cleanly to the schema; "
                "'needs_clarification' when it does not and you propose interpretations; "
                "'unanswerable' when no interpretation exists."
            ),
        },
        "sql": {
            "type": ["string", "null"],
            "description": "A single read-only SELECT statement. Required when status is 'ok'.",
        },
        "explanation": {
            "type": ["string", "null"],
            "description": "A short, plain-language summary of the query or of why it cannot run.",
        },
        "clarification_question": {
            "type": ["string", "null"],
            "description": (
                "Question to ask the user back. Required when status is 'needs_clarification'."
            ),
        },
        "suggested_interpretations": {
            "type": ["array", "null"],
            "description": "2-4 concrete rephrasings answerable from the schema.",
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string", "description": "Short button text."},
                    "description": {
                        "type": "string",
                        "description": "A complete, self-contained question.",
                    },
                },
                "required": ["label", "description"],
                "additionalProperties": False,
            },
        },
    },
    "required": [
        "status",
        "sql",
        "explanation",
        "clarification_question",
        "suggested_interpretations",
    ],
    "additionalProperties": False,
}

# Structured output for schema-derived example questions.
QUESTIONS_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "questions": {
            "type": "array",
            "minItems": 4,
            "maxItems": 6,
            "items": {"type": "string"},
            "description": "Example natural-language questions answerable from the schema.",
        },
    },
    "required": ["questions"],
    "additionalProperties": False,
}


class LLMProvider(Protocol):
    """Generates SQL from a conversation and a (cacheable) schema block.

    The caller (a connector) supplies the dialect-specific ``system_prompt`` and
    the already-wrapped ``schema_block`` so the provider stays source-agnostic.
    Retry/correction logic lives in the orchestrator (``services/ai/generate.py``);
    providers only render the message list.
    """

    name: str
    model: str

    def generate_sql(
        self, *, messages: list[ChatMessage], system_prompt: str, schema_block: str
    ) -> SqlGenerationResult:
        """Return the structured generation result for the conversation so far.

        Implementations MUST place ``schema_block`` as a stable leading prefix so
        provider prompt caching applies across repeated questions and retries.
        """
        ...

    def suggest_questions(self, *, system_prompt: str, schema_block: str) -> list[str]:
        """Return 4-6 example questions a user could ask about this schema."""
        ...

    def summarize(self, *, system_prompt: str, user_prompt: str) -> str:
        """Return a short plain-text answer summary (no structured output)."""
        ...
