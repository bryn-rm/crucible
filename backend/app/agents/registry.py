"""Maps a requested model string to the negotiation Agent that can serve it.

Provider is resolved by model-name prefix, so a match's per-agent `model`
field is the single source of truth for both scoring the LLM and choosing
which SDK to call. Adding a provider is one entry here plus one agent class,
not a change to the orchestrator or ws.py wiring.
"""

from __future__ import annotations

import os

from app.agents.claude_agent import ClaudeNegotiationAgent
from app.agents.openai_agent import OpenAINegotiationAgent
from app.agents.scripted import ScriptedNegotiationAgent
from app.contract.interfaces import Agent, AgentConfig

# (model prefix, required API key env var, agent class)
_PROVIDERS: list[tuple[str, str, type[Agent]]] = [
    ("claude-", "ANTHROPIC_API_KEY", ClaudeNegotiationAgent),
    ("gpt-", "OPENAI_API_KEY", OpenAINegotiationAgent),
]


def make_negotiation_agent(config: AgentConfig) -> Agent:
    """Pick the negotiation Agent implementation for `config.model`.

    Falls back to the scripted/dummy agent when the model doesn't match a
    known provider prefix, or that provider's API key isn't configured — so
    a match still runs end-to-end instead of failing outright.
    """
    for prefix, api_key_env, agent_cls in _PROVIDERS:
        if config.model.startswith(prefix) and os.environ.get(api_key_env):
            return agent_cls(config)
    return ScriptedNegotiationAgent(config)
