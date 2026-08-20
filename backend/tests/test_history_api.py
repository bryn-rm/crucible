import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.agents.scripted import ScriptedNegotiationAgent
from app.contract.interfaces import AgentConfig
from app.db import engine
from app.environments.negotiation import NegotiationEnvironment
from app.main import app
from app.orchestrator import MatchOrchestrator


def make_agents() -> list[ScriptedNegotiationAgent]:
    return [
        ScriptedNegotiationAgent(
            AgentConfig(id="agent_a", label="Alice", model="scripted", strategy_prompt="greedy"),
            seed=1,
        ),
        ScriptedNegotiationAgent(
            AgentConfig(id="agent_b", label="Bob", model="scripted", strategy_prompt="cautious"),
            seed=2,
        ),
    ]


async def run_and_persist(match_id: str, seed: int = 7) -> None:
    env = NegotiationEnvironment(seed=seed, max_turns=10)
    orchestrator = MatchOrchestrator(environment=env, agents=make_agents())
    with Session(engine) as session:
        async for _ in orchestrator.run(match_id, session=session):
            pass


@pytest.mark.asyncio
async def test_list_matches_returns_newest_first():
    await run_and_persist("match-old")
    await run_and_persist("match-new")

    with TestClient(app) as client:
        resp = client.get("/api/matches")

    assert resp.status_code == 200
    body = resp.json()
    assert [m["id"] for m in body] == ["match-new", "match-old"]
    assert body[0]["status"] == "completed"
    assert {a["agent_id"] for a in body[0]["agents"]} == {"agent_a", "agent_b"}


@pytest.mark.asyncio
async def test_list_matches_respects_limit_and_offset():
    for i in range(3):
        await run_and_persist(f"match-{i}", seed=i)

    with TestClient(app) as client:
        first_page = client.get("/api/matches", params={"limit": 2}).json()
        second_page = client.get("/api/matches", params={"limit": 2, "offset": 2}).json()

    assert len(first_page) == 2
    assert len(second_page) == 1
    assert {m["id"] for m in first_page} | {m["id"] for m in second_page} == {
        "match-0",
        "match-1",
        "match-2",
    }


@pytest.mark.asyncio
async def test_get_match_returns_turns_and_scores_for_replay():
    await run_and_persist("match-detail")

    with TestClient(app) as client:
        resp = client.get("/api/matches/match-detail")

    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == "match-detail"
    assert len(body["turns"]) > 0
    assert body["turns"] == sorted(body["turns"], key=lambda t: t["turn_no"])
    assert {s["dimension"] for s in body["scores"]} == {"payoff"}


def test_get_match_404_for_unknown_id():
    with TestClient(app) as client:
        resp = client.get("/api/matches/does-not-exist")

    assert resp.status_code == 404
