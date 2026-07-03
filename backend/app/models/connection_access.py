"""Per-user access grants to connections owned by someone else.

A connection is owned by exactly one user (:attr:`Connection.owner_id`). This
join table lets an admin grant *other* users read/use access to a connection —
they can ask questions, run read-only queries, browse the schema, and edit the
semantic glossary, but never edit the connection settings or delete it.
"""

from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class ConnectionAccess(Base, TimestampMixin):
    __tablename__ = "connection_access"
    __table_args__ = (UniqueConstraint("connection_id", "user_id", name="uq_connection_access"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    connection_id: Mapped[int] = mapped_column(
        ForeignKey("connections.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # The admin who granted the access; kept for auditing. SET NULL if they go.
    granted_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
