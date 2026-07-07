"""Tests for the Ask WebSocket endpoint (auth, streaming, cancellation)."""

from __future__ import annotations

import threading
from types import SimpleNamespace
from typing import Any

import pytest
from app.config import Settings
from app.db.panel import get_session
from app.models.query_history import QueryHistory
from app.routers import ask_ws as ask_ws_module
from app.services import ask_flow as ask_flow_module
from app.services.ai.base import ChatMessage, SqlGenerationResult, TokenUsage
from app.services.ai.prompts import build_schema_block, build_system_prompt
from app.services.sql_guard import validate_select
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect


def _table(name: str, columns: list[str]) -> dict[str, Any]:
    return {
        "schema": "public",
        "name": name,
        "comment": None,
        "columns": [
            {"name": c, "type": "integer", "nullable": False, "comment": None} for c in columns
        ],
        "primary_key": ["id"],
        "foreign_keys": [],
    }


SCHEMA_JSON: dict[str, Any] = {"tables": [_table("payments", ["id", "amount"])]}


class FakeProvider:
    name = "fake"
    model = "fake-model"

    def __init__(self, results: list[SqlGenerationResult], block: threading.Event | None = None):
        self._results = list(results)
        self._block = block

    def generate_sql(
        self, *, messages: list[ChatMessage], system_prompt: str, schema_block: str
    ) -> tuple[SqlGenerationResult, TokenUsage]:
        if self._block is not None:
            self._block.wait(timeout=10)
        return self._results.pop(0), TokenUsage()

    def chat(self, **_kwargs: Any):
        from app.services.ai.base import ChatTurn

        return ChatTurn(text="ready", tool_calls=[])


class FakeConnector:
    type = "postgres"
    dialect = "postgres"
    label = "PostgreSQL"

    def system_prompt(self) -> str:
        return build_system_prompt("PostgreSQL")

    def schema_block(self, schema_text: str) -> str:
        return build_schema_block(schema_text, "PostgreSQL")

    def validate(self, query: str) -> str:
        return validate_select(query, "postgres")


class FakeSession:
    def __init__(self) -> None:
        self.added: list[QueryHistory] = []
        self.committed = False
        self.rolled_back = False
        # app_settings rows visible to get_setting (key -> value).
        self.settings: dict[str, Any] = {}

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    async def get(self, model: Any, key: Any) -> Any:
        if key in self.settings:
            return SimpleNamespace(key=key, value=self.settings[key])
        return None

    async def flush(self) -> None:
        for i, obj in enumerate(self.added, start=1):
            if getattr(obj, "id", None) is None:
                obj.id = i

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True
        self.added.clear()


@pytest.fixture()
def harness(monkeypatch: pytest.MonkeyPatch):
    app = FastAPI()
    app.include_router(ask_ws_module.router, prefix="/api")

    session = FakeSession()
    connection = SimpleNamespace(id=7, name="demo", database="demo", host="localhost", port=5432)
    snapshot = SimpleNamespace(table_count=1, content_json=SCHEMA_JSON)
    provider_holder: dict[str, FakeProvider] = {}

    async def fake_load_connector(*_args: Any, **_kwargs: Any):
        return connection, FakeConnector()

    async def fake_ensure_snapshot(*_args: Any, **_kwargs: Any):
        return snapshot

    async def fake_load_glossary(*_args: Any, **_kwargs: Any):
        return [], []

    async def fake_resolve_user(_session: Any, token: str):
        return SimpleNamespace(id=1) if token == "good-token" else None

    monkeypatch.setattr(ask_flow_module, "load_connector", fake_load_connector)
    monkeypatch.setattr(ask_flow_module, "ensure_snapshot", fake_ensure_snapshot)
    monkeypatch.setattr(ask_flow_module, "load_glossary", fake_load_glossary)
    monkeypatch.setattr(ask_flow_module, "get_ai_provider", lambda: provider_holder["provider"])
    monkeypatch.setattr(
        ask_flow_module,
        "get_settings",
        lambda: Settings(ai_api_key="test", ask_schema_discovery=False),
    )
    monkeypatch.setattr(ask_ws_module, "resolve_user_from_token", fake_resolve_user)

    app.dependency_overrides[get_session] = lambda: session

    return SimpleNamespace(client=TestClient(app), session=session, providers=provider_holder)


