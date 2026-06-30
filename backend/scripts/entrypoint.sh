#!/usr/bin/env bash
# Panel container entrypoint:
#   1. migrate the panel DB
#   2. start the API server
#
# Data sources are configured at runtime via the connection registry, so there
# is no role provisioning or schema bootstrap to do here — schema snapshots
# build lazily on the first question against a connection.
set -euo pipefail

echo "[entrypoint] applying panel database migrations..."
alembic upgrade head

echo "[entrypoint] starting API on :8000"
exec python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
