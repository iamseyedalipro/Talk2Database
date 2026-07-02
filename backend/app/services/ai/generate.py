"""Orchestrates SQL generation: guard validation, schema verification, retries.

Providers only render a message list; all correction logic lives here. When the
model hallucinates identifiers (or fails the read-only guard) the previous
answer plus a corrective message are appended to the conversation and the call
is repeated — the system prompt and schema block stay byte-identical, so
provider prompt caching still applies across retries.
"""

from __future__ import annotations

from dataclasses import dataclass

from starlette.concurrency import run_in_threadpool

from app.config import Settings
from app.connectors.base import Connector
from app.services.ai.base import ChatMessage, LLMProvider, SqlGenerationResult
from app.services.ai.prompts import build_guard_feedback, build_question_block
from app.services.schema.introspect import SchemaData
from app.services.sql_guard import SqlGuardError
from app.services.sql_verify import (
    VerificationResult,
    build_correction_feedback,
    verify_identifiers,
)


@dataclass
class GenerationOutcome:
    """Final result of the generate -> validate -> verify loop."""

    result: SqlGenerationResult
    # Guard-normalized SQL. Set when the guard accepted the statement — even on
    # verification failure, so the user can inspect and hand-edit the last try.
    safe_sql: str | None
    retry_count: int
    # The failed verification when retries were exhausted; None on success.
    verification: VerificationResult | None

    @property
    def verified(self) -> bool:
        return self.result.status == "ok" and self.verification is None


async def generate_with_verification(
    *,
    provider: LLMProvider,
    connector: Connector,
    question: str,
    full_schema: SchemaData,
    selected_text: str,
    settings: Settings,
) -> GenerationOutcome:
    """Generate SQL for ``question``, verifying identifiers against ``full_schema``.

    ``full_schema`` must be the complete snapshot (not the token-trimmed text in
    ``selected_text``), so a table the trimming dropped is not flagged as
    hallucinated.

    Raises:
        AIProviderError: when the provider fails.
        SqlGuardError: when even the final attempt is not a read-only SELECT.
    """
    system_prompt = connector.system_prompt()
    schema_block = connector.schema_block(selected_text)
    messages: list[ChatMessage] = [{"role": "user", "content": build_question_block(question)}]

    attempts = 1 + max(0, settings.ask_max_retries)
    retry_count = 0
    last_verification: VerificationResult | None = None
    safe_sql: str | None = None

    for attempt in range(attempts):
        result: SqlGenerationResult = await run_in_threadpool(
            provider.generate_sql,
            messages=messages,
            system_prompt=system_prompt,
            schema_block=schema_block,
        )

        if result.status != "ok":
            # A clarification request or unanswerable verdict is a final answer,
            # not a failure — never retried.
            return GenerationOutcome(
                result=result, safe_sql=None, retry_count=retry_count, verification=None
            )

        try:
            safe_sql = connector.validate(result.sql or "")
        except SqlGuardError as exc:
            if attempt == attempts - 1:
                raise
            messages.append({"role": "assistant", "content": result.model_dump_json()})
            messages.append({"role": "user", "content": build_guard_feedback(str(exc))})
            retry_count += 1
            continue

        if not settings.ask_verify_identifiers:
            return GenerationOutcome(
                result=result, safe_sql=safe_sql, retry_count=retry_count, verification=None
            )

        verification = verify_identifiers(safe_sql, full_schema, connector.dialect)
        if verification.ok:
            return GenerationOutcome(
                result=result, safe_sql=safe_sql, retry_count=retry_count, verification=None
            )

        last_verification = verification
        if attempt < attempts - 1:
            messages.append({"role": "assistant", "content": result.model_dump_json()})
            messages.append(
                {"role": "user", "content": build_correction_feedback(verification, full_schema)}
            )
            retry_count += 1

    return GenerationOutcome(
        result=result, safe_sql=safe_sql, retry_count=retry_count, verification=last_verification
    )
