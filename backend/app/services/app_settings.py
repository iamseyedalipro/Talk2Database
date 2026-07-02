"""Read/write helpers for the ``app_settings`` key/value table.

Also defines the Microsoft Clarity configuration keys and their defaults. The
Clarity API token is stored Fernet-encrypted (same key as connection secrets)
and only decrypted at fetch time.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.app_setting import AppSetting
from app.services.crypto import SecretCryptoError, decrypt_secret

# Dimensions accepted by the Clarity Data Export API.
ALLOWED_DIMENSIONS: tuple[str, ...] = (
    "Browser",
    "Device",
    "Country/Region",
    "OS",
    "Source",
    "Medium",
    "Campaign",
    "Channel",
    "URL",
)

# 8 combinations by default, leaving 2 of the 10 daily requests as headroom
# for manual "Fetch now" retries.
DEFAULT_DIMENSION_COMBOS: list[list[str]] = [
    [],
    ["URL"],
    ["Device"],
    ["Source"],
    ["Country/Region"],
    ["OS"],
    ["Browser"],
    ["URL", "Device"],
]

KEY_CLARITY_TOKEN = "clarity_api_token"
KEY_CLARITY_PROJECT_ID = "clarity_project_id"
KEY_CLARITY_FETCH_TIME = "clarity_fetch_time"
KEY_CLARITY_TIMEZONE = "clarity_timezone"
KEY_CLARITY_COMBOS = "clarity_dimension_combos"

DEFAULT_FETCH_TIME = "00:30"
DEFAULT_TIMEZONE = "UTC"


async def get_setting(session: AsyncSession, key: str) -> Any:
    row = await session.get(AppSetting, key)
    return None if row is None else row.value


async def set_setting(session: AsyncSession, key: str, value: Any) -> None:
    row = await session.get(AppSetting, key)
    if row is None:
        session.add(AppSetting(key=key, value=value))
    else:
        row.value = value
    await session.flush()


async def delete_setting(session: AsyncSession, key: str) -> None:
    row = await session.get(AppSetting, key)
    if row is not None:
        await session.delete(row)
        await session.flush()


def combo_key(dimensions: list[str]) -> str:
    """Human-readable identifier for a dimension combination."""
    return "+".join(dimensions) if dimensions else "overall"


def validate_combos(combos: list[list[str]]) -> None:
    """Raise ``ValueError`` when a combo list cannot be fetched within limits."""
    if len(combos) > 10:
        raise ValueError("At most 10 dimension combinations (Clarity allows 10 requests/day).")
    seen: set[str] = set()
    for combo in combos:
        if len(combo) > 3:
            raise ValueError("Each combination may use at most 3 dimensions.")
        if len(set(combo)) != len(combo):
            raise ValueError("A combination cannot repeat a dimension.")
        for dim in combo:
            if dim not in ALLOWED_DIMENSIONS:
                raise ValueError(
                    f"Unknown dimension '{dim}'. Allowed: {', '.join(ALLOWED_DIMENSIONS)}."
                )
        key = combo_key(combo)
        if key in seen:
            raise ValueError(f"Duplicate combination '{key}'.")
        seen.add(key)


@dataclass(frozen=True)
class ClarityConfig:
    """Decrypted, ready-to-use Clarity settings."""

    token: str | None
    project_id: str | None
    fetch_time: str  # "HH:MM"
    timezone: str  # IANA name
    dimension_combos: list[list[str]]


async def get_clarity_config(session: AsyncSession) -> ClarityConfig:
    token_encrypted = await get_setting(session, KEY_CLARITY_TOKEN)
    token: str | None = None
    if token_encrypted:
        try:
            token = decrypt_secret(str(token_encrypted))
        except SecretCryptoError:
            token = None

    combos = await get_setting(session, KEY_CLARITY_COMBOS)
    if not isinstance(combos, list) or not combos:
        combos = DEFAULT_DIMENSION_COMBOS

    return ClarityConfig(
        token=token,
        project_id=await get_setting(session, KEY_CLARITY_PROJECT_ID),
        fetch_time=str(await get_setting(session, KEY_CLARITY_FETCH_TIME) or DEFAULT_FETCH_TIME),
        timezone=str(await get_setting(session, KEY_CLARITY_TIMEZONE) or DEFAULT_TIMEZONE),
        dimension_combos=[list(c) for c in combos],
    )
