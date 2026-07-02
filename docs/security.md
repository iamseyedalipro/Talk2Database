# Security model

Talk2Database executes AI-generated SQL against a copy of your data. It is built so that **no AI-generated statement can ever modify, delete, or exfiltrate data**, even if one defensive layer fails. This document describes how that guarantee is constructed and the operational practices that keep it intact.

## Table of contents

- [Threat model](#threat-model)
- [Defence in depth: two read-only layers](#defence-in-depth-two-read-only-layers)
  - [Layer 1 — the SELECT-only Postgres role](#layer-1--the-select-only-postgres-role)
  - [Layer 2 — single-SELECT validation (sqlglot)](#layer-2--single-select-validation-sqlglot)
- [Read-only transactions and timeouts](#read-only-transactions-and-timeouts)
- [Schema-only AI grounding](#schema-only-ai-grounding)
- [Authentication and secrets](#authentication-and-secrets)
- [Operational notes](#operational-notes)
- [Responsible disclosure](#responsible-disclosure)

---

## Threat model

The central risk is that a language model — or a malicious user crafting a prompt — produces SQL that writes, drops, exfiltrates, or hangs the database. Talk2Database treats the model's output as **untrusted** and assumes:

- A prompt may try to coax the model into generating destructive SQL.
- The SQL validator could, in principle, have a parser gap.
- A database role could, in principle, be misconfigured.

No single mitigation is trusted to be perfect. The design ensures that **two independent layers** must both fail before any harm is possible.

---

## Defence in depth: two read-only layers

> Neither layer alone is the security boundary; both together are. A weakness in either one is not, by itself, exploitable.

### Layer 1 — the SELECT-only Postgres role

All query execution and schema introspection connect to the user-data database as a dedicated role, `t2db_readonly` (`USERDATA_READONLY_USER`). The role is created and (re-)granted by `app/services/readonly_role.py` at startup and after every import/sync, because a freshly restored database does not carry over grants. The same grants are mirrored in `cron/sync.sh` for the scheduled path.

The grants are intentionally minimal:

```sql
-- Per database:
REVOKE ALL    ON DATABASE <userdata> FROM t2db_readonly;
GRANT  CONNECT ON DATABASE <userdata> TO   t2db_readonly;

-- Per schema in SCHEMA_INCLUDE_SCHEMAS:
GRANT  USAGE  ON SCHEMA <s> TO t2db_readonly;
GRANT  SELECT ON ALL TABLES IN SCHEMA <s> TO t2db_readonly;
ALTER  DEFAULT PRIVILEGES IN SCHEMA <s> GRANT SELECT ON TABLES TO t2db_readonly;
REVOKE CREATE ON SCHEMA <s> FROM t2db_readonly;   -- belt and braces
```

The role can `CONNECT`, `USAGE` schemas, and `SELECT` tables — and nothing else. It is never granted `INSERT`/`UPDATE`/`DELETE`/`TRUNCATE`, DDL, or `CREATE`. The full-privilege admin role (`USERDATA_DB_ADMIN_USER`) is used **only** for restores and sync and never enters the request-serving path. Because this is enforced by PostgreSQL itself, even a complete bypass of the application-level validator cannot mutate data or create objects.

### Layer 2 — single-SELECT validation (`sqlglot`)

Before any statement reaches the database, `app/services/sql_guard.py` parses it with `sqlglot` (PostgreSQL dialect) and accepts it only if it is a **single, read-only `SELECT`**. The validated statement is re-serialized from the parsed AST, so the text that executes is exactly the text that was validated. The validator runs at both **ask** time (on the model's output) and **execute** time (on whatever is submitted, including edited SQL and re-runs).

It **rejects**:

- **Multiple statements** — only a single top-level statement is allowed (no `;`-separated commands).
- **Non-SELECT roots** — the top-level node must be `SELECT`/`UNION`/`EXCEPT`/`INTERSECT`. A leading `WITH … SELECT` is fine.
- **Any DML/DDL anywhere in the tree** (including inside CTEs and subqueries): `INSERT`, `UPDATE`, `DELETE`, `MERGE`, `CREATE`, `DROP`, `ALTER`, `TRUNCATE`, `GRANT`, `REVOKE`, `COPY`, `SET`, `USE`, and generic/unparsed commands (`VACUUM`, `CALL`, `DO`, …).
- **Data-modifying CTEs** — because the forbidden nodes are searched across the *entire* tree, a writable CTE such as `WITH x AS (DELETE …) SELECT …` is rejected.
- **`SELECT … INTO new_table`** — rejected (it creates a table).
- **`FOR UPDATE` / `FOR SHARE`** — rejected (locking / write intent).
- **Dangerous functions** — a denylist of functions that can read the filesystem, sleep, or reach other systems: `pg_read_file`, `pg_read_binary_file`, `pg_ls_dir`, `pg_stat_file`, `pg_sleep`, `pg_sleep_for`, `pg_sleep_until`, `lo_import`, `lo_export`, `lo_get`, `lo_put`, `dblink`, `dblink_exec`, `dblink_connect`, and `copy`.

If parsing fails or any rule is violated, the API responds with `422 Unprocessable Entity` and a clear message, and nothing is sent to the database.

> The prompt instructs the model to produce only read-only SELECTs, but the prompt is **not** the boundary — the role and the validator are. The prompt only improves first-try accuracy.

---

## Read-only transactions and timeouts

Every read-only connection (`app/db/userdata.py`) is hardened beyond the role itself. Before any query runs, the connection sets:

- `default_transaction_read_only = on` — a third independent read-only guarantee at the session level.
- `statement_timeout = QUERY_TIMEOUT_SECONDS` — a runaway or pathological query is aborted instead of hanging the panel.
- `idle_in_transaction_session_timeout = QUERY_TIMEOUT_SECONDS` — abandoned transactions are reaped.

Result size is bounded too: queries return at most `QUERY_MAX_ROWS` rows (the runner fetches `max_rows + 1` to flag truncation), and CSV export streams in batches so memory stays bounded.

---

## Schema-only AI grounding

Only **structural metadata** is ever sent to the AI provider: table and column names, data types, nullability, primary keys, foreign keys, and any object/column comments. This comes from `information_schema`/`pg_catalog` introspection (`app/services/schema/introspect.py`) run through the read-only connection. **No row data is ever read for introspection, and none is sent to the provider by default.** Results of executed queries are returned only to the authenticated user in the panel; they are not sent back to the model.

**Result summaries keep the same promise by default.** `POST /api/results/summarize` ("Explain results" in the panel) sends only column names/types and *locally-computed* aggregates to the provider — no raw rows. A deployment may opt into also sending a small sample of result rows for richer summaries via `AI_ALLOW_SAMPLE_ROWS=true` (capped at `AI_SAMPLE_ROWS`, default 5). Leave it off if your data must never reach the provider.

You can further restrict what the model sees:

- `SCHEMA_TABLES` — an allowlist of tables to expose (empty = all).
- `SCHEMA_INCLUDE_SCHEMAS` — which Postgres schemas to introspect and grant on.

When a schema exceeds `SCHEMA_MAX_TOKENS`, only the most relevant tables (plus FK neighbours and a name directory) are sent — which also reduces how much of the schema leaves the host.

---

## Authentication and secrets

- **Passwords** are hashed with Argon2 (`pwdlib[argon2]`); plaintext passwords are never stored.
- **Sessions** use JWT bearer tokens signed with `JWT_SECRET` (HS256), expiring after `JWT_EXPIRE_MINUTES`. Use a long, random secret — `openssl rand -hex 32`.
- **Roles.** Accounts are `admin` or `user`. The first registration **bootstraps an admin** and is only possible while no users exist; afterwards, admins invite others. Admin-only routes (user management, imports) require the `admin` role. The system also refuses to delete the last administrator or your own account.
- **Invite tokens are stored hashed.** `POST /users/invite` generates a URL-safe random token, stores only its **SHA-256 hash** (`token_hash`), and returns the raw token once in the acceptance link. Invites expire (7-day TTL) and are single-use (`accepted_at`). The database never holds a usable invite token.
- **Secrets stay in `.env`.** All credentials (AI key, DB passwords, JWT secret, remote DSN) live in the environment, sourced from `.env`. Nothing secret is persisted to a database. `.env` is gitignored — never commit it. Restrict file permissions on the host and rotate `JWT_SECRET` and database passwords if you suspect exposure.

---

## Operational notes

- **Set `POSTGRES_VERSION` to match your source.** A single `POSTGRES_VERSION` knob (default `16`) drives the user-data server, the cron sync tooling, and the panel's restore client, so `pg_dump`/`pg_restore`/`psql` all line up. It must be **≥** your source database's major version.
- **Source version must be `<=` `POSTGRES_VERSION`.** A newer source dump cannot be restored into an older server. Both the scheduled sync and manual uploads run a **preflight version check** that aborts early with an actionable message rather than failing partway through a restore; the atomic-swap design leaves live data untouched on such a failure.
- **The read-only role must be re-granted after every data load.** A restore replaces the database contents and drops grants. Both the manual importer and the cron sync re-run the grant logic; if you restore data out of band, re-run `python -m app.cli ensure-readonly-role`.
- **Keep the two grant implementations in sync.** `app/services/readonly_role.py` (manual/startup) and `cron/sync.sh` (scheduled) implement the same grants. Change them together.
- **Network exposure.** The panel listens on `:8000`. Put it behind a TLS-terminating reverse proxy for any non-local deployment, and do not expose the Postgres ports publicly. Set `CORS_ORIGINS` only if the SPA is served from a different origin.
- **Keep dependencies current.** `sqlglot` is part of the boundary; update it (and the rest of the stack) to pick up parser and security fixes.

---

## Responsible disclosure

If you discover a security vulnerability, please **do not** open a public issue. Instead, report it privately to the maintainers at **security@example.com** *(replace with the project's real security contact)*. Please include a description, reproduction steps, and the affected version/commit. We aim to acknowledge reports promptly and will coordinate a fix and disclosure timeline with you. We appreciate responsible disclosure and will credit reporters who wish to be acknowledged.
