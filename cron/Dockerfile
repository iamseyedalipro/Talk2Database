# Scheduled-sync container.
# Based on the same postgres major version as the user-data server so
# pg_dump / pg_restore / psql / createdb line up (the most common real-world
# failure). Override with the POSTGRES_VERSION build arg / .env value.
ARG POSTGRES_VERSION=16
FROM postgres:${POSTGRES_VERSION}

# cron daemon + gettext (envsubst) for rendering the crontab.
RUN apt-get update \
    && apt-get install -y --no-install-recommends cron gettext-base \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/talk2database
COPY sync.sh entrypoint.sh crontab.tmpl ./
RUN chmod +x sync.sh entrypoint.sh

ENTRYPOINT ["./entrypoint.sh"]
