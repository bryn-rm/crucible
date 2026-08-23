import asyncio
from collections.abc import Awaitable, Callable

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

    async def act(
        self,
        observation: Observation,
        on_chunk: Callable[[str], Awaitable[None]] | None = None,
    ) -> Action:
        if on_chunk is not None:
            await on_chunk("I have no idea what I'm doing")
        return {"type": "not_a_real_action"}


class SlowAgent(Agent):
    """Blocks until cancelled, to exercise the cancel-in-flight-act path."""

    async def act(
        self,
        observation: Observation,
        on_chunk: Callable[[str], Awaitable[None]] | None = None,
    ) -> Action:
        if on_chunk is not None:
            await on_chunk("thinking forever...")
        await asyncio.sleep(3600)
        raise AssertionError("should have been cancelled before waking up")


class RetryAgent(Agent):
    """Returns an invalid action once, then a valid action with distinct reasoning."""

    def __init__(self, config: AgentConfig) -> None:
        super().__init__(config)
        self.attempts = 0

    async def act(
        self,
        observation: Observation,
        on_chunk: Callable[[str], Awaitable[None]] | None = None,
    ) -> Action:
        self.attempts += 1
        reasoning = f"attempt {self.attempts};"
        if on_chunk is not None:
            await on_chunk(reasoning)
        if self.attempts == 1:
            return {"type": "not_a_real_action"}
        return {"type": "offer", "split": {item: 0 for item in observation["items"]}}


class ProviderFailureAgent(Agent):
    """Raises like an unavailable provider, to exercise retry/forfeit."""

    def __init__(self, config: AgentConfig) -> None:
        super().__init__(config)
        self.attempts = 0

    async def act(
        self,
        observation: Observation,
        on_chunk: Callable[[str], Awaitable[None]] | None = None,
    ) -> Action:
        self.attempts += 1
        raise ConnectionError("provider connection failed")


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


@pytest.mark.asyncio
async def test_provider_failure_retries_then_forfeits_and_match_completes():
    env = NegotiationEnvironment(seed=3, max_turns=1)
    failing_agent = ProviderFailureAgent(
        AgentConfig(id="agent_a", label="Unavailable", model="provider", strategy_prompt="x")
    )
    orchestrator = MatchOrchestrator(environment=env, agents=[failing_agent, make_agents()[1]])

    events = [event async for event in orchestrator.run("match-provider-failure")]

    assert failing_agent.attempts == 2
    error = next(event for event in events if event.type == "error")
    assert "provider unavailable (ConnectionError)" in error.message
    assert events[-1].type == "match_ended"


@pytest.mark.asyncio
async def test_persists_reasoning_from_all_retry_attempts():
    env = NegotiationEnvironment(seed=3, max_turns=1)
    retry_agent = RetryAgent(
        AgentConfig(id="agent_a", label="Retry", model="scripted", strategy_prompt="x")
    )
    orchestrator = MatchOrchestrator(environment=env, agents=[retry_agent, make_agents()[1]])

    with in_memory_session() as session:
        events = [event async for event in orchestrator.run("match-retry", session=session)]

        turn = session.exec(select(Turn).where(Turn.match_id == "match-retry")).one()
        streamed = "".join(event.chunk for event in events if event.type == "reasoning_delta")
        assert turn.reasoning_text == "attempt 1;attempt 2;"
        assert turn.reasoning_text == streamed


@pytest.mark.asyncio
async def test_cancelling_the_match_cancels_an_in_flight_act():
    env = NegotiationEnvironment(seed=1, max_turns=10)
    slow_agent = SlowAgent(
        AgentConfig(id="agent_a", label="Slow", model="scripted", strategy_prompt="x")
    )
    agents = [slow_agent, make_agents()[1]]
    orchestrator = MatchOrchestrator(environment=env, agents=agents)

    async def drain() -> None:
        async for _ in orchestrator.run("match-4"):
            pass

    task = asyncio.create_task(drain())
    await asyncio.sleep(0.2)  # let it reach the blocked agent.act() call
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=1)
