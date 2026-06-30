"""Tests for the connector factory and shared connector behavior (no network)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from app.connectors import (
    ConnectionConfig,
    ConnectorError,
    get_connector,
    supported_types,
    to_jsonable,
)
from app.connectors.factory import supported_types as factory_supported_types
from app.services.sql_guard import SqlGuardError


def _cfg(type_: str) -> ConnectionConfig:
    return ConnectionConfig(type=type_, host="h", port=1, database="d", username="u", password="p")


def test_factory_selects_postgres() -> None:
    connector = get_connector(_cfg("postgres"))
    assert connector.type == "postgres"
    assert connector.dialect == "postgres"


def test_factory_selects_mysql_and_mariadb() -> None:
    mysql = get_connector(_cfg("mysql"))
    assert mysql.type == "mysql"
    assert mysql.dialect == "mysql"

    maria = get_connector(_cfg("mariadb"))
    assert maria.type == "mariadb"
    assert maria.dialect == "mysql"  # MariaDB shares the MySQL grammar


def test_factory_unknown_type_raises() -> None:
    with pytest.raises(ConnectorError):
        get_connector(_cfg("oracle"))


def test_supported_types_lists_sql_connectors() -> None:
    assert set(supported_types()) >= {"postgres", "mysql", "mariadb"}
    assert factory_supported_types() == supported_types()


@pytest.mark.parametrize("type_", ["postgres", "mysql", "mariadb"])
def test_validate_accepts_select_rejects_write(type_: str) -> None:
    connector = get_connector(_cfg(type_))
    assert connector.validate("select 1")
    with pytest.raises(SqlGuardError):
        connector.validate("drop table t")


@pytest.mark.parametrize("type_", ["postgres", "mysql"])
def test_prompt_label_matches_dialect(type_: str) -> None:
    connector = get_connector(_cfg(type_))
    label = "PostgreSQL" if type_ == "postgres" else "MySQL"
    assert label in connector.system_prompt()
    assert label in connector.schema_block("TABLE t")


def test_to_jsonable_conversions() -> None:
    assert to_jsonable(Decimal("1.5")) == 1.5
    assert to_jsonable(b"\x00\xff") == "\\x00ff"
    assert to_jsonable(None) is None
    assert to_jsonable([1, 2]) == [1, 2]
