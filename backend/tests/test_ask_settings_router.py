"""Tests for the admin Ask-analysis-mode settings endpoints."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from app.db.panel import get_session
from app.deps import get_current_user
from app.models.app_setting import AppSetting
from app.routers import ask_settings as ask_settings_module
from fastapi import FastAPI
from fastapi.testclient import TestClient


class FakeSettingsSession:
    """In-memory stand-in for the app_settings key/value table."""

    def __init__(self) -> None:
        self.rows: dict[str, AppSetting] = {}

    async def get(self, _model: Any, key: str) -> AppSetting | None:
        return self.rows.get(key)

    def add(self, obj: AppSetting) -> None:
        self.rows[obj.key] = obj

    async def flush(self) -> None:
        pass


@pytest.fixture()
def harness():
    app = FastAPI()
    app.include_router(ask_settings_module.router, prefix="/api")

    session = FakeSettingsSession()
    user_holder = {"user": SimpleNamespace(id=1, is_admin=True)}

    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_current_user] = lambda: user_holder["user"]

    return SimpleNamespace(client=TestClient(app), session=session, user_holder=user_holder)


def test_defaults(harness) -> None:
    response = harness.client.get("/api/admin/ask-settings")
    assert response.status_code == 200
    body = response.json()
    assert body["analysis_mode"] is False
    assert body["row_cap"] == 10
    assert body["row_cap_min"] == 5
    assert body["row_cap_max"] == 100


def test_put_roundtrip(harness) -> None:
    response = harness.client.put(
        "/api/admin/ask-settings", json={"analysis_mode": True, "row_cap": 25}
    )
    assert response.status_code == 200
    assert response.json()["analysis_mode"] is True
    assert response.json()["row_cap"] == 25

    body = harness.client.get("/api/admin/ask-settings").json()
    assert body["analysis_mode"] is True
    assert body["row_cap"] == 25


@pytest.mark.parametrize("row_cap", [0, 4, 101])
def test_row_cap_out_of_range_rejected(harness, row_cap: int) -> None:
    response = harness.client.put(
        "/api/admin/ask-settings", json={"analysis_mode": True, "row_cap": row_cap}
    )
    assert response.status_code == 422


def test_non_admin_forbidden(harness) -> None:
    harness.user_holder["user"] = SimpleNamespace(id=2, is_admin=False)
    assert harness.client.get("/api/admin/ask-settings").status_code == 403
    assert (
        harness.client.put(
            "/api/admin/ask-settings", json={"analysis_mode": True, "row_cap": 10}
        ).status_code
        == 403
    )
