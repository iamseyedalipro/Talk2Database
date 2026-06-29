"""PostgreSQL major-version compatibility checks for restores.

``pg_dump``/``pg_restore`` only move data safely when the tooling and the target
server are at least as new as the source. We surface that as an actionable error
*before* a restore runs, instead of letting it fail cryptically partway through.

Compatibility rule (majors): ``source <= tool`` and ``source <= target``.
"""

from __future__ import annotations

import re
import subprocess

import psycopg

# Matches the version comment pg_dump writes, in both plain SQL
# ("-- Dumped from database version 16.2") and custom/tar archive listings
# ("; Dumped from database version: 16.2").
_DUMP_HEADER_RE = re.compile(r"Dumped from database version:?\s*(\d+)")


def major_from_tool_output(text: str) -> int | None:
    """Parse a ``--version`` line, e.g. 'pg_restore (PostgreSQL) 16.2' -> 16."""
    if not text.strip():
        return None
    last = text.strip().split()[-1]  # '16.2', '17beta1', ...
    match = re.match(r"(\d+)", last)
    return int(match.group(1)) if match else None


def local_pg_restore_major() -> int | None:
    """Major version of the bundled ``pg_restore`` (None if unavailable)."""
    try:
        result = subprocess.run(
            ["pg_restore", "--version"], capture_output=True, text=True, check=True
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return major_from_tool_output(result.stdout)


def server_major(dsn: str) -> int | None:
    """Major version of the server at ``dsn`` (None if it cannot be reached)."""
    try:
        with psycopg.connect(dsn, connect_timeout=10) as conn, conn.cursor() as cur:
            cur.execute("SHOW server_version_num")
            row = cur.fetchone()
    except Exception:
        return None
    if not row or row[0] is None:
        return None
    return int(row[0]) // 10000


def dump_source_major(path: str, is_plain: bool) -> int | None:
    """Best-effort source major version recorded in a backup file."""
    try:
        if is_plain:
            with open(path, encoding="utf-8", errors="ignore") as handle:
                text = handle.read(16384)
        else:
            result = subprocess.run(
                ["pg_restore", "--list", path], capture_output=True, text=True, check=False
            )
            text = f"{result.stdout}\n{result.stderr}"
    except (OSError, subprocess.SubprocessError):
        return None
    match = _DUMP_HEADER_RE.search(text)
    return int(match.group(1)) if match else None


def restore_incompatibility(
    source_major: int | None, target_major: int | None, tool_major: int | None
) -> str | None:
    """Return an actionable error if a restore would be unsafe, else ``None``.

    When the source version is unknown we do not block — the restore is allowed
    to proceed and surface its own error if anything is wrong.
    """
    if source_major is None:
        return None
    if target_major is not None and source_major > target_major:
        return (
            f"the backup is from PostgreSQL {source_major}, but this deployment's data "
            f"database is PostgreSQL {target_major}. Restore into an equal or newer major "
            f"version: set POSTGRES_VERSION={source_major} and recreate the userdata volume."
        )
    if tool_major is not None and source_major > tool_major:
        return (
            f"the backup is from PostgreSQL {source_major}, but the bundled pg_restore is "
            f"PostgreSQL {tool_major}. Set POSTGRES_VERSION={source_major} and rebuild the images."
        )
    return None


def check_restore_compatibility(path: str, is_plain: bool, target_dsn: str) -> str | None:
    """Convenience wrapper: returns an error message, or ``None`` if compatible."""
    return restore_incompatibility(
        dump_source_major(path, is_plain),
        server_major(target_dsn),
        local_pg_restore_major(),
    )
