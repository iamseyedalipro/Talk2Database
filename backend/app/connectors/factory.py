"""Select and construct a connector for a data source (mirrors ai/factory.py)."""

from __future__ import annotations

import dataclasses
import os

from app.connectors.base import ConnectionConfig, Connector, ConnectorError

_IN_DOCKER = os.path.exists("/.dockerenv")
_LOOPBACK = {"localhost", "127.0.0.1", "::1"}


def _resolve_host(host: str) -> str:
    """Remap loopback addresses to host.docker.internal when running in Docker."""
    if _IN_DOCKER and host in _LOOPBACK:
        return "host.docker.internal"
    return host


def supported_types() -> list[str]:
    """Connection types the backend can build a connector for."""
    return ["postgres", "mysql", "mariadb"]


def get_connector(config: ConnectionConfig) -> Connector:
    """Return a connector for ``config.type``.

    Imports are local so a missing optional driver only fails for the type that
    needs it, not at module import time.
    """
    resolved = _resolve_host(config.host)
    if resolved != config.host:
        config = dataclasses.replace(config, host=resolved)

    match config.type:
        case "postgres":
            from app.connectors.postgres import PostgresConnector

            return PostgresConnector(config)
        case "mysql" | "mariadb":
            from app.connectors.mysql import MySQLConnector

            return MySQLConnector(config)

    raise ConnectorError(f"unsupported connection type: {config.type}")
