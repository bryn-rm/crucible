"""Match WebSocket endpoint.

Single-writer discipline (non-negotiable, see build plan "Technical risks"):
every ServerEvent, regardless of which agent task produced it, goes onto one
asyncio.Queue; a single writer task drains the queue and is the only thing
that ever calls websocket.send_*. No concurrent sends from parallel agent
tasks. `start_match` spawns the orchestrator's `run()` as a background task
that only ever *puts* onto that queue; it never touches the socket directly.

Phase 1: agents are always the scripted/dummy negotiation agent regardless of
the requested `model` — Phase 2 swaps in the Claude-backed agent once an env
var is set, without changing this wiring.
"""

from __future__ import annotations

import asyncio
import json
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import TypeAdapter, ValidationError
from sqlmodel import Session

from app.agents.scripted import ScriptedNegotiationAgent
from app.contract.events import AgentConfig as ClientAgentConfig
from app.contract.events import ClientEvent, ErrorEvent, ServerEvent
from app.contract.interfaces import AgentConfig as EnvAgentConfig
from app.db import engine
from app.environments.registry import get_environment
from app.orchestrator import MatchOrchestrator

router = APIRouter()
_client_event_adapter: TypeAdapter[ClientEvent] = TypeAdapter(ClientEvent)


async def _writer(websocket: WebSocket, queue: "asyncio.Queue[ServerEvent]") -> None:
    while True:
        event = await queue.get()
        await websocket.send_text(event.model_dump_json())


async def _run_match(
    match_id: str,
    environment: str,
    agent_configs: list[ClientAgentConfig],
    queue: "asyncio.Queue[ServerEvent]",
) -> None:
    try:
        env = get_environment(environment)
        agents = [
            ScriptedNegotiationAgent(
                EnvAgentConfig(
                    id=cfg.id,
                    label=cfg.label,
                    model=cfg.model,
                    strategy_prompt=cfg.strategy_prompt,
                    temperature=cfg.temperature,
                )
            )
            for cfg in agent_configs
        ]
        orchestrator = MatchOrchestrator(environment=env, agents=agents)
        with Session(engine) as session:
            async for event in orchestrator.run(match_id, session=session):
                await queue.put(event)
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001 - a bad match must not crash the socket
        await queue.put(ErrorEvent(match_id=match_id, recoverable=False, message=str(exc)))


@router.websocket("/ws/match")
async def match_socket(websocket: WebSocket) -> None:
    await websocket.accept()
    queue: "asyncio.Queue[ServerEvent]" = asyncio.Queue()
    writer_task = asyncio.create_task(_writer(websocket, queue))
    match_tasks: dict[str, asyncio.Task] = {}

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
                match_id = str(uuid.uuid4())
                match_tasks[match_id] = asyncio.create_task(
                    _run_match(match_id, event.environment, event.agents, queue)
                )
            elif event.type == "cancel_match":
                task = match_tasks.pop(event.match_id, None)
                if task is not None:
                    task.cancel()
                    await queue.put(
                        ErrorEvent(match_id=event.match_id, recoverable=False, message="cancelled")
                    )
                else:
                    await queue.put(
                        ErrorEvent(
                            match_id=event.match_id, recoverable=True, message="unknown match_id"
                        )
                    )
    except WebSocketDisconnect:
        pass
    finally:
        for task in match_tasks.values():
            task.cancel()
        writer_task.cancel()
