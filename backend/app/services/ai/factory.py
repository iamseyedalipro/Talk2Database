"""Select and construct the configured AI provider."""

from __future__ import annotations

from functools import lru_cache

from app.config import AIProvider, get_settings
from app.services.ai.anthropic_provider import AnthropicProvider
from app.services.ai.base import LLMProvider
from app.services.ai.openai_provider import OpenAIProvider


@lru_cache
def get_ai_provider() -> LLMProvider:
    """Return the configured provider, validating credentials up front."""
    settings = get_settings()
    settings.validate_ai_config()

    match settings.ai_provider:
        case AIProvider.ANTHROPIC:
            return AnthropicProvider(settings.ai_api_key, settings.ai_model)
        case AIProvider.OPENAI:
            return OpenAIProvider(settings.ai_api_key, settings.ai_model)

    raise ValueError(f"unsupported AI provider: {settings.ai_provider}")
