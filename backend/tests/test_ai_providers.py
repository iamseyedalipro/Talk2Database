"""Tests for the AI providers using fake SDK clients (no network)."""

from __future__ import annotations

import json
from typing import Any

import pytest
from app.services.ai.anthropic_provider import AnthropicProvider
from app.services.ai.base import AIProviderError
from app.services.ai.openai_provider import OpenAIProvider


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
                _Block("tool_use", "emit_sql", {"sql": "SELECT 1", "explanation": "one"}),
            ]
        )
    )
    provider._client = client  # type: ignore[assignment]

    result = provider.generate_sql(
        question="q?", system_prompt="SYS", schema_block="SCHEMA: TABLE t"
    )
    assert result.sql == "SELECT 1"
    assert result.explanation == "one"

    system = client.messages.calls[0]["system"]
    assert any(block.get("cache_control") for block in system), "schema must be cache-marked"


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
        provider.generate_sql(question="q?", system_prompt="SYS", schema_block="SCHEMA: TABLE t")


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
    payload = json.dumps({"sql": "SELECT 2", "explanation": "two"})
    client = _OAClient(_OAResponse(payload))
    provider._client = client  # type: ignore[assignment]

    result = provider.generate_sql(
        question="q?", system_prompt="SYS", schema_block="SCHEMA: TABLE t"
    )
    assert result.sql == "SELECT 2"
    # The schema is part of the leading system message (a stable, cacheable prefix).
    system_msg = client.chat.completions.calls[0]["messages"][0]
    assert system_msg["role"] == "system"
    assert "TABLE t" in system_msg["content"]


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
        provider.generate_sql(question="q?", system_prompt="SYS", schema_block="SCHEMA: TABLE t")
