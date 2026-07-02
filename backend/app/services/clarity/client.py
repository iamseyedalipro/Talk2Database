"""Thin async client for the Microsoft Clarity Data Export API.

One endpoint, Bearer-token auth. Each call counts against Clarity's hard limit
of 10 requests per project per day, so the caller (the fetcher) budgets calls;
this module only performs a single request and maps failures to
:class:`ClarityAPIError`.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import httpx

CLARITY_EXPORT_URL = "https://www.clarity.ms/export-data/api/v1/project-live-insights"

_TIMEOUT_SECONDS = 30.0
# One retry for transient failures only; never for auth or rate-limit errors,
# which would just burn the daily budget.
_RETRYABLE_STATUS = frozenset({500, 502, 503, 504})


class ClarityAPIError(RuntimeError):
    """A Clarity Data Export request failed."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code

    @property
    def is_auth_error(self) -> bool:
        return self.status_code in (401, 403)

    @property
    def is_rate_limited(self) -> bool:
        return self.status_code == 429


def build_params(num_of_days: int, dimensions: Sequence[str]) -> dict[str, str]:
    """Query parameters for one export request (up to 3 dimensions)."""
    if not 1 <= num_of_days <= 3:
        raise ValueError("numOfDays must be 1, 2 or 3")
    if len(dimensions) > 3:
        raise ValueError("Clarity accepts at most 3 dimensions per request")
    params = {"numOfDays": str(num_of_days)}
    for i, dim in enumerate(dimensions, start=1):
        params[f"dimension{i}"] = dim
    return params


async def fetch_insights(
    token: str,
    *,
    num_of_days: int = 1,
    dimensions: Sequence[str] = (),
    transport: httpx.AsyncBaseTransport | None = None,
) -> Any:
    """Fetch aggregated insights; returns the decoded JSON payload.

    ``transport`` is injectable for tests (httpx.MockTransport).
    """
    params = build_params(num_of_days, dimensions)
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

    last_error: ClarityAPIError | None = None
    async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS, transport=transport) as client:
        for _attempt in range(2):
            try:
                response = await client.get(CLARITY_EXPORT_URL, params=params, headers=headers)
            except httpx.HTTPError as exc:
                last_error = ClarityAPIError(f"Clarity request failed: {exc}")
                continue

            if response.status_code == 200:
                try:
                    return response.json()
                except ValueError as exc:
                    raise ClarityAPIError(
                        "Clarity returned a non-JSON response.", status_code=200
                    ) from exc
            if response.status_code in (401, 403):
                raise ClarityAPIError(
                    "Clarity rejected the API token. Generate a new token in the Clarity "
                    "project's Settings > Data Export and save it in the admin panel.",
                    status_code=response.status_code,
                )
            if response.status_code == 429:
                raise ClarityAPIError(
                    "Clarity daily request limit reached (10 requests per project per day). "
                    "Try again after the limit resets.",
                    status_code=429,
                )
            last_error = ClarityAPIError(
                f"Clarity request failed with HTTP {response.status_code}: {response.text[:300]}",
                status_code=response.status_code,
            )
            if response.status_code not in _RETRYABLE_STATUS:
                break

    assert last_error is not None
    raise last_error
