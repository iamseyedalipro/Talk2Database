"""Router-level tests for POST /api/ask using dependency overrides (no network/DB)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from app.config import Settings
from app.db.panel import get_session
from app.deps import get_current_user
from app.models.query_history import QueryHistory
from app.models.token_usage import TokenUsageRecord
from app.routers import ask as ask_module
from app.services import ask_flow as ask_flow_module
from app.services.ai.base import (
    ChatMessage,
    ChatTurn,
    SqlGenerationResult,
    SuggestedInterpretation,
    TokenUsage,
    ToolCall,
    ToolChatMessage,
    ToolSpec,
)
from app.services.ai.prompts import build_schema_block, build_system_prompt
from app.services.sql_guard import validate_select
from fastapi import FastAPI
from fastapi.testclient import TestClient


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


SCHEMA_JSON: dict[str, Any] = {
    "tables": [
        _table("payments", ["id", "amount"]),
        _table("users_payment", ["id", "amount", "status", "created_at"]),
    ]
}


class FakeProvider:
    name = "fake"
    model = "fake-model"

    def __init__(
        self,
        results: list[SqlGenerationResult],
        usage: TokenUsage | None = None,
        chat_turns: list[ChatTurn] | None = None,
    ) -> None:
        self._results = list(results)
        self._usage = usage or TokenUsage()
        # Discovery turns; default is a single no-tool text turn, which makes the
        # discovery loop gather nothing and fall back to ``select_schema`` — so
        # tests that only care about the generate/verify path stay unaffected.
        self._chat_turns = list(chat_turns) if chat_turns is not None else []
        self.chat_systems: list[str] = []
        self.seen_schema_blocks: list[str] = []

    def generate_sql(
        self, *, messages: list[ChatMessage], system_prompt: str, schema_block: str
    ) -> tuple[SqlGenerationResult, TokenUsage]:
        self.seen_schema_blocks.append(schema_block)
        return self._results.pop(0), self._usage

    def chat(
        self,
        *,
        system: str,
        messages: list[ToolChatMessage],
        tools: list[ToolSpec],
        force_text: bool = False,
    ) -> ChatTurn:
        self.chat_systems.append(system)
        if self._chat_turns:
            return self._chat_turns.pop(0)
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
    """Captures the QueryHistory row the router writes."""

    def __init__(self) -> None:
        self.added: list[QueryHistory] = []

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    async def get(self, model: Any, key: Any) -> None:
        # No stored settings rows: the prompt store falls back to defaults.
        return None

    async def flush(self) -> None:
        for i, obj in enumerate(self.added, start=1):
            if getattr(obj, "id", None) is None:
                obj.id = i


@pytest.fixture()
def harness(monkeypatch: pytest.MonkeyPatch):
    """A TestClient wired with fakes; tests inject provider results."""
    app = FastAPI()
    app.include_router(ask_module.router, prefix="/api")

    session = FakeSession()
    connection = SimpleNamespace(id=7, name="demo", database="demo", host="localhost", port=5432)
    snapshot = SimpleNamespace(table_count=2, content_json=SCHEMA_JSON)
    provider_holder: dict[str, FakeProvider] = {}
    settings_holder: dict[str, Settings] = {
        "settings": Settings(ai_api_key="test", ask_max_retries=1)
    }

    async def fake_load_connector(*_args: Any, **_kwargs: Any):
        return connection, FakeConnector()

    async def fake_ensure_snapshot(*_args: Any, **_kwargs: Any):
        return snapshot

    async def fake_load_glossary(*_args: Any, **_kwargs: Any):
        return [], []

    # The pipeline lives in services/ask_flow (shared by /ask, /ask/ws, and
    # /chats/{id}/ask).
    monkeypatch.setattr(ask_flow_module, "load_connector", fake_load_connector)
    monkeypatch.setattr(ask_flow_module, "ensure_snapshot", fake_ensure_snapshot)
    monkeypatch.setattr(ask_flow_module, "load_glossary", fake_load_glossary)
    monkeypatch.setattr(ask_flow_module, "get_ai_provider", lambda: provider_holder["provider"])
    monkeypatch.setattr(ask_flow_module, "get_settings", lambda: settings_holder["settings"])

    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=1)

    client = TestClient(app)

    def run(
        results: list[SqlGenerationResult],
        usage: TokenUsage | None = None,
        chat_turns: list[ChatTurn] | None = None,
        **settings_overrides: Any,
    ):
        if settings_overrides:
            settings_holder["settings"] = Settings(
                ai_api_key="test", ask_max_retries=1, **settings_overrides
            )
        provider = FakeProvider(results, usage=usage, chat_turns=chat_turns)
        provider_holder["provider"] = provider
        response = client.post(
            "/api/ask", json={"connection_id": 7, "question": "income last year?"}
        )
        return response

    return SimpleNamespace(run=run, session=session, provider=lambda: provider_holder["provider"])


def _ok(sql: str) -> SqlGenerationResult:
    return SqlGenerationResult(status="ok", sql=sql, explanation="e")


def test_ok_status_returns_sql_and_history(harness) -> None:
    response = harness.run([_ok("SELECT amount FROM payments")])
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "payments" in body["generated_sql"]
    assert body["retry_count"] == 0
    row = harness.session.added[0]
    assert row.response_status == "ok"
    assert row.generated_sql is not None


def test_needs_clarification_returns_interpretations(harness) -> None:
    result = SqlGenerationResult(
        status="needs_clarification",
        clarification_question="There is no income table — did you mean payments?",
        suggested_interpretations=[
            SuggestedInterpretation(
                label="Total payments",
                description="What is the total of payments.amount for last year?",
            )
        ],
    )
    response = harness.run([result])
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "needs_clarification"
    assert body["generated_sql"] is None
    assert body["clarification_question"].startswith("There is no income table")
    assert body["suggested_interpretations"][0]["label"] == "Total payments"
    row = harness.session.added[0]
    assert row.response_status == "needs_clarification"
    assert row.generated_sql is None
    assert row.clarification_json["suggested_interpretations"][0]["label"] == "Total payments"


def test_unanswerable_status(harness) -> None:
    result = SqlGenerationResult(status="unanswerable", explanation="No such data.")
    response = harness.run([result])
    body = response.json()
    assert response.status_code == 200
    assert body["status"] == "unanswerable"
    assert body["explanation"] == "No such data."
    assert harness.session.added[0].response_status == "unanswerable"


def test_verification_failed_after_retries(harness) -> None:
    # ask_max_retries=1 in the harness -> two attempts, both hallucinate.
    response = harness.run([_ok("SELECT x FROM income"), _ok("SELECT y FROM income")])
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "verification_failed"
    assert "income" in body["invalid_identifiers"]
    assert body["retry_count"] == 1
    assert "income" in body["generated_sql"]  # last SQL surfaced for manual fixing
    assert harness.session.added[0].response_status == "verification_failed"


def test_hallucination_recovers_via_retry(harness) -> None:
    response = harness.run([_ok("SELECT x FROM income"), _ok("SELECT amount FROM payments")])
    body = response.json()
    assert body["status"] == "ok"
    assert body["retry_count"] == 1
    assert "payments" in body["generated_sql"]


def test_token_usage_recorded_when_reported(harness) -> None:
    usage = TokenUsage(input_tokens=120, output_tokens=30, cache_read_tokens=50)
    response = harness.run([_ok("SELECT amount FROM payments")], usage=usage)
    assert response.status_code == 200
    records = [obj for obj in harness.session.added if isinstance(obj, TokenUsageRecord)]
    assert len(records) == 1
    row = records[0]
    assert row.operation == "generate_sql"
    assert row.provider == "fake"
    assert row.model == "fake-model"
    assert row.input_tokens == 120
    assert row.output_tokens == 30
    assert row.cache_read_tokens == 50
    assert row.total_tokens == 200
    assert row.connection_id == 7


def test_no_usage_row_when_zero_tokens(harness) -> None:
    # The default fake reports zero tokens (e.g. a fully cached/mocked call).
    harness.run([_ok("SELECT amount FROM payments")])
    records = [obj for obj in harness.session.added if isinstance(obj, TokenUsageRecord)]
    assert records == []


def _details_call() -> ChatTurn:
    return ChatTurn(
        text=None,
        tool_calls=[
            ToolCall(id="c1", name="get_table_details", input={"table_names": ["users_payment"]})
        ],
    )


def test_discovery_includes_semantically_matched_table(harness) -> None:
    # The model asks for users_payment's columns during discovery, then generates.
    response = harness.run(
        [_ok("SELECT SUM(amount) FROM users_payment")],
        chat_turns=[_details_call(), ChatTurn(text="ready", tool_calls=[])],
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    # The block handed to generate_sql must carry users_payment's full column detail.
    schema_block = harness.provider().seen_schema_blocks[0]
    assert "TABLE users_payment" in schema_block
    assert "status" in schema_block  # a column only present in the detailed block
    # payments was never requested -> only its name appears (in the directory).
    assert "TABLE payments" not in schema_block


def test_discovery_disabled_uses_select_schema(harness) -> None:
    response = harness.run([_ok("SELECT amount FROM payments")], ask_schema_discovery=False)
    assert response.status_code == 200
    # Discovery off -> provider.chat is never invoked.
    assert harness.provider().chat_systems == []


def test_discovery_usage_added_to_generate_usage(harness) -> None:
    discovery_turn = ChatTurn(
        text="ready", tool_calls=[], usage=TokenUsage(input_tokens=40, output_tokens=10)
    )
    harness.run(
        [_ok("SELECT amount FROM users_payment")],
        usage=TokenUsage(input_tokens=100, output_tokens=20),
        chat_turns=[_details_call(), discovery_turn],
    )
    records = [obj for obj in harness.session.added if isinstance(obj, TokenUsageRecord)]
    assert len(records) == 1
    # 40+10 (discovery) + 100+20 (generate) = 170.
    assert records[0].total_tokens == 170
