"""Environment and Agent interfaces (frozen contract, Phase 0).

Every environment (negotiation, role-play, ...) implements Environment.
Every agent (scripted, Claude-backed, ...) implements Agent. The orchestrator
(app/orchestrator.py) is written against these interfaces only, so a new
environment or agent never touches orchestration code.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentConfig:
    id: str
    label: str
    model: str
    strategy_prompt: str
    temperature: float = 1.0


# State and Observation are intentionally untyped (dict[str, Any]) at the
# interface level: each environment defines its own shape. Environments
# should still keep them JSON-serializable, since state_after_json /
# observation_json persist them verbatim.
State = dict[str, Any]
Observation = dict[str, Any]
Action = dict[str, Any]


@dataclass
class StepResult:
    state: State
    events: list[dict[str, Any]] = field(default_factory=list)


class Environment(ABC):
    """A pluggable match environment (negotiation, role-play, debate, ...)."""

    name: str

    @abstractmethod
    def reset(self, agent_ids: list[str]) -> State:
        """Initialize a new match state for the given agents."""

    @abstractmethod
    def observe(self, state: State, agent_id: str) -> Observation:
        """What `agent_id` sees: private info (e.g. its valuations) + public history."""

    @abstractmethod
    def action_schema(self, agent_id: str) -> type:
        """The pydantic model (or discriminated union) legal actions must validate against."""

    @abstractmethod
    def step(self, state: State, agent_id: str, action: Action) -> StepResult:
        """Apply a validated action, returning the new state and any emitted events."""

    @abstractmethod
    def is_terminal(self, state: State) -> bool:
        """Whether the match has ended (agreement, round limit, etc.)."""

    @abstractmethod
    def score(self, state: State) -> dict[str, float]:
        """Objective payoffs per agent id. Return {} for judge-only environments."""

    @abstractmethod
    def public_view(self, state: State) -> dict[str, Any]:
        """The redacted state safe to stream to viewers. Must never leak private info."""


class Agent(ABC):
    """An agent that observes and acts (scripted, Claude-backed, ...)."""

    def __init__(self, config: AgentConfig) -> None:
        self.config = config

    @property
    def id(self) -> str:
        return self.config.id

    @abstractmethod
    async def act(
        self,
        observation: Observation,
        on_chunk: Callable[[str], Awaitable[None]] | None = None,
    ) -> Action:
        """Produce a structured action for `observation`.

        Implementations that stream reasoning (e.g. an LLM) call `on_chunk`
        with each piece of reasoning text as it's produced, so the caller can
        forward it live rather than waiting for the full response. `on_chunk`
        is optional — the orchestrator always passes one, but implementations
        that don't stream (e.g. a scripted agent) may still call it with their
        full canned reasoning, or not at all.
        """
