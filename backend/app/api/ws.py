"""Match WebSocket endpoint.

Single-writer discipline (non-negotiable, see build plan "Technical risks"):
every ServerEvent, regardless of which agent task produced it, goes onto one
asyncio.Queue; a single writer task drains the queue and is the only thing
that ever calls websocket.send_*. No concurrent sends from parallel agent
tasks.

Phase 0: the connection accepts and speaks the contract (start_match /
cancel_match in, error out) but does not yet run a real match — that's
Phase 1 (orchestrator) and Phase 2 (LLM agents) wiring in on top of this.
"""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import TypeAdapter, ValidationError

from app.contract.events import ClientEvent, ErrorEvent, ServerEvent

router = APIRouter()
_client_event_adapter: TypeAdapter[ClientEvent] = TypeAdapter(ClientEvent)


async def _writer(websocket: WebSocket, queue: "asyncio.Queue[ServerEvent]") -> None:
    while True:
        event = await queue.get()
        await websocket.send_text(event.model_dump_json())


@router.websocket("/ws/match")
async def match_socket(websocket: WebSocket) -> None:
    await websocket.accept()
    queue: "asyncio.Queue[ServerEvent]" = asyncio.Queue()
    writer_task = asyncio.create_task(_writer(websocket, queue))

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                payload = json.loads(raw)
                event: ClientEvent = _client_event_adapter.validate_python(payload)
            except (json.JSONDecodeError, ValidationError) as exc:
                await queue.put(ErrorEvent(recoverable=True, message=f"bad client event: {exc}"))
                continue

            if event.type == "start_match":
                # Phase 1+: hand off to MatchOrchestrator, forward its events
                # onto `queue`. Stubbed for now.
                await queue.put(
                    ErrorEvent(recoverable=False, message="start_match not yet implemented")
                )
            elif event.type == "cancel_match":
                await queue.put(
                    ErrorEvent(
                        match_id=event.match_id,
                        recoverable=False,
                        message="cancel_match not yet implemented",
                    )
                )
    except WebSocketDisconnect:
        pass
    finally:
        writer_task.cancel()
