"""Tests for the AI providers using fake SDK clients (no network)."""

from __future__ import annotations

import json
from typing import Any

import anthropic
import pytest
from app.services.ai.anthropic_provider import AnthropicProvider
from app.services.ai.base import (
    SQL_OUTPUT_SCHEMA,
    AIProviderError,
    ChatMessage,
    ToolChatMessage,
)
from app.services.ai.openai_provider import OpenAIProvider

_QUESTION: list[ChatMessage] = [{"role": "user", "content": "Question: q?"}]

_OK_PAYLOAD = {
    "status": "ok",
    "sql": "SELECT 1",
    "explanation": "one",
    "clarification_question": None,
    "suggested_interpretations": None,
}


# --- Anthropic fakes ------------------------------------------------------- #
class _Block:
    def __init__(self, type_: str, name: str | None = None, data: dict | None = None) -> None:
        self.type = type_
        self.name = name
        self.input = data


class _AnthUsage:
    def __init__(
        self, input_tokens: int, output_tokens: int, cache_read: int, cache_write: int
    ) -> None:
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.cache_read_input_tokens = cache_read
        self.cache_creation_input_tokens = cache_write


class _AnthResponse:
    def __init__(self, content: list[_Block], usage: _AnthUsage | None = None) -> None:
        self.content = content
        self.usage = usage


class _AnthMessages:
    def __init__(self, response: _AnthResponse) -> None:
        self._response = response
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> _AnthResponse:
        self.calls.append(kwargs)
        return self._response


class _AnthClient:
    def __init__(self, response: _AnthResponse) -> None:
        self.messages = _AnthMessages(response)


def test_anthropic_returns_structured_sql_and_caches_schema() -> None:
    provider = AnthropicProvider(api_key="x", model="claude-test")
    client = _AnthClient(
        _AnthResponse(
            [
                _Block("text"),
                _Block("tool_use", "emit_sql", dict(_OK_PAYLOAD)),
            ],
            usage=_AnthUsage(input_tokens=100, output_tokens=20, cache_read=40, cache_write=10),
        )
    )
    provider._client = client  # type: ignore[assignment]

    result, usage = provider.generate_sql(
        messages=_QUESTION, system_prompt="SYS", schema_block="SCHEMA: TABLE t"
    )
    assert result.status == "ok"
    assert result.sql == "SELECT 1"
    assert result.explanation == "one"

    # Token usage is captured from response.usage (cache tokens tracked separately).
    assert usage.input_tokens == 100
    assert usage.output_tokens == 20
    assert usage.cache_read_tokens == 40
    assert usage.cache_write_tokens == 10
    assert usage.total == 170

    system = client.messages.calls[0]["system"]
    assert any(block.get("cache_control") for block in system), "schema must be cache-marked"


def test_anthropic_passes_message_list_through() -> None:
    provider = AnthropicProvider(api_key="x", model="claude-test")
    client = _AnthClient(_AnthResponse([_Block("tool_use", "emit_sql", dict(_OK_PAYLOAD))]))
    provider._client = client  # type: ignore[assignment]

    convo: list[ChatMessage] = [
        {"role": "user", "content": "Question: q?"},
        {"role": "assistant", "content": '{"sql": "SELECT bogus"}'},
        {"role": "user", "content": "table bogus does not exist"},
    ]
    provider.generate_sql(messages=convo, system_prompt="SYS", schema_block="SCHEMA")
    sent = client.messages.calls[0]["messages"]
    assert [m["role"] for m in sent] == ["user", "assistant", "user"]
    # Schema stays in the cached system prefix — retries must not move it.
    assert client.messages.calls[0]["system"][1]["text"] == "SCHEMA"


def test_anthropic_clarification_result() -> None:
    provider = AnthropicProvider(api_key="x", model="claude-test")
    payload = {
        "status": "needs_clarification",
        "sql": None,
        "explanation": None,
        "clarification_question": "Did you mean payments?",
        "suggested_interpretations": [
            {"label": "Total payments", "description": "What is the total of payments.amount?"}
        ],
    }
    provider._client = _AnthClient(  # type: ignore[assignment]
        _AnthResponse([_Block("tool_use", "emit_sql", payload)])
    )
    result, _usage = provider.generate_sql(messages=_QUESTION, system_prompt="S", schema_block="B")
    assert result.status == "needs_clarification"
    assert result.clarification_question == "Did you mean payments?"
    assert result.suggested_interpretations is not None
    assert result.suggested_interpretations[0].label == "Total payments"


def test_anthropic_invalid_structured_result_raises() -> None:
    provider = AnthropicProvider(api_key="x", model="claude-test")
    # status ok without sql violates the model validator.
    payload = {"status": "ok", "sql": None, "explanation": None}
    provider._client = _AnthClient(  # type: ignore[assignment]
        _AnthResponse([_Block("tool_use", "emit_sql", payload)])
    )
    with pytest.raises(AIProviderError):
        provider.generate_sql(messages=_QUESTION, system_prompt="S", schema_block="B")


