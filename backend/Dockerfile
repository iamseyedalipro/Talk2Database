# syntax=docker/dockerfile:1
# Multi-stage build: compile the React SPA, then run FastAPI serving it.
# Build context is the repository root (see docker-compose.yml).
#
# Slow or filtered networks: pip gives up on PyPI after 15s per read, which is
# not enough on a congested link, and where PyPI or the npm registry is blocked
# outright no timeout helps. Both fetches below take a mirror as a build arg:
#
#   docker compose build --build-arg PIP_INDEX_URL=https://<mirror>/simple \
#                        --build-arg NPM_CONFIG_REGISTRY=https://<mirror>/
#
# or set PIP_INDEX_URL / NPM_CONFIG_REGISTRY in .env (see .env.example).
# The values are scoped to their RUN step so a mirror URL carrying credentials
# is not baked into the published image.

# ----------------------------------------------------------------------------
# Stage 1 — build the frontend
# ----------------------------------------------------------------------------
FROM node:20-bookworm-slim AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json* ./

ARG NPM_CONFIG_REGISTRY=https://registry.npmjs.org/
RUN NPM_CONFIG_REGISTRY="${NPM_CONFIG_REGISTRY:-https://registry.npmjs.org/}" \
    NPM_CONFIG_FETCH_RETRIES=5 \
    npm install

COPY frontend/ ./
RUN npm run build

# ----------------------------------------------------------------------------
# Stage 2 — backend runtime
# ----------------------------------------------------------------------------
FROM python:3.12-slim AS runtime
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install the backend (editable so /app/app is the importable package and
# /app/frontend_dist resolves relative to it).
COPY backend/ ./

ARG PIP_INDEX_URL=https://pypi.org/simple
RUN PIP_INDEX_URL="${PIP_INDEX_URL:-https://pypi.org/simple}" \
    PIP_DEFAULT_TIMEOUT=120 \
    PIP_RETRIES=10 \
    pip install -e .

# Built SPA from stage 1.
COPY --from=frontend /frontend/dist ./frontend_dist

RUN chmod +x scripts/entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["scripts/entrypoint.sh"]
