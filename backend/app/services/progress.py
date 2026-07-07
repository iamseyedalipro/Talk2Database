"""Progress-event plumbing shared by the Ask flow services.

An emitter receives one JSON-serializable event dict per step (each carries a
``type`` key). The WebSocket endpoint forwards events to the browser; the HTTP
endpoint uses the no-op emitter, so services never need to know the transport.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

ProgressEmitter = Callable[[dict[str, Any]], Awaitable[None]]


async def noop_emit(event: dict[str, Any]) -> None:
    return None
