"""Create and (re-)grant the SELECT-only role on the user-data database.

Run at startup and after every import/sync, because a freshly restored database
does not carry over role grants. This is the database half of the read-only
guarantee; it must stay in sync with ``cron/sync.sh`` which does the same in
the scheduled path.
"""

from __future__ import annotations

import psycopg
from psycopg import sql

from app.config import get_settings


def ensure_readonly_role() -> None:
    """Ensure the read-only role exists and can SELECT (only) everything."""
    settings = get_settings()
    role = settings.userdata_readonly_user
    password = settings.userdata_readonly_password
    database = settings.userdata_db_name
    role_ident = sql.Identifier(role)

    with (
        psycopg.connect(settings.userdata_admin_dsn, autocommit=True) as conn,
        conn.cursor() as cur,
    ):
        cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,))
        exists = cur.fetchone() is not None

        verb = sql.SQL("ALTER") if exists else sql.SQL("CREATE")
        cur.execute(
            sql.SQL("{} ROLE {} WITH LOGIN PASSWORD {}").format(
                verb, role_ident, sql.Literal(password)
            )
        )

        cur.execute(
            sql.SQL("REVOKE ALL ON DATABASE {} FROM {}").format(
                sql.Identifier(database), role_ident
            )
        )
        cur.execute(
            sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                sql.Identifier(database), role_ident
            )
        )

        for schema_name in settings.schema_namespaces:
            schema_ident = sql.Identifier(schema_name)
            cur.execute(sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(schema_ident, role_ident))
            cur.execute(
                sql.SQL("GRANT SELECT ON ALL TABLES IN SCHEMA {} TO {}").format(
                    schema_ident, role_ident
                )
            )
            cur.execute(
                sql.SQL(
                    "ALTER DEFAULT PRIVILEGES IN SCHEMA {} GRANT SELECT ON TABLES TO {}"
                ).format(schema_ident, role_ident)
            )
            # Belt and braces: the read-only role must never create objects.
            cur.execute(
                sql.SQL("REVOKE CREATE ON SCHEMA {} FROM {}").format(schema_ident, role_ident)
            )
