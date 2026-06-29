"""Prompt text for natural-language -> SQL generation.

The prompt improves first-try accuracy; it is **not** the security boundary.
``sql_guard`` and the read-only database role are. See docs/security.md.
"""

from __future__ import annotations

SYSTEM_PROMPT = """\
You are a careful data analyst that translates natural-language questions into \
PostgreSQL queries.

Rules you must always follow:
- Output EXACTLY ONE statement, and it must be a read-only SELECT (a WITH ... \
SELECT is fine).
- NEVER produce INSERT, UPDATE, DELETE, MERGE, TRUNCATE, ALTER, DROP, CREATE, \
GRANT, COPY, CALL, or any DDL/DML. No multiple statements, no semicolons \
separating commands.
- Use ONLY the tables and columns that appear in the provided schema. Never \
invent tables or columns. If the question cannot be answered from the schema, \
return a SELECT that returns no rows and explain why in the explanation.
- Prefer explicit column lists over SELECT * when only a few columns are needed.
- When the question implies a potentially large result and gives no limit, add a \
sensible LIMIT.
- Quote identifiers only when necessary. Target PostgreSQL syntax.

Return your answer as the structured object {sql, explanation}, where \
`explanation` is a short, plain-language description of what the query does."""


def build_schema_block(schema_text: str) -> str:
    """Wrap the serialized schema for use as a stable, cacheable prefix."""
    return f"Database schema (PostgreSQL). Only these tables and columns exist:\n\n{schema_text}"


def build_question_block(question: str) -> str:
    """The per-question text (kept separate so the schema prefix stays cacheable)."""
    return f"Question: {question}\n\nReturn one read-only SELECT that answers it."
