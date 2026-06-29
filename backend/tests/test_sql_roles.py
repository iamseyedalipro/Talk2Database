"""Tests for extracting roles referenced by a plain SQL dump."""

from __future__ import annotations

from app.services.sql_roles import extract_referenced_roles

_DUMP = """\
SET statement_timeout = 0;
ALTER SCHEMA public OWNER TO root;
CREATE TABLE public.users (id integer);
ALTER TABLE public.users OWNER TO root;
GRANT SELECT ON TABLE public.users TO reporting, "Weird Role";
GRANT SELECT ON TABLE public.users TO pg_monitor;
REVOKE ALL ON SCHEMA public FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE deployer IN SCHEMA public GRANT SELECT ON TABLES TO PUBLIC;
SET SESSION AUTHORIZATION 'analytics';
COPY public.logs (msg) FROM stdin;
this row mentions OWNER TO ghost; but it is data, not SQL
\\.
GRANT INSERT ON TABLE public.users TO after_copy;
"""


def test_extract_referenced_roles() -> None:
    roles = extract_referenced_roles(_DUMP)
    assert roles == {"root", "reporting", "Weird Role", "deployer", "analytics", "after_copy"}


def test_reserved_and_builtin_roles_excluded() -> None:
    roles = extract_referenced_roles(_DUMP)
    assert "public" not in {r.lower() for r in roles}  # PUBLIC pseudo-role
    assert "pg_monitor" not in roles  # built-in pg_* role
    assert "ghost" not in roles  # inside a COPY data block


def test_no_roles_in_plain_schema() -> None:
    assert extract_referenced_roles("CREATE TABLE t (id int);\n") == set()
