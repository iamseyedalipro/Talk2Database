"""Tests for the analysis agent loop using a scripted fake provider (no network,
no database: collaborators are monkeypatched at the agent-module seams)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from app.connectors.base import QueryResult
from app.services.ai.base import ChatMessage, ChatTurn, ToolCall, ToolSpec
from app.services.analysis import agent as agent_module
from app.services.analysis.agent import MAX_QUERIES, run_analysis
from app.services.sql_guard import SqlGuardError


class FakeConnector:
    label = "PostgreSQL"

    def validate(self, sql: str) -> str:
        if "select" not in sql.lower():
            raise SqlGuardError("only SELECT is allowed")
        return sql

    def run(self, sql: str, max_rows: int) -> QueryResult:
        return QueryResult(
            columns=[("n", "int")], rows=[[42]], row_count=1, truncated=False, elapsed_ms=1
        )


class FakeProvider:
    name = "fake"
    model = "fake-1"

    def __init__(self, turns: list[ChatTurn]) -> None:
        self._turns = list(turns)
        self.calls: list[dict[str, Any]] = []

    def chat(
        self,
        *,
        system: str,
        messages: list[ChatMessage],
        tools: list[ToolSpec],
        force_text: bool = False,
    ) -> ChatTurn:
        self.calls.append({"force_text": force_text, "n_messages": len(messages)})
        if force_text:
            # With tools withheld a real provider can only answer in text.
            return ChatTurn(text="Forced final answer.", tool_calls=[])
        if self._turns:
            return self._turns.pop(0)
        return ChatTurn(text="out of script", tool_calls=[])


def _tool_turn(sql: str, call_id: str = "c1") -> ChatTurn:
    return ChatTurn(
        text=None,
        tool_calls=[ToolCall(id=call_id, name="run_sql", input={"connection_id": 1, "sql": sql})],
    )


@pytest.fixture
def wired(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Patch the agent's collaborators; returns a dict to set the provider on."""
    holder: dict[str, Any] = {}

    async def fake_load_connector(session: Any, conn_id: int, user: Any) -> tuple[Any, Any]:
        return SimpleNamespace(id=conn_id, name=f"db{conn_id}"), FakeConnector()

    async def fake_build_system(session: Any, **kwargs: Any) -> str:
        return "SYSTEM"

    monkeypatch.setattr(agent_module, "load_connector", fake_load_connector)
    monkeypatch.setattr(agent_module, "_build_system", fake_build_system)
    monkeypatch.setattr(agent_module, "get_ai_provider", lambda: holder["provider"])
    return holder


async def test_tool_call_then_answer_records_a_step(wired: dict[str, Any]) -> None:
    provider = FakeProvider(
        [
            _tool_turn("SELECT count(*) FROM podcasts"),
            ChatTurn(text="There are 42 podcasts.", tool_calls=[]),
        ]
    )
    wired["provider"] = provider

    outcome = await run_analysis(
        None, None, question="how many?", connection_ids=[1], include_clarity=False
    )
    assert outcome.answer == "There are 42 podcasts."
    assert len(outcome.steps) == 1
    assert outcome.steps[0].row_count == 1
    assert outcome.steps[0].error is None
    assert outcome.steps[0].connection_name == "db1"


async def test_endless_tool_calls_stop_at_limit_and_force_text(wired: dict[str, Any]) -> None:
    turns = [_tool_turn("SELECT 1", call_id=f"c{i}") for i in range(10)]
    provider = FakeProvider(turns)
    wired["provider"] = provider

    outcome = await run_analysis(
        None, None, question="dig deep", connection_ids=[1], include_clarity=False
    )
    assert outcome.answer == "Forced final answer."
    assert len(outcome.steps) == MAX_QUERIES
    # The last call must have been the forced-text close-out.
    assert provider.calls[-1]["force_text"] is True


async def test_guard_rejection_becomes_error_result_not_exception(wired: dict[str, Any]) -> None:
    provider = FakeProvider(
        [
            _tool_turn("DROP TABLE users"),
            ChatTurn(text="I could not run that query.", tool_calls=[]),
        ]
    )
    wired["provider"] = provider

    outcome = await run_analysis(
        None, None, question="break it", connection_ids=[1], include_clarity=False
    )
    assert outcome.answer == "I could not run that query."
    assert len(outcome.steps) == 1
    assert outcome.steps[0].error is not None
    assert "guard" in outcome.steps[0].error


async def test_unknown_connection_id_is_reported_to_the_model(wired: dict[str, Any]) -> None:
    provider = FakeProvider(
        [
            ChatTurn(
                text=None,
                tool_calls=[
                    ToolCall(
                        id="c1", name="run_sql", input={"connection_id": 99, "sql": "SELECT 1"}
                    )
                ],
            ),
            ChatTurn(text="done", tool_calls=[]),
        ]
    )
    wired["provider"] = provider

    outcome = await run_analysis(
        None, None, question="q", connection_ids=[1], include_clarity=False
    )
    assert outcome.answer == "done"
    assert outcome.steps[0].error is not None
    assert "Unknown connection_id" in outcome.steps[0].error
