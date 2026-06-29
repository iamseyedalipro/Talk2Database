# Scheduled-sync container.
# Based on postgres:16 so pg_dump / pg_restore / psql / createdb match the
# user-data server major version exactly (the most common real-world failure).
FROM postgres:16

# cron daemon + gettext (envsubst) for rendering the crontab.
RUN apt-get update \
    && apt-get install -y --no-install-recommends cron gettext-base \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/talk2database
COPY sync.sh entrypoint.sh crontab.tmpl ./
RUN chmod +x sync.sh entrypoint.sh

ENTRYPOINT ["./entrypoint.sh"]
