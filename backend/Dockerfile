# syntax=docker/dockerfile:1
# Multi-stage build: compile the React SPA, then run FastAPI serving it.
# Build context is the repository root (see docker-compose.yml).

# ----------------------------------------------------------------------------
# Stage 1 — build the frontend
# ----------------------------------------------------------------------------
FROM node:20-bookworm-slim AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# ----------------------------------------------------------------------------
# Stage 2 — backend runtime
# ----------------------------------------------------------------------------
FROM python:3.12-slim AS runtime
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# postgresql-client provides psql / pg_restore used by manual imports.
RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install the backend (editable so /app/app is the importable package and
# /app/frontend_dist resolves relative to it).
COPY backend/ ./
RUN pip install -e .

# Built SPA from stage 1.
COPY --from=frontend /frontend/dist ./frontend_dist

RUN chmod +x scripts/entrypoint.sh scripts/bootstrap_readonly_role.sh

EXPOSE 8000
ENTRYPOINT ["scripts/entrypoint.sh"]
