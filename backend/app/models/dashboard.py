"""User-built dashboards: a grid of SQL-backed chart/table widgets.

A :class:`Dashboard` is owned by a user; ``shared=True`` makes it visible to
every panel user (widget data still respects per-connection access). Each
:class:`DashboardWidget` carries its own connection, SQL, visualization config,
and grid geometry.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class Dashboard(Base, TimestampMixin):
    __tablename__ = "dashboards"
    __table_args__ = (Index("ix_dashboards_owner_created", "owner_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    shared: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class DashboardWidget(Base, TimestampMixin):
    __tablename__ = "dashboard_widgets"

    id: Mapped[int] = mapped_column(primary_key=True)
    dashboard_id: Mapped[int] = mapped_column(
        ForeignKey("dashboards.id", ondelete="CASCADE"), nullable=False
    )
    # The data source this widget queries; SET NULL if it is deleted.
    connection_id: Mapped[int | None] = mapped_column(
        ForeignKey("connections.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    sql: Mapped[str] = mapped_column(Text, nullable=False)
    # {view: "table"|"bar"|"hbar"|"line"|"area"|"pie"|"scatter", x_column, y_column}
    viz_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    # Grid geometry in react-grid-layout units.
    pos_x: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    pos_y: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    width: Mapped[int] = mapped_column(Integer, nullable=False, default=6, server_default="6")
    height: Mapped[int] = mapped_column(Integer, nullable=False, default=4, server_default="4")
