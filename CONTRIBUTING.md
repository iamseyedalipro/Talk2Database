# Contributing to Talk2Database

Thanks for your interest in improving Talk2Database! This guide covers setting up a development environment, the quality gates your change must pass, and the workflow for getting it merged.

By participating you agree to abide by our [Code of Conduct](CODE_OF_CONDUCT.md).

## Table of contents

- [Development setup](#development-setup)
- [Running the app locally](#running-the-app-locally)
- [Quality gates](#quality-gates)
- [Coding standards](#coding-standards)
- [Commit messages](#commit-messages)
- [Branch & PR workflow](#branch--pr-workflow)
- [Database migrations](#database-migrations)
- [Reporting bugs & requesting features](#reporting-bugs--requesting-features)

---

## Development setup

**Prerequisites:** Python 3.12, Node 20, and a reachable PostgreSQL 16 for the panel and user-data databases (the easiest way is the compose bundle's Postgres services). Docker with the Compose plugin is recommended.

```bash
git clone https://github.com/your-org/Talk2Database.git
cd Talk2Database
cp .env.example .env        # then edit values (AI key, DB passwords, JWT secret)
```

Install both toolchains:

```bash
# Backend (runtime + dev tools: ruff, mypy, pytest)
cd backend
pip install -e ".[dev]"

# Frontend
cd ../frontend
npm install
```

Run `make help` from the repo root to see all developer targets.

---

## Running the app locally

```bash
# Backend API with autoreload (needs the panel DB migrated + .env)
make migrate          # alembic upgrade head
make backend-dev      # uvicorn app.main:app --reload --port 8000

# Frontend dev server (proxies /api -> :8000)
make frontend-dev     # npm run dev
```

Or run the full Docker bundle: `make up` (manual mode) / `make up-scheduled` (with the sync cron).

---

## Quality gates

**Every PR must pass lint, type checks, and tests** for any area it touches. These are the same checks CI runs.

Run everything at once:

```bash
make lint    # backend ruff + mypy, frontend eslint + tsc
make test    # backend pytest, frontend vitest
```

### Backend

| Check       | Command (from `backend/`)   |
| ----------- | --------------------------- |
| Lint        | `ruff check .`              |
| Format      | `ruff format --check .`     |
| Type check  | `mypy app`                  |
| Tests       | `pytest`                    |

`mypy` runs in `strict` mode with the Pydantic plugin — keep type annotations complete (`disallow_untyped_defs`). Auto-fix and format with `make format` (`ruff format` + `ruff check --fix`).

### Frontend

| Check       | Command (from `frontend/`)  |
| ----------- | --------------------------- |
| Lint        | `npm run lint`              |
| Type check  | `npm run typecheck`         |
| Build       | `npm run build`             |
| Tests       | `npm test` (`vitest run`)   |

Format with `npm run format` (Prettier).

---

## Coding standards

- **Backend (Python 3.12):** Follow the existing style — `from __future__ import annotations`, full type hints, small focused functions, and module docstrings explaining intent. Ruff enforces the rule set in `backend/pyproject.toml` (pycodestyle/pyflakes, import sorting, pyupgrade, bugbear, comprehensions, simplify, etc.); line length is 100. Prefer the existing service/router layering; keep security-relevant code (`sql_guard.py`, `readonly_role.py`, the userdata connection) conservative and well-commented.
- **Frontend (TypeScript + React):** Strict TypeScript, function components, ESLint clean. Match the existing structure under `frontend/src` (`api/`, `store/`, `components/`, `pages/`).
- **Security first:** Read-only enforcement is two-layered (SELECT-only role + `sqlglot` validation) — never weaken either. Never send row data to the AI provider; only schema metadata. If you change the read-only grants, update **both** `app/services/readonly_role.py` and `cron/sync.sh`.
- **Docs:** Update `README.md` / `docs/` when you change behaviour, env vars, endpoints, or the import/security model. If you add an env var, add it to `.env.example` and the README env table.

---

## Commit messages

Use [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<optional scope>): <short summary>
```

Common types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `ci`, `perf`, `build`. Examples:

```
feat(ask): warn when the schema is trimmed to fit the token budget
fix(sql-guard): reject SELECT ... INTO
docs(security): document invite-token hashing
ci: add compose config validation job
```

Keep the summary in the imperative mood and under ~72 characters; add a body for the why when it isn't obvious.

---

## Branch & PR workflow

1. **Fork** the repo (or create a branch if you have access). Branch from `main`, e.g. `feat/schema-trim-warning` or `fix/csv-encoding`.
2. **Make focused changes.** Keep PRs small and single-purpose where possible.
3. **Run the quality gates locally:** `make lint && make test`. Add or update tests for behavioural changes.
4. **Open a PR** against `main` using the [pull request template](.github/pull_request_template.md). Fill in Summary, Changes, Testing, and the Checklist.
5. **Keep it green.** CI (lint, type checks, tests, and `docker compose config` validation) must pass.
6. **Address review feedback** and keep your branch up to date with `main`.

Do **not** include secrets, real `.env` files, API keys, tokens, or production credentials in commits, PRs, issues, or screenshots.

---

## Database migrations

The panel database is managed with Alembic. When you change a model under `backend/app/models/`:

```bash
make revision m="describe the change"   # alembic revision --autogenerate -m "..."
make migrate                            # alembic upgrade head
```

Review the generated migration before committing — autogenerate is a starting point, not a guarantee. Only the **panel** database is migrated; the user-data database schema comes from the imported/synced data.

---

## Reporting bugs & requesting features

Use the issue templates:

- [Bug report](.github/ISSUE_TEMPLATE/bug_report.md)
- [Feature request](.github/ISSUE_TEMPLATE/feature_request.md)

For security vulnerabilities, **do not** open a public issue — follow the [responsible-disclosure note](docs/security.md#responsible-disclosure).
