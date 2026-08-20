import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.contract.models import Match, MatchAgent, Score
from app.db import engine
from app.main import app


def seed_completed_match(
    match_id: str,
    a_model: str,
    a_strategy: str,
    a_payoff: float,
    b_model: str,
    b_strategy: str,
    b_payoff: float,
) -> None:
    with Session(engine) as session:
        session.add(Match(id=match_id, environment="negotiation", status="completed"))
        session.add(
            MatchAgent(
                match_id=match_id,
                agent_id="agent_a",
                label="Alice",
                model=a_model,
                strategy=a_strategy,
                final_score=a_payoff,
            )
        )
        session.add(
            MatchAgent(
                match_id=match_id,
                agent_id="agent_b",
                label="Bob",
                model=b_model,
                strategy=b_strategy,
                final_score=b_payoff,
            )
        )
        session.add(Score(match_id=match_id, agent_id="agent_a", dimension="payoff", value=a_payoff))
        session.add(Score(match_id=match_id, agent_id="agent_b", dimension="payoff", value=b_payoff))
        session.commit()


def test_leaderboard_computes_win_rate_and_mean_payoff_by_model():
    seed_completed_match("m1", "claude-haiku-4-5", "aggressive", 70, "gpt-4o-mini", "cautious", 30)
    seed_completed_match("m2", "claude-haiku-4-5", "aggressive", 40, "gpt-4o-mini", "cautious", 60)

    with TestClient(app) as client:
        resp = client.get("/api/leaderboard")

    assert resp.status_code == 200
    by_model = {e["key"]: e for e in resp.json()["by_model"]}

    assert by_model["claude-haiku-4-5"]["matches"] == 2
    assert by_model["claude-haiku-4-5"]["wins"] == 1
    assert by_model["claude-haiku-4-5"]["win_rate"] == pytest.approx(0.5)
    assert by_model["claude-haiku-4-5"]["mean_payoff"] == pytest.approx(55.0)

    assert by_model["gpt-4o-mini"]["wins"] == 1
    assert by_model["gpt-4o-mini"]["mean_payoff"] == pytest.approx(45.0)


def test_leaderboard_treats_equal_payoffs_as_a_draw():
    seed_completed_match("m3", "claude-haiku-4-5", "balanced", 50, "gpt-4o-mini", "balanced", 50)

    with TestClient(app) as client:
        resp = client.get("/api/leaderboard")

    by_model = {e["key"]: e for e in resp.json()["by_model"]}
    assert by_model["claude-haiku-4-5"]["wins"] == 0
    assert by_model["claude-haiku-4-5"]["draws"] == 1
    assert by_model["claude-haiku-4-5"]["win_rate"] == pytest.approx(0.0)


def test_leaderboard_ignores_matches_that_have_not_completed():
    with Session(engine) as session:
        session.add(Match(id="m4", environment="negotiation", status="running"))
        session.add(
            MatchAgent(
                match_id="m4", agent_id="agent_a", label="Alice", model="claude-haiku-4-5", strategy="x"
            )
        )
        session.add(Score(match_id="m4", agent_id="agent_a", dimension="payoff", value=99))
        session.commit()

    with TestClient(app) as client:
        resp = client.get("/api/leaderboard")

    by_model = {e["key"]: e for e in resp.json()["by_model"]}
    assert "claude-haiku-4-5" not in by_model


def test_leaderboard_groups_by_strategy_too():
    seed_completed_match("m5", "claude-haiku-4-5", "aggressive", 80, "gpt-4o-mini", "cautious", 20)

    with TestClient(app) as client:
        resp = client.get("/api/leaderboard")

    by_strategy = {e["key"]: e for e in resp.json()["by_strategy"]}
    assert by_strategy["aggressive"]["wins"] == 1
    assert by_strategy["cautious"]["wins"] == 0
