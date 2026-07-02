"""Anthropic (Claude) implementation of the SQL provider.

The schema is sent as a separate ``system`` block marked ``cache_control:
ephemeral`` so its tokens are billed once and reused across questions in the
caching window. Structured output is forced via a single tool call.
"""

from __future__ import annotations

from typing import Any

import anthropic

from app.services.ai.base import (
    SQL_OUTPUT_SCHEMA,
    AIProviderError,
    ChatMessage,
    ChatTurn,
    GeneratedSQL,
    ToolCall,
    ToolSpec,
)
from app.services.ai.prompts import build_question_block

_TOOL_NAME = "emit_sql"


def _to_anthropic_messages(messages: list[ChatMessage]) -> list[Any]:
    """Translate neutral chat turns into Anthropic content blocks."""
    out: list[dict[str, Any]] = []
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

    def chat(
        self,
        *,
        system: str,
        messages: list[ChatMessage],
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
