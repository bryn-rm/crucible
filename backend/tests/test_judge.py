import json

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.contract.models import Match, MatchAgent, Score, Turn
from app.db import engine
from app.judge import judge_match
from app.main import app


class _TextBlock:
    def __init__(self, text: str) -> None:
        self.type = "text"
        self.text = text


class _FakeResponse:
    def __init__(self, text: str) -> None:
        self.content = [_TextBlock(text)]


class _FakeMessages:
    def __init__(self, text: str, calls: list[dict]) -> None:
        self._text = text
        self._calls = calls

    async def create(self, **kwargs: object) -> _FakeResponse:
        self._calls.append(kwargs)
        return _FakeResponse(self._text)


class _FakeClient:
    def __init__(self, text: str) -> None:
        self.calls: list[dict] = []
        self.messages = _FakeMessages(text, self.calls)


JUDGE_JSON = json.dumps(
    {
        "agent_a": {
            "scores": {"toughness": 8, "fairness": 4, "clarity": 7},
            "rationale": "Held firm and rarely conceded.",
        },
        "agent_b": {
            "scores": {"toughness": 3, "fairness": 8, "clarity": 6},
            "rationale": "Conceded quickly but stayed fair.",
        },
    }
)

AGENTS = [
    {"agent_id": "agent_a", "label": "Alice", "model": "claude-haiku-4-5", "strategy": "aggressive"},
    {"agent_id": "agent_b", "label": "Bob", "model": "claude-haiku-4-5", "strategy": "cautious"},
]

TURNS = [
    {"turn_no": 1, "agent_id": "agent_a", "reasoning_text": "I'll open high.", "action_json": {"type": "offer"}},
    {"turn_no": 2, "agent_id": "agent_b", "reasoning_text": "I'll accept.", "action_json": {"type": "accept"}},
]


@pytest.mark.asyncio
async def test_judge_match_parses_scores_and_rationale():
    client = _FakeClient(JUDGE_JSON)

    result = await judge_match("negotiation", AGENTS, TURNS, outcome="agent_a=70", client=client)

    assert set(result.dimensions) == {"toughness", "fairness", "clarity"}
    assert result.agents["agent_a"].scores["toughness"] == 8
    assert "Held firm" in result.agents["agent_a"].rationale
    assert client.calls[0]["temperature"] == 0


@pytest.mark.asyncio
async def test_judge_match_parses_json_even_with_surrounding_prose():
    client = _FakeClient(f"Here is my assessment:\n{JUDGE_JSON}\nHope that helps!")

    result = await judge_match("negotiation", AGENTS, TURNS, outcome=None, client=client)

    assert result.agents["agent_b"].scores["fairness"] == 8


@pytest.mark.asyncio
async def test_judge_match_raises_for_unknown_environment():
    client = _FakeClient(JUDGE_JSON)

    with pytest.raises(ValueError):
        await judge_match("role_play", AGENTS, TURNS, outcome=None, client=client)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        {"agent_a": json.loads(JUDGE_JSON)["agent_a"]},
        {
            **json.loads(JUDGE_JSON),
            "agent_b": {
                "scores": {"toughness": 11, "fairness": 8, "clarity": 6},
                "rationale": "Out of range.",
            },
        },
        {
            **json.loads(JUDGE_JSON),
            "agent_b": {
                "scores": {"toughness": 3, "fairness": 8},
                "rationale": "Missing a dimension.",
            },
        },
    ],
)
async def test_judge_match_rejects_invalid_roster_dimensions_and_ranges(response: dict):
    client = _FakeClient(json.dumps(response))

    with pytest.raises(ValueError):
        await judge_match("negotiation", AGENTS, TURNS, outcome=None, client=client)


def test_judge_endpoint_requires_completed_match(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    with Session(engine) as session:
        session.add(Match(id="running-match", environment="negotiation", status="running"))
        session.commit()

    with TestClient(app) as client:
        resp = client.post("/api/matches/running-match/judge")

    assert resp.status_code == 400


def test_judge_endpoint_404_for_unknown_match(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    with TestClient(app) as client:
        resp = client.post("/api/matches/does-not-exist/judge")

    assert resp.status_code == 404


def test_judge_endpoint_503_without_api_key(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with Session(engine) as session:
        session.add(Match(id="completed-match", environment="negotiation", status="completed"))
        session.commit()

    with TestClient(app) as client:
        resp = client.post("/api/matches/completed-match/judge")

    assert resp.status_code == 503


def test_judge_endpoint_persists_judge_scores(monkeypatch: pytest.MonkeyPatch):
    import app.judge as judge_module

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(
        judge_module.anthropic, "AsyncAnthropic", lambda: _FakeClient(JUDGE_JSON)
    )

    with Session(engine) as session:
        session.add(Match(id="judged-match", environment="negotiation", status="completed"))
        session.add(
            MatchAgent(
                match_id="judged-match",
                agent_id="agent_a",
                label="Alice",
                model="claude-haiku-4-5",
                strategy="aggressive",
            )
        )
        session.add(
            MatchAgent(
                match_id="judged-match",
                agent_id="agent_b",
                label="Bob",
                model="claude-haiku-4-5",
                strategy="cautious",
            )
        )
        session.add(
            Turn(
                match_id="judged-match",
                agent_id="agent_a",
                turn_no=1,
                reasoning_text="I'll open high.",
                action_json={"type": "offer"},
            )
        )
        session.commit()

    with TestClient(app) as client:
        resp = client.post("/api/matches/judged-match/judge")

    assert resp.status_code == 200
    with Session(engine) as session:
        scores = session.exec(select(Score).where(Score.match_id == "judged-match")).all()
    dimensions = {s.dimension for s in scores}
    assert dimensions == {"judge_toughness", "judge_fairness", "judge_clarity"}
