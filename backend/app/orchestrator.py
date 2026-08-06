"""Match orchestrator (Phase 1).

Runs a single match: reset env -> loop turns -> for the active agent,
observe -> agent.act -> validate action -> env.step -> emit events ->
check terminal -> score. Emits ServerEvent instances; the caller (the
WebSocket handler) is responsible for the single-writer queue that
serializes them onto the socket.

Left as a stub until Phase 1: this is where turn order, round limits, and
malformed-action retry/forfeit get implemented, against dummy agents first.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from app.contract.events import ServerEvent
from app.contract.interfaces import Agent, Environment


class MatchOrchestrator:
    def __init__(self, environment: Environment, agents: list[Agent], max_rounds: int = 20) -> None:
        self.environment = environment
        self.agents = agents
        self.max_rounds = max_rounds

    async def run(self, match_id: str) -> AsyncIterator[ServerEvent]:
        raise NotImplementedError("Phase 1: implement the turn loop against a scripted agent first.")
        yield  # pragma: no cover - makes this an async generator
