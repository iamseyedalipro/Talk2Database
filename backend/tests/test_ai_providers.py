"""Tests for the AI providers using fake SDK clients (no network)."""

from __future__ import annotations

import json
from typing import Any

import pytest
from app.services.ai.anthropic_provider import AnthropicProvider
from app.services.ai.base import SQL_OUTPUT_SCHEMA, AIProviderError, ChatMessage
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


class _AnthResponse:
    def __init__(self, content: list[_Block]) -> None:
        self.content = content


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
            ]
        )
    )
    provider._client = client  # type: ignore[assignment]

    result = provider.generate_sql(
        messages=_QUESTION, system_prompt="SYS", schema_block="SCHEMA: TABLE t"
    )
    assert result.status == "ok"
    assert result.sql == "SELECT 1"
    assert result.explanation == "one"

    system = client.messages.calls[0]["system"]
    assert any(block.get("cache_control") for block in system), "schema must be cache-marked"


def test_anthropic_passes_message_list_through() -> None:
    provider = AnthropicProvider(api_key="x", model="claude-test")
    client = _AnthClient(
        _AnthResponse([_Block("tool_use", "emit_sql", dict(_OK_PAYLOAD))])
    )
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
    result = provider.generate_sql(messages=_QUESTION, system_prompt="S", schema_block="B")
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

    result = provider.summarize_results(system_prompt="SYS", context="stats...")
    assert result.summary == "Orders rise over time."
    assert result.chart_type == "line"
    assert result.x_column == "day"


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
    assert provider.suggest_questions(system_prompt="S", schema_block="B") == [
        "q1",
        "q2",
        "q3",
        "q4",
    ]


# --- OpenAI fakes ---------------------------------------------------------- #
class _Message:
    def __init__(self, content: str | None) -> None:
        self.content = content


class _Choice:
    def __init__(self, content: str | None) -> None:
        self.message = _Message(content)


class _OAResponse:
    def __init__(self, content: str | None) -> None:
        self.choices = [_Choice(content)]


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
    client = _OAClient(_OAResponse(payload))
    provider._client = client  # type: ignore[assignment]

    result = provider.generate_sql(
        messages=_QUESTION, system_prompt="SYS", schema_block="SCHEMA: TABLE t"
    )
    assert result.status == "ok"
    assert result.sql == "SELECT 2"
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

    result = provider.summarize_results(system_prompt="SYS", context="stats...")
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
    assert provider.suggest_questions(system_prompt="S", schema_block="B") == ["a", "b", "c", "d"]


# --- output schema shape ---------------------------------------------------- #
def test_output_schema_is_strict_mode_compatible() -> None:
    """OpenAI strict mode: every property listed in required, nulls via type unions."""
    assert set(SQL_OUTPUT_SCHEMA["required"]) == set(SQL_OUTPUT_SCHEMA["properties"])
    assert SQL_OUTPUT_SCHEMA["additionalProperties"] is False
    for name, prop in SQL_OUTPUT_SCHEMA["properties"].items():
        if name == "status":
            continue
        assert "null" in prop["type"], f"{name} must be nullable for strict mode"
