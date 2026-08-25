import pytest
from pydantic import ValidationError

from app.contract.events import AgentConfig, StartMatch
from app.security import allowed_models, token_is_valid


def config(**overrides) -> dict:
    values = {
        "id": "agent-a",
        "label": "Atlas",
        "model": "scripted",
        "strategy_prompt": "balanced",
        "temperature": 0.7,
    }
    values.update(overrides)
    return values


def test_token_requires_configured_matching_secret(monkeypatch):
    monkeypatch.delenv("ARENA_API_TOKEN", raising=False)
    assert not token_is_valid("secret")

    monkeypatch.setenv("ARENA_API_TOKEN", "secret")
    assert token_is_valid("secret")
    assert not token_is_valid("wrong")


def test_agent_config_rejects_unapproved_model_prompt_and_temperature(monkeypatch):
    monkeypatch.setenv("ALLOWED_MODELS", "scripted,gpt-approved")
    assert allowed_models() == {"scripted", "gpt-approved"}

    with pytest.raises(ValidationError, match="not allowed"):
        AgentConfig(**config(model="gpt-unapproved"))
    with pytest.raises(ValidationError):
        AgentConfig(**config(strategy_prompt="x" * 2001))
    with pytest.raises(ValidationError):
        AgentConfig(**config(temperature=2.1))


def test_start_match_requires_exactly_two_agents():
    with pytest.raises(ValidationError):
        StartMatch(environment="negotiation", agents=[AgentConfig(**config())])
