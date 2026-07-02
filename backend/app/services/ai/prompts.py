"""Prompt text for natural-language -> query generation.

The prompt improves first-try accuracy; it is **not** the security boundary.
``sql_guard`` (or a connector's own validator) and the read-only data-source
credentials are. See docs/security.md.

Prompts are parameterized by a human-readable *dialect label* (e.g.
"PostgreSQL", "MySQL") so a single template serves every SQL connector.
"""

from __future__ import annotations

_SYSTEM_TEMPLATE = """\
You are a careful data analyst that translates natural-language questions into \
{label} queries.

Rules you must always follow:
- Output EXACTLY ONE statement, and it must be a read-only SELECT (a WITH ... \
SELECT is fine).
- NEVER produce INSERT, UPDATE, DELETE, MERGE, TRUNCATE, ALTER, DROP, CREATE, \
GRANT, COPY, CALL, or any DDL/DML. No multiple statements, no semicolons \
separating commands.
- Use ONLY the tables and columns that appear in the provided schema. Never \
invent tables or columns.
- Prefer explicit column lists over SELECT * when only a few columns are needed.
- When the question implies a potentially large result and gives no limit, add a \
sensible LIMIT.
- Quote identifiers only when necessary. Target {label} syntax.

Deciding the `status` field:
- "ok": the question maps cleanly onto the schema. Set `sql` and a short \
`explanation`.
- "needs_clarification": the question mentions concepts that do not directly \
exist in the schema (for example it asks about "income" but there is no income \
table). DO NOT invent identifiers and DO NOT guess silently. Set \
`clarification_question` to a concrete question, and propose 2-4 \
`suggested_interpretations` — each `description` must be a complete, \
self-contained question that IS answerable from the schema (e.g. "What is the \
total of payments.amount for 2025?"), with a short `label` for its button.
- "unanswerable": no reasonable interpretation exists in this schema. Explain \
why in `explanation`.

Return your answer as the structured object {{status, sql, explanation, \
clarification_question, suggested_interpretations}}."""


def build_system_prompt(label: str) -> str:
    """The dialect-specific system prompt (e.g. label="PostgreSQL")."""
    return _SYSTEM_TEMPLATE.format(label=label)


def build_schema_block(schema_text: str, label: str) -> str:
    """Wrap the serialized schema for use as a stable, cacheable prefix."""
    return f"Database schema ({label}). Only these tables and columns exist:\n\n{schema_text}"


def build_question_block(question: str) -> str:
    """The per-question text (kept separate so the schema prefix stays cacheable)."""
    return f"Question: {question}\n\nReturn one read-only SELECT that answers it."


def build_guard_feedback(error: str) -> str:
    """Correction message when the statement failed read-only validation."""
    return (
        f"Your previous statement was rejected by the SQL validator: {error}\n\n"
        "Return EXACTLY ONE read-only SELECT statement that answers the question."
    )


_SUMMARY_SYSTEM = """\
You are a data analyst. Given a question, the SQL that answered it, and a \
sample of the result rows, write a 1-3 sentence factual answer in plain \
language. State concrete numbers from the sample when they answer the \
question. If the sample is truncated, only make claims the sample supports. \
Never speculate beyond the data shown. Respond with the answer text only."""


def build_summary_system_prompt() -> str:
    return _SUMMARY_SYSTEM


def build_summary_user_prompt(
    *, question: str, sql: str, table_text: str, row_count: int, truncated_note: str
) -> str:
    return (
        f"Question: {question}\n\n"
        f"SQL executed:\n{sql}\n\n"
        f"Result ({row_count} rows{truncated_note}):\n{table_text}\n\n"
        "Write the short answer."
    )


_SUGGESTIONS_TEMPLATE = """\
You are helping a user discover what they can ask about their {label} database. \
Based on the schema provided, propose example questions in plain language that \
a business user would realistically ask and that can be answered with a single \
read-only SELECT. Cover different tables and analysis styles (totals, trends \
over time, top-N, breakdowns). Keep each question under 15 words. Return the \
structured object {{questions}}."""


def build_suggestions_prompt(label: str) -> str:
    """System prompt for generating schema-derived example questions."""
    return _SUGGESTIONS_TEMPLATE.format(label=label)
