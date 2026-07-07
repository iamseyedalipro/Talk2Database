"""Tests for the on-demand table-detail discovery orchestrator."""

from __future__ import annotations

from typing import Any

from app.config import Settings
from app.services.ai.base import (
    AIProviderError,
    ChatTurn,
    TokenUsage,
    ToolCall,
    ToolChatMessage,
    ToolSpec,
)
from app.services.schema.discover import discover_schema
from app.services.schema.introspect import SchemaData


def _table(name: str, columns: list[str]) -> dict:
    return {
        "schema": "public",
        "name": name,
        "comment": None,
        "columns": [
            {"name": c, "type": "text", "nullable": True, "comment": None} for c in columns
        ],
        "primary_key": [],
        "foreign_keys": [],
    }


# Many tables so the schema comfortably exceeds a low token budget.
SCHEMA: SchemaData = {
    "tables": [
        _table("users_payment", ["id", "amount", "status", "created_at"]),
        _table("journeys_tag", ["id", "name"]),
        _table("content_content", ["id", "title", "description"]),
        _table("habits_habit", ["id", "name", "description"]),
        _table("auth_group", ["id", "name"]),
    ]
}


class FakeProvider:
    """A ``chat``-only provider returning scripted turns and recording calls."""

    name = "fake"
    model = "fake-model"

    def __init__(self, turns: list[ChatTurn] | Exception) -> None:
        self._turns = turns
        self.calls: list[dict[str, Any]] = []

    def chat(
        self,
        *,
        system: str,
        messages: list[ToolChatMessage],
        tools: list[ToolSpec],
        force_text: bool = False,
    ) -> ChatTurn:
        self.calls.append({"system": system, "messages": list(messages), "tools": tools})
        if isinstance(self._turns, Exception):
            raise self._turns
        return self._turns.pop(0)


def _details(call_id: str, names: list[str]) -> ChatTurn:
    return ChatTurn(
        text=None,
        tool_calls=[ToolCall(id=call_id, name="get_table_details", input={"table_names": names})],
    )


def _done(text: str = "ready") -> ChatTurn:
    return ChatTurn(text=text, tool_calls=[])


def _settings(**overrides: Any) -> Settings:
    return Settings(ai_api_key="test", schema_max_tokens=50, **overrides)


async def _discover(provider: FakeProvider, settings: Settings | None = None):
    return await discover_schema(
        provider=provider,
        schema=SCHEMA,
        question="how much we sell week by week",
        ask_system_prompt="ASK RULES",
        glossary_text="",
        settings=settings or _settings(),
    )


async def test_single_round_expands_requested_table() -> None:
    provider = FakeProvider([_details("c1", ["users_payment"]), _done()])
    result = await _discover(provider)
    assert "TABLE users_payment" in result.text
    assert "status" in result.text  # a detailed column
    assert result.text.startswith("TABLES:")  # directory prefix retained
    assert result.table_count_sent == 1
    assert result.table_count_total == 5


async def test_multi_round_accumulates_and_dedups() -> None:
    provider = FakeProvider(
        [
            _details("c1", ["users_payment"]),
            _details("c2", ["journeys_tag", "users_payment"]),  # re-request is deduped
            _done(),
        ]
    )
    result = await _discover(provider)
    assert "TABLE users_payment" in result.text
    assert "TABLE journeys_tag" in result.text
    assert result.text.count("TABLE users_payment") == 1
    assert result.table_count_sent == 2


async def test_unknown_table_returns_error_result() -> None:
    provider = FakeProvider(
        [_details("c1", ["nope"]), _details("c2", ["users_payment"]), _done()]
    )
    result = await _discover(provider)
    # The error ToolResult from the first (unknown) call was fed back to the model.
    fed_back = [
        tr
        for call in provider.calls
        for msg in call["messages"]
        for tr in msg.tool_results
    ]
    assert any(tr.is_error and "users_payment" in tr.content for tr in fed_back)
    # The valid follow-up still resolved.
    assert "TABLE users_payment" in result.text


async def test_round_cap_proceeds_with_warning() -> None:
    # Model keeps asking for details forever; loop must stop at the round cap.
    provider = FakeProvider([_details(f"c{i}", ["journeys_tag"]) for i in range(10)])
    result = await _discover(provider, _settings(ask_discovery_max_rounds=3))
    assert len(provider.calls) == 3
    assert any("round limit" in w for w in result.warnings)
    assert "TABLE journeys_tag" in result.text


async def test_table_cap_enforced() -> None:
    provider = FakeProvider(
        [
            _details("c1", ["users_payment", "journeys_tag"]),
            _details("c2", ["content_content", "habits_habit"]),
            _done(),
        ]
    )
    result = await _discover(provider, _settings(ask_discovery_max_tables=2))
    assert result.table_count_sent == 2
    assert any("table limit" in w.lower() for w in result.warnings)


async def test_prose_only_falls_back_to_select_schema() -> None:
    provider = FakeProvider([_done("I can answer without more detail.")])
    result = await _discover(provider)
    # Nothing expanded -> fall back to the lexical selector, with a fallback note.
    assert any("keyword relevance" in w for w in result.warnings)
    assert result.text  # non-empty schema block still produced


async def test_provider_error_falls_back() -> None:
    provider = FakeProvider(AIProviderError("boom"))
    result = await _discover(provider)
    assert any("unavailable" in w for w in result.warnings)
    assert result.text


async def test_usage_summed_across_rounds() -> None:
    provider = FakeProvider(
        [
            ChatTurn(
                text=None,
                tool_calls=[
                    ToolCall(
                        id="c1",
                        name="get_table_details",
                        input={"table_names": ["journeys_tag"]},
                    )
                ],
                usage=TokenUsage(input_tokens=30, output_tokens=5),
            ),
            ChatTurn(
                text="ready", tool_calls=[], usage=TokenUsage(input_tokens=20, output_tokens=3)
            ),
        ]
    )
    result = await _discover(provider)
    assert result.usage.total == 58


async def test_glossary_in_discovery_system_prompt() -> None:
    provider = FakeProvider([_details("c1", ["users_payment"]), _done()])
    await discover_schema(
        provider=provider,
        schema=SCHEMA,
        question="revenue",
        ask_system_prompt="ASK RULES",
        glossary_text="BUSINESS GLOSSARY:\n- revenue -> users_payment.amount",
        settings=_settings(),
    )
    assert "BUSINESS GLOSSARY" in provider.calls[0]["system"]
    assert "ASK RULES" in provider.calls[0]["system"]


async def test_empty_schema_skips_provider() -> None:
    provider = FakeProvider([])
    result = await discover_schema(
        provider=provider,
        schema={"tables": []},
        question="anything",
        ask_system_prompt="ASK RULES",
        glossary_text="",
        settings=_settings(),
    )
    assert provider.calls == []
    assert result.table_count_total == 0
