"""Tests for the admin audit feed: schema mapping and the disable flag."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from app.config import Settings
from app.models.query_history import QueryHistory, QueryStatus
from app.routers import admin_audit
from app.schemas.audit import AuditItem
from fastapi import HTTPException


def test_audit_item_maps_from_query_history() -> None:
    history = QueryHistory(
        id=7,
        user_id=3,
        connection_id=2,
        question="how many orders?",
        generated_sql="SELECT count(*) FROM orders",
        provider="anthropic",
        model="claude",
        last_status=QueryStatus.SUCCESS,
        row_count=1,
        created_at=datetime.now(tz=UTC),
    )
    item = AuditItem.model_validate(history, from_attributes=True)
    item.user_email = "user@example.com"

    assert item.id == 7
    assert item.user_id == 3
    assert item.question == "how many orders?"
    assert item.last_status == QueryStatus.SUCCESS
    assert item.user_email == "user@example.com"


async def test_audit_disabled_returns_404(monkeypatch: pytest.MonkeyPatch) -> None:
    disabled = Settings(admin_audit_enabled=False, ai_api_key="x", jwt_secret="s")
    monkeypatch.setattr(admin_audit, "get_settings", lambda: disabled)

    with pytest.raises(HTTPException) as excinfo:
        # The disabled check runs before any DB access, so the session is unused.
        await admin_audit.list_audit(_admin=object(), session=object())  # type: ignore[arg-type]
    assert excinfo.value.status_code == 404