def _start_message(token: str = "good-token") -> dict[str, Any]:
    return {
        "type": "start",
        "token": token,
        "connection_id": 7,
        "question": "total payments?",
    }


def test_happy_path_streams_and_ends_with_final_result(harness) -> None:
    harness.providers["provider"] = FakeProvider(
        [SqlGenerationResult(status="ok", sql="SELECT amount FROM payments", explanation="e")]
    )

    with harness.client.websocket_connect("/api/ask/ws") as ws:
        ws.send_json(_start_message())
        events = []
        while True:
            event = ws.receive_json()
            events.append(event)
            if event["type"] in {"final_result", "error", "cancelled"}:
                break

    types = [e["type"] for e in events]
    assert types[0] == "run_started"
    assert events[0]["mode"] == "standard"
    assert "generating_sql" in types
    assert types[-1] == "final_result"
    final = events[-1]
    assert final["status"] == "ok"
    assert "payments" in final["generated_sql"]
    # seq is monotonically increasing from 1.
    assert [e["seq"] for e in events] == list(range(1, len(events) + 1))
    # History persisted and the session committed.
    assert harness.session.committed
    assert len(harness.session.added) >= 1


def test_bad_token_gets_error_and_4401(harness) -> None:
    harness.providers["provider"] = FakeProvider([])

    with harness.client.websocket_connect("/api/ask/ws") as ws:
        ws.send_json(_start_message(token="wrong"))
        event = ws.receive_json()
        assert event["type"] == "error"
        assert event["code"] == "unauthorized"
        with pytest.raises(WebSocketDisconnect) as excinfo:
            ws.receive_json()
        assert excinfo.value.code == 4401


def test_bad_first_message_rejected(harness) -> None:
    harness.providers["provider"] = FakeProvider([])

    with harness.client.websocket_connect("/api/ask/ws") as ws:
        ws.send_json({"type": "cancel"})
        event = ws.receive_json()
        assert event["type"] == "error"
        assert event["code"] == "bad_request"


def test_analysis_mode_toggle_switches_flow(harness) -> None:
    harness.session.settings["ask_analysis_mode"] = True
    harness.session.settings["ask_analysis_row_cap"] = 15
    harness.providers["provider"] = FakeProvider(
        [SqlGenerationResult(status="ok", sql="SELECT amount FROM payments", explanation="e")]
    )

    with harness.client.websocket_connect("/api/ask/ws") as ws:
        ws.send_json(_start_message())
        events = []
        while True:
            event = ws.receive_json()
            events.append(event)
            if event["type"] in {"final_result", "error", "cancelled"}:
                break

    assert events[0]["type"] == "run_started"
    assert events[0]["mode"] == "analysis"
    # The FakeProvider's chat answers in prose without requesting tables, so
    # the analysis loop degrades to the lexical selector and warns about it.
    final = events[-1]
    assert final["type"] == "final_result"
    assert any("keyword relevance" in w for w in final["warnings"])


def test_cancel_mid_flow_leaves_no_history(harness) -> None:
    block = threading.Event()
    harness.providers["provider"] = FakeProvider(
        [SqlGenerationResult(status="ok", sql="SELECT 1", explanation="e")], block=block
    )

    try:
        with harness.client.websocket_connect("/api/ask/ws") as ws:
            ws.send_json(_start_message())
            assert ws.receive_json()["type"] == "run_started"
            # Wait until the flow is inside the (blocked) provider call.
            while ws.receive_json()["type"] != "generating_sql":
                pass
            ws.send_json({"type": "cancel"})
            while True:
                event = ws.receive_json()
                if event["type"] == "cancelled":
                    break
    finally:
        block.set()  # release the provider thread

    assert harness.session.rolled_back
    assert harness.session.added == []
    assert not harness.session.committed
