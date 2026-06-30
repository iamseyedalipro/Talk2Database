"""OpenAI implementation of the SQL provider.

The schema is placed in the leading ``system`` message so OpenAI's automatic
prompt caching applies to the shared prefix across questions. Structured output
is enforced with a strict JSON schema.
"""

from __future__ import annotations

import json

import openai

from app.services.ai.base import SQL_OUTPUT_SCHEMA, AIProviderError, GeneratedSQL
from app.services.ai.prompts import build_question_block


class OpenAIProvider:
    """Generate SQL using the OpenAI Chat Completions API."""

    name = "openai"

    def __init__(self, api_key: str, model: str) -> None:
        self.model = model
        self._client = openai.OpenAI(api_key=api_key)

    def generate_sql(self, *, question: str, system_prompt: str, schema_block: str) -> GeneratedSQL:
        try:
            response = self._client.chat.completions.create(
                model=self.model,
                temperature=0,
                messages=[
                    {
                        "role": "system",
                        "content": f"{system_prompt}\n\n{schema_block}",
                    },
                    {"role": "user", "content": build_question_block(question)},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "sql_result",
                        "schema": SQL_OUTPUT_SCHEMA,
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
        return GeneratedSQL.model_validate(data)
