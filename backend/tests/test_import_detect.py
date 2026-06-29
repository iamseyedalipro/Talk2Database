"""Tests for backup format detection."""

from __future__ import annotations

from pathlib import Path

from app.importers.manual import BackupFormat, detect_format


def test_detect_pg_dump_custom(tmp_path: Path) -> None:
    path = tmp_path / "dump.custom"
    path.write_bytes(b"PGDMP\x01\x0e\x00" + b"\x00" * 32)
    assert detect_format(str(path)) is BackupFormat.CUSTOM


def test_detect_tar(tmp_path: Path) -> None:
    path = tmp_path / "dump.tar"
    # The ustar magic sits at offset 257 in a tar header.
    path.write_bytes(b"\x00" * 257 + b"ustar\x00" + b"\x00" * 250)
    assert detect_format(str(path)) is BackupFormat.TAR


def test_detect_plain_sql(tmp_path: Path) -> None:
    path = tmp_path / "dump.sql"
    path.write_text("-- PostgreSQL database dump\nCREATE TABLE t (id int);\n")
    assert detect_format(str(path)) is BackupFormat.PLAIN
