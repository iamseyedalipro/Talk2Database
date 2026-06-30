"""Small operational CLI used by the container entrypoint.

    python -m app.cli refresh-schema <connection_id>   # re-introspect a source

Schema snapshots otherwise build lazily on the first question against a
connection, so this command is only needed to force a refresh.
"""

from __future__ import annotations

import asyncio
import sys

from app.db.panel import get_sessionmaker
from app.models.connection import Connection
from app.services.connections import build_connector
from app.services.schema.cache import rebuild_snapshot

_USAGE = "usage: python -m app.cli refresh-schema <connection_id>"


async def _refresh_schema(connection_id: int) -> None:
    async with get_sessionmaker()() as session:
        connection = await session.get(Connection, connection_id)
        if connection is None:
            print(f"connection {connection_id} not found", file=sys.stderr)
            raise SystemExit(1)
        connector = build_connector(connection)
        await rebuild_snapshot(session, connection_id, connector)
        await session.commit()


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if len(args) == 2 and args[0] == "refresh-schema":
        try:
            connection_id = int(args[1])
        except ValueError:
            print(_USAGE, file=sys.stderr)
            return 2
        asyncio.run(_refresh_schema(connection_id))
        return 0

    print(_USAGE, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
