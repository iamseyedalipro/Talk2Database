"""Tests for dashboard visibility/edit permissions and the widget run endpoint."""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import pytest
from app.db.panel import get_session
from app.deps import get_current_user
from app.models.dashboard import Dashboard, DashboardWidget
from app.routers import dashboards as dashboards_module
from app.routers.dashboards import can_edit, can_view
from app.services.sql_guard import validate_select
from fastapi import FastAPI, HTTPException, status
from fastapi.testclient import TestClient


@dataclass
class _User:
    id: int
    is_admin: bool = False


@dataclass
class _Dashboard:
    owner_id: int
    shared: bool = False


OWNER = _User(id=1)
OTHER = _User(id=2)
ADMIN = _User(id=3, is_admin=True)


@pytest.mark.parametrize(
    ("user", "dashboard", "expected"),
    [
        (OWNER, _Dashboard(owner_id=1, shared=False), True),  # own private
        (OTHER, _Dashboard(owner_id=1, shared=False), False),  # other's private hidden
        (OTHER, _Dashboard(owner_id=1, shared=True), True),  # other's shared visible
        (ADMIN, _Dashboard(owner_id=1, shared=False), False),  # admin can't see private
    ],
)
def test_can_view(user: _User, dashboard: _Dashboard, expected: bool) -> None:
    assert can_view(user, dashboard) is expected  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("user", "dashboard", "expected"),
    [
        (OWNER, _Dashboard(owner_id=1, shared=False), True),  # owner edits own
        (OTHER, _Dashboard(owner_id=1, shared=True), False),  # non-owner cannot edit shared
        (ADMIN, _Dashboard(owner_id=1, shared=True), True),  # admin moderates shared
        (ADMIN, _Dashboard(owner_id=1, shared=False), False),  # admin can't touch private
    ],
)
def test_can_edit(user: _User, dashboard: _Dashboard, expected: bool) -> None:
    assert can_edit(user, dashboard) is expected  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# POST /dashboards/{id}/widgets/{wid}/run (router-level, fakes, no DB)
# --------------------------------------------------------------------------- #


class FakeConnector:
    type = "postgres"
    dialect = "postgres"
    label = "PostgreSQL"

    def validate(self, query: str) -> str:
        return validate_select(query, "postgres")

    def run(self, query: str, max_rows: int) -> SimpleNamespace:
        return SimpleNamespace(
            columns=[("n", "integer")],
            rows=[[1]],
            row_count=1,
            truncated=False,
            elapsed_ms=3,
        )


class FakeSession:
    """Serves the dashboard + widget rows the run endpoint loads."""

    def __init__(self, dashboard: Dashboard, widget: DashboardWidget) -> None:
        self._rows = {(Dashboard, dashboard.id): dashboard, (DashboardWidget, widget.id): widget}

    async def get(self, model: Any, key: Any) -> Any:
        return self._rows.get((model, key))


def _harness(
    *,
    dashboard: Dashboard,
    widget: DashboardWidget,
    caller: SimpleNamespace,
    connector_access: bool,
) -> TestClient:
    app = FastAPI()
    app.include_router(dashboards_module.router, prefix="/api")

    async def fake_load_connector(*_args: Any, **_kwargs: Any):
        if not connector_access:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")
        return SimpleNamespace(id=widget.connection_id), FakeConnector()

    original = dashboards_module.load_connector
    dashboards_module.load_connector = fake_load_connector
    app.dependency_overrides[get_session] = lambda: FakeSession(dashboard, widget)
    app.dependency_overrides[get_current_user] = lambda: caller
    client = TestClient(app)
    client.original_load_connector = original  # type: ignore[attr-defined]
    return client


def _dashboard(owner_id: int, shared: bool) -> Dashboard:
    return Dashboard(id=10, owner_id=owner_id, name="d", shared=shared)


def _widget(sql: str) -> DashboardWidget:
    return DashboardWidget(
        id=20, dashboard_id=10, connection_id=5, title="w", sql=sql, viz_json={"view": "table"}
    )


def _restore(client: TestClient) -> None:
    dashboards_module.load_connector = client.original_load_connector  # type: ignore[attr-defined]


def test_run_widget_ok() -> None:
    caller = SimpleNamespace(id=1, is_admin=False)
    client = _harness(
        dashboard=_dashboard(owner_id=1, shared=False),
        widget=_widget("SELECT count(*) AS n FROM users"),
        caller=caller,
        connector_access=True,
    )
    try:
        res = client.post("/api/dashboards/10/widgets/20/run", json={})
        assert res.status_code == 200
        assert res.json()["rows"] == [[1]]
    finally:
        _restore(client)


def test_run_widget_no_access_gets_friendly_403() -> None:
    # A viewer of a *shared* dashboard without access to the widget's connection.
    caller = SimpleNamespace(id=2, is_admin=False)
    client = _harness(
        dashboard=_dashboard(owner_id=1, shared=True),
        widget=_widget("SELECT count(*) AS n FROM users"),
        caller=caller,
        connector_access=False,
    )
    try:
        res = client.post("/api/dashboards/10/widgets/20/run", json={})
        assert res.status_code == 403
        assert "access to this widget's data source" in res.json()["detail"]
    finally:
        _restore(client)


def test_run_widget_guard_rejects_writes() -> None:
    caller = SimpleNamespace(id=1, is_admin=False)
    client = _harness(
        dashboard=_dashboard(owner_id=1, shared=False),
        widget=_widget("UPDATE users SET name = 'x'"),
        caller=caller,
        connector_access=True,
    )
    try:
        res = client.post("/api/dashboards/10/widgets/20/run", json={})
        assert res.status_code == 422
        assert "read-only" in res.json()["detail"]
    finally:
        _restore(client)


def test_run_widget_private_dashboard_hidden_from_others() -> None:
    caller = SimpleNamespace(id=2, is_admin=False)
    client = _harness(
        dashboard=_dashboard(owner_id=1, shared=False),
        widget=_widget("SELECT 1 AS n"),
        caller=caller,
        connector_access=True,
    )
    try:
        res = client.post("/api/dashboards/10/widgets/20/run", json={})
        assert res.status_code == 404
    finally:
        _restore(client)
