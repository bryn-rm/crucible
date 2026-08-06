"""Frozen contract: event schema, action schemas, Environment/Agent interfaces, DB models.

Everything in this package is the Phase 0 deliverable from
docs/multi_agent_arena_build_plan.md. Changing it is a deliberate, coordinated
act — update the TypeScript mirror in frontend/src/contract/ in the same change.
"""

from app.contract.events import ClientEvent, ServerEvent
from app.contract.interfaces import Agent, AgentConfig, Environment
from app.contract.models import Match, MatchAgent, Score, Turn

__all__ = [
    "ServerEvent",
    "ClientEvent",
    "Environment",
    "Agent",
    "AgentConfig",
    "Match",
    "MatchAgent",
    "Turn",
    "Score",
]