def test_anthropic_summarize_returns_structured_summary() -> None:
    provider = AnthropicProvider(api_key="x", model="claude-test")
    client = _AnthClient(
        _AnthResponse(
            [
                _Block(
                    "tool_use",
                    "emit_summary",
                    {
                        "summary": "Orders rise over time.",
                        "chart_type": "line",
                        "x_column": "day",
                        "y_column": "orders",
                    },
                ),
            ]
        )
    )
    provider._client = client  # type: ignore[assignment]

    result, _usage = provider.summarize_results(system_prompt="SYS", context="stats...")
    assert result.summary == "Orders rise over time."
    assert result.chart_type == "line"
    assert result.x_column == "day"
    # Legacy y_column lifts into y_columns for new clients.
    assert result.y_columns == ["orders"]


def test_anthropic_summarize_multi_series_fields() -> None:
    provider = AnthropicProvider(api_key="x", model="claude-test")
    provider._client = _AnthClient(  # type: ignore[assignment]
        _AnthResponse(
            [
                _Block(
                    "tool_use",
                    "emit_summary",
                    {
                        "summary": "Sales per product per month.",
                        "chart_type": "line",
                        "x_column": "month",
                        "y_columns": ["sales"],
                        "series_column": "product",
                        "stacked": False,
                        "combo_line_columns": None,
                    },
                ),
            ]
        )
    )
    result, _usage = provider.summarize_results(system_prompt="SYS", context="stats...")
    assert result.y_columns == ["sales"]
    assert result.series_column == "product"
    assert result.stacked is False
    # Derived legacy field mirrors the first Y column.
    assert result.y_column == "sales"


@pytest.mark.parametrize("chart_type", ["pie", "area", "scatter", "hbar", "radar", "combo"])
def test_anthropic_summarize_accepts_new_chart_types(chart_type: str) -> None:
    provider = AnthropicProvider(api_key="x", model="claude-test")
    provider._client = _AnthClient(  # type: ignore[assignment]
        _AnthResponse(
            [
                _Block(
                    "tool_use",
                    "emit_summary",
                    {
                        "summary": "A summary.",
                        "chart_type": chart_type,
                        "x_column": "a",
                        "y_column": "b",
                    },
                ),
            ]
        )
    )
    result, _usage = provider.summarize_results(system_prompt="SYS", context="stats...")
    assert result.chart_type == chart_type


def test_anthropic_without_tool_call_raises() -> None:
    provider = AnthropicProvider(api_key="x", model="claude-test")
    provider._client = _AnthClient(_AnthResponse([_Block("text")]))  # type: ignore[assignment]
    with pytest.raises(AIProviderError):
        provider.generate_sql(messages=_QUESTION, system_prompt="SYS", schema_block="SCHEMA")


def test_anthropic_suggest_questions() -> None:
    provider = AnthropicProvider(api_key="x", model="claude-test")
    provider._client = _AnthClient(  # type: ignore[assignment]
        _AnthResponse(
            [_Block("tool_use", "emit_questions", {"questions": ["q1", "q2", "q3", "q4"]})]
        )
    )
    questions, _usage = provider.suggest_questions(system_prompt="S", schema_block="B")
    assert questions == ["q1", "q2", "q3", "q4"]


# --- OpenAI fakes ---------------------------------------------------------- #
class _Message:
    def __init__(self, content: str | None, tool_calls: list[Any] | None = None) -> None:
        self.content = content
        self.tool_calls = tool_calls


class _Choice:
    def __init__(self, content: str | None) -> None:
        self.message = _Message(content)


class _OAPromptDetails:
    def __init__(self, cached_tokens: int) -> None:
        self.cached_tokens = cached_tokens


class _OAUsage:
    def __init__(self, prompt_tokens: int, completion_tokens: int, cached_tokens: int) -> None:
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.prompt_tokens_details = _OAPromptDetails(cached_tokens)


class _OAResponse:
    def __init__(self, content: str | None, usage: _OAUsage | None = None) -> None:
        self.choices = [_Choice(content)]
        self.usage = usage


class _OACompletions:
    def __init__(self, response: _OAResponse) -> None:
        self._response = response
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> _OAResponse:
        self.calls.append(kwargs)
        return self._response


class _OAChat:
    def __init__(self, response: _OAResponse) -> None:
        self.completions = _OACompletions(response)


class _OAClient:
    def __init__(self, response: _OAResponse) -> None:
        self.chat = _OAChat(response)


