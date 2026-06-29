#!/usr/bin/env bash
# Create or refresh the SELECT-only role on the user-data database.
# Thin wrapper around the Python implementation so the same grants are used
# everywhere (see app/services/readonly_role.py).
set -euo pipefail
exec python -m app.cli ensure-readonly-role
