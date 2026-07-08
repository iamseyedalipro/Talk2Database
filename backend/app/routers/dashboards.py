"""Dashboards: user-arranged grids of SQL-backed chart/table widgets.

Visibility mirrors saved queries: owners see their own dashboards, everyone
sees ``shared`` ones, and only the owner (or an admin, for shared dashboards)
may edit. Widget data always flows through the caller's own connection access
(``load_connector``) and the read-only SQL guard, so sharing a dashboard never
grants access to data the viewer couldn't already query.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import delete, func, or_, select
from starlette.concurrency import run_in_threadpool

from app.config import get_settings
from app.connectors import ConnectorQueryError
from app.deps import CurrentUser, SessionDep
from app.models.dashboard import Dashboard, DashboardWidget
from app.models.dashboard_share import DashboardAccessLevel, DashboardShare
from app.models.user import User
from app.schemas.dashboard import (
    DashboardCreate,
    DashboardDetail,
    DashboardItem,
    DashboardShareItem,
    DashboardSharesUpdate,
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


def can_view(
    user: User, dashboard: Dashboard, share_level: DashboardAccessLevel | None = None
) -> bool:
    """A user may view their own dashboards, any globally shared one, or one
    shared with them directly (``share_level`` being their grant, if any)."""
    return dashboard.owner_id == user.id or dashboard.shared or share_level is not None


def can_edit(
    user: User, dashboard: Dashboard, share_level: DashboardAccessLevel | None = None
) -> bool:
    """The owner may always edit; an admin may manage a *shared* one; a user
    granted ``edit`` access may edit their share."""
    return (
        dashboard.owner_id == user.id
        or (user.is_admin and dashboard.shared)
        or share_level == DashboardAccessLevel.EDIT
    )


def access_label(
    user: User, dashboard: Dashboard, share_level: DashboardAccessLevel | None = None
) -> str | None:
    """The caller's effective access as ``"owner"``/``"edit"``/``"view"``, or
    ``None`` when they cannot see the dashboard at all."""
    if dashboard.owner_id == user.id:
        return "owner"
    if can_edit(user, dashboard, share_level):
        return "edit"
    if can_view(user, dashboard, share_level):
        return "view"
    return None


async def _share_level(
    session: SessionDep, user: User, dashboard_id: int
) -> DashboardAccessLevel | None:
    """The caller's direct share grant on a dashboard, if any."""
    level: DashboardAccessLevel | None = await session.scalar(
        select(DashboardShare.access_level).where(
            DashboardShare.dashboard_id == dashboard_id,
            DashboardShare.user_id == user.id,
        )
    )
    return level


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
    dashboard: Dashboard,
    user: User,
    owner_email: str | None,
    widget_count: int,
    my_access: str = "owner",
) -> DashboardItem:
    item = DashboardItem.model_validate(dashboard)
    item.owner_email = owner_email
    item.is_owner = dashboard.owner_id == user.id
    item.my_access = my_access  # type: ignore[assignment]
    item.widget_count = widget_count
    return item


async def _get_visible(session: SessionDep, user: User, dashboard_id: int) -> Dashboard:
    dashboard = await session.get(Dashboard, dashboard_id)
    if dashboard is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dashboard not found.")
    level = await _share_level(session, user, dashboard_id)
    if not can_view(user, dashboard, level):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dashboard not found.")
    return dashboard


async def _get_editable(session: SessionDep, user: User, dashboard_id: int) -> Dashboard:
    dashboard = await _get_visible(session, user, dashboard_id)
    level = await _share_level(session, user, dashboard_id)
    if not can_edit(user, dashboard, level):
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
    # The caller's own share grants, joined in so we can both surface
    # shared-with-me dashboards and label the caller's effective access.
    shares = (
        select(DashboardShare.dashboard_id, DashboardShare.access_level)
        .where(DashboardShare.user_id == user.id)
        .subquery()
    )
    result = await session.execute(
        select(Dashboard, User.email, func.coalesce(counts.c.n, 0), shares.c.access_level)
        .join(User, User.id == Dashboard.owner_id)
        .outerjoin(counts, counts.c.dashboard_id == Dashboard.id)
        .outerjoin(shares, shares.c.dashboard_id == Dashboard.id)
        .where(
            or_(
                Dashboard.owner_id == user.id,
                Dashboard.shared.is_(True),
                shares.c.dashboard_id.is_not(None),
            )
        )
        .order_by(Dashboard.updated_at.desc())
    )
    return [
        _to_item(d, user, email, n, access_label(user, d, level) or "view")
        for d, email, n, level in result.all()
    ]


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
    return _to_item(dashboard, user, user.email, 0, "owner")


