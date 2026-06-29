#!/usr/bin/env bash
# Full-refresh sync: copy the remote Postgres into the user-data database.
#
# Safety model:
#   * dump the remote first; if that fails, the live data is never touched
#   * restore into a fresh temp database, not the live one
#   * swap atomically by renaming databases, so a mid-sync failure leaves the
#     live database intact
#   * re-grant the read-only role on the new database (grants do not survive a
#     restore) and invalidate the panel's schema snapshot so it rebuilds
#
# This script mirrors app/services/readonly_role.py — keep the grants in sync.
set -euo pipefail

LOCK_FILE=/tmp/t2db-sync.lock
exec 9>"${LOCK_FILE}"
if ! flock -n 9; then
  echo "[sync] another sync is already running; skipping."
  exit 0
fi

NAME="${USERDATA_DB_NAME}"
NEW_DB="${NAME}_new"
OLD_DB="${NAME}_old"
RO_USER="${USERDATA_READONLY_USER}"
RO_PW="${USERDATA_READONLY_PASSWORD}"
DUMP_FILE="$(mktemp /tmp/t2db-sync.XXXXXX.dump)"

host="${USERDATA_DB_HOST}"
port="${USERDATA_DB_PORT}"
admin="${USERDATA_DB_ADMIN_USER}"
export PGPASSWORD="${USERDATA_DB_ADMIN_PASSWORD}"

maint_dsn="postgresql://${admin}@${host}:${port}/postgres"
new_dsn="postgresql://${admin}@${host}:${port}/${NEW_DB}"
live_dsn="postgresql://${admin}@${host}:${port}/${NAME}"
panel_dsn="postgresql://${PANEL_DB_USER}:${PANEL_DB_PASSWORD}@${PANEL_DB_HOST}:${PANEL_DB_PORT}/${PANEL_DB_NAME}"

RUN_ID=""

panel_psql() { psql "${panel_dsn}" -v ON_ERROR_STOP=1 "$@"; }

start_run() {
  RUN_ID="$(panel_psql -tAc \
    "INSERT INTO import_runs (kind, status, started_at) \
     VALUES ('scheduled', 'running', now()) RETURNING id;")"
  RUN_ID="${RUN_ID//[[:space:]]/}"
  echo "[sync] started import_run ${RUN_ID}"
}

finish_run() { # status, message
  [ -n "${RUN_ID}" ] || return 0
  panel_psql -c \
    "UPDATE import_runs SET status='$1', finished_at=now(), \
     message=\$msg\$$2\$msg\$ WHERE id=${RUN_ID};" || true
}

cleanup() { rm -f "${DUMP_FILE}"; }

fail() {
  echo "[sync] FAILED: $1"
  psql "${maint_dsn}" -c "DROP DATABASE IF EXISTS \"${NEW_DB}\";" || true
  finish_run failed "$1"
  cleanup
  exit 1
}

trap 'cleanup' EXIT

[ -n "${REMOTE_DB_DSN:-}" ] || { echo "[sync] REMOTE_DB_DSN not set"; exit 1; }

start_run

echo "[sync] dumping remote database..."
pg_dump --format=custom --no-owner --no-privileges --dbname="${REMOTE_DB_DSN}" \
  --file="${DUMP_FILE}" || fail "pg_dump of remote source failed"

echo "[sync] preparing fresh database ${NEW_DB}..."
psql "${maint_dsn}" -v ON_ERROR_STOP=1 -c "DROP DATABASE IF EXISTS \"${NEW_DB}\";" \
  || fail "could not drop stale ${NEW_DB}"
psql "${maint_dsn}" -v ON_ERROR_STOP=1 -c "CREATE DATABASE \"${NEW_DB}\";" \
  || fail "could not create ${NEW_DB}"

echo "[sync] restoring into ${NEW_DB}..."
pg_restore --no-owner --no-privileges --dbname="${new_dsn}" "${DUMP_FILE}" \
  || fail "pg_restore into ${NEW_DB} failed"

echo "[sync] swapping ${NEW_DB} -> ${NAME}..."
psql "${maint_dsn}" -v ON_ERROR_STOP=1 <<SQL || fail "atomic swap failed"
SELECT pg_terminate_backend(pid)
  FROM pg_stat_activity
 WHERE datname IN ('${NAME}', '${OLD_DB}', '${NEW_DB}')
   AND pid <> pg_backend_pid();
DROP DATABASE IF EXISTS "${OLD_DB}";
ALTER DATABASE "${NAME}" RENAME TO "${OLD_DB}";
ALTER DATABASE "${NEW_DB}" RENAME TO "${NAME}";
DROP DATABASE "${OLD_DB}";
SQL

echo "[sync] re-granting read-only role on ${NAME}..."
IFS=',' read -ra SCHEMAS <<<"${SCHEMA_INCLUDE_SCHEMAS:-public}"
{
  psql "${live_dsn}" -v ON_ERROR_STOP=1 <<SQL
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '${RO_USER}') THEN
    EXECUTE format('CREATE ROLE %I LOGIN PASSWORD %L', '${RO_USER}', '${RO_PW}');
  END IF;
END
\$\$;
REVOKE ALL ON DATABASE "${NAME}" FROM "${RO_USER}";
GRANT CONNECT ON DATABASE "${NAME}" TO "${RO_USER}";
SQL
  for schema in "${SCHEMAS[@]}"; do
    schema="$(echo "${schema}" | xargs)"
    [ -n "${schema}" ] || continue
    psql "${live_dsn}" -v ON_ERROR_STOP=1 <<SQL
GRANT USAGE ON SCHEMA "${schema}" TO "${RO_USER}";
GRANT SELECT ON ALL TABLES IN SCHEMA "${schema}" TO "${RO_USER}";
ALTER DEFAULT PRIVILEGES IN SCHEMA "${schema}" GRANT SELECT ON TABLES TO "${RO_USER}";
REVOKE CREATE ON SCHEMA "${schema}" FROM "${RO_USER}";
SQL
  done
} || fail "re-granting read-only role failed"

echo "[sync] invalidating panel schema snapshot..."
panel_psql -c "DELETE FROM schema_snapshots;" || true

finish_run success "full refresh completed"
echo "[sync] done."
