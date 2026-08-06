"""Server -> client WebSocket event schema.

This is the frozen contract (see docs/multi_agent_arena_build_plan.md, Phase 0).
Every event the backend emits over the match WebSocket is one of the models
below, discriminated on `type`. Do not change a field's meaning or remove a
field without a coordinated update to frontend/src/contract/events.ts in the
same change.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, Field


class AgentRosterEntry(BaseModel):
    id: str
    label: str
    model: str
    strategy: str


class MatchStarted(BaseModel):
    type: Literal["match_started"] = "match_started"
    match_id: str
    environment: str
    agents: list[AgentRosterEntry]


class TurnStarted(BaseModel):
    type: Literal["turn_started"] = "turn_started"
    match_id: str
    agent_id: str
    turn_no: int


class ReasoningDelta(BaseModel):
    type: Literal["reasoning_delta"] = "reasoning_delta"
    match_id: str
    agent_id: str
    turn_no: int
    chunk: str


class ActionEvent(BaseModel):
    type: Literal["action"] = "action"
    match_id: str
    agent_id: str
    turn_no: int
    action: dict[str, Any]


class StateUpdate(BaseModel):
    type: Literal["state_update"] = "state_update"
    match_id: str
    state: dict[str, Any]


class ScoreUpdate(BaseModel):
    type: Literal["score_update"] = "score_update"
    match_id: str
    scores: dict[str, float]


class MatchEndedReason(BaseModel):
    """Enumerated only by convention; kept as str for forward compatibility."""

    AGREEMENT: Literal["agreement"] = "agreement"
    ROUND_LIMIT: Literal["round_limit"] = "round_limit"
    ERROR: Literal["error"] = "error"
    CANCELLED: Literal["cancelled"] = "cancelled"


class MatchEnded(BaseModel):
    type: Literal["match_ended"] = "match_ended"
    match_id: str
    outcome: str
    final_scores: dict[str, float]
    reason: Literal["agreement", "round_limit", "error", "cancelled"]


class ErrorEvent(BaseModel):
    type: Literal["error"] = "error"
    match_id: str | None = None
    recoverable: bool
    message: str


ServerEvent = Annotated[
    Union[
        MatchStarted,
        TurnStarted,
        ReasoningDelta,
        ActionEvent,
        StateUpdate,
        ScoreUpdate,
        MatchEnded,
        ErrorEvent,
    ],
    Field(discriminator="type"),
]


# --- Client -> server ---


class AgentConfig(BaseModel):
    id: str
    label: str
    model: str
    strategy_prompt: str
    temperature: float = 1.0


class StartMatch(BaseModel):
    type: Literal["start_match"] = "start_match"
    environment: str
    agents: list[AgentConfig]


class CancelMatch(BaseModel):
    type: Literal["cancel_match"] = "cancel_match"
    match_id: str


ClientEvent = Annotated[
    Union[StartMatch, CancelMatch],
    Field(discriminator="type"),
]
