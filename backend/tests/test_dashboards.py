"""Tests for dashboard visibility/edit permissions and the widget run endpoint."""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import pytest
from app.db.panel import get_session
from app.deps import get_current_user
from app.models.dashboard import Dashboard, DashboardWidget
from app.models.dashboard_share import DashboardAccessLevel
from app.routers import dashboards as dashboards_module
from app.routers.dashboards import access_label, can_edit, can_view
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


VIEW = DashboardAccessLevel.VIEW
EDIT = DashboardAccessLevel.EDIT


@pytest.mark.parametrize(
    ("level", "view", "edit", "label"),
    [
        (None, False, False, None),  # no grant on a private dashboard
        (VIEW, True, False, "view"),  # view grant: visible, not editable
        (EDIT, True, True, "edit"),  # edit grant: visible and editable
    ],
)
def test_per_user_share_levels(
    level: DashboardAccessLevel | None, view: bool, edit: bool, label: str | None
) -> None:
    # A non-owner, non-admin user on someone else's *private* dashboard.
    dash = _Dashboard(owner_id=1, shared=False)
    assert can_view(OTHER, dash, level) is view  # type: ignore[arg-type]
    assert can_edit(OTHER, dash, level) is edit  # type: ignore[arg-type]
    assert access_label(OTHER, dash, level) == label  # type: ignore[arg-type]


def test_access_label_owner_and_admin() -> None:
    assert access_label(OWNER, _Dashboard(owner_id=1, shared=False)) == "owner"  # type: ignore[arg-type]
    # An admin moderating a globally shared dashboard is labelled as an editor.
    assert access_label(ADMIN, _Dashboard(owner_id=1, shared=True)) == "edit"  # type: ignore[arg-type]
    # A plain viewer of a globally shared dashboard.
    assert access_label(OTHER, _Dashboard(owner_id=1, shared=True)) == "view"  # type: ignore[arg-type]


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

    def __init__(
        self,
        dashboard: Dashboard,
        widget: DashboardWidget,
        share_level: DashboardAccessLevel | None = None,
    ) -> None:
        self._rows = {(Dashboard, dashboard.id): dashboard, (DashboardWidget, widget.id): widget}
        self._share_level = share_level

    async def get(self, model: Any, key: Any) -> Any:
        return self._rows.get((model, key))

    async def scalar(self, *_args: Any, **_kwargs: Any) -> Any:
        # Stands in for the caller's per-user share grant lookup.
        return self._share_level


def _harness(
    *,
    dashboard: Dashboard,
    widget: DashboardWidget,
    caller: SimpleNamespace,
    connector_access: bool,
    share_level: DashboardAccessLevel | None = None,
) -> TestClient:
    app = FastAPI()
    app.include_router(dashboards_module.router, prefix="/api")

    async def fake_load_connector(*_args: Any, **_kwargs: Any):
        if not connector_access:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")
        return SimpleNamespace(id=widget.connection_id), FakeConnector()

    original = dashboards_module.load_connector
    dashboards_module.load_connector = fake_load_connector
    app.dependency_overrides[get_session] = lambda: FakeSession(dashboard, widget, share_level)
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


def test_run_widget_view_grantee_can_run_private_dashboard() -> None:
    # A per-user *view* grant makes an otherwise-private dashboard visible.
    caller = SimpleNamespace(id=2, is_admin=False)
    client = _harness(
        dashboard=_dashboard(owner_id=1, shared=False),
        widget=_widget("SELECT 1 AS n"),
        caller=caller,
        connector_access=True,
        share_level=DashboardAccessLevel.VIEW,
    )
    try:
        res = client.post("/api/dashboards/10/widgets/20/run", json={})
        assert res.status_code == 200
        assert res.json()["rows"] == [[1]]
    finally:
        _restore(client)


# --------------------------------------------------------------------------- #
# WidgetViz schema: legacy normalization and new-shape round trip
# --------------------------------------------------------------------------- #


def test_widget_viz_legacy_row_normalizes() -> None:
    from app.schemas.dashboard import WidgetViz

    viz = WidgetViz.model_validate({"view": "bar", "x_column": "day", "y_column": "orders"})
    assert viz.y_columns == ["orders"]
    assert viz.y_column == "orders"
    assert viz.series_column is None
    assert viz.stacked == "none"
    assert viz.pie_mode == "category"


def test_widget_viz_new_shape_round_trips() -> None:
    from app.schemas.dashboard import WidgetViz

    payload = {
        "view": "combo",
        "x_column": "month",
        "y_columns": ["revenue", "growth"],
        "series_column": None,
        "stacked": "none",
        "combo_types": {"growth": "line"},
        "right_axis": ["growth"],
        "pie_mode": "category",
    }
    viz = WidgetViz.model_validate(payload)
    dumped = viz.model_dump()
    assert dumped["y_columns"] == ["revenue", "growth"]
    assert dumped["combo_types"] == {"growth": "line"}
    assert dumped["right_axis"] == ["growth"]
    # Legacy key mirrors the first Y column for rollback safety.
    assert dumped["y_column"] == "revenue"
    assert WidgetViz.model_validate(dumped) == viz


def test_widget_viz_defaults_stay_empty() -> None:
    from app.schemas.dashboard import WidgetViz

    viz = WidgetViz()
    assert viz.view == "table"
    assert viz.y_columns == []
    assert viz.y_column is None
