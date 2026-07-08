"""Per-user share grants for dashboards owned by someone else.

A dashboard is owned by exactly one user (:attr:`Dashboard.owner_id`) and can be
made globally visible with ``Dashboard.shared``. This join table lets the *owner*
share a dashboard with specific users at a chosen access level:

* ``view`` — the grantee can open the dashboard, run its widgets (through their
  own connection access), and read each widget's SQL, but not change anything.
* ``edit`` — additionally lets the grantee add/edit/delete widgets and rearrange
  the layout.

Per-user grants are layered on top of ``Dashboard.shared``: the global toggle
still grants everyone view access; these rows add named recipients (and the
``edit`` level, which the global toggle never confers to non-admins).
"""

from __future__ import annotations

from enum import StrEnum

from sqlalchemy import Enum, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class DashboardAccessLevel(StrEnum):
    VIEW = "view"
    EDIT = "edit"


class DashboardShare(Base, TimestampMixin):
    __tablename__ = "dashboard_shares"
    __table_args__ = (UniqueConstraint("dashboard_id", "user_id", name="uq_dashboard_share"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    dashboard_id: Mapped[int] = mapped_column(
        ForeignKey("dashboards.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    access_level: Mapped[DashboardAccessLevel] = mapped_column(
        Enum(DashboardAccessLevel, name="dashboard_access_level"),
        nullable=False,
        default=DashboardAccessLevel.VIEW,
    )
    # The user who granted the share (usually the owner); kept for auditing.
    granted_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
