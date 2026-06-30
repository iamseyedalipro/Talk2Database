"""Application configuration loaded from environment variables / ``.env``.

A single :class:`Settings` instance (returned by :func:`get_settings`) is the
authoritative source of *deployment* configuration for the backend. Per-data
source credentials are **not** here - those live in the connection registry
(encrypted in the panel database). Nothing secret about a data source is read
from the environment anymore.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from typing import Literal

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AIProvider(StrEnum):
    """Supported large-language-model providers."""

    ANTHROPIC = "anthropic"
    OPENAI = "openai"


class Settings(BaseSettings):
    """Strongly-typed view of the deployment's environment."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # -- General ----------------------------------------------------------- #
    app_base_url: str = "http://localhost:8000"
    cors_origins: str = ""

    # -- AI ---------------------------------------------------------------- #
    ai_provider: AIProvider = AIProvider.ANTHROPIC
    ai_api_key: str = ""
    ai_model: str = "claude-opus-4-8"

    # -- Schema cost control ---------------------------------------------- #
    schema_max_tokens: int = 6000
    # Default namespace/table scoping. A connection may override these in its
    # ``options`` (e.g. {"schemas": ["public", "sales"]}).
    schema_tables: str = ""  # comma-separated allowlist; empty => all tables
    schema_include_schemas: str = ""  # comma-separated; empty => auto-discover all user schemas

    # -- Auth -------------------------------------------------------------- #
    jwt_secret: str = "change-me"
    jwt_expire_minutes: int = 60
    jwt_algorithm: Literal["HS256"] = "HS256"

    # -- Connection registry ---------------------------------------------- #
    # Fernet key used to encrypt data-source passwords at rest. Generate with:
    #   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    connections_secret_key: str = ""

    # -- Query guard rails ------------------------------------------------- #
    query_max_rows: int = 1000
    query_timeout_seconds: int = 30

    # -- Panel DB ---------------------------------------------------------- #
    panel_db_host: str = "postgres-panel"
    panel_db_port: int = 5432
    panel_db_name: str = "panel"
    panel_db_user: str = "panel"
    panel_db_password: str = ""

    # ------------------------------------------------------------------ #
    # Derived values
    # ------------------------------------------------------------------ #
    @computed_field  # type: ignore[prop-decorator]
    @property
    def panel_db_dsn(self) -> str:
        """Async SQLAlchemy DSN for the panel database."""
        return (
            f"postgresql+asyncpg://{self.panel_db_user}:{self.panel_db_password}"
            f"@{self.panel_db_host}:{self.panel_db_port}/{self.panel_db_name}"
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def panel_db_sync_dsn(self) -> str:
        """Synchronous DSN for the panel database (used by Alembic)."""
        return (
            f"postgresql+psycopg://{self.panel_db_user}:{self.panel_db_password}"
            f"@{self.panel_db_host}:{self.panel_db_port}/{self.panel_db_name}"
        )

    @property
    def schema_table_allowlist(self) -> list[str]:
        return [t.strip() for t in self.schema_tables.split(",") if t.strip()]

    @property
    def schema_namespaces(self) -> list[str]:
        return [s.strip() for s in self.schema_include_schemas.split(",") if s.strip()] or [
            "public"
        ]

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def validate_ai_config(self) -> None:
        """Fail fast (at startup) when AI configuration is incomplete."""
        if not self.ai_api_key or self.ai_api_key == "replace-me":
            raise ValueError(
                "AI_API_KEY is not set. Configure AI_PROVIDER / AI_API_KEY / AI_MODEL in .env."
            )
        if not self.ai_model:
            raise ValueError("AI_MODEL is not set.")


@lru_cache
def get_settings() -> Settings:
    """Return the cached, process-wide settings instance."""
    return Settings()
