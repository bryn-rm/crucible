"""Shared base for LLM-backed negotiation agents (Phase 2).

Every provider (Claude, OpenAI, ...) plays the negotiation environment the
same way: build the same system prompt from the agent's strategy, hand the
observation to the model, stream reasoning text live via `on_chunk`, then
parse a trailing JSON action from the response. That shared shape lives here
once; a subclass only implements `_stream_reasoning` against its own
provider's SDK. Malformed JSON or an illegal-in-context action surfaces as a
ValueError, which the orchestrator's retry/forfeit loop already handles —
subclasses never need their own retry logic.
"""

from __future__ import annotations

import json
from abc import abstractmethod
from collections.abc import Awaitable, Callable

from app.contract.interfaces import Action, Agent, Observation

SYSTEM_PROMPT_TEMPLATE = """You are {label}, an agent negotiating in a multi-issue bargaining game.

Strategy: {strategy_prompt}

Two agents divide a pool of items. You have private per-item valuations; the
other agent's valuations are unknown to you. You alternate making offers
until one side accepts or the round limit is reached. On acceptance, you
score your own valuation of the share you end up with; if no agreement is
reached by the round limit, you score 0.

Briefly reason about the standing offer and your strategy, then end your
response with exactly one JSON object on its own line describing your
action, and nothing after it. Valid actions:
- {{"type": "offer", "split": {{"<item>": <quantity you keep for yourself>, ...}}}}
- {{"type": "accept"}}
- {{"type": "walk"}}
"""

class LLMNegotiationAgent(Agent):
    """Base class for LLM-backed negotiation agents. Not provider-specific."""

    async def act(
        self,
        observation: Observation,
        on_chunk: Callable[[str], Awaitable[None]] | None = None,
    ) -> Action:
        system = SYSTEM_PROMPT_TEMPLATE.format(
            label=self.config.label, strategy_prompt=self.config.strategy_prompt
        )
        full_text = await self._stream_reasoning(system, _build_user_message(observation), on_chunk)
        return _parse_action(full_text)

    @abstractmethod
    async def _stream_reasoning(
        self,
        system: str,
        user_message: str,
        on_chunk: Callable[[str], Awaitable[None]] | None,
    ) -> str:
        """Call the provider's API, forwarding reasoning text to `on_chunk`
        as it's produced, and return the full concatenated response text."""


def _build_user_message(observation: Observation) -> str:
    message = json.dumps({k: v for k, v in observation.items() if k != "retry_hint"})
    retry_hint = observation.get("retry_hint")
    if retry_hint:
        message += (
            f"\n\nYour previous action was invalid: {retry_hint}. "
            "Respond again with a single valid JSON action."
        )
    return message


def _parse_action(text: str) -> Action:
    decoder = json.JSONDecoder()
    # Prefer the last complete object, while allowing markdown fences or other
    # harmless trailing text after it. raw_decode is linear for each candidate
    # and avoids repeatedly allocating progressively larger suffixes.
    parsed: Action | None = None
    for start, character in enumerate(text):
        if character != "{":
            continue
        try:
            action, _ = decoder.raw_decode(text, start)
        except json.JSONDecodeError:
            continue
        if isinstance(action, dict) and action.get("type") in {
            "offer",
            "accept",
            "walk",
            "say",
            "end_interview",
        }:
            parsed = action
    if parsed is not None:
        return parsed
    raise ValueError(f"no JSON action found in response: {text!r}")
