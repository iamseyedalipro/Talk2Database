"""Anthropic (Claude) implementation of the SQL provider.

The schema is sent as a separate ``system`` block marked ``cache_control:
ephemeral`` so its tokens are billed once and reused across questions in the
caching window. Structured output is forced via a single tool call.
"""

from __future__ import annotations

import anthropic

from app.services.ai.base import (
    RESULT_SUMMARY_SCHEMA,
    SQL_OUTPUT_SCHEMA,
    AIProviderError,
    GeneratedSQL,
    ResultSummary,
)
from app.services.ai.prompts import build_question_block

_TOOL_NAME = "emit_sql"
_SUMMARY_TOOL_NAME = "emit_summary"


class AnthropicProvider:
    """Generate SQL using the Anthropic Messages API."""

    name = "anthropic"

    def __init__(self, api_key: str, model: str) -> None:
        self.model = model
        self._client = anthropic.Anthropic(api_key=api_key)

    def generate_sql(self, *, question: str, system_prompt: str, schema_block: str) -> GeneratedSQL:
        tool = {
            "name": _TOOL_NAME,
            "description": "Return the single read-only SQL SELECT that answers the question.",
            "input_schema": SQL_OUTPUT_SCHEMA,
        }
        try:
            response = self._client.messages.create(  # type: ignore[call-overload]
                model=self.model,
                max_tokens=1500,
                system=[
                    {"type": "text", "text": system_prompt},
                    {
                        "type": "text",
                        "text": schema_block,
                        "cache_control": {"type": "ephemeral"},
                    },
                ],
                tools=[tool],
                tool_choice={"type": "tool", "name": _TOOL_NAME},
                messages=[{"role": "user", "content": build_question_block(question)}],
            )
        except Exception as exc:
            raise AIProviderError(f"Anthropic request failed: {exc}") from exc

        for block in response.content:
            if getattr(block, "type", None) == "tool_use" and block.name == _TOOL_NAME:
                return GeneratedSQL.model_validate(block.input)

        raise AIProviderError("Anthropic did not return a structured SQL result.")

    def summarize_results(self, *, system_prompt: str, context: str) -> ResultSummary:
        tool = {
            "name": _SUMMARY_TOOL_NAME,
            "description": "Return a one-line summary of the results and a chart suggestion.",
            "input_schema": RESULT_SUMMARY_SCHEMA,
        }
        try:
            response = self._client.messages.create(  # type: ignore[call-overload]
                model=self.model,
                max_tokens=500,
                system=[{"type": "text", "text": system_prompt}],
                tools=[tool],
                tool_choice={"type": "tool", "name": _SUMMARY_TOOL_NAME},
                messages=[{"role": "user", "content": context}],
            )
        except Exception as exc:
            raise AIProviderError(f"Anthropic request failed: {exc}") from exc

        for block in response.content:
            if getattr(block, "type", None) == "tool_use" and block.name == _SUMMARY_TOOL_NAME:
                return ResultSummary.model_validate(block.input)

        raise AIProviderError("Anthropic did not return a structured summary result.")
