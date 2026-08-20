"""REST routes: match history, replay, and the leaderboard (Phase 4).

Reads persisted matches/turns/scores written by the orchestrator
(app/orchestrator.py) via the SQLModel tables in app/contract/models.py.
Response shapes live in app/api/schemas.py.
"""

from __future__ import annotations

import os
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.api.schemas import (
    LeaderboardEntry,
    LeaderboardResponse,
    MatchAgentOut,
    MatchDetail,
    MatchSummary,
    ScoreOut,
    TurnOut,
)
from app.contract.models import Match, MatchAgent, Score, Turn
from app.db import get_session
from app.judge import JudgeResult, judge_match

router = APIRouter()


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

    # Role-play observations are persisted server-side and contain the trusted,
    # role-scoped JD/CV context. Give each agent's first context to the judge so
    # role fidelity can be assessed without exposing it through public replay.
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


def _leaderboard_entries(rows: dict[str, list[tuple[float, bool, bool]]]) -> list[LeaderboardEntry]:
    """`rows` maps a grouping key (model or strategy) to a list of
    `(payoff, won, drew)` tuples, one per agent-in-a-match."""
    entries = []
    for key, results in rows.items():
        matches = len(results)
        wins = sum(1 for _, won, _ in results if won)
        draws = sum(1 for _, _, drew in results if drew)
        mean_payoff = sum(payoff for payoff, _, _ in results) / matches
        entries.append(
            LeaderboardEntry(
                key=key,
                matches=matches,
                wins=wins,
                draws=draws,
                win_rate=wins / matches,
                mean_payoff=mean_payoff,
            )
        )
    entries.sort(key=lambda e: e.win_rate, reverse=True)
    return entries


@router.get("/leaderboard")
def leaderboard(session: Session = Depends(get_session)) -> LeaderboardResponse:
    """Win rates and mean payoffs by model and by strategy, across completed
    matches with an objective `payoff` score. A win is a strictly higher
    payoff than the other participant(s) in that match; equal payoffs are a
    draw. Every entry carries its match count alongside the rate — a handful
    of nondeterministic LLM matches proves nothing on its own."""
    completed_ids = {
        m.id for m in session.exec(select(Match).where(Match.status == "completed")).all()
    }
    payoff_scores = session.exec(select(Score).where(Score.dimension == "payoff")).all()

    by_match: dict[str, dict[str, float]] = defaultdict(dict)
    for score in payoff_scores:
        if score.match_id in completed_ids:
            by_match[score.match_id][score.agent_id] = score.value

    match_agents = session.exec(select(MatchAgent)).all()
    agent_meta: dict[tuple[str, str], MatchAgent] = {
        (ma.match_id, ma.agent_id): ma for ma in match_agents
    }

    by_model: dict[str, list[tuple[float, bool, bool]]] = defaultdict(list)
    by_strategy: dict[str, list[tuple[float, bool, bool]]] = defaultdict(list)

    for match_id, scores in by_match.items():
        if len(scores) < 2:
            continue
        best = max(scores.values())
        winners = [agent_id for agent_id, value in scores.items() if value == best]
        drew = len(winners) != 1
        for agent_id, payoff in scores.items():
            meta = agent_meta.get((match_id, agent_id))
            if meta is None:
                continue
            won = not drew and agent_id in winners
            by_model[meta.model].append((payoff, won, drew))
            by_strategy[meta.strategy].append((payoff, won, drew))

    return LeaderboardResponse(
        by_model=_leaderboard_entries(by_model),
        by_strategy=_leaderboard_entries(by_strategy),
    )


@router.post("/matches/{match_id}/judge")
async def judge(match_id: str, session: Session = Depends(get_session)) -> JudgeResult:
    """Run the rubric-based LLM judge over a completed match's trajectory as
    a separate pass, and persist its dimensions as `judge_<dimension>` Score
    rows (re-running replaces the previous judge pass, never the objective
    `payoff` rows the orchestrator wrote)."""
    match = session.get(Match, match_id)
    if match is None:
        raise HTTPException(status_code=404, detail="match not found")
    if match.status != "completed":
        raise HTTPException(status_code=400, detail="match has not completed yet")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise HTTPException(status_code=503, detail="ANTHROPIC_API_KEY not configured")

    agents = _match_agents_out(session, match_id)
    turns = session.exec(
        select(Turn).where(Turn.match_id == match_id).order_by(Turn.turn_no)
    ).all()

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

    existing = session.exec(
        select(Score).where(Score.match_id == match_id, Score.dimension.startswith("judge_"))
    ).all()
    for row in existing:
        session.delete(row)
    for agent_id, judgment in result.agents.items():
        for dimension, value in judgment.scores.items():
            session.add(Score(match_id=match_id, agent_id=agent_id, dimension=f"judge_{dimension}", value=value))
    session.commit()

    return result
