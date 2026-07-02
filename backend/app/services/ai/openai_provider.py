"""OpenAI implementation of the SQL provider.

The schema is placed in the leading ``system`` message so OpenAI's automatic
prompt caching applies to the shared prefix across questions. Structured output
is enforced with a strict JSON schema.
"""

from __future__ import annotations

import json
from typing import Any

import openai

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


def _to_openai_messages(system: str, messages: list[ChatMessage]) -> list[Any]:
    """Translate neutral chat turns into Chat Completions messages."""
    out: list[dict[str, Any]] = [{"role": "system", "content": system}]
    for msg in messages:
        if msg.role == "assistant":
            entry: dict[str, Any] = {"role": "assistant", "content": msg.text or None}
            if msg.tool_calls:
                entry["tool_calls"] = [
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {"name": call.name, "arguments": json.dumps(call.input)},
                    }
                    for call in msg.tool_calls
                ]
            out.append(entry)
            continue
        # Tool results must be standalone "tool" messages preceding further text.
        for result in msg.tool_results:
            content = result.content
            if result.is_error:
                content = f"ERROR: {content}"
            out.append({"role": "tool", "tool_call_id": result.tool_call_id, "content": content})
        if msg.text:
            out.append({"role": "user", "content": msg.text})
    return out


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

    def chat(
        self,
        *,
        system: str,
        messages: list[ChatMessage],
        tools: list[ToolSpec],
        force_text: bool = False,
    ) -> ChatTurn:
        kwargs: dict[str, Any] = {}
        if tools:
            kwargs["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.input_schema,
                    },
                }
                for t in tools
            ]
            if force_text:
                kwargs["tool_choice"] = "none"
        try:
            response = self._client.chat.completions.create(
                model=self.model,
                temperature=0,
                messages=_to_openai_messages(system, messages),
                **kwargs,
            )
        except Exception as exc:
            raise AIProviderError(f"OpenAI request failed: {exc}") from exc

        message = response.choices[0].message
        tool_calls: list[ToolCall] = []
        for call in message.tool_calls or []:
            if call.type != "function":
                continue
            try:
                arguments = json.loads(call.function.arguments or "{}")
            except json.JSONDecodeError:
                arguments = {}
            if not isinstance(arguments, dict):
                arguments = {}
            tool_calls.append(ToolCall(id=call.id, name=call.function.name, input=arguments))
        text = (message.content or "").strip()
        return ChatTurn(text=text or None, tool_calls=tool_calls)
