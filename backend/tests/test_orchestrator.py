from collections.abc import AsyncIterator

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.agents.scripted import ScriptedNegotiationAgent
from app.contract import models  # noqa: F401 - registers tables on SQLModel.metadata
from app.contract.interfaces import Action, Agent, AgentConfig, Observation
from app.contract.models import Match, Score, Turn
from app.environments.negotiation import NegotiationEnvironment
from app.orchestrator import MatchOrchestrator


def make_agents(seed_a: int = 1, seed_b: int = 2) -> list[Agent]:
    return [
        ScriptedNegotiationAgent(
            AgentConfig(id="agent_a", label="Alice", model="scripted", strategy_prompt="greedy"),
            seed=seed_a,
        ),
        ScriptedNegotiationAgent(
            AgentConfig(id="agent_b", label="Bob", model="scripted", strategy_prompt="greedy"),
            seed=seed_b,
        ),
    ]


class BrokenAgent(Agent):
    """Always returns a schema-invalid action, to exercise retry/forfeit."""

    async def act(self, observation: Observation) -> tuple[AsyncIterator[str], Action]:
        return self._stream(), {"type": "not_a_real_action"}

    async def _stream(self) -> AsyncIterator[str]:
        yield "I have no idea what I'm doing"


def in_memory_session() -> Session:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    return Session(engine)


@pytest.mark.asyncio
async def test_full_match_reaches_match_ended():
    env = NegotiationEnvironment(seed=7, max_turns=10)
    orchestrator = MatchOrchestrator(environment=env, agents=make_agents())

    events = [event async for event in orchestrator.run("match-1")]

    assert events[0].type == "match_started"
    assert events[-1].type == "match_ended"
    assert events[-1].reason in {"agreement", "round_limit"}
    assert set(events[-1].final_scores) == {"agent_a", "agent_b"}
    assert any(e.type == "reasoning_delta" for e in events)
    assert any(e.type == "action" for e in events)


@pytest.mark.asyncio
async def test_persists_full_trajectory():
    env = NegotiationEnvironment(seed=7, max_turns=10)
    orchestrator = MatchOrchestrator(environment=env, agents=make_agents())

    with in_memory_session() as session:
        events = [event async for event in orchestrator.run("match-2", session=session)]
        turn_events = [e for e in events if e.type == "action"]

        match = session.get(Match, "match-2")
        assert match is not None
        assert match.status == "completed"
        assert match.ended_at is not None

        turns = session.exec(select(Turn).where(Turn.match_id == "match-2")).all()
        assert len(turns) == len(turn_events)
        assert all(t.action_json for t in turns)

        scores = session.exec(select(Score).where(Score.match_id == "match-2")).all()
        assert {s.agent_id for s in scores} == {"agent_a", "agent_b"}
        assert all(s.dimension == "payoff" for s in scores)


@pytest.mark.asyncio
async def test_malformed_action_forfeits_and_match_still_completes():
    env = NegotiationEnvironment(seed=3, max_turns=100)
    agents = [
        BrokenAgent(AgentConfig(id="agent_a", label="Broken", model="scripted", strategy_prompt="x")),
        make_agents()[1],
    ]
    orchestrator = MatchOrchestrator(environment=env, agents=agents, max_rounds=6)

    events = [event async for event in orchestrator.run("match-3")]

    forfeits = [e for e in events if e.type == "error" and "forfeited" in e.message]
    assert forfeits, "expected at least one forfeited-turn error event"
    assert events[-1].type == "match_ended"
