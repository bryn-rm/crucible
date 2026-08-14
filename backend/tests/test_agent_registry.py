from app.agents.claude_agent import ClaudeNegotiationAgent
from app.agents.openai_agent import OpenAINegotiationAgent
from app.agents.registry import make_negotiation_agent
from app.agents.scripted import ScriptedNegotiationAgent
from app.contract.interfaces import AgentConfig


def config(model: str) -> AgentConfig:
    return AgentConfig(id="agent_a", label="Alice", model=model, strategy_prompt="greedy")


def test_claude_model_with_key_set_picks_claude_agent(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    agent = make_negotiation_agent(config("claude-haiku-4-5"))

    assert isinstance(agent, ClaudeNegotiationAgent)


def test_gpt_model_with_key_set_picks_openai_agent(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    agent = make_negotiation_agent(config("gpt-4o"))

    assert isinstance(agent, OpenAINegotiationAgent)


def test_known_provider_without_api_key_falls_back_to_scripted(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    agent = make_negotiation_agent(config("claude-haiku-4-5"))

    assert isinstance(agent, ScriptedNegotiationAgent)


def test_unknown_model_falls_back_to_scripted(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    agent = make_negotiation_agent(config("scripted"))

    assert isinstance(agent, ScriptedNegotiationAgent)
