"""Persistence models (frozen contract, Phase 0).

SQLModel tables for matches, their agents, per-turn trajectory, and scores.
One SQLite file, no infra. See docs/multi_agent_arena_build_plan.md Phase 0
for the spec these mirror.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Optional

from sqlmodel import JSON, Column, Field, SQLModel


def _uuid() -> str:
    import uuid

    return str(uuid.uuid4())


class Match(SQLModel, table=True):
    __tablename__ = "matches"

    id: str = Field(default_factory=_uuid, primary_key=True)
    environment: str
    status: str = Field(default="pending", index=True)  # pending | running | completed | error | cancelled
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    ended_at: Optional[datetime] = None
    outcome: Optional[str] = None
    reason: Optional[str] = None  # agreement | completed | round_limit | error | cancelled


class MatchAgent(SQLModel, table=True):
    __tablename__ = "match_agents"

    id: str = Field(default_factory=_uuid, primary_key=True)
    match_id: str = Field(foreign_key="matches.id", index=True)
    agent_id: str  # the agent's id within the match (e.g. "agent_a")
    label: str
    model: str
    strategy: str
    final_score: Optional[float] = None


class Turn(SQLModel, table=True):
    __tablename__ = "turns"

    id: str = Field(default_factory=_uuid, primary_key=True)
    match_id: str = Field(foreign_key="matches.id", index=True)
    agent_id: str
    turn_no: int
    observation_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    reasoning_text: str = Field(default="")
    action_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    state_after_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    latency_ms: Optional[int] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Score(SQLModel, table=True):
    """Objective payoffs (Phase 1+) and judge-rubric dimensions (Phase 4)."""

    __tablename__ = "scores"

    id: str = Field(default_factory=_uuid, primary_key=True)
    match_id: str = Field(foreign_key="matches.id", index=True)
    agent_id: str
    dimension: str  # e.g. "payoff", "toughness", "fairness", "probing_quality"
    value: float


class Tournament(SQLModel, table=True):
    __tablename__ = "tournaments"

    id: str = Field(default_factory=_uuid, primary_key=True)
    requested: int
    concurrency: int
    status: str = Field(default="running", index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), index=True)
    ended_at: Optional[datetime] = None


class TournamentResult(SQLModel, table=True):
    __tablename__ = "tournament_results"

    id: str = Field(default_factory=_uuid, primary_key=True)
    tournament_id: str = Field(foreign_key="tournaments.id", index=True)
    position: int
    result_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
