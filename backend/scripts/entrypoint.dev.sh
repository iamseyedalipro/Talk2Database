#!/usr/bin/env bash
set -euo pipefail

echo "[entrypoint.dev] applying panel database migrations..."
alembic upgrade head

echo "[entrypoint.dev] starting API on :8000 (hot-reload enabled)"
exec python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --reload-dir /app/app
