"""A user-registered data source (PostgreSQL, MySQL, MariaDB, ...).

The password is stored **encrypted** (Fernet) in :attr:`Connection.secret_encrypted`
and is never returned by the API. Everything else is non-secret connection
metadata. ``options`` holds source-specific extras (e.g. schema allowlist).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class DataSourceType(StrEnum):
    """Supported data-source types."""

    POSTGRES = "postgres"
    MYSQL = "mysql"
    MARIADB = "mariadb"


class Connection(Base, TimestampMixin):
    __tablename__ = "connections"
    __table_args__ = (UniqueConstraint("owner_id", "name", name="uq_connection_owner_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    type: Mapped[DataSourceType] = mapped_column(String(32), nullable=False)
    host: Mapped[str] = mapped_column(String(255), nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False)
    database: Mapped[str] = mapped_column(String(255), nullable=False)
    username: Mapped[str] = mapped_column(String(255), nullable=False)
    # Fernet token; decrypted only at connect time, never serialized out.
    secret_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    options: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
