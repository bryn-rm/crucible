"""Match WebSocket endpoint.

Single-writer discipline (non-negotiable, see build plan "Technical risks"):
every ServerEvent, regardless of which agent task produced it, goes onto one
asyncio.Queue; a single writer task drains the queue and is the only thing
that ever calls websocket.send_*. No concurrent sends from parallel agent
tasks. `start_match` spawns the orchestrator's `run()` as a background task
that only ever *puts* onto that queue; it never touches the socket directly.

Phase 2: which Agent implementation backs each requested `model` (Claude,
OpenAI, or the explicitly requested scripted implementation) is resolved per-agent by
app.agents.registry.make_negotiation_agent, keyed on model name and which
provider API keys are configured — without changing this wiring.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import TypeAdapter, ValidationError
from sqlmodel import Session

from app.agents.registry import make_agent
from app.contract.events import AgentConfig as ClientAgentConfig
from app.contract.events import ClientEvent, ErrorEvent, ServerEvent
from app.contract.interfaces import Agent
from app.contract.interfaces import AgentConfig as EnvAgentConfig
from app.db import engine
from app.environments.registry import get_environment
from app.orchestrator import MatchOrchestrator
from app.security import configured_origins, token_is_valid

router = APIRouter()
_client_event_adapter: TypeAdapter[ClientEvent] = TypeAdapter(ClientEvent)
logger = logging.getLogger(__name__)
MAX_CONCURRENT_MATCHES = int(os.environ.get("MAX_CONCURRENT_MATCHES_PER_SOCKET", "2"))
MAX_TOTAL_MATCHES = int(os.environ.get("MAX_TOTAL_MATCHES_PER_SOCKET", "20"))


def _make_agent(cfg: ClientAgentConfig, environment: str) -> Agent:
    agent_config = EnvAgentConfig(
        id=cfg.id,
        label=cfg.label,
        model=cfg.model,
        strategy_prompt=cfg.strategy_prompt,
        temperature=cfg.temperature,
    )
    return make_agent(agent_config, environment)


async def _writer(websocket: WebSocket, queue: "asyncio.Queue[ServerEvent]") -> None:
    try:
        while True:
            event = await queue.get()
            await websocket.send_text(event.model_dump_json())
    except asyncio.CancelledError:
        raise
    except (WebSocketDisconnect, RuntimeError) as exc:
        logger.warning("WebSocket writer stopped: %s", exc)
    except Exception:
        logger.exception("WebSocket writer failed")
    finally:
        try:
            await websocket.close()
        except Exception:  # socket may already be closed
            pass


async def _run_match(
    match_id: str,
    environment: str,
    agent_configs: list[ClientAgentConfig],
    queue: "asyncio.Queue[ServerEvent]",
) -> None:
    started_at = time.monotonic()
    try:
        env = get_environment(environment)
        agents = [_make_agent(cfg, environment) for cfg in agent_configs]
        orchestrator = MatchOrchestrator(environment=env, agents=agents)
        with Session(engine) as session:
            async for event in orchestrator.run(match_id, session=session):
                await queue.put(event)
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001 - a bad match must not crash the socket
        logger.exception("Match %s failed", match_id)
        await queue.put(ErrorEvent(match_id=match_id, recoverable=False, message=str(exc)))
    finally:
        logger.info(
            "Match task %s ended duration_ms=%d",
            match_id,
            int((time.monotonic() - started_at) * 1000),
        )


@router.websocket("/ws/match")
async def match_socket(websocket: WebSocket) -> None:
    origin = websocket.headers.get("origin")
    if origin not in configured_origins():
        logger.warning("Rejected WebSocket origin %r", origin)
        await websocket.close(code=1008, reason="origin not allowed")
        return
    if not os.environ.get("ARENA_API_TOKEN"):
        logger.error("Rejected WebSocket because ARENA_API_TOKEN is not configured")
        await websocket.close(code=1011, reason="server authentication is not configured")
        return
    if not token_is_valid(websocket.query_params.get("token")):
        logger.warning("Rejected unauthenticated WebSocket")
        await websocket.close(code=1008, reason="invalid arena token")
        return

    await websocket.accept()
    queue: "asyncio.Queue[ServerEvent]" = asyncio.Queue()
    writer_task = asyncio.create_task(_writer(websocket, queue))
    match_tasks: dict[str, asyncio.Task] = {}
    total_matches = 0

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
                active_matches = sum(not task.done() for task in match_tasks.values())
                if active_matches >= MAX_CONCURRENT_MATCHES:
                    await queue.put(
                        ErrorEvent(recoverable=True, message="concurrent match limit reached")
                    )
                    continue
                if total_matches >= MAX_TOTAL_MATCHES:
                    await queue.put(ErrorEvent(recoverable=False, message="match limit reached"))
                    continue
                match_id = str(uuid.uuid4())
                total_matches += 1
                task = asyncio.create_task(
                    _run_match(match_id, event.environment, event.agents, queue)
                )
                match_tasks[match_id] = task
                task.add_done_callback(lambda _task, mid=match_id: match_tasks.pop(mid, None))
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
        tasks = list(match_tasks.values())
        for task in tasks:
            task.cancel()
        writer_task.cancel()
        await asyncio.gather(*tasks, writer_task, return_exceptions=True)
