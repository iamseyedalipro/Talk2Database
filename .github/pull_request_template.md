## Summary

Briefly describe what this PR does and why. Link any related issues (e.g. `Closes #123`).

## Changes

- What changed, at a high level (bullet points).
-

## Testing

How did you verify this change? Include commands run and what you observed.

- [ ] `make lint`
- [ ] `make test`
- [ ] Manually verified (describe):

## Checklist

- [ ] Lint passes (`make lint` — backend ruff + mypy, frontend eslint + tsc)
- [ ] Tests pass (`make test`) and new behaviour is covered by tests
- [ ] Docs updated (`README.md` / `docs/`) when behaviour, env vars, endpoints, or the import/security model changed
- [ ] New env vars (if any) added to `.env.example` and the README env reference
- [ ] Read-only enforcement (SELECT-only role + `sqlglot` validation) is preserved; no row data is sent to the AI provider
- [ ] Commits follow Conventional Commits
- [ ] No secrets, tokens, credentials, or real `.env` files are included
