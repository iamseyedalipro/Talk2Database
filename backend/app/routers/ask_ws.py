"""WebSocket transport for Ask: the same flow as ``POST /api/ask``, streamed.

Protocol (JSON messages, discriminated by ``type``):

- client -> server: ``{"type": "start", "token", "connection_id", "question"}``
  (first message; the browser cannot send an Authorization header, so the JWT
  travels here instead of in the URL, keeping it out of access logs), then
  optionally ``{"type": "cancel"}``.
- server -> client: progress events from the flow (``run_started``, ``status``,
  ``tables_directory``, ``tables_requested``, ``table_details_sent``,
  ``assistant_note``, ``exploratory_query``, ``query_result``,
  ``generating_sql``, ``retry``), then exactly one of ``final_result`` (the
  ``AskResponse`` fields), ``error``, or ``cancelled``. Every server event
  carries a monotonically increasing ``seq``.

Cancellation: a ``cancel`` message (or the socket closing) cancels the flow
task; the panel-DB session rolls back, so a cancelled run leaves no history
row. Progress already shown stays client-side.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from typing import Any

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from app.deps import SessionDep, resolve_user_from_token
from app.services.ask_flow import AskFlowError, run_ask_flow

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ask"])

_START_TIMEOUT_S = 10.0

# Application close codes (4000-4999 are free for applications).
_CLOSE_BAD_REQUEST = 4400
_CLOSE_UNAUTHORIZED = 4401
_CLOSE_TIMEOUT = 4408


async def _close(websocket: WebSocket, code: int) -> None:
    with suppress(Exception):
        await websocket.close(code=code)


async def _reject(websocket: WebSocket, code: int, error_code: str, detail: str) -> None:
    with suppress(Exception):
        await websocket.send_json({"type": "error", "code": error_code, "detail": detail})
    await _close(websocket, code)


@router.websocket("/ask/ws")
async def ask_ws(websocket: WebSocket, session: SessionDep) -> None:
    await websocket.accept()

    try:
        async with asyncio.timeout(_START_TIMEOUT_S):
            raw = await websocket.receive_json()
    except TimeoutError:
        await _reject(
            websocket, _CLOSE_TIMEOUT, "timeout", "Expected a 'start' message within 10s."
        )
        return
    except WebSocketDisconnect:
        return
    except ValueError:
        await _reject(websocket, _CLOSE_BAD_REQUEST, "bad_request", "Messages must be JSON.")
        return

    if not isinstance(raw, dict) or raw.get("type") != "start":
        await _reject(
            websocket, _CLOSE_BAD_REQUEST, "bad_request", "The first message must be 'start'."
        )
        return

    question = str(raw.get("question") or "").strip()
    connection_id = raw.get("connection_id")
    if not question or not isinstance(connection_id, int):
        await _reject(
            websocket,
            _CLOSE_BAD_REQUEST,
            "bad_request",
            "'start' requires a non-empty question and an integer connection_id.",
        )
        return

    user = await resolve_user_from_token(session, str(raw.get("token") or ""))
    if user is None:
        await _reject(websocket, _CLOSE_UNAUTHORIZED, "unauthorized", "Not authenticated")
        return

    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

    async def emit(event: dict[str, Any]) -> None:
        await queue.put(event)

    async def forward_events() -> None:
        seq = 0
        while True:
            event = await queue.get()
            if event is None:
                return
            seq += 1
            await websocket.send_json({"seq": seq, **event})

    async def run_flow() -> None:
        """Run the flow; commit on success, roll back on failure.

        Puts the terminal event (``final_result``/``error``) on the queue but
        never the sentinel — the coordinator owns shutdown ordering.
        """
        try:
            outcome = await run_ask_flow(
                session,
                user,
                connection_id=connection_id,
                question=question,
                emit=emit,
            )
        except AskFlowError as exc:
            await session.rollback()
            await queue.put({"type": "error", "code": "ask_failed", "detail": exc.detail})
        except HTTPException as exc:  # load_connector raises 403/404 directly
            await session.rollback()
            await queue.put({"type": "error", "code": "ask_failed", "detail": str(exc.detail)})
        except Exception:
            logger.exception("Unexpected error in the Ask WebSocket flow")
            await session.rollback()
            await queue.put(
                {"type": "error", "code": "internal", "detail": "Unexpected server error."}
            )
        else:
            await session.commit()
            await queue.put({"type": "final_result", **outcome.response.model_dump()})

    async def watch_client() -> str:
        """Return 'cancel' on a cancel message, 'disconnect' when the socket dies."""
        while True:
            try:
                message = await websocket.receive_json()
            except WebSocketDisconnect:
                return "disconnect"
            except ValueError:
                continue  # ignore non-JSON frames
            except Exception:
                return "disconnect"
            if isinstance(message, dict) and message.get("type") == "cancel":
                return "cancel"

    sender = asyncio.create_task(forward_events())
    flow = asyncio.create_task(run_flow())
    watcher = asyncio.create_task(watch_client())

    try:
        done, _ = await asyncio.wait({flow, watcher}, return_when=asyncio.FIRST_COMPLETED)

        if flow in done:
            await queue.put(None)
        else:
            # The client cancelled or went away: stop the flow mid-step and
            # make sure nothing it did reaches the panel DB.
            flow.cancel()
            with suppress(asyncio.CancelledError):
                await flow
            with suppress(Exception):
                await session.rollback()
            if watcher.result() == "cancel":
                await queue.put({"type": "cancelled"})
            await queue.put(None)

        with suppress(Exception):
            await sender  # drain remaining events; exits on the sentinel
    finally:
        for task in (sender, flow, watcher):
            task.cancel()
            with suppress(BaseException):
                await task
        await _close(websocket, 1000)
