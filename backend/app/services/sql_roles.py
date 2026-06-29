"""Pre-create roles referenced by a plain ``.sql`` dump.

A plain ``pg_dump`` bakes ``ALTER ... OWNER TO <role>`` and ``GRANT ... TO
<role>`` statements into the SQL text. Restoring into a fresh cluster that lacks
those roles fails with ``role "<x>" does not exist``. Custom/tar archives avoid
this via ``pg_restore --no-owner --no-privileges``, but a plain restore cannot
strip it at load time — so we scan the dump and create any missing roles as
harmless ``NOLOGIN`` roles first (the standard restore workaround).
"""

from __future__ import annotations

import re
from collections.abc import Iterable

import psycopg
from psycopg import sql

from app.config import get_settings

# Pseudo-roles / keywords that are never real, creatable roles.
_RESERVED = {"public", "current_user", "session_user", "current_role", "none"}

# A SQL identifier: a double-quoted name (with "" escapes) or a bare name.
_IDENT = r'"(?:[^"]|"")+"|[A-Za-z_][A-Za-z0-9_$]*'

_OWNER_RE = re.compile(rf"\bOWNER\s+TO\s+({_IDENT})", re.IGNORECASE)
_ADP_RE = re.compile(rf"\bALTER\s+DEFAULT\s+PRIVILEGES\s+FOR\s+ROLE\s+({_IDENT})", re.IGNORECASE)
_AUTHZ_RE = re.compile(
    rf"\bSET\s+SESSION\s+AUTHORIZATION\s+(?:'([^']+)'|({_IDENT}))", re.IGNORECASE
)
_GRANT_RE = re.compile(
    r"\bGRANT\b[^;]*?\bTO\s+([^;]+?)(?:\s+WITH\s+GRANT\s+OPTION)?\s*;", re.IGNORECASE
)
_REVOKE_RE = re.compile(
    r"\bREVOKE\b[^;]*?\bFROM\s+([^;]+?)(?:\s+CASCADE|\s+RESTRICT)?\s*;", re.IGNORECASE
)
_COPY_START_RE = re.compile(r"^\s*COPY\b.*\bFROM\s+stdin", re.IGNORECASE)


def _normalize_ident(token: str) -> str:
    """Fold an identifier the way PostgreSQL would (quoted = exact, bare = lower)."""
    token = token.strip()
    if len(token) >= 2 and token.startswith('"') and token.endswith('"'):
        return token[1:-1].replace('""', '"')
    return token.lower()


def _grantees(raw: str) -> list[str]:
    names = []
    for part in raw.split(","):
        cleaned = re.sub(r"^\s*GROUP\s+", "", part.strip(), flags=re.IGNORECASE)
        if cleaned:
            names.append(cleaned)
    return names


def _roles_in_line(line: str) -> set[str]:
    roles: set[str] = set()
    for match in _OWNER_RE.finditer(line):
        roles.add(_normalize_ident(match.group(1)))
    for match in _ADP_RE.finditer(line):
        roles.add(_normalize_ident(match.group(1)))
    for match in _AUTHZ_RE.finditer(line):
        roles.add(_normalize_ident(match.group(1) or match.group(2)))
    for match in _GRANT_RE.finditer(line):
        roles.update(_normalize_ident(name) for name in _grantees(match.group(1)))
    for match in _REVOKE_RE.finditer(line):
        roles.update(_normalize_ident(name) for name in _grantees(match.group(1)))
    return {
        r for r in roles if r and r.lower() not in _RESERVED and not r.lower().startswith("pg_")
    }


def _extract_from_lines(lines: Iterable[str]) -> set[str]:
    """Collect referenced role names, skipping COPY data blocks (and their noise)."""
    roles: set[str] = set()
    in_copy = False
    for line in lines:
        if in_copy:
            if line.startswith("\\."):
                in_copy = False
            continue
        if _COPY_START_RE.match(line):
            in_copy = True
            continue
        roles |= _roles_in_line(line)
    return roles


def extract_referenced_roles(text: str) -> set[str]:
    """Role names referenced by a dump given as a string (used in tests)."""
    return _extract_from_lines(text.splitlines())


def extract_referenced_roles_from_file(path: str) -> set[str]:
    """Stream a (possibly large) dump file and collect referenced role names."""
    with open(path, encoding="utf-8", errors="ignore") as handle:
        return _extract_from_lines(handle)


def ensure_roles_exist(roles: Iterable[str]) -> list[str]:
    """Create any of ``roles`` that do not already exist; return the created names."""
    wanted = sorted({r for r in roles if r})
    if not wanted:
        return []

    created: list[str] = []
    dsn = get_settings().userdata_admin_dsn
    with psycopg.connect(dsn, autocommit=True) as conn, conn.cursor() as cur:
        for role in wanted:
            cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,))
            if cur.fetchone() is None:
                cur.execute(sql.SQL("CREATE ROLE {} NOLOGIN").format(sql.Identifier(role)))
                created.append(role)
    return created


def ensure_roles_for_plain_dump(path: str) -> list[str]:
    """Pre-create roles referenced by a plain SQL dump. Returns created names."""
    return ensure_roles_exist(extract_referenced_roles_from_file(path))
