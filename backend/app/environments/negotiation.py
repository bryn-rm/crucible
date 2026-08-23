"""Multi-issue negotiation environment (Phase 1 flagship, see build plan).

Two agents divide a fixed item pool. Each has private per-item valuations;
they alternate offers over a turn cap. Accepting the standing offer scores
each agent's valuation of the share they end up with; no agreement scores 0.
"""

from __future__ import annotations

import copy
import random
from typing import Any

from app.contract.actions import NegotiationAction
from app.contract.interfaces import Action, Environment, Observation, State, StepResult

DEFAULT_ITEMS: dict[str, int] = {"books": 3, "hats": 2, "balls": 1}
DEFAULT_MAX_TURNS = 10
VALUATION_TOTAL = 100


def _generate_valuations(
    items: dict[str, int], agent_ids: list[str], rng: random.Random
) -> dict[str, dict[str, int]]:
    valuations: dict[str, dict[str, int]] = {}
    item_names = list(items)
    for agent_id in agent_ids:
        weights = [rng.random() for _ in item_names]
        weight_sum = sum(weights)
        remaining = VALUATION_TOTAL
        per_unit: dict[str, int] = {}
        for i, item in enumerate(item_names):
            qty = items[item]
            if i == len(item_names) - 1:
                item_total = remaining
            else:
                item_total = round(VALUATION_TOTAL * weights[i] / weight_sum)
                remaining -= item_total
            per_unit[item] = item_total // qty if qty else 0
        valuations[agent_id] = per_unit
    return valuations


class NegotiationEnvironment(Environment):
    name = "negotiation"

    def __init__(
        self,
        items: dict[str, int] | None = None,
        max_turns: int = DEFAULT_MAX_TURNS,
        seed: int | None = None,
    ) -> None:
        self.items = dict(items or DEFAULT_ITEMS)
        self.max_turns = max_turns
        self._rng = random.Random(seed)

    def reset(self, agent_ids: list[str]) -> State:
        if len(agent_ids) != 2:
            raise ValueError(f"negotiation requires exactly 2 agents, got {len(agent_ids)}")
        return {
            "agent_ids": list(agent_ids),
            "items": dict(self.items),
            "valuations": _generate_valuations(self.items, agent_ids, self._rng),
            "history": [],
            "standing_offer": None,
            "status": "open",
            "allocations": None,
            "max_turns": self.max_turns,
        }

    def observe(self, state: State, agent_id: str) -> Observation:
        return {
            "items": dict(state["items"]),
            "valuation": dict(state["valuations"][agent_id]),
            "history": list(state["history"]),
            "standing_offer": state["standing_offer"],
            "turns_taken": len(state["history"]),
            "max_turns": state["max_turns"],
        }

    def action_schema(self, agent_id: str) -> type:
        return NegotiationAction

    def step(self, state: State, agent_id: str, action: Action) -> StepResult:
        new_state = copy.deepcopy(state)
        items = new_state["items"]
        atype = action["type"]

        if atype == "offer":
            split = action["split"]
            for item, qty in split.items():
                if item not in items:
                    raise ValueError(f"offer references unknown item {item!r}")
                if not (0 <= qty <= items[item]):
                    raise ValueError(f"offer for {item!r} out of range 0..{items[item]}")
            # Missing items mean the offerer requests zero of that item. Store a
            # complete split so accepted allocations are always safe to score.
            normalized_split = {item: split.get(item, 0) for item in items}
            new_state["standing_offer"] = {"agent_id": agent_id, "split": normalized_split}

        elif atype == "accept":
            offer = new_state["standing_offer"]
            if offer is None:
                raise ValueError("no standing offer to accept")
            if offer["agent_id"] == agent_id:
                raise ValueError("cannot accept your own offer")
            offering_agent = offer["agent_id"]
            offering_share = offer["split"]
            accepting_share = {item: items[item] - offering_share.get(item, 0) for item in items}
            new_state["allocations"] = {offering_agent: offering_share, agent_id: accepting_share}
            new_state["status"] = "agreement"

        elif atype == "walk":
            new_state["status"] = "walked"

        else:
            raise ValueError(f"unknown action type {atype!r}")

        new_state["history"].append(
            {"turn_no": len(state["history"]) + 1, "agent_id": agent_id, "action": action}
        )
        return StepResult(state=new_state)

    def is_terminal(self, state: State) -> bool:
        return state["status"] != "open" or len(state["history"]) >= state["max_turns"]

    def score(self, state: State) -> dict[str, float]:
        if state["status"] == "agreement":
            allocations = state["allocations"]
            valuations = state["valuations"]
            return {
                agent_id: float(
                    sum(valuations[agent_id][item] * allocations[agent_id][item] for item in state["items"])
                )
                for agent_id in state["agent_ids"]
            }
        return {agent_id: 0.0 for agent_id in state["agent_ids"]}

    def public_view(self, state: State) -> dict[str, Any]:
        return {
            "items": dict(state["items"]),
            "history": list(state["history"]),
            "standing_offer": state["standing_offer"],
            "status": state["status"],
            "allocations": state["allocations"],
            "turns_taken": len(state["history"]),
            "max_turns": state["max_turns"],
        }
