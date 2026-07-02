"""Router-level tests for POST /api/ask using dependency overrides (no network/DB)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from app.config import Settings
from app.db.panel import get_session
from app.deps import get_current_user
from app.models.query_history import QueryHistory
from app.routers import ask as ask_module
from app.services.ai.base import ChatMessage, SqlGenerationResult, SuggestedInterpretation
from app.services.ai.prompts import build_schema_block, build_system_prompt
from app.services.sql_guard import validate_select
from fastapi import FastAPI
from fastapi.testclient import TestClient

SCHEMA_JSON: dict[str, Any] = {
    "tables": [
        {
            "schema": "public",
            "name": "payments",
            "comment": None,
            "columns": [
                {"name": "id", "type": "integer", "nullable": False, "comment": None},
                {"name": "amount", "type": "numeric", "nullable": True, "comment": None},
            ],
            "primary_key": ["id"],
            "foreign_keys": [],
        }
    ]
}


class FakeProvider:
    name = "fake"
    model = "fake-model"

    def __init__(self, results: list[SqlGenerationResult]) -> None:
        self._results = list(results)

    def generate_sql(
        self, *, messages: list[ChatMessage], system_prompt: str, schema_block: str
    ) -> SqlGenerationResult:
        return self._results.pop(0)


class FakeConnector:
    type = "postgres"
    dialect = "postgres"

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
    connection = SimpleNamespace(
        id=7, name="demo", database="demo", host="localhost", port=5432
    )
    snapshot = SimpleNamespace(table_count=1, content_json=SCHEMA_JSON)
    provider_holder: dict[str, FakeProvider] = {}

    async def fake_load_connector(*_args: Any, **_kwargs: Any):
        return connection, FakeConnector()

    async def fake_ensure_snapshot(*_args: Any, **_kwargs: Any):
        return snapshot

    async def fake_load_glossary(*_args: Any, **_kwargs: Any):
        return [], []

    monkeypatch.setattr(ask_module, "load_connector", fake_load_connector)
    monkeypatch.setattr(ask_module, "ensure_snapshot", fake_ensure_snapshot)
    monkeypatch.setattr(ask_module, "load_glossary", fake_load_glossary)
    monkeypatch.setattr(ask_module, "get_ai_provider", lambda: provider_holder["provider"])
    monkeypatch.setattr(
        ask_module, "get_settings", lambda: Settings(ai_api_key="test", ask_max_retries=1)
    )

    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=1)

    client = TestClient(app)

    def run(results: list[SqlGenerationResult]):
        provider_holder["provider"] = FakeProvider(results)
        return client.post("/api/ask", json={"connection_id": 7, "question": "income last year?"})

    return SimpleNamespace(run=run, session=session)


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
