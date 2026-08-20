import asyncio

import pytest
from fastapi import HTTPException
from sqlmodel import Session, select

from app.contract.events import AgentConfig
from app.api.routes import tournament
from app.api.schemas import TournamentRequest
from app.contract.models import Match
from app.db import engine
from app.tournament import bounded_map, get_tournament, run_tournament, start_tournament


@pytest.mark.asyncio
async def test_bounded_map_never_exceeds_concurrency_limit():
    active = 0
    peak = 0

    async def worker(index: int) -> int:
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.01)
        active -= 1
        return index

    results = await bounded_map(8, 3, worker)

    assert results == list(range(8))
    assert peak == 3


@pytest.mark.asyncio
async def test_scripted_tournament_runs_and_persists_every_match():
    agents = [
        AgentConfig(id="agent-a", label="Atlas", model="scripted", strategy_prompt="balanced"),
        AgentConfig(id="agent-b", label="Nova", model="scripted", strategy_prompt="firm"),
    ]

    results = await run_tournament("negotiation", agents, matches=3, concurrency=2)

    assert len(results) == 3
    assert all(result.status == "completed" for result in results)
    assert all(set(result.final_scores) == {"agent-a", "agent-b"} for result in results)
    winners = [max(result.final_scores, key=result.final_scores.get) for result in results]
    assert winners[:2] == ["agent-a", "agent-b"]
    with Session(engine) as session:
        persisted = session.exec(select(Match).where(Match.id.in_([r.match_id for r in results]))).all()
    assert len(persisted) == 3
    assert all(match.status == "completed" for match in persisted)


@pytest.mark.asyncio
async def test_tournament_endpoint_rejects_unsafe_batch_limits():
    agents = [
        AgentConfig(id="a", label="A", model="scripted", strategy_prompt="a"),
        AgentConfig(id="b", label="B", model="scripted", strategy_prompt="b"),
    ]
    with pytest.raises(HTTPException) as exc_info:
        await tournament(TournamentRequest(agents=agents, matches=51, concurrency=2))
    assert exc_info.value.status_code == 422


@pytest.mark.asyncio
async def test_background_tournament_returns_handle_and_completes():
    agents = [
        AgentConfig(id="a", label="A", model="scripted", strategy_prompt="a"),
        AgentConfig(id="b", label="B", model="scripted", strategy_prompt="b"),
    ]
    job = start_tournament("negotiation", agents, matches=2, concurrency=2, seed=9)

    assert job.status == "running"
    for _ in range(100):
        current = get_tournament(job.id)
        if current is not None and current.status == "completed":
            break
        await asyncio.sleep(0.01)

    assert current is not None
    assert current.status == "completed"
    assert len(current.results) == 2
