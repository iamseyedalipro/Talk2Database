"""Provider-agnostic interface for natural-language -> SQL generation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, TypedDict

from pydantic import BaseModel, Field, model_validator

ChartType = Literal[
    "bar", "line", "area", "pie", "scatter", "hbar", "radar", "combo", "table", "none"
]


@dataclass(frozen=True)
class TokenUsage:
    """Token counts for a single provider API call.

    ``cache_read_tokens`` / ``cache_write_tokens`` are reported separately from
    ``input_tokens`` by both SDKs (Anthropic prompt caching; OpenAI cached-prompt
    reads — OpenAI has no cache-write billing concept, so it stays 0).
    """

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    @property
    def total(self) -> int:
        return (
            self.input_tokens
            + self.output_tokens
            + self.cache_read_tokens
            + self.cache_write_tokens
        )

    def __add__(self, other: TokenUsage) -> TokenUsage:
        return TokenUsage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            cache_read_tokens=self.cache_read_tokens + other.cache_read_tokens,
            cache_write_tokens=self.cache_write_tokens + other.cache_write_tokens,
        )


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


class ResultSummary(BaseModel):
    """An AI-written one-line summary plus a suggested visualization."""

    summary: str = Field(description="A one or two sentence summary of the result set.")
    chart_type: ChartType = Field(default="none", description="The best chart for these results.")
    x_column: str | None = Field(
        default=None, description="Column for the chart X axis (a label/category/time)."
    )
    y_columns: list[str] | None = Field(
        default=None, description="Numeric columns to plot as series, in order."
    )
    series_column: str | None = Field(
        default=None,
        description="Category column that splits rows into one series per distinct value.",
    )
    stacked: bool = Field(default=False, description="Stack bar/area series.")
    combo_line_columns: list[str] | None = Field(
        default=None, description="For 'combo': the y_columns drawn as lines (the rest are bars)."
    )
    # Legacy single-Y field: not requested from the model, derived from y_columns so
    # stored payloads and older clients keep working.
    y_column: str | None = Field(default=None, description="Numeric column for the chart Y axis.")

    @model_validator(mode="after")
    def _sync_legacy_y(self) -> ResultSummary:
        if self.y_columns and not self.y_column:
            self.y_column = self.y_columns[0]
        elif self.y_column and not self.y_columns:
            self.y_columns = [self.y_column]
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
            "enum": [
                "bar",
                "line",
                "area",
                "pie",
                "scatter",
                "hbar",
                "radar",
                "combo",
                "table",
                "none",
            ],
            "description": "The best chart type for these results.",
        },
        "x_column": {
            "type": ["string", "null"],
            "description": "Column name for the chart X axis, or null.",
        },
        "y_columns": {
            "type": ["array", "null"],
            "items": {"type": "string"},
            "description": "Numeric column names to plot as series, in order, or null.",
        },
        "series_column": {
            "type": ["string", "null"],
            "description": (
                "Low-cardinality category column that groups rows into one series per "
                "distinct value, or null. When set, y_columns holds the single value column."
            ),
        },
        "stacked": {
            "type": "boolean",
            "description": "true to stack bar/area series (parts of a whole per x value).",
        },
        "combo_line_columns": {
            "type": ["array", "null"],
            "items": {"type": "string"},
            "description": (
                "For chart_type 'combo': which y_columns are drawn as lines; the rest "
                "are bars. Null otherwise."
            ),
        },
    },
    "required": [
        "summary",
        "chart_type",
        "x_column",
        "y_columns",
        "series_column",
        "stacked",
        "combo_line_columns",
    ],
    "additionalProperties": False,
}


# --------------------------------------------------------------------------- #
# Tool-using chat (the Analysis agent)
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
class ToolChatMessage:
    """One turn of a tool-using conversation (distinct from :class:`ChatMessage`,
    the plain-text ask thread).

    ``assistant`` turns may carry ``tool_calls``; the following ``user`` turn
    carries the matching ``tool_results``.
    """

    role: Literal["user", "assistant"]
    text: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_results: list[ToolResult] = field(default_factory=list)


@dataclass(frozen=True)
class ChatTurn:
    """What the model produced for one tool-chat turn."""

    text: str | None
    tool_calls: list[ToolCall]
    # Token usage for this single turn. Defaulted so existing callers that build
    # a ``ChatTurn`` positionally (and ignore usage) keep working unchanged.
    usage: TokenUsage = field(default_factory=TokenUsage)


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
    ) -> tuple[SqlGenerationResult, TokenUsage]:
        """Return the structured generation result plus the call's token usage.

        Implementations MUST place ``schema_block`` as a stable leading prefix so
        provider prompt caching applies across repeated questions and retries.
        """
        ...

    def suggest_questions(
        self, *, system_prompt: str, schema_block: str
    ) -> tuple[list[str], TokenUsage]:
        """Return 4-6 example questions a user could ask about this schema."""
        ...

    def summarize_results(
        self, *, system_prompt: str, context: str
    ) -> tuple[ResultSummary, TokenUsage]:
        """Summarize a result set and suggest a chart from a prepared ``context``.

        The caller builds ``context`` from column names/types and locally-computed
        aggregates (plus an optional opted-in row sample), so the provider never
        sees raw row data unless the deployment enabled it.
        """
        ...

    def chat(
        self,
        *,
        system: str,
        messages: list[ToolChatMessage],
        tools: list[ToolSpec],
        force_text: bool = False,
    ) -> ChatTurn:
        """One turn of a tool-using conversation (the Analysis agent).

        With ``force_text=True`` the model must answer in plain text (tools are
        withheld) - used to close out the analysis loop.
        """
        ...
