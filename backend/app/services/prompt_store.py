"""DB-backed, panel-editable prompt templates with hard-coded fallbacks.

Admins can override the Ask (NL -> SQL) system template and the Analysis
system prompt from the admin panel. Overrides live in ``app_settings`` under
``prompt.<key>``; a missing row means "use the built-in default", so resetting
a prompt is just deleting its row. A malformed override can never take the
/ask endpoint down: rendering falls back to the built-in template.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.ai.prompts import DEFAULT_PROMPTS
from app.services.app_settings import delete_setting, get_setting, set_setting

PROMPT_KEYS: frozenset[str] = frozenset(DEFAULT_PROMPTS)

ASK_PROMPT_KEY = "ask_system_template"
ANALYSIS_PROMPT_KEY = "analysis_system"
ASK_ANALYSIS_PROMPT_KEY = "ask_analysis_loop"


def _setting_key(key: str) -> str:
    return f"prompt.{key}"


def _check_key(key: str) -> None:
    if key not in PROMPT_KEYS:
        raise KeyError(f"Unknown prompt '{key}'. Known prompts: {', '.join(sorted(PROMPT_KEYS))}")


async def get_prompt(session: AsyncSession, key: str) -> tuple[str, bool]:
    """Return ``(content, is_customized)`` for a prompt key."""
    _check_key(key)
    override = await get_setting(session, _setting_key(key))
    if isinstance(override, str) and override.strip():
        return override, True
    return DEFAULT_PROMPTS[key], False


async def set_prompt(session: AsyncSession, key: str, content: str) -> None:
    _check_key(key)
    await set_setting(session, _setting_key(key), content)


async def reset_prompt(session: AsyncSession, key: str) -> None:
    _check_key(key)
    await delete_setting(session, _setting_key(key))


# Appended after the (admin-editable) template so prompt overrides can never
# drop it: the model must answer Persian questions in Persian, etc. The suffix
# is byte-stable per dialect, so provider prompt caching is unaffected.
_ANSWER_LANGUAGE_SUFFIX = (
    "\n\nAnswer language: write `explanation`, `clarification_question`, and the "
    "interpretation labels/descriptions in the same language as the user's "
    "question (e.g. a Persian question gets Persian text). SQL keywords and "
    "identifiers always remain SQL."
)


def render_ask_system(template: str, label: str) -> str:
    """Render the ask system template, surviving bad admin edits.

    A template with a typo'd placeholder (e.g. ``{labl}``) or stray braces
    would raise from ``str.format``; fall back to the built-in default rather
    than failing the request.
    """
    try:
        rendered = template.format(label=label)
    except (KeyError, IndexError, ValueError):
        rendered = DEFAULT_PROMPTS[ASK_PROMPT_KEY].format(label=label)
    return rendered + _ANSWER_LANGUAGE_SUFFIX
