"""Tests for the Ask analysis loop (table discovery + exploratory queries)."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from app.config import Settings
from app.connectors.base import ConnectorError, QueryResult
from app.services.ai.base import (
    AIProviderError,
    ChatTurn,
    TokenUsage,
    ToolCall,
    ToolChatMessage,
    ToolSpec,
)
from app.services.ask_analysis import run_ask_analysis_loop
from app.services.schema.introspect import SchemaData
from app.services.sql_guard import validate_select


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


SCHEMA: SchemaData = {  # type: ignore[assignment]
    "tables": [
        _table("payments", ["id", "amount", "status"]),
        _table("users", ["id", "email"]),
    ]
}


class FakeProvider:
    name = "fake"
    model = "fake-model"

    def __init__(self, turns: list[ChatTurn]) -> None:
        self._turns = list(turns)
        self.systems: list[str] = []
        self.seen_messages: list[list[ToolChatMessage]] = []

    def chat(
        self,
        *,
        system: str,
        messages: list[ToolChatMessage],
        tools: list[ToolSpec],
        force_text: bool = False,
    ) -> ChatTurn:
        self.systems.append(system)
        self.seen_messages.append(list(messages))
        if not self._turns:
            return ChatTurn(text="done", tool_calls=[])
        return self._turns.pop(0)


class ErrorProvider(FakeProvider):
    def chat(self, **_kwargs: Any) -> ChatTurn:
        raise AIProviderError("provider down")


class FakeConnector:
    dialect = "postgres"
    label = "PostgreSQL"

    def __init__(self, result: QueryResult | None = None, error: str | None = None) -> None:
        self._result = result
        self._error = error
        self.run_calls: list[tuple[str, int]] = []

    def validate(self, query: str) -> str:
        return validate_select(query, "postgres")

    def run(self, sql: str, max_rows: int) -> QueryResult:
        self.run_calls.append((sql, max_rows))
        if self._error:
            raise ConnectorError(self._error)
        assert self._result is not None
        return self._result


class FakeSession:
    """No stored prompt overrides: get_prompt falls back to the defaults."""

    async def get(self, model: Any, key: Any) -> None:
        return None


def _details_turn(call_id: str, names: list[str]) -> ChatTurn:
    return ChatTurn(
        text=None,
        tool_calls=[ToolCall(id=call_id, name="get_table_details", input={"table_names": names})],
        usage=TokenUsage(input_tokens=10, output_tokens=5),
    )


def _query_turn(call_id: str, sql: str, purpose: str = "peek at the data") -> ChatTurn:
    return ChatTurn(
        text="Checking the data",
        tool_calls=[
            ToolCall(
                id=call_id, name="run_exploratory_query", input={"sql": sql, "purpose": purpose}
            )
        ],
        usage=TokenUsage(input_tokens=10, output_tokens=5),
    )


def _run(provider: FakeProvider, connector: FakeConnector, *, row_cap: int = 10, **overrides: Any):
    settings = Settings(ai_api_key="test", **overrides)
    events: list[dict[str, Any]] = []

    async def emit(event: dict[str, Any]) -> None:
        events.append(event)

    result = asyncio.run(
        run_ask_analysis_loop(
            FakeSession(),  # type: ignore[arg-type]
            provider=provider,
            connector=connector,  # type: ignore[arg-type]
            schema=SCHEMA,
            question="how much did we sell last month?",
            ask_system_prompt="You write SQL.",
            glossary_text="",
            settings=settings,
            row_cap=row_cap,
            emit=emit,
        )
    )
    return result, events


def test_full_loop_details_then_query_then_done() -> None:
    result_rows = QueryResult(
        columns=[("status", "text")],
        rows=[["successful"], ["failed"]],
        row_count=2,
        truncated=False,
        elapsed_ms=1,
    )
    connector = FakeConnector(result=result_rows)
    provider = FakeProvider(
        [
            _details_turn("1", ["payments"]),
            _query_turn("2", "SELECT DISTINCT status FROM payments LIMIT 5"),
            ChatTurn(text="I understand the data now.", tool_calls=[]),
        ]
    )

    exploration, events = _run(provider, connector, row_cap=7)

    # The row cap reaches the connector.
    assert connector.run_calls == [("SELECT DISTINCT status FROM payments LIMIT 5", 7)]

    # The rendered block is JSON: directory, details, and findings.
    assert "TABLE DIRECTORY (JSON):" in exploration.text
    assert "TABLE DETAILS (JSON):" in exploration.text
    assert "EXPLORATION FINDINGS (JSON)" in exploration.text
    assert '"table":"payments"' in exploration.text
    assert '"rows":[["successful"],["failed"]]' in exploration.text
    assert exploration.table_count_sent == 1
    assert exploration.table_count_total == 2
    assert exploration.usage.input_tokens == 20  # two turns reported usage; the closing turn none

    kinds = [e["type"] for e in events]
    assert kinds == [
        "tables_directory",
        "tables_requested",
        "table_details_sent",
        "assistant_note",  # "Checking the data" on the query turn
        "exploratory_query",
        "query_result",
        "assistant_note",  # the closing text turn
    ]
    query_result = next(e for e in events if e["type"] == "query_result")
    assert query_result["rows"] == [["successful"], ["failed"]]
    assert query_result["error"] is None


def test_guard_rejects_non_select_and_loop_recovers() -> None:
    connector = FakeConnector(result=None)
    provider = FakeProvider(
        [
            _details_turn("1", ["payments"]),
            _query_turn("2", "DELETE FROM payments"),
            ChatTurn(text="understood", tool_calls=[]),
        ]
    )

    exploration, events = _run(provider, connector)

    # The dangerous statement never reached the connector.
    assert connector.run_calls == []
    query_result = next(e for e in events if e["type"] == "query_result")
    assert "read-only guard" in (query_result["error"] or "")
    # The failed attempt is recorded in the findings for the generator to see.
    assert "read-only guard" in exploration.text


def test_query_limit_enforced() -> None:
    result_rows = QueryResult(
        columns=[("n", "int")], rows=[[1]], row_count=1, truncated=False, elapsed_ms=1
    )
    connector = FakeConnector(result=result_rows)
    provider = FakeProvider(
        [
            _details_turn("1", ["payments"]),
            _query_turn("2", "SELECT 1"),
            _query_turn("3", "SELECT 2"),
            ChatTurn(text="ok", tool_calls=[]),
        ]
    )

    _, _events = _run(provider, connector, ask_analysis_max_queries=1)
    assert len(connector.run_calls) == 1  # the second query was refused


def test_round_limit_warns() -> None:
    provider = FakeProvider([_details_turn(str(i), ["payments"]) for i in range(1, 10)])
    exploration, _events = _run(provider, FakeConnector(), ask_analysis_max_rounds=2)
    assert any("round limit" in w for w in exploration.warnings)


def test_provider_error_falls_back_to_select_schema() -> None:
    exploration, _events = _run(ErrorProvider([]), FakeConnector())
    assert any("unavailable" in w for w in exploration.warnings)
    assert exploration.text  # lexical fallback still produced a schema block


def test_no_details_falls_back_but_keeps_findings() -> None:
    result_rows = QueryResult(
        columns=[("n", "int")], rows=[[1]], row_count=1, truncated=False, elapsed_ms=1
    )
    connector = FakeConnector(result=result_rows)
    provider = FakeProvider(
        [
            _query_turn("1", "SELECT 1"),
            ChatTurn(text="done", tool_calls=[]),
        ]
    )

    exploration, _events = _run(provider, connector)
    assert any("requested no table details" in w for w in exploration.warnings)
    assert "EXPLORATION FINDINGS (JSON)" in exploration.text


def test_directory_and_details_are_valid_json() -> None:
    provider = FakeProvider(
        [
            _details_turn("1", ["payments", "users"]),
            ChatTurn(text="ok", tool_calls=[]),
        ]
    )
    exploration, events = _run(provider, FakeConnector())

    directory = events[0]
    assert directory["type"] == "tables_directory"
    assert directory["tables"] == ["payments", "users"]

    # The details block sent to the model round-trips as JSON.
    details_part = exploration.text.split("TABLE DETAILS (JSON):\n")[1]
    parsed = json.loads(details_part)
    assert [t["table"] for t in parsed] == ["payments", "users"]
    assert parsed[0]["columns"][0] == {"name": "id", "type": "text", "nullable": True}
