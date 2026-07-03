"""Tests for the generate -> validate -> verify retry orchestrator."""

from __future__ import annotations

from typing import Any

import pytest
from app.config import Settings
from app.services.ai.base import ChatMessage, SqlGenerationResult
from app.services.ai.generate import generate_with_verification
from app.services.ai.prompts import build_schema_block, build_system_prompt
from app.services.schema.introspect import SchemaData
from app.services.sql_guard import SqlGuardError, validate_select


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


SCHEMA: SchemaData = {"tables": [_table("payments", ["id", "amount", "paid_at"])]}


def _ok(sql: str) -> SqlGenerationResult:
    return SqlGenerationResult(status="ok", sql=sql, explanation="e")


class FakeProvider:
    """Returns scripted results in order, recording every message list."""

    name = "fake"
    model = "fake-model"

    def __init__(self, results: list[SqlGenerationResult]) -> None:
        self._results = list(results)
        self.seen_messages: list[list[ChatMessage]] = []

    def generate_sql(
        self, *, messages: list[ChatMessage], system_prompt: str, schema_block: str
    ) -> SqlGenerationResult:
        self.seen_messages.append(list(messages))
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


def _settings(**overrides: Any) -> Settings:
    return Settings(ai_api_key="test", **overrides)


async def _run(provider: FakeProvider, settings: Settings | None = None):
    return await generate_with_verification(
        provider=provider,
        connector=FakeConnector(),
        question="how much income last year?",
        full_schema=SCHEMA,
        selected_text="TABLE payments",
        settings=settings or _settings(),
    )


async def test_valid_sql_passes_first_try() -> None:
    provider = FakeProvider([_ok("SELECT amount FROM payments")])
    outcome = await _run(provider)
    assert outcome.verified
    assert outcome.retry_count == 0
    assert outcome.safe_sql is not None and "payments" in outcome.safe_sql


async def test_hallucinated_table_triggers_corrective_retry() -> None:
    provider = FakeProvider(
        [_ok("SELECT total FROM income"), _ok("SELECT SUM(amount) FROM payments")]
    )
    outcome = await _run(provider)
    assert outcome.verified
    assert outcome.retry_count == 1
    # The retry conversation carries the previous answer and the correction.
    retry_messages = provider.seen_messages[1]
    assert retry_messages[1]["role"] == "assistant"
    correction = retry_messages[2]["content"]
    assert "income" in correction
    assert "TABLES:" in correction


async def test_retries_stop_at_configured_cap() -> None:
    provider = FakeProvider([_ok("SELECT x FROM income")] * 3)
    outcome = await _run(provider, _settings(ask_max_retries=2))
    assert not outcome.verified
    assert outcome.retry_count == 2
    assert outcome.verification is not None
    assert outcome.verification.unknown_tables == ["income"]
    # The last SQL is still surfaced for manual inspection.
    assert outcome.safe_sql is not None and "income" in outcome.safe_sql


async def test_clarification_short_circuits_without_retry() -> None:
    provider = FakeProvider(
        [
            SqlGenerationResult(
                status="needs_clarification",
                clarification_question="Did you mean payments?",
            )
        ]
    )
    outcome = await _run(provider)
    assert outcome.result.status == "needs_clarification"
    assert outcome.retry_count == 0
    assert outcome.safe_sql is None
    assert len(provider.seen_messages) == 1


async def test_guard_rejection_also_triggers_retry() -> None:
    provider = FakeProvider([_ok("DELETE FROM payments"), _ok("SELECT amount FROM payments")])
    outcome = await _run(provider)
    assert outcome.verified
    assert outcome.retry_count == 1
    assert "rejected" in provider.seen_messages[1][2]["content"]


async def test_guard_rejection_on_final_attempt_raises() -> None:
    provider = FakeProvider([_ok("DELETE FROM payments")] * 3)
    with pytest.raises(SqlGuardError):
        await _run(provider, _settings(ask_max_retries=2))


async def test_verification_can_be_disabled() -> None:
    provider = FakeProvider([_ok("SELECT total FROM income")])
    outcome = await _run(provider, _settings(ask_verify_identifiers=False))
    assert outcome.verified
    assert outcome.retry_count == 0
