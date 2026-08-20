"""REST response DTOs for match history, replay, and the leaderboard (Phase 4).

These are ordinary REST response shapes, not part of the frozen WS contract
in app/contract/ — there is no TypeScript mirror requirement for them, though
frontend/src/api/types.ts hand-mirrors them for convenience.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class MatchAgentOut(BaseModel):
    agent_id: str
    label: str
    model: str
    strategy: str
    final_score: float | None


class MatchSummary(BaseModel):
    id: str
    environment: str
    status: str
    created_at: datetime
    ended_at: datetime | None
    outcome: str | None
    reason: str | None
    agents: list[MatchAgentOut]


class TurnOut(BaseModel):
    turn_no: int
    agent_id: str
    reasoning_text: str
    action_json: dict[str, Any]
    state_after_json: dict[str, Any]
    latency_ms: int | None


class ScoreOut(BaseModel):
    agent_id: str
    dimension: str
    value: float


class MatchDetail(MatchSummary):
    turns: list[TurnOut]
    scores: list[ScoreOut]


class LeaderboardEntry(BaseModel):
    key: str
    matches: int
    wins: int
    draws: int
    win_rate: float
    mean_payoff: float


class LeaderboardResponse(BaseModel):
    by_model: list[LeaderboardEntry]
    by_strategy: list[LeaderboardEntry]
