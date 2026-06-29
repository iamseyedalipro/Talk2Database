#!/usr/bin/env bash
# Render the crontab from SYNC_INTERVAL_HOURS, optionally run one sync now,
# then hand off to the cron daemon.
set -euo pipefail

N="${SYNC_INTERVAL_HOURS:-6}"
export CRON_SCHEDULE="0 */${N} * * *"

# Capture the variables the sync job needs so the cron environment has them.
ENV_FILE=/opt/talk2database/env.sh
: >"${ENV_FILE}"
for var in \
  REMOTE_DB_DSN \
  USERDATA_DB_HOST USERDATA_DB_PORT USERDATA_DB_NAME \
  USERDATA_DB_ADMIN_USER USERDATA_DB_ADMIN_PASSWORD \
  USERDATA_READONLY_USER USERDATA_READONLY_PASSWORD \
  PANEL_DB_HOST PANEL_DB_PORT PANEL_DB_NAME PANEL_DB_USER PANEL_DB_PASSWORD \
  SCHEMA_INCLUDE_SCHEMAS; do
  printf 'export %s=%q\n' "${var}" "${!var-}" >>"${ENV_FILE}"
done

# Install the cron schedule.
envsubst '${CRON_SCHEDULE}' <crontab.tmpl >/etc/cron.d/talk2database
chmod 0644 /etc/cron.d/talk2database

touch /var/log/t2db-sync.log

if [ "${SYNC_RUN_ON_STARTUP:-true}" = "true" ]; then
  echo "[cron] running initial sync on startup..."
  ./sync.sh >>/var/log/t2db-sync.log 2>&1 || echo "[cron] initial sync failed (see log)."
fi

echo "[cron] scheduling sync: ${CRON_SCHEDULE}"
cron
exec tail -F /var/log/t2db-sync.log
