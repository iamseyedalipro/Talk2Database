"""Anthropic (Claude) implementation of the SQL provider.

The schema is sent as a separate ``system`` block marked ``cache_control:
ephemeral`` so its tokens are billed once and reused across questions — and
across correction retries, which only append to the message list. Structured
output is forced via a single tool call.
"""

from __future__ import annotations

from typing import Any

import anthropic

from app.services.ai.base import (
    QUESTIONS_OUTPUT_SCHEMA,
    RESULT_SUMMARY_SCHEMA,
    SQL_OUTPUT_SCHEMA,
    AIProviderError,
    ChatMessage,
    ResultSummary,
    SqlGenerationResult,
)

_TOOL_NAME = "emit_sql"
_QUESTIONS_TOOL_NAME = "emit_questions"
_SUMMARY_TOOL_NAME = "emit_summary"


class AnthropicProvider:
    """Generate SQL using the Anthropic Messages API."""

    name = "anthropic"

    def __init__(self, api_key: str, model: str) -> None:
        self.model = model
        self._client = anthropic.Anthropic(api_key=api_key)

    def _system_blocks(self, system_prompt: str, schema_block: str) -> list[dict[str, Any]]:
        return [
            {"type": "text", "text": system_prompt},
            {
                "type": "text",
                "text": schema_block,
                "cache_control": {"type": "ephemeral"},
            },
        ]

    def _structured_call(
        self,
        *,
        system: list[dict[str, Any]],
        messages: list[ChatMessage],
        tool_name: str,
        tool_description: str,
        output_schema: dict[str, Any],
    ) -> dict[str, Any]:
        """Run one forced-tool call and return the tool input as a dict."""
        tool = {
            "name": tool_name,
            "description": tool_description,
            "input_schema": output_schema,
        }
        try:
            response = self._client.messages.create(  # type: ignore[call-overload]
                model=self.model,
                max_tokens=1500,
                system=system,
                tools=[tool],
                tool_choice={"type": "tool", "name": tool_name},
                messages=list(messages),
            )
        except Exception as exc:
            raise AIProviderError(f"Anthropic request failed: {exc}") from exc

        for block in response.content:
            if getattr(block, "type", None) == "tool_use" and block.name == tool_name:
                return dict(block.input)
        raise AIProviderError("Anthropic did not return a structured result.")

    def generate_sql(
        self, *, messages: list[ChatMessage], system_prompt: str, schema_block: str
    ) -> SqlGenerationResult:
        data = self._structured_call(
            system=self._system_blocks(system_prompt, schema_block),
            messages=messages,
            tool_name=_TOOL_NAME,
            tool_description=(
                "Return the structured generation result: a single read-only SQL "
                "SELECT, a clarification request, or an unanswerable verdict."
            ),
            output_schema=SQL_OUTPUT_SCHEMA,
        )
        try:
            return SqlGenerationResult.model_validate(data)
        except ValueError as exc:
            raise AIProviderError(f"Anthropic returned an invalid result: {exc}") from exc

    def suggest_questions(self, *, system_prompt: str, schema_block: str) -> list[str]:
        data = self._structured_call(
            system=self._system_blocks(system_prompt, schema_block),
            messages=[
                {"role": "user", "content": "Propose example questions for this schema."}
            ],
            tool_name=_QUESTIONS_TOOL_NAME,
            tool_description="Return example natural-language questions for this schema.",
            output_schema=QUESTIONS_OUTPUT_SCHEMA,
        )
        questions = data.get("questions")
        if not isinstance(questions, list) or not questions:
            raise AIProviderError("Anthropic returned no example questions.")
        return [str(q) for q in questions]

    def summarize_results(self, *, system_prompt: str, context: str) -> ResultSummary:
        data = self._structured_call(
            system=[{"type": "text", "text": system_prompt}],
            messages=[{"role": "user", "content": context}],
            tool_name=_SUMMARY_TOOL_NAME,
            tool_description="Return a one-line summary of the results and a chart suggestion.",
            output_schema=RESULT_SUMMARY_SCHEMA,
        )
        try:
            return ResultSummary.model_validate(data)
        except ValueError as exc:
            raise AIProviderError(f"Anthropic returned an invalid summary: {exc}") from exc
