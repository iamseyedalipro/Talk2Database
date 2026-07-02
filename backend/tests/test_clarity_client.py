"""Tests for the Clarity Data Export client (no network: httpx.MockTransport)."""

from __future__ import annotations

import httpx
import pytest
from app.services.clarity.client import ClarityAPIError, build_params, fetch_insights


def test_build_params_no_dimensions() -> None:
    assert build_params(1, ()) == {"numOfDays": "1"}


def test_build_params_with_dimensions() -> None:
    assert build_params(3, ("URL", "Device")) == {
        "numOfDays": "3",
        "dimension1": "URL",
        "dimension2": "Device",
    }


def test_build_params_rejects_bad_inputs() -> None:
    with pytest.raises(ValueError):
        build_params(0, ())
    with pytest.raises(ValueError):
        build_params(4, ())
    with pytest.raises(ValueError):
        build_params(1, ("a", "b", "c", "d"))


@pytest.mark.asyncio
async def test_fetch_insights_success_sends_token_and_params() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers["Authorization"]
        seen["url"] = str(request.url)
        return httpx.Response(200, json=[{"metricName": "Traffic"}])

    payload = await fetch_insights(
        "tok",
        dimensions=("URL",),
        transport=httpx.MockTransport(handler),
    )
    assert payload == [{"metricName": "Traffic"}]
    assert seen["auth"] == "Bearer tok"
    assert "numOfDays=1" in seen["url"]
    assert "dimension1=URL" in seen["url"]


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [401, 403])
async def test_fetch_insights_auth_error_is_fatal_and_not_retried(status: int) -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(status)

    with pytest.raises(ClarityAPIError) as excinfo:
        await fetch_insights("bad", transport=httpx.MockTransport(handler))
    assert excinfo.value.status_code == status
    assert excinfo.value.is_auth_error
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_fetch_insights_rate_limit_maps_to_429() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429)

    with pytest.raises(ClarityAPIError) as excinfo:
        await fetch_insights("tok", transport=httpx.MockTransport(handler))
    assert excinfo.value.is_rate_limited


@pytest.mark.asyncio
async def test_fetch_insights_retries_5xx_once_then_succeeds() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(503)
        return httpx.Response(200, json={"ok": True})

    payload = await fetch_insights("tok", transport=httpx.MockTransport(handler))
    assert payload == {"ok": True}
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_fetch_insights_gives_up_after_retry() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    with pytest.raises(ClarityAPIError) as excinfo:
        await fetch_insights("tok", transport=httpx.MockTransport(handler))
    assert excinfo.value.status_code == 500
