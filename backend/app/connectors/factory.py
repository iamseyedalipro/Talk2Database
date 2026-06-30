"""Select and construct a connector for a data source (mirrors ai/factory.py)."""

from __future__ import annotations

from app.connectors.base import ConnectionConfig, Connector, ConnectorError


def supported_types() -> list[str]:
    """Connection types the backend can build a connector for."""
    return ["postgres", "mysql", "mariadb"]


def get_connector(config: ConnectionConfig) -> Connector:
    """Return a connector for ``config.type``.

    Imports are local so a missing optional driver only fails for the type that
    needs it, not at module import time.
    """
    match config.type:
        case "postgres":
            from app.connectors.postgres import PostgresConnector

            return PostgresConnector(config)
        case "mysql" | "mariadb":
            from app.connectors.mysql import MySQLConnector

            return MySQLConnector(config)

    raise ConnectorError(f"unsupported connection type: {config.type}")
