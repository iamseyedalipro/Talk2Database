"""Provider-agnostic interfaces for natural-language -> SQL generation and
tool-using chat (the analysis agent)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

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


# --------------------------------------------------------------------------- #
# Tool-using chat (analysis agent)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ToolSpec:
    """A tool the model may call, described provider-neutrally."""

    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass(frozen=True)
class ToolCall:
    """A tool invocation requested by the model."""

    id: str
    name: str
    input: dict[str, Any]


@dataclass(frozen=True)
class ToolResult:
    """The outcome of executing a :class:`ToolCall`, fed back to the model."""

    tool_call_id: str
    content: str
    is_error: bool = False


@dataclass
class ChatMessage:
    """One conversation turn.

    ``assistant`` turns may carry ``tool_calls``; the following ``user`` turn
    carries the matching ``tool_results``.
    """

    role: Literal["user", "assistant"]
    text: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_results: list[ToolResult] = field(default_factory=list)


@dataclass(frozen=True)
class ChatTurn:
    """What the model produced for one turn."""

    text: str | None
    tool_calls: list[ToolCall]


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

    def chat(
        self,
        *,
        system: str,
        messages: list[ChatMessage],
        tools: list[ToolSpec],
        force_text: bool = False,
    ) -> ChatTurn:
        """One turn of a tool-using conversation.

        With ``force_text=True`` the model must answer in plain text (tools are
        withheld) - used to close out the analysis loop.
        """
        ...
