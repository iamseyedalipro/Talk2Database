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
    ChatTurn,
    ResultSummary,
    SqlGenerationResult,
    TokenUsage,
    ToolCall,
    ToolChatMessage,
    ToolSpec,
)

_TOOL_NAME = "emit_sql"
_QUESTIONS_TOOL_NAME = "emit_questions"
_SUMMARY_TOOL_NAME = "emit_summary"


def _to_anthropic_messages(messages: list[ToolChatMessage]) -> list[Any]:
    """Translate neutral tool-chat turns into Anthropic content blocks."""
    out: list[Any] = []
    for msg in messages:
        blocks: list[dict[str, Any]] = []
        for result in msg.tool_results:
            blocks.append(
                {
                    "type": "tool_result",
                    "tool_use_id": result.tool_call_id,
                    "content": result.content,
                    "is_error": result.is_error,
                }
            )
        if msg.text:
            blocks.append({"type": "text", "text": msg.text})
        for call in msg.tool_calls:
            blocks.append(
                {"type": "tool_use", "id": call.id, "name": call.name, "input": call.input}
            )
        out.append({"role": msg.role, "content": blocks})
    return out


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
    ) -> tuple[dict[str, Any], TokenUsage]:
        """Run one forced-tool call and return the tool input plus token usage."""
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

        usage = _usage_from_response(response)
        for block in response.content:
            if getattr(block, "type", None) == "tool_use" and block.name == tool_name:
                return dict(block.input), usage
        raise AIProviderError("Anthropic did not return a structured result.")

    def generate_sql(
        self, *, messages: list[ChatMessage], system_prompt: str, schema_block: str
    ) -> tuple[SqlGenerationResult, TokenUsage]:
        data, usage = self._structured_call(
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
            return SqlGenerationResult.model_validate(data), usage
        except ValueError as exc:
            raise AIProviderError(f"Anthropic returned an invalid result: {exc}") from exc

    def suggest_questions(
        self, *, system_prompt: str, schema_block: str
    ) -> tuple[list[str], TokenUsage]:
        data, usage = self._structured_call(
            system=self._system_blocks(system_prompt, schema_block),
            messages=[{"role": "user", "content": "Propose example questions for this schema."}],
            tool_name=_QUESTIONS_TOOL_NAME,
            tool_description="Return example natural-language questions for this schema.",
            output_schema=QUESTIONS_OUTPUT_SCHEMA,
        )
        questions = data.get("questions")
        if not isinstance(questions, list) or not questions:
            raise AIProviderError("Anthropic returned no example questions.")
        return [str(q) for q in questions], usage

    def summarize_results(
        self, *, system_prompt: str, context: str
    ) -> tuple[ResultSummary, TokenUsage]:
        data, usage = self._structured_call(
            system=[{"type": "text", "text": system_prompt}],
            messages=[{"role": "user", "content": context}],
            tool_name=_SUMMARY_TOOL_NAME,
            tool_description="Return a one-line summary of the results and a chart suggestion.",
            output_schema=RESULT_SUMMARY_SCHEMA,
        )
        try:
            return ResultSummary.model_validate(data), usage
        except ValueError as exc:
            raise AIProviderError(f"Anthropic returned an invalid summary: {exc}") from exc

    def chat(
        self,
        *,
        system: str,
        messages: list[ToolChatMessage],
        tools: list[ToolSpec],
        force_text: bool = False,
    ) -> ChatTurn:
        kwargs: dict[str, Any] = {}
        if tools and not force_text:
            kwargs["tools"] = [
                {"name": t.name, "description": t.description, "input_schema": t.input_schema}
                for t in tools
            ]
        try:
            response = self._client.messages.create(
                model=self.model,
                max_tokens=3000,
                system=[
                    {
                        "type": "text",
                        "text": system,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=_to_anthropic_messages(messages),
                **kwargs,
            )
        except Exception as exc:
            raise AIProviderError(f"Anthropic request failed: {exc}") from exc

        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        for block in response.content:
            if isinstance(block, anthropic.types.TextBlock):
                text_parts.append(block.text)
            elif isinstance(block, anthropic.types.ToolUseBlock):
                block_input = block.input if isinstance(block.input, dict) else {}
                tool_calls.append(ToolCall(id=block.id, name=block.name, input=dict(block_input)))
        return ChatTurn(text="\n".join(text_parts).strip() or None, tool_calls=tool_calls)


def _usage_from_response(response: Any) -> TokenUsage:
    """Map an Anthropic Messages response's ``usage`` to a :class:`TokenUsage`.

    Anthropic reports cache reads/writes separately from ``input_tokens``, so the
    four counts do not overlap.
    """
    usage = getattr(response, "usage", None)
    if usage is None:
        return TokenUsage()
    return TokenUsage(
        input_tokens=getattr(usage, "input_tokens", 0) or 0,
        output_tokens=getattr(usage, "output_tokens", 0) or 0,
        cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
        cache_write_tokens=getattr(usage, "cache_creation_input_tokens", 0) or 0,
    )
