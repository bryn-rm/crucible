"""Scripted (dummy) negotiation agent — Phase 1.

Picks a legal action from the observation and emits a short canned reasoning
stream. Used to prove out the orchestrator loop end-to-end before real LLM
agents (Phase 2) add latency, cost, and nondeterminism. Deterministic given a
seed, so orchestrator tests are reproducible.
"""

from __future__ import annotations

import random
from collections.abc import AsyncIterator

from app.contract.interfaces import Action, Agent, AgentConfig, Observation

ACCEPT_THRESHOLD = 0.5


class ScriptedNegotiationAgent(Agent):
    def __init__(self, config: AgentConfig, seed: int | None = None) -> None:
        super().__init__(config)
        self._rng = random.Random(seed)

    async def act(self, observation: Observation) -> tuple[AsyncIterator[str], Action]:
        action = self._decide(observation)
        return self._stream_reasoning(action), action

    def _decide(self, observation: Observation) -> Action:
        items: dict[str, int] = observation["items"]
        valuation: dict[str, int] = observation["valuation"]
        standing_offer = observation.get("standing_offer")
        turns_taken: int = observation.get("turns_taken", 0)
        max_turns: int = observation.get("max_turns", 10)
        last_turn = turns_taken >= max_turns - 1

        if standing_offer is not None and standing_offer["agent_id"] != self.id:
            my_share = {item: items[item] - standing_offer["split"].get(item, 0) for item in items}
            offer_value = sum(valuation.get(item, 0) * qty for item, qty in my_share.items())
            max_value = sum(valuation.get(item, 0) * qty for item, qty in items.items()) or 1
            if offer_value / max_value >= ACCEPT_THRESHOLD or last_turn:
                return {"type": "accept"}
            if last_turn:
                return {"type": "walk"}

        return {"type": "offer", "split": self._propose_split(items, valuation)}

    def _propose_split(self, items: dict[str, int], valuation: dict[str, int]) -> dict[str, int]:
        return {
            item: qty if valuation.get(item, 0) > 0 else self._rng.randint(0, qty)
            for item, qty in items.items()
        }

    async def _stream_reasoning(self, action: Action) -> AsyncIterator[str]:
        label = self.config.label
        yield f"[{label}] weighing the current offer against my valuations... "
        yield f"[{label}] decided: {action['type']}"
