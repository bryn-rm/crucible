"""REST routes: match history, replay, and the leaderboard (Phase 4).

Reads persisted matches/turns/scores written by the orchestrator
(app/orchestrator.py) via the SQLModel tables in app/contract/models.py.
Response shapes live in app/api/schemas.py.
"""

from __future__ import annotations

import os
import asyncio

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlmodel import Session, select

from app.api.schemas import (
    LeaderboardEntry,
    LeaderboardResponse,
    MatchAgentOut,
    MatchDetail,
    MatchSummary,
    ScoreOut,
    TournamentRequest,
    TournamentResponse,
    TurnOut,
)
from app.contract.models import Match, MatchAgent, Score, Turn
from app.db import get_session
from app.environments.registry import get_environment
from app.judge import JudgeResult, judge_match
from app.security import require_api_token
from app.tournament import get_tournament, start_tournament

router = APIRouter()


@router.post(
    "/tournaments", response_model=TournamentResponse, dependencies=[Depends(require_api_token)]
)
async def tournament(request: TournamentRequest) -> TournamentResponse:
    if len(request.agents) != 2:
        raise HTTPException(status_code=422, detail="tournaments require exactly two agents")
    try:
        get_environment(request.environment)
        job = await start_tournament(
            request.environment,
            request.agents,
            request.matches,
            request.concurrency,
            request.seed,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _tournament_response(job)


@router.get(
    "/tournaments/{tournament_id}",
    response_model=TournamentResponse,
    dependencies=[Depends(require_api_token)],
)
async def tournament_status(tournament_id: str) -> TournamentResponse:
    job = await asyncio.to_thread(get_tournament, tournament_id)
    if job is None:
        raise HTTPException(status_code=404, detail="tournament not found")
    return _tournament_response(job)


def _tournament_response(job) -> TournamentResponse:
    completed = sum(result.status == "completed" for result in job.results)
    return TournamentResponse(
        tournament_id=job.id,
        status=job.status,
        requested=job.requested,
        completed=completed,
        failed=sum(result.status == "error" for result in job.results),
        concurrency=job.concurrency,
        matches=job.results,
    )


@router.get("/environments")
def list_environments() -> list[str]:
    from app.environments import ENVIRONMENTS

    return sorted(ENVIRONMENTS)


def _match_agents_out(session: Session, match_id: str) -> list[MatchAgentOut]:
    match_agents = session.exec(
        select(MatchAgent).where(MatchAgent.match_id == match_id)
    ).all()
    return [
        MatchAgentOut(
            agent_id=ma.agent_id,
            label=ma.label,
            model=ma.model,
            strategy=ma.strategy,
            final_score=ma.final_score,
        )
        for ma in match_agents
    ]


@router.get("/matches")
def list_matches(
    limit: int = 20, offset: int = 0, session: Session = Depends(get_session)
) -> list[MatchSummary]:
    limit = max(1, min(limit, 100))
    offset = max(0, offset)
    matches = session.exec(
        select(Match).order_by(Match.created_at.desc()).offset(offset).limit(limit)
    ).all()
    return [
        MatchSummary(
            id=match.id,
            environment=match.environment,
            status=match.status,
            created_at=match.created_at,
            ended_at=match.ended_at,
            outcome=match.outcome,
            reason=match.reason,
            agents=_match_agents_out(session, match.id),
        )
        for match in matches
    ]


@router.get("/matches/{match_id}")
def get_match(match_id: str, session: Session = Depends(get_session)) -> MatchDetail:
    match = session.get(Match, match_id)
    if match is None:
        raise HTTPException(status_code=404, detail="match not found")

    turns = session.exec(
        select(Turn).where(Turn.match_id == match_id).order_by(Turn.turn_no)
    ).all()

    scores = session.exec(select(Score).where(Score.match_id == match_id)).all()

    return MatchDetail(
        id=match.id,
        environment=match.environment,
        status=match.status,
        created_at=match.created_at,
        ended_at=match.ended_at,
        outcome=match.outcome,
        reason=match.reason,
        agents=_match_agents_out(session, match_id),
        turns=[
            TurnOut(
                turn_no=t.turn_no,
                agent_id=t.agent_id,
                reasoning_text=t.reasoning_text,
                action_json=t.action_json,
                state_after_json=t.state_after_json,
                latency_ms=t.latency_ms,
            )
            for t in turns
        ],
        scores=[ScoreOut(agent_id=s.agent_id, dimension=s.dimension, value=s.value) for s in scores],
    )


def _leaderboard_entries(session: Session, grouping: str) -> list[LeaderboardEntry]:
    """Aggregate completed payoff rows in SQLite, including win/draw status."""
    if grouping not in {"model", "strategy"}:
        raise ValueError("invalid leaderboard grouping")
    statement = text(f"""
        WITH payoffs AS (
            SELECT s.match_id, s.agent_id, s.value, ma.{grouping} AS grouping_key,
                   MAX(s.value) OVER (PARTITION BY s.match_id) AS best,
                   COUNT(*) OVER (PARTITION BY s.match_id) AS participants
            FROM scores AS s
            JOIN matches AS m ON m.id = s.match_id AND m.status = 'completed'
            JOIN match_agents AS ma
              ON ma.match_id = s.match_id AND ma.agent_id = s.agent_id
            WHERE s.dimension = 'payoff'
        ), assessed AS (
            SELECT *, SUM(CASE WHEN value = best THEN 1 ELSE 0 END)
                       OVER (PARTITION BY match_id) AS winner_count
            FROM payoffs
            WHERE participants >= 2
        )
        SELECT grouping_key, COUNT(*) AS matches,
               SUM(CASE WHEN value = best AND winner_count = 1 THEN 1 ELSE 0 END) AS wins,
               SUM(CASE WHEN winner_count != 1 THEN 1 ELSE 0 END) AS draws,
               AVG(value) AS mean_payoff
        FROM assessed
        GROUP BY grouping_key
        ORDER BY (1.0 * SUM(CASE WHEN value = best AND winner_count = 1 THEN 1 ELSE 0 END)
                  / COUNT(*)) DESC
    """)
    entries: list[LeaderboardEntry] = []
    for row in session.execute(statement).mappings():
        matches = int(row["matches"])
        wins = int(row["wins"])
        entries.append(
            LeaderboardEntry(
                key=str(row["grouping_key"]),
                matches=matches,
                wins=wins,
                draws=int(row["draws"]),
                win_rate=wins / matches,
                mean_payoff=float(row["mean_payoff"]),
            )
        )
    return entries


@router.get("/leaderboard")
def leaderboard(session: Session = Depends(get_session)) -> LeaderboardResponse:
    """Win rates and mean payoffs by model and by strategy, across completed
    matches with an objective `payoff` score. A win is a strictly higher
    payoff than the other participant(s) in that match; equal payoffs are a
    draw. Every entry carries its match count alongside the rate — a handful
    of nondeterministic LLM matches proves nothing on its own."""
    return LeaderboardResponse(
        by_model=_leaderboard_entries(session, "model"),
        by_strategy=_leaderboard_entries(session, "strategy"),
    )


@router.post("/matches/{match_id}/judge")
async def judge(match_id: str, session: Session = Depends(get_session)) -> JudgeResult:
    """Run the rubric-based LLM judge over a completed match's trajectory as
    a separate pass, and persist its dimensions as `judge_<dimension>` Score
    rows (re-running replaces the previous judge pass, never the objective
    `payoff` rows the orchestrator wrote)."""
    # This is the only async REST route using the synchronous SQLModel engine;
    # run each DB phase in a worker thread so judging cannot stall live sockets.
    match = await asyncio.to_thread(session.get, Match, match_id)
    if match is None:
        raise HTTPException(status_code=404, detail="match not found")
    if match.status != "completed":
        raise HTTPException(status_code=400, detail="match has not completed yet")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise HTTPException(status_code=503, detail="ANTHROPIC_API_KEY not configured")

    agents = await asyncio.to_thread(_match_agents_out, session, match_id)

    def load_turns() -> list[Turn]:
        return list(
            session.exec(select(Turn).where(Turn.match_id == match_id).order_by(Turn.turn_no)).all()
        )

    turns = await asyncio.to_thread(load_turns)

    # Persisted observations contain trusted role-scoped JD/CV context. It is
    # supplied only to the server-side judge, never to public replay responses.
    role_contexts: dict[str, dict] | None = None
    if match.environment == "role_play":
        role_contexts = {}
        for turn in turns:
            if turn.agent_id in role_contexts:
                continue
            observation = turn.observation_json or {}
            role_contexts[turn.agent_id] = {
                "role": observation.get("role"),
                "private_context": observation.get("private_context", {}),
            }

    try:
        result = await judge_match(
            environment=match.environment,
            agents=[a.model_dump() for a in agents],
            turns=[
                {
                    "turn_no": t.turn_no,
                    "agent_id": t.agent_id,
                    "reasoning_text": t.reasoning_text,
                    "action_json": t.action_json,
                }
                for t in turns
            ],
            outcome=match.outcome,
            role_contexts=role_contexts,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    def persist_scores() -> None:
        existing = session.exec(
            select(Score).where(Score.match_id == match_id, Score.dimension.like("judge\\_%", escape="\\"))
        ).all()
        for row in existing:
            session.delete(row)
        for agent_id, judgment in result.agents.items():
            for dimension, value in judgment.scores.items():
                session.add(
                    Score(
                        match_id=match_id,
                        agent_id=agent_id,
                        dimension=f"judge_{dimension}",
                        value=value,
                    )
                )
        session.commit()

    await asyncio.to_thread(persist_scores)

    return result
