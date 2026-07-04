"""OpenAI implementation of the SQL provider.

The schema is placed in the leading ``system`` message so OpenAI's automatic
prompt caching applies to the shared prefix across questions — and across
correction retries, which only append to the message list. Structured output
is enforced with a strict JSON schema.
"""

from __future__ import annotations

import json
from typing import Any

import openai

from app.services.ai.base import (
    QUESTIONS_OUTPUT_SCHEMA,
    RESULT_SUMMARY_SCHEMA,
    SQL_OUTPUT_SCHEMA,
    AIProviderError,
    ChatMessage,
    ResultSummary,
    SqlGenerationResult,
    TokenUsage,
)


class OpenAIProvider:
    """Generate SQL using the OpenAI Chat Completions API."""

    name = "openai"

    def __init__(self, api_key: str, model: str) -> None:
        self.model = model
        self._client = openai.OpenAI(api_key=api_key)

    def _structured_call(
        self,
        *,
        system_content: str,
        messages: list[ChatMessage],
        schema_name: str,
        output_schema: dict[str, Any],
    ) -> tuple[dict[str, Any], TokenUsage]:
        """Run one strict-JSON-schema call and return the parsed object + usage."""
        chat_messages: list[Any] = [
            {"role": "system", "content": system_content},
            *[dict(m) for m in messages],
        ]
        try:
            response = self._client.chat.completions.create(
                model=self.model,
                temperature=0,
                messages=chat_messages,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": schema_name,
                        "schema": output_schema,
                        "strict": True,
                    },
                },
            )
        except Exception as exc:
            raise AIProviderError(f"OpenAI request failed: {exc}") from exc

        usage = _usage_from_response(response)
        content = response.choices[0].message.content
        if not content:
            raise AIProviderError("OpenAI returned an empty response.")
        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            raise AIProviderError("OpenAI returned invalid JSON.") from exc
        if not isinstance(data, dict):
            raise AIProviderError("OpenAI returned a non-object JSON payload.")
        return data, usage

    def generate_sql(
        self, *, messages: list[ChatMessage], system_prompt: str, schema_block: str
    ) -> tuple[SqlGenerationResult, TokenUsage]:
        data, usage = self._structured_call(
            system_content=f"{system_prompt}\n\n{schema_block}",
            messages=messages,
            schema_name="sql_result",
            output_schema=SQL_OUTPUT_SCHEMA,
        )
        try:
            return SqlGenerationResult.model_validate(data), usage
        except ValueError as exc:
            raise AIProviderError(f"OpenAI returned an invalid structured result: {exc}") from exc

    def suggest_questions(
        self, *, system_prompt: str, schema_block: str
    ) -> tuple[list[str], TokenUsage]:
        data, usage = self._structured_call(
            system_content=f"{system_prompt}\n\n{schema_block}",
            messages=[{"role": "user", "content": "Propose example questions for this schema."}],
            schema_name="example_questions",
            output_schema=QUESTIONS_OUTPUT_SCHEMA,
        )
        questions = data.get("questions")
        if not isinstance(questions, list) or not questions:
            raise AIProviderError("OpenAI returned no example questions.")
        return [str(q) for q in questions], usage

    def summarize_results(
        self, *, system_prompt: str, context: str
    ) -> tuple[ResultSummary, TokenUsage]:
        data, usage = self._structured_call(
            system_content=system_prompt,
            messages=[{"role": "user", "content": context}],
            schema_name="result_summary",
            output_schema=RESULT_SUMMARY_SCHEMA,
        )
        try:
            return ResultSummary.model_validate(data), usage
        except ValueError as exc:
            raise AIProviderError(f"OpenAI returned an invalid summary: {exc}") from exc


def _usage_from_response(response: Any) -> TokenUsage:
    """Map an OpenAI chat-completion response's ``usage`` to a :class:`TokenUsage`.

    OpenAI's ``prompt_tokens`` already includes any cached tokens, which it also
    reports separately under ``prompt_tokens_details.cached_tokens``. We surface
    the cached count for visibility but keep it inside ``input_tokens`` here would
    double count, so ``input_tokens`` holds the non-cached remainder. OpenAI has
    no cache-write billing concept, so ``cache_write_tokens`` stays 0.
    """
    usage = getattr(response, "usage", None)
    if usage is None:
        return TokenUsage()
    prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
    details = getattr(usage, "prompt_tokens_details", None)
    cached = getattr(details, "cached_tokens", 0) or 0 if details is not None else 0
    return TokenUsage(
        input_tokens=max(prompt_tokens - cached, 0),
        output_tokens=getattr(usage, "completion_tokens", 0) or 0,
        cache_read_tokens=cached,
        cache_write_tokens=0,
    )
