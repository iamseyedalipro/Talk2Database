"""Generic key/value application settings stored in the panel database.

Holds admin-editable configuration that must survive restarts and be
changeable without a redeploy: Microsoft Clarity credentials/schedule and
prompt-template overrides. Secret values (the Clarity API token) are stored
Fernet-encrypted, never plaintext.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