@router.get("/{dashboard_id}", response_model=DashboardDetail)
async def get_dashboard(
    dashboard_id: int, user: CurrentUser, session: SessionDep
) -> DashboardDetail:
    dashboard = await _get_visible(session, user, dashboard_id)
    level = await _share_level(session, user, dashboard_id)
    owner_email = await session.scalar(select(User.email).where(User.id == dashboard.owner_id))
    widgets = (
        await session.scalars(
            select(DashboardWidget)
            .where(DashboardWidget.dashboard_id == dashboard.id)
            .order_by(DashboardWidget.pos_y, DashboardWidget.pos_x, DashboardWidget.id)
        )
    ).all()
    item = _to_item(
        dashboard, user, owner_email, len(widgets), access_label(user, dashboard, level) or "view"
    )
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
    level = await _share_level(session, user, dashboard_id)
    owner_email = await session.scalar(select(User.email).where(User.id == dashboard.owner_id))
    count = await session.scalar(
        select(func.count())
        .select_from(DashboardWidget)
        .where(DashboardWidget.dashboard_id == dashboard.id)
    )
    return _to_item(
        dashboard, user, owner_email, count or 0, access_label(user, dashboard, level) or "view"
    )


@router.delete("/{dashboard_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_dashboard(dashboard_id: int, user: CurrentUser, session: SessionDep) -> Response:
    dashboard = await _get_editable(session, user, dashboard_id)
    await session.delete(dashboard)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# -------------------------------- Sharing --------------------------------- #


async def _get_manageable(session: SessionDep, user: User, dashboard_id: int) -> Dashboard:
    """Only the owner (or an admin) may manage who a dashboard is shared with."""
    dashboard = await _get_visible(session, user, dashboard_id)
    if dashboard.owner_id != user.id and not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the dashboard owner can manage sharing.",
        )
    return dashboard


async def _list_shares(session: SessionDep, dashboard_id: int) -> list[DashboardShareItem]:
    rows = await session.execute(
        select(DashboardShare.user_id, User.email, DashboardShare.access_level)
        .join(User, User.id == DashboardShare.user_id)
        .where(DashboardShare.dashboard_id == dashboard_id)
        .order_by(User.email)
    )
    return [
        DashboardShareItem(user_id=uid, email=email, access_level=level.value)
        for uid, email, level in rows.all()
    ]


@router.get("/{dashboard_id}/shares", response_model=list[DashboardShareItem])
async def list_dashboard_shares(
    dashboard_id: int, user: CurrentUser, session: SessionDep
) -> list[DashboardShareItem]:
    await _get_manageable(session, user, dashboard_id)
    return await _list_shares(session, dashboard_id)


@router.put("/{dashboard_id}/shares", response_model=list[DashboardShareItem])
async def set_dashboard_shares(
    dashboard_id: int,
    payload: DashboardSharesUpdate,
    user: CurrentUser,
    session: SessionDep,
) -> list[DashboardShareItem]:
    """Replace a dashboard's full set of per-user grants.

    The owner's own id and unknown/inactive users are ignored; the last grant
    wins if a user id is repeated.
    """
    dashboard = await _get_manageable(session, user, dashboard_id)

    # Desired level per user id (skip the owner — their access is implicit).
    desired: dict[int, DashboardAccessLevel] = {
        entry.user_id: DashboardAccessLevel(entry.access_level)
        for entry in payload.shares
        if entry.user_id != dashboard.owner_id
    }
    if desired:
        valid_ids = set(
            (
                await session.scalars(
                    select(User.id).where(User.id.in_(desired), User.is_active.is_(True))
                )
            ).all()
        )
        desired = {uid: level for uid, level in desired.items() if uid in valid_ids}

    existing = {
        share.user_id: share
        for share in (
            await session.scalars(
                select(DashboardShare).where(DashboardShare.dashboard_id == dashboard_id)
            )
        ).all()
    }

    to_remove = set(existing) - set(desired)
    if to_remove:
        await session.execute(
            delete(DashboardShare).where(
                DashboardShare.dashboard_id == dashboard_id,
                DashboardShare.user_id.in_(to_remove),
            )
        )
    for user_id, level in desired.items():
        current = existing.get(user_id)
        if current is None:
            session.add(
                DashboardShare(
                    dashboard_id=dashboard_id,
                    user_id=user_id,
                    access_level=level,
                    granted_by=user.id,
                )
            )
        elif current.access_level != level:
            current.access_level = level
    await session.flush()

    return await _list_shares(session, dashboard_id)


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


async def _get_widget(session: SessionDep, dashboard_id: int, widget_id: int) -> DashboardWidget:
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
