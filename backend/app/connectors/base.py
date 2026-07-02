"""The connector contract shared by every data source."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date, datetime
from datetime import time as dtime
from decimal import Decimal
from typing import Any, Protocol
from uuid import UUID

from app.services.schema.introspect import SchemaData


@dataclass(frozen=True)
class ConnectionConfig:
    """Decrypted, ready-to-use parameters for a single data source.

    Built from a :class:`~app.models.connection.Connection` row (with its secret
    decrypted) just before a connector is constructed. ``options`` carries
    source-specific extras (e.g. ``{"schemas": ["public"], "ssl": true}``).
    """

    type: str
    host: str
    port: int
    database: str
    username: str
    password: str
    options: dict[str, Any] = field(default_factory=dict)


@dataclass
class QueryResult:
    """The source-agnostic shape every connector returns from :meth:`Connector.run`."""

    columns: list[tuple[str, str]]  # (name, type)
    rows: list[list[Any]]
    row_count: int
    truncated: bool
    elapsed_ms: int


class ConnectorError(RuntimeError):
    """Base error for connector connect/introspect/execute failures."""


class ConnectorQueryError(ConnectorError):
    """The data source rejected or failed to run a (validated) query."""


def to_jsonable(value: Any) -> Any:
    """Convert a database value into a JSON-serializable form.

    Generic across drivers: Decimals become floats, temporals ISO strings, bytes
    a ``\\x``-hex string, UUIDs strings; lists/dicts pass through; anything else
    falls back to ``str``.
    """
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date, dtime)):
        return value.isoformat()
    if isinstance(value, (bytes, bytearray, memoryview)):
        return "\\x" + bytes(value).hex()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (list, dict)):
        return value
    return str(value)


class Connector(Protocol):
    """Everything source-specific behind one interface.

    Implementations open their own read-only connection per call; there is no
    shared pool, mirroring the original hardened-per-connection design.
    """

    type: str
    """Stable identifier, e.g. ``"postgres"`` | ``"mysql"`` | ``"mariadb"``."""

    dialect: str
    """sqlglot dialect for the guard/AST, or a non-SQL marker (e.g. ``"promql"``)."""

    label: str
    """Human-readable dialect name used in prompts, e.g. ``"PostgreSQL"``."""

    def introspect(self) -> SchemaData:
        """Read structural metadata (tables/columns/PK/FK), never row data."""
        ...

    def validate(self, query: str) -> str:
        """Return a normalized, read-only-safe query or raise ``SqlGuardError``."""
        ...

    def run(self, query: str, max_rows: int) -> QueryResult:
        """Execute a validated read-only query and return up to ``max_rows`` rows."""
        ...

    def stream_csv(self, query: str, max_rows: int) -> Iterator[str]:
        """Yield the validated query's result as CSV text (memory-bounded)."""
        ...

    def reachable(self) -> bool:
        """Return ``True`` if a read-only connection + trivial query succeeds."""
        ...

    def system_prompt(self) -> str:
        """The dialect-specific LLM system prompt."""
        ...

    def schema_block(self, schema_text: str) -> str:
        """Wrap serialized schema text as the cacheable LLM prefix."""
        ...
