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
    ) -> dict[str, Any]:
        """Run one strict-JSON-schema call and return the parsed object."""
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

        content = response.choices[0].message.content
        if not content:
            raise AIProviderError("OpenAI returned an empty response.")
        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            raise AIProviderError("OpenAI returned invalid JSON.") from exc
        if not isinstance(data, dict):
            raise AIProviderError("OpenAI returned a non-object JSON payload.")
        return data

    def generate_sql(
        self, *, messages: list[ChatMessage], system_prompt: str, schema_block: str
    ) -> SqlGenerationResult:
        data = self._structured_call(
            system_content=f"{system_prompt}\n\n{schema_block}",
            messages=messages,
            schema_name="sql_result",
            output_schema=SQL_OUTPUT_SCHEMA,
        )
        try:
            return SqlGenerationResult.model_validate(data)
        except ValueError as exc:
            raise AIProviderError(f"OpenAI returned an invalid structured result: {exc}") from exc

    def suggest_questions(self, *, system_prompt: str, schema_block: str) -> list[str]:
        data = self._structured_call(
            system_content=f"{system_prompt}\n\n{schema_block}",
            messages=[
                {"role": "user", "content": "Propose example questions for this schema."}
            ],
            schema_name="example_questions",
            output_schema=QUESTIONS_OUTPUT_SCHEMA,
        )
        questions = data.get("questions")
        if not isinstance(questions, list) or not questions:
            raise AIProviderError("OpenAI returned no example questions.")
        return [str(q) for q in questions]

    def summarize_results(self, *, system_prompt: str, context: str) -> ResultSummary:
        data = self._structured_call(
            system_content=system_prompt,
            messages=[{"role": "user", "content": context}],
            schema_name="result_summary",
            output_schema=RESULT_SUMMARY_SCHEMA,
        )
        try:
            return ResultSummary.model_validate(data)
        except ValueError as exc:
            raise AIProviderError(f"OpenAI returned an invalid summary: {exc}") from exc
