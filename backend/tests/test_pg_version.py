"""Tests for PostgreSQL version compatibility checks."""

from __future__ import annotations

from pathlib import Path

import pytest
from app.services.pg_version import (
    dump_source_major,
    major_from_tool_output,
    restore_incompatibility,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("pg_restore (PostgreSQL) 16.2", 16),
        ("pg_dump (PostgreSQL) 16.3 (Debian 16.3-1.pgdg120+1)", 16),  # Debian packaging suffix
        ("psql (PostgreSQL) 17beta1", 17),
        ("", None),
    ],
)
def test_major_from_tool_output(text: str, expected: int | None) -> None:
    assert major_from_tool_output(text) == expected


def test_dump_source_major_from_plain_sql(tmp_path: Path) -> None:
    path = tmp_path / "dump.sql"
    path.write_text(
        "--\n-- PostgreSQL database dump\n--\n\n-- Dumped from database version 16.3\n"
        "-- Dumped by pg_dump version 16.3\n\nCREATE TABLE t (id int);\n"
    )
    assert dump_source_major(str(path), is_plain=True) == 16


def test_dump_source_major_unknown_returns_none(tmp_path: Path) -> None:
    path = tmp_path / "dump.sql"
    path.write_text("CREATE TABLE t (id int);\n")
    assert dump_source_major(str(path), is_plain=True) is None


def test_restore_incompatibility_matrix() -> None:
    # Source newer than target -> blocked.
    assert restore_incompatibility(17, 16, 16) is not None
    # Source newer than tooling -> blocked.
    assert restore_incompatibility(17, 17, 16) is not None
    # Source <= target and <= tooling -> allowed.
    assert restore_incompatibility(15, 16, 16) is None
    assert restore_incompatibility(16, 16, 16) is None
    # Unknown source -> never block (let the restore try).
    assert restore_incompatibility(None, 16, 16) is None
