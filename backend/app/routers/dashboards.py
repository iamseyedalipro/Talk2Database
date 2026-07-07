"""Dashboards: user-arranged grids of SQL-backed chart/table widgets.

Visibility mirrors saved queries: owners see their own dashboards, everyone
sees ``shared`` ones, and only the owner (or an admin, for shared dashboards)
may edit. Widget data always flows through the caller's own connection access
(``load_connector``) and the read-only SQL guard, so sharing a dashboard never
grants access to data the viewer couldn't already query.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import func, or_, select
from starlette.concurrency import run_in_threadpool

from app.config import get_settings
from app.connectors import ConnectorQueryError
from app.deps import CurrentUser, SessionDep
from app.models.dashboard import Dashboard, DashboardWidget
from app.models.user import User
from app.schemas.dashboard import (
    DashboardCreate,
    DashboardDetail,
    DashboardItem,
    DashboardUpdate,
    LayoutUpdate,
    WidgetCreate,
    WidgetItem,
    WidgetRunRequest,
    WidgetUpdate,
    WidgetViz,
)
from app.schemas.execute import ExecuteResponse, ResultColumn
from app.services.connections import load_connector
from app.services.sql_guard import SqlGuardError

router = APIRouter(prefix="/dashboards", tags=["dashboards"])


def can_view(user: User, dashboard: Dashboard) -> bool:
    """A user may view their own dashboards and any shared one."""
    return dashboard.owner_id == user.id or dashboard.shared


def can_edit(user: User, dashboard: Dashboard) -> bool:
    """The owner may always edit; an admin may manage a *shared* one."""
    return dashboard.owner_id == user.id or (user.is_admin and dashboard.shared)


def _widget_item(widget: DashboardWidget) -> WidgetItem:
    return WidgetItem(
        id=widget.id,
        title=widget.title,
        connection_id=widget.connection_id,
        sql=widget.sql,
        viz=WidgetViz.model_validate(widget.viz_json),
        x=widget.pos_x,
        y=widget.pos_y,
        w=widget.width,
        h=widget.height,
    )


def _to_item(
    dashboard: Dashboard, user: User, owner_email: str | None, widget_count: int
) -> DashboardItem:
    item = DashboardItem.model_validate(dashboard)
    item.owner_email = owner_email
    item.is_owner = dashboard.owner_id == user.id
    item.widget_count = widget_count
    return item


async def _get_visible(session: SessionDep, user: User, dashboard_id: int) -> Dashboard:
    dashboard = await session.get(Dashboard, dashboard_id)
    if dashboard is None or not can_view(user, dashboard):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dashboard not found.")
    return dashboard


async def _get_editable(session: SessionDep, user: User, dashboard_id: int) -> Dashboard:
    dashboard = await _get_visible(session, user, dashboard_id)
    if not can_edit(user, dashboard):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to edit this dashboard.",
        )
    return dashboard


@router.get("", response_model=list[DashboardItem])
async def list_dashboards(user: CurrentUser, session: SessionDep) -> list[DashboardItem]:
    counts = (
        select(DashboardWidget.dashboard_id, func.count().label("n"))
        .group_by(DashboardWidget.dashboard_id)
        .subquery()
    )
    result = await session.execute(
        select(Dashboard, User.email, func.coalesce(counts.c.n, 0))
        .join(User, User.id == Dashboard.owner_id)
        .outerjoin(counts, counts.c.dashboard_id == Dashboard.id)
        .where(or_(Dashboard.owner_id == user.id, Dashboard.shared.is_(True)))
        .order_by(Dashboard.updated_at.desc())
    )
    return [_to_item(d, user, email, n) for d, email, n in result.all()]


@router.post("", response_model=DashboardItem, status_code=status.HTTP_201_CREATED)
async def create_dashboard(
    payload: DashboardCreate, user: CurrentUser, session: SessionDep
) -> DashboardItem:
    dashboard = Dashboard(
        owner_id=user.id,
        name=payload.name,
        description=payload.description,
        shared=payload.shared,
    )
    session.add(dashboard)
    await session.flush()
    await session.refresh(dashboard)
    return _to_item(dashboard, user, user.email, 0)


@router.get("/{dashboard_id}", response_model=DashboardDetail)
async def get_dashboard(
    dashboard_id: int, user: CurrentUser, session: SessionDep
) -> DashboardDetail:
    dashboard = await _get_visible(session, user, dashboard_id)
    owner_email = await session.scalar(select(User.email).where(User.id == dashboard.owner_id))
    widgets = (
        await session.scalars(
            select(DashboardWidget)
            .where(DashboardWidget.dashboard_id == dashboard.id)
            .order_by(DashboardWidget.pos_y, DashboardWidget.pos_x, DashboardWidget.id)
        )
    ).all()
    item = _to_item(dashboard, user, owner_email, len(widgets))
    return DashboardDetail(**item.model_dump(), widgets=[_widget_item(w) for w in widgets])


@router.patch("/{dashboard_id}", response_model=DashboardItem)
async def update_dashboard(
    dashboard_id: int, payload: DashboardUpdate, user: CurrentUser, session: SessionDep
) -> DashboardItem:
    dashboard = await _get_editable(session, user, dashboard_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(dashboard, field, value)
    await session.flush()
    await session.refresh(dashboard)
    owner_email = await session.scalar(select(User.email).where(User.id == dashboard.owner_id))
    count = await session.scalar(
        select(func.count())
        .select_from(DashboardWidget)
        .where(DashboardWidget.dashboard_id == dashboard.id)
    )
    return _to_item(dashboard, user, owner_email, count or 0)


@router.delete("/{dashboard_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_dashboard(dashboard_id: int, user: CurrentUser, session: SessionDep) -> Response:
    dashboard = await _get_editable(session, user, dashboard_id)
    await session.delete(dashboard)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ------------------------------- Widgets ---------------------------------- #


@router.post("/{dashboard_id}/widgets", response_model=WidgetItem, status_code=201)
async def create_widget(
    dashboard_id: int, payload: WidgetCreate, user: CurrentUser, session: SessionDep
) -> WidgetItem:
    dashboard = await _get_editable(session, user, dashboard_id)
    # The editor must themselves have access to the widget's data source.
    await load_connector(session, payload.connection_id, user)
    widget = DashboardWidget(
        dashboard_id=dashboard.id,
        connection_id=payload.connection_id,
        title=payload.title,
        sql=payload.sql,
        viz_json=payload.viz.model_dump(),
        pos_x=payload.x,
        pos_y=payload.y,
        width=payload.w,
        height=payload.h,
    )
    session.add(widget)
    await session.flush()
    return _widget_item(widget)


async def _get_widget(
    session: SessionDep, dashboard_id: int, widget_id: int
) -> DashboardWidget:
    widget = await session.get(DashboardWidget, widget_id)
    if widget is None or widget.dashboard_id != dashboard_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Widget not found.")
    return widget


@router.patch("/{dashboard_id}/widgets/{widget_id}", response_model=WidgetItem)
async def update_widget(
    dashboard_id: int,
    widget_id: int,
    payload: WidgetUpdate,
    user: CurrentUser,
    session: SessionDep,
) -> WidgetItem:
    await _get_editable(session, user, dashboard_id)
    widget = await _get_widget(session, dashboard_id, widget_id)
    data = payload.model_dump(exclude_unset=True)
    if "connection_id" in data and data["connection_id"] is not None:
        await load_connector(session, data["connection_id"], user)
    if "viz" in data and data["viz"] is not None:
        widget.viz_json = WidgetViz.model_validate(data.pop("viz")).model_dump()
    for field, value in data.items():
        setattr(widget, field, value)
    await session.flush()
    return _widget_item(widget)


@router.delete("/{dashboard_id}/widgets/{widget_id}", status_code=204)
async def delete_widget(
    dashboard_id: int, widget_id: int, user: CurrentUser, session: SessionDep
) -> Response:
    await _get_editable(session, user, dashboard_id)
    widget = await _get_widget(session, dashboard_id, widget_id)
    await session.delete(widget)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/{dashboard_id}/layout", status_code=204)
async def save_layout(
    dashboard_id: int, payload: LayoutUpdate, user: CurrentUser, session: SessionDep
) -> Response:
    await _get_editable(session, user, dashboard_id)
    widgets = (
        await session.scalars(
            select(DashboardWidget).where(DashboardWidget.dashboard_id == dashboard_id)
        )
    ).all()
    by_id = {w.id: w for w in widgets}
    for item in payload.items:
        widget = by_id.get(item.widget_id)
        if widget is None:
            continue
        widget.pos_x = item.x
        widget.pos_y = item.y
        widget.width = item.w
        widget.height = item.h
    await session.flush()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{dashboard_id}/widgets/{widget_id}/run", response_model=ExecuteResponse)
async def run_widget(
    dashboard_id: int,
    widget_id: int,
    payload: WidgetRunRequest,
    user: CurrentUser,
    session: SessionDep,
) -> ExecuteResponse:
    dashboard = await _get_visible(session, user, dashboard_id)
    widget = await _get_widget(session, dashboard_id, widget_id)
    if widget.connection_id is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The connection for this widget no longer exists.",
        )

    # load_connector enforces the *caller's* access to the widget's connection —
    # a viewer of a shared dashboard without access gets a per-widget, non-leaky
    # message instead of the whole dashboard failing.
    try:
        _, connector = await load_connector(session, widget.connection_id, user)
    except HTTPException as exc:
        if exc.status_code == status.HTTP_404_NOT_FOUND and dashboard.owner_id != user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have access to this widget's data source.",
            ) from exc
        raise

    try:
        safe_sql = connector.validate(widget.sql)
    except SqlGuardError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Only single read-only SELECT statements may be executed: {exc}",
        ) from exc

    cap = get_settings().query_max_rows
    max_rows = min(payload.max_rows, cap) if payload.max_rows else cap

    try:
        result = await run_in_threadpool(connector.run, safe_sql, max_rows)
    except ConnectorQueryError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Query failed: {exc}"
        ) from exc

    return ExecuteResponse(
        columns=[ResultColumn(name=name, type=type_) for name, type_ in result.columns],
        rows=result.rows,
        row_count=result.row_count,
        truncated=result.truncated,
        elapsed_ms=result.elapsed_ms,
    )
