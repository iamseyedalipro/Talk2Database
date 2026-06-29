"""Small operational CLI used by the container entrypoint.

python -m app.cli ensure-readonly-role   # create/refresh the SELECT-only role
python -m app.cli rebuild-schema         # re-introspect and snapshot the schema
"""

from __future__ import annotations

import asyncio
import sys

from app.db.panel import get_sessionmaker
from app.services.readonly_role import ensure_readonly_role
from app.services.schema.cache import rebuild_snapshot

_USAGE = "usage: python -m app.cli [ensure-readonly-role|rebuild-schema]"


async def _rebuild_schema() -> None:
    async with get_sessionmaker()() as session:
        await rebuild_snapshot(session)
        await session.commit()


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if not args:
        print(_USAGE, file=sys.stderr)
        return 2

    command = args[0]
    if command == "ensure-readonly-role":
        ensure_readonly_role()
    elif command == "rebuild-schema":
        asyncio.run(_rebuild_schema())
    else:
        print(_USAGE, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
