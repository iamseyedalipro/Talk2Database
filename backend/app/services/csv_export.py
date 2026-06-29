"""Stream a read-only query's result set as CSV."""

from __future__ import annotations

import csv
import io
from collections.abc import Iterator

from app.db.userdata import readonly_connection
from app.services.query_runner import to_jsonable

_BATCH = 1000


def stream_csv(sql: str, max_rows: int) -> Iterator[str]:
    """Yield the result of ``sql`` as CSV text, capped at ``max_rows`` rows.

    Rows are fetched in batches so memory stays bounded regardless of the cap.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer)

    def flush() -> str:
        chunk = buffer.getvalue()
        buffer.seek(0)
        buffer.truncate(0)
        return chunk

    with readonly_connection() as conn, conn.cursor() as cur:
        cur.execute(sql)
        writer.writerow([col.name for col in (cur.description or [])])
        yield flush()

        remaining = max_rows
        while remaining > 0:
            batch = cur.fetchmany(min(_BATCH, remaining))
            if not batch:
                break
            for row in batch:
                writer.writerow([to_jsonable(value) for value in row])
            remaining -= len(batch)
            yield flush()