def test_openai_parses_json_response() -> None:
    provider = OpenAIProvider(api_key="x", model="gpt-test")
    payload = json.dumps({**_OK_PAYLOAD, "sql": "SELECT 2", "explanation": "two"})
    client = _OAClient(
        _OAResponse(
            payload,
            usage=_OAUsage(prompt_tokens=90, completion_tokens=15, cached_tokens=40),
        )
    )
    provider._client = client  # type: ignore[assignment]

    result, usage = provider.generate_sql(
        messages=_QUESTION, system_prompt="SYS", schema_block="SCHEMA: TABLE t"
    )
    assert result.status == "ok"
    assert result.sql == "SELECT 2"

    # prompt_tokens includes cached; input_tokens holds the non-cached remainder so
    # the four counts sum to the billed total without double-counting.
    assert usage.input_tokens == 50
    assert usage.cache_read_tokens == 40
    assert usage.output_tokens == 15
    assert usage.cache_write_tokens == 0
    assert usage.total == 105
    # The schema is part of the leading system message (a stable, cacheable prefix).
    system_msg = client.chat.completions.calls[0]["messages"][0]
    assert system_msg["role"] == "system"
    assert "TABLE t" in system_msg["content"]


def test_openai_passes_message_list_after_system() -> None:
    provider = OpenAIProvider(api_key="x", model="gpt-test")
    client = _OAClient(_OAResponse(json.dumps(_OK_PAYLOAD)))
    provider._client = client  # type: ignore[assignment]

    convo: list[ChatMessage] = [
        {"role": "user", "content": "Question: q?"},
        {"role": "assistant", "content": "{}"},
        {"role": "user", "content": "fix it"},
    ]
    provider.generate_sql(messages=convo, system_prompt="SYS", schema_block="SCHEMA")
    sent = client.chat.completions.calls[0]["messages"]
    assert [m["role"] for m in sent] == ["system", "user", "assistant", "user"]


def test_openai_summarize_parses_json() -> None:
    provider = OpenAIProvider(api_key="x", model="gpt-test")
    payload = json.dumps(
        {
            "summary": "Three categories, roughly equal.",
            "chart_type": "bar",
            "x_column": "category",
            "y_column": "total",
        }
    )
    provider._client = _OAClient(_OAResponse(payload))  # type: ignore[assignment]

    result, _usage = provider.summarize_results(system_prompt="SYS", context="stats...")
    assert result.chart_type == "bar"
    assert result.y_column == "total"


def test_openai_empty_response_raises() -> None:
    provider = OpenAIProvider(api_key="x", model="gpt-test")
    provider._client = _OAClient(_OAResponse(None))  # type: ignore[assignment]
    with pytest.raises(AIProviderError):
        provider.generate_sql(messages=_QUESTION, system_prompt="SYS", schema_block="SCHEMA")


def test_openai_suggest_questions() -> None:
    provider = OpenAIProvider(api_key="x", model="gpt-test")
    provider._client = _OAClient(  # type: ignore[assignment]
        _OAResponse(json.dumps({"questions": ["a", "b", "c", "d"]}))
    )
    questions, _usage = provider.suggest_questions(system_prompt="S", schema_block="B")
    assert questions == ["a", "b", "c", "d"]


# --- output schema shape ---------------------------------------------------- #
def test_output_schema_is_strict_mode_compatible() -> None:
    """OpenAI strict mode: every property listed in required, nulls via type unions."""
    assert set(SQL_OUTPUT_SCHEMA["required"]) == set(SQL_OUTPUT_SCHEMA["properties"])
    assert SQL_OUTPUT_SCHEMA["additionalProperties"] is False
    for name, prop in SQL_OUTPUT_SCHEMA["properties"].items():
        if name == "status":
            continue
        assert "null" in prop["type"], f"{name} must be nullable for strict mode"


# --- tool-chat usage threading (the discovery loop relies on this) --------- #
def test_anthropic_chat_populates_usage() -> None:
    provider = AnthropicProvider(api_key="x", model="claude-test")
    blocks = [
        anthropic.types.TextBlock.model_construct(type="text", text="thinking"),
        anthropic.types.ToolUseBlock.model_construct(
            type="tool_use",
            id="t1",
            name="get_table_details",
            input={"table_names": ["payments"]},
        ),
    ]
    client = _AnthClient(
        _AnthResponse(
            blocks,
            usage=_AnthUsage(input_tokens=100, output_tokens=20, cache_read=40, cache_write=10),
        )
    )
    provider._client = client  # type: ignore[assignment]

    turn = provider.chat(
        system="SYS", messages=[ToolChatMessage(role="user", text="q")], tools=[]
    )
    assert turn.text == "thinking"
    assert [c.name for c in turn.tool_calls] == ["get_table_details"]
    assert turn.usage.total == 170


def test_openai_chat_populates_usage() -> None:
    provider = OpenAIProvider(api_key="x", model="gpt-test")
    client = _OAClient(
        _OAResponse(
            "done", usage=_OAUsage(prompt_tokens=90, completion_tokens=15, cached_tokens=40)
        )
    )
    provider._client = client  # type: ignore[assignment]

    turn = provider.chat(
        system="SYS", messages=[ToolChatMessage(role="user", text="q")], tools=[]
    )
    assert turn.text == "done"
    assert turn.tool_calls == []
    assert turn.usage.total == 105  # input 50 + cache 40 + output 15
