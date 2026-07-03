"""Pluggable data-source connectors.

Each connector encapsulates everything source-specific: how to connect
read-only, how to introspect the schema, how to validate a generated query, how
to execute it and map values, and how to ground the LLM (dialect-specific system
prompt + schema block). The rest of the app (AI providers, schema caching, query
history, CSV export, frontend) stays source-agnostic.

Add a new database by implementing :class:`~app.connectors.base.Connector` and
registering it in :mod:`app.connectors.factory`.
"""

from app.connectors.base import (
    ConnectionConfig,
    Connector,
    ConnectorError,
    ConnectorQueryError,
    ExplainResult,
    QueryResult,
    to_jsonable,
)
from app.connectors.factory import get_connector, supported_types

__all__ = [
    "ConnectionConfig",
    "Connector",
    "ConnectorError",
    "ConnectorQueryError",
    "ExplainResult",
    "QueryResult",
    "get_connector",
    "supported_types",
    "to_jsonable",
]
