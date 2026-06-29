# Talk2Database

**Ask your database questions in plain language — preview the generated read-only SQL, then run it safely against a local copy of your data.**

Talk2Database is a self-hostable panel that turns natural-language questions into a single, **read-only** PostgreSQL `SELECT`. You preview the AI-generated SQL, accept it, and it runs against a *local* Postgres copy of your data. Results come back as a sortable table plus basic charts, with per-user query history, CSV export, and one-click re-run/edit.

It ships as a single `docker compose` bundle: a FastAPI + React panel, two PostgreSQL databases (one for panel metadata, one for your queryable data), and an optional cron container for scheduled syncing.

> Only your database **schema** is ever sent to the AI provider — never a single row of your data.

---

## Table of contents

- [Features](#features)
- [How it works](#how-it-works)
- [Architecture](#architecture)
- [Quickstart](#quickstart)
- [Environment reference](#environment-reference)
- [Import modes](#import-modes)
- [Security model](#security-model)
- [Local development](#local-development)
- [Project structure](#project-structure)
- [Tech stack](#tech-stack)
- [Screenshots](#screenshots)
- [Contributing](#contributing)
- [License](#license)

---

## Features

- **Natural language → SQL.** Ask a question; get a single read-only `SELECT` with a plain-language explanation.
- **Preview before you run.** The generated SQL is shown and validated *before* execution — you stay in control.
- **Two-layer read-only safety.** Every query runs as a dedicated SELECT-only Postgres role *and* is parsed and validated as a single read-only statement. See [Security model](#security-model).
- **Schema-only AI grounding.** The provider sees table/column/key metadata only. Row data never leaves your machine.
- **Low, predictable AI cost.** The schema is introspected once per import and reused as a cacheable prompt prefix; oversized schemas are trimmed to the tables most relevant to your question. See [docs/architecture.md](docs/architecture.md).
- **Configurable AI provider.** Anthropic (Claude) or OpenAI, selected with one environment variable.
- **Results, charts & export.** Tabular results, simple charts (Recharts), and one-click CSV download.
- **Query history.** Per-user history of questions, generated SQL, and outcomes — with re-run and edit-then-run.
- **Multi-user with roles.** First account bootstraps as admin; admins invite others via tokenized links. Passwords hashed with Argon2; JWT bearer auth.
- **Two data-load modes.** Upload a `.sql`/`pg_dump` backup through the panel (**manual**), or let a cron container full-refresh from a remote source on a schedule (**scheduled**).
- **Self-hosted, single command.** `docker compose up -d --build` and you are running.

---

## How it works

```text
                ┌──────────────────────────────────────────────────────────┐
   "How many    │  1. ASK                                                  │
    orders did  │     question + cached schema snapshot  ──►  AI provider   │
    we ship     │                                            (schema only)  │
    last week?" │  2. PREVIEW                                               │
       ─────────►     generated SELECT  ──►  sql_guard (single read-only?)  │
                │  3. ACCEPT                                                │
                │     you review the SQL and click Run                      │
                │  4. EXECUTE                                               │
                │     run as t2db_readonly, read-only txn + timeout         │
                │  ◄── rows + charts, saved to history, exportable as CSV   │
                └──────────────────────────────────────────────────────────┘
```

1. **Ask.** You type a question. The panel loads the stored schema snapshot (no live introspection), trims it to fit the token budget if needed, and asks the configured provider for one `SELECT`.
2. **Preview.** The returned SQL is validated by `sql_guard` (a single, read-only `SELECT`) and shown to you with an explanation. Nothing has touched your data yet.
3. **Accept.** You review — and optionally edit — the SQL, then run it.
4. **Execute.** The statement is re-validated and executed by the SELECT-only role inside a read-only transaction with a statement timeout. Results are paged into a table and charts, recorded in history, and available as CSV.

```mermaid
sequenceDiagram
    actor U as User
    participant P as Panel (FastAPI)
    participant S as Schema snapshot
    participant AI as AI provider
    participant G as sql_guard
    participant DB as userdata (t2db_readonly)

    U->>P: POST /api/ask {question}
    P->>S: load latest snapshot (trim to budget)
    P->>AI: question + schema (schema only)
    AI-->>P: {sql, explanation}
    P->>G: validate single read-only SELECT
    G-->>P: normalized SQL
    P-->>U: preview SQL + explanation
    U->>P: POST /api/execute {sql}
    P->>G: re-validate
    P->>DB: run (read-only txn + timeout)
    DB-->>P: rows
    P-->>U: table + charts (+ CSV)
```

---

## Architecture

Talk2Database runs as **four services** and **two databases**:

```mermaid
flowchart LR
    subgraph Bundle["docker compose bundle"]
        Panel["panel<br/>FastAPI API + built React SPA<br/>:8000"]
        Cron["cron (optional, profile: scheduled)<br/>full-refresh sync"]
        PanelDB[("postgres-panel<br/>users, history,<br/>import_runs, snapshots")]
        UserDB[("postgres-userdata<br/>your queryable data")]
    end
    Browser(["Browser"]) -->|HTTP :8000| Panel
    Panel -->|async SQLAlchemy| PanelDB
    Panel -->|psycopg, read-only role| UserDB
    Panel -->|admin role, restores only| UserDB
    Cron -->|dump → temp DB → swap| UserDB
    Remote[("Remote source DB")] -. scheduled only .-> Cron
    Panel -->|schema only| AI["AI provider<br/>(Anthropic / OpenAI)"]
```

| Service             | Role                                                                                                   |
| ------------------- | ------------------------------------------------------------------------------------------------------ |
| `panel`             | FastAPI JSON API under `/api` plus the built React SPA, on port `8000`. The only user-facing endpoint. |
| `postgres-panel`    | Panel metadata: users, invites, query history, import runs, schema snapshots.                          |
| `postgres-userdata` | The queryable copy of your data. Queried only via the read-only `t2db_readonly` role.                  |
| `cron`              | Optional. Started with `--profile scheduled`. Full-refreshes `postgres-userdata` from a remote source. |

For the request path, the schema-caching subsystem, the two DB layers, and the panel DB schema, see **[docs/architecture.md](docs/architecture.md)**.

---

## Quickstart

### Prerequisites

- **Docker** with the Compose plugin (`docker compose`).
- An **AI API key** for Anthropic or OpenAI.

### Steps

1. **Clone and create your env file.**

   ```bash
   git clone https://github.com/your-org/Talk2Database.git
   cd Talk2Database
   cp .env.example .env
   ```

2. **Edit `.env`.** At minimum, set:
   - `AI_PROVIDER`, `AI_API_KEY`, `AI_MODEL` — your provider and credentials.
   - `JWT_SECRET` — a long random secret, e.g. `openssl rand -hex 32`.
   - `PANEL_DB_PASSWORD`, `USERDATA_DB_ADMIN_PASSWORD`, `USERDATA_READONLY_PASSWORD` — strong passwords.
   - `IMPORT_MODE` — `manual` or `scheduled` (see [Import modes](#import-modes)).
   - For scheduled mode only: `REMOTE_DB_DSN` (and optionally `SYNC_INTERVAL_HOURS`).

   See the full [Environment reference](#environment-reference) below.

3. **Bring up the stack.**

   ```bash
   # Manual import mode (default)
   docker compose up -d --build

   # Scheduled sync mode (also starts the cron container)
   docker compose --profile scheduled up -d --build
   ```

   Equivalent Makefile targets: `make up` and `make up-scheduled`.

4. **Open the panel** at <http://localhost:8000> and **create the first admin account.** The very first registration bootstraps as an admin; this is only available while no users exist. After that, admins invite additional users from the panel.

5. **Load your data.**
   - *Manual mode:* upload a `.sql` or `pg_dump` backup through the panel.
   - *Scheduled mode:* the cron container syncs from `REMOTE_DB_DSN` on startup (if `SYNC_RUN_ON_STARTUP=true`) and every `SYNC_INTERVAL_HOURS`.

6. **Ask a question.** Once data is imported, head to the ask page and start querying in plain language.

---

## Environment reference

Every variable lives in `.env` (copied from `.env.example`). All services read from this single file. **Never commit your real `.env`** — it is gitignored.

### Data loading mode

| Variable           | Default  | Description                                                                                      |
| ------------------ | -------- | ------------------------------------------------------------------------------------------------ |
| `IMPORT_MODE`      | `manual` | How the user-data DB is populated. `manual` = upload backups in the panel; `scheduled` = cron full-refresh from `REMOTE_DB_DSN`. The unused path is disabled at runtime. |
| `POSTGRES_VERSION` | `16`     | Postgres major version for the user-data DB, the cron sync tooling, and the panel's restore client. Must be **≥** your source database's major version (see [Postgres version compatibility](#postgres-version-compatibility)). Changing it after first run requires recreating the userdata volume. |

### AI provider

| Variable           | Default          | Description                                                                                          |
| ------------------ | ---------------- | ---------------------------------------------------------------------------------------------------- |
| `AI_PROVIDER`      | `anthropic`      | Provider that converts natural language to SQL. One of `anthropic` or `openai`.                      |
| `AI_API_KEY`       | `replace-me`     | API key for the selected provider. Startup fails fast if this is unset or still `replace-me`.        |
| `AI_MODEL`         | `claude-opus-4-8`| Model id, e.g. `claude-opus-4-8` (Anthropic) or `gpt-4o` (OpenAI).                                   |
| `SCHEMA_MAX_TOKENS`| `6000`           | Token budget for the schema sent to the provider. If the serialized schema exceeds this, only the tables most relevant to the question (plus their FK neighbours) are sent. |
| `SCHEMA_TABLES`    | *(empty)*        | Optional comma-separated allowlist of tables to expose to the AI. Empty means all tables.            |
| `SCHEMA_INCLUDE_SCHEMAS` | `public`   | Comma-separated list of Postgres schemas to introspect and grant the read-only role on.              |

### Authentication

| Variable             | Default                              | Description                                                            |
| -------------------- | ------------------------------------ | ---------------------------------------------------------------------- |
| `JWT_SECRET`         | `replace-me-with-a-long-random-secret` | HMAC secret used to sign JWTs. Generate with `openssl rand -hex 32`. |
| `JWT_EXPIRE_MINUTES` | `60`                                 | Access-token lifetime, in minutes.                                     |
| `APP_BASE_URL`       | `http://localhost:8000`              | Base URL of the panel, used to build invite acceptance links.          |

### Query execution guard rails

| Variable                | Default | Description                                                                 |
| ----------------------- | ------- | --------------------------------------------------------------------------- |
| `QUERY_MAX_ROWS`        | `1000`  | Maximum rows returned per query (also the cap for CSV export and re-runs).   |
| `QUERY_TIMEOUT_SECONDS` | `30`    | `statement_timeout` (and idle-in-transaction timeout) applied to every query. |

### Panel database (`postgres-panel`)

Stores users, invites, query history, import runs, and schema snapshots.

| Variable            | Default          | Description                          |
| ------------------- | ---------------- | ------------------------------------ |
| `PANEL_DB_HOST`     | `postgres-panel` | Hostname of the panel database.      |
| `PANEL_DB_PORT`     | `5432`           | Port of the panel database.          |
| `PANEL_DB_NAME`     | `panel`          | Panel database name.                 |
| `PANEL_DB_USER`     | `panel`          | Panel database user.                 |
| `PANEL_DB_PASSWORD` | `replace-me-panel` | Panel database password.           |

### User-data database (`postgres-userdata`)

The queryable copy of your data. The admin role is used **only** for restores/sync; the read-only role is used for **all** AI query execution and schema introspection.

| Variable                    | Default              | Description                                                          |
| --------------------------- | -------------------- | ------------------------------------------------------------------- |
| `USERDATA_DB_HOST`          | `postgres-userdata`  | Hostname of the user-data database.                                 |
| `USERDATA_DB_PORT`          | `5432`               | Port of the user-data database.                                     |
| `USERDATA_DB_NAME`          | `userdata`           | User-data database name.                                            |
| `USERDATA_DB_ADMIN_USER`    | `postgres`           | Full-privilege role, used only for restores/sync — never for queries. |
| `USERDATA_DB_ADMIN_PASSWORD`| `replace-me-userdata-admin` | Password for the admin role.                                 |
| `USERDATA_READONLY_USER`    | `t2db_readonly`      | SELECT-only role used for all query execution and introspection.    |
| `USERDATA_READONLY_PASSWORD`| `replace-me-readonly`| Password for the read-only role.                                    |

### Scheduled sync (only used when `IMPORT_MODE=scheduled`)

| Variable              | Default                                            | Description                                                                             |
| --------------------- | -------------------------------------------------- | --------------------------------------------------------------------------------------- |
| `SYNC_INTERVAL_HOURS` | `6`                                                | How often the cron container full-refreshes from the remote source.                     |
| `SYNC_RUN_ON_STARTUP` | `true`                                             | Run one sync immediately when the cron container starts.                                 |
| `REMOTE_DB_DSN`       | `postgresql://user:password@remote-host:5432/source_db` | Source Postgres to copy *from*. Its major version must be `<=` the userdata Postgres major version. |

> **Note:** `CORS_ORIGINS` is also recognised by the backend (comma-separated allowed origins for cross-origin API access). It is not needed for the default same-origin compose deployment and is therefore not listed in `.env.example`; set it only if you serve the SPA from a different origin during development.

---

## Import modes

The two modes are **mutually exclusive**, selected by `IMPORT_MODE`. The unused path is disabled at runtime.

### `manual`

An admin uploads a database backup through the panel:

- **Plain SQL dumps** (`.sql`) are restored with `psql`.
- **`pg_dump` custom or tar backups** are restored with `pg_restore`.

The format is auto-detected from the file's leading bytes. The restore runs as a background task using the admin role (DDL is required), so the upload returns immediately. On success the read-only role is re-granted and the schema snapshot is rebuilt. Progress and outcomes appear as **import runs**.

### `scheduled`

Start the stack with `--profile scheduled` (or `make up-scheduled`). The cron container full-refreshes the user-data database from `REMOTE_DB_DSN`:

1. **Dump** the remote source first — if that fails, the live data is never touched.
2. **Restore** into a fresh temporary database (`<name>_new`), not the live one.
3. **Swap** atomically by renaming databases, so a mid-sync failure leaves the live database intact.
4. **Re-grant** the read-only role (grants do not survive a restore) and invalidate the panel's schema snapshot so it rebuilds.

A sync runs on startup when `SYNC_RUN_ON_STARTUP=true`, then every `SYNC_INTERVAL_HOURS`. The cron image is built from `postgres:${POSTGRES_VERSION}` so `pg_dump`/`pg_restore` match the user-data server version.

### Postgres version compatibility

`pg_dump`/`pg_restore` only move data safely when the tooling and the target server are **at least as new as the source**. In Talk2Database the relevant majors are the **cron/client tooling** and the **user-data server** — both set by `POSTGRES_VERSION` (default `16`). So the rule is:

> Your source database's major version must be **≤** `POSTGRES_VERSION`.

- **Source older than `POSTGRES_VERSION`** (e.g. source 14, `POSTGRES_VERSION=16`): ✅ works.
- **Source newer than `POSTGRES_VERSION`** (e.g. source 17, `POSTGRES_VERSION=16`): ❌ — set `POSTGRES_VERSION=17` (or higher) and rebuild. Bumping it requires recreating the userdata volume (it is a rebuildable copy; re-import or the next sync repopulates it). The panel metadata DB is independent and stays on its own pinned version.
- **Minor** differences (16.2 vs 16.7) never matter.

Rather than failing cryptically partway through a restore, Talk2Database performs a **preflight version check**: scheduled syncs and manual uploads compare the source/dump major version against the tooling and target and abort early with an actionable message (e.g. *"source is PostgreSQL 17 … set POSTGRES_VERSION=17"*). The atomic-swap design guarantees the live data is untouched on such a failure. Plain `.sql` dumps are the most portable option when versions are close.

---

## Security model

Read-only access is enforced as **defence in depth** — two independent layers, neither of which is the boundary on its own:

1. **A dedicated SELECT-only Postgres role (`t2db_readonly`).** All query execution and schema introspection connect as this role. It is granted `CONNECT`, `USAGE`, and `SELECT` only; `CREATE` is explicitly revoked and write/DDL privileges are never granted. Even a total parser bypass cannot mutate data.
2. **Server-side SQL validation (`sqlglot`).** Every statement is parsed and must be a *single, read-only `SELECT`*. The validator rejects multiple statements, any DML/DDL, data-modifying CTEs, `SELECT ... INTO`, `FOR UPDATE/SHARE`, and a denylist of dangerous functions (file/large-object access, `pg_sleep`, `dblink`, …). The text executed is re-serialized from the validated AST.

Additional guarantees:

- **Read-only transactions with timeouts.** Each query connection sets `default_transaction_read_only = on`, `statement_timeout`, and `idle_in_transaction_session_timeout` (from `QUERY_TIMEOUT_SECONDS`).
- **Schema-only AI grounding.** Only structural metadata (tables, columns, types, keys, comments) is sent to the provider — never row data.
- **Secrets stay in `.env`.** Nothing secret is persisted to a database. Invite tokens are stored **hashed**; the raw token only ever lives in the invite link.

Full details — including the exact grants, the validator's reject list, and operational notes — are in **[docs/security.md](docs/security.md)**.

---

## Local development

You can run the panel without Docker for fast iteration. You will need Python 3.12, Node 20, and a reachable Postgres for both databases. Most workflows are wrapped in the [`Makefile`](Makefile) — run `make help` for the full list.

### Backend

```bash
cd backend
pip install -e ".[dev]"     # runtime + dev tooling (ruff, mypy, pytest)
alembic upgrade head        # apply panel-DB migrations  (or: make migrate)
uvicorn app.main:app --reload --port 8000   # or: make backend-dev
```

### Frontend

```bash
cd frontend
npm install
npm run dev                 # Vite dev server, proxies /api -> :8000  (or: make frontend-dev)
```

### Quality gates

| Command              | What it runs                                                        |
| -------------------- | ------------------------------------------------------------------- |
| `make lint`          | Backend `ruff check` + `ruff format --check` + `mypy`, frontend `eslint` + `tsc`. |
| `make test`          | Backend `pytest`, frontend `vitest`.                                |
| `make format`        | Auto-format backend (ruff) and frontend (prettier).                 |
| `make migrate`       | Apply Alembic migrations to the panel DB.                           |
| `make revision m="…"`| Create a new autogenerated migration.                               |
| `make up` / `make down` | Start / stop the Docker bundle.                                  |

See **[CONTRIBUTING.md](CONTRIBUTING.md)** for the full contributor workflow.

---

## Project structure

```text
Talk2Database/
├── backend/                  # Python 3.12 + FastAPI
│   ├── app/
│   │   ├── config.py         # env-driven settings
│   │   ├── main.py           # FastAPI app: /api + SPA
│   │   ├── cli.py            # ensure-readonly-role / rebuild-schema
│   │   ├── deps.py           # auth dependencies
│   │   ├── db/               # panel (async SQLAlchemy) + userdata (psycopg)
│   │   ├── models/           # users, invites, query_history, import_runs, schema_snapshots
│   │   ├── routers/          # auth, users, ask, execute, history, imports, system
│   │   ├── schemas/          # Pydantic request/response models
│   │   ├── importers/        # manual backup restore
│   │   └── services/
│   │       ├── ai/           # provider abstraction (anthropic, openai), prompts
│   │       ├── schema/       # introspect, serialize, cache, relevance selection
│   │       ├── sql_guard.py  # single read-only SELECT validation
│   │       ├── query_runner.py
│   │       ├── readonly_role.py
│   │       └── auth_service.py
│   ├── alembic/              # panel DB migrations
│   └── pyproject.toml
├── frontend/                 # React + TypeScript (Vite)
├── cron/                     # scheduled full-refresh sync container
├── docs/                     # architecture & security docs
├── docker-compose.yml
├── Makefile
└── .env.example
```

---

## Tech stack

- **Backend:** Python 3.12, FastAPI, SQLAlchemy 2 (async, asyncpg) for the panel DB, psycopg 3 for read-only user-data access, Pydantic / pydantic-settings, Alembic, `sqlglot` (SQL validation), PyJWT, `pwdlib[argon2]` (password hashing).
- **AI:** Anthropic and OpenAI SDKs, with provider-agnostic structured output and prompt caching.
- **Frontend:** React 18 + TypeScript, Vite, React Router, Zustand, Recharts.
- **Databases:** PostgreSQL 16 (panel metadata + user data).
- **Packaging:** Docker / docker compose; multi-stage build (SPA → FastAPI runtime).

---

## Screenshots

Screenshots can be added under [`docs/screenshots/`](docs/screenshots/). Reference them here once available, for example:

```markdown
![Ask page](docs/screenshots/ask.png)
![Results & charts](docs/screenshots/results.png)
```

---

## Contributing

Contributions are welcome! Please read **[CONTRIBUTING.md](CONTRIBUTING.md)** for setup, coding standards, commit conventions, and the PR workflow, and our **[Code of Conduct](CODE_OF_CONDUCT.md)**. Security issues should follow the responsible-disclosure note in [docs/security.md](docs/security.md).

## License

Talk2Database is released under the [MIT License](LICENSE).
