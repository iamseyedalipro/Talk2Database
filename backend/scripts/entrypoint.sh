#!/usr/bin/env bash
# Panel container entrypoint:
#   1. migrate the panel DB
#   2. ensure the read-only role exists on the user-data DB
#   3. build an initial schema snapshot (best effort)
#   4. start the API server
set -euo pipefail

echo "[entrypoint] applying panel database migrations..."
alembic upgrade head

echo "[entrypoint] ensuring read-only role on user-data database..."
if ! python -m app.cli ensure-readonly-role; then
  echo "[entrypoint] WARNING: could not ensure read-only role yet (will retry after first import)."
fi

echo "[entrypoint] building initial schema snapshot..."
if ! python -m app.cli rebuild-schema; then
  echo "[entrypoint] WARNING: could not build schema snapshot yet (no data imported?)."
fi

echo "[entrypoint] starting API on :8000"
exec python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
