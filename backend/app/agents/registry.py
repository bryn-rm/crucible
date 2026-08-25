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
from app.agents.role_play import ClaudeRolePlayAgent, OpenAIRolePlayAgent, ScriptedRolePlayAgent
from app.agents.scripted import ScriptedNegotiationAgent
from app.contract.interfaces import Agent, AgentConfig

# (model prefix, required API key env var, agent class), per environment
_PROVIDERS_BY_ENV: dict[str, list[tuple[str, str, type[Agent]]]] = {
    "negotiation": [
        ("claude-", "ANTHROPIC_API_KEY", ClaudeNegotiationAgent),
        ("gpt-", "OPENAI_API_KEY", OpenAINegotiationAgent),
    ],
    "role_play": [
        ("claude-", "ANTHROPIC_API_KEY", ClaudeRolePlayAgent),
        ("gpt-", "OPENAI_API_KEY", OpenAIRolePlayAgent),
    ],
}

_SCRIPTED_BY_ENV: dict[str, type[Agent]] = {
    "negotiation": ScriptedNegotiationAgent,
    "role_play": ScriptedRolePlayAgent,
}


def make_negotiation_agent(config: AgentConfig) -> Agent:
    """Pick the negotiation Agent implementation for `config.model`.

    The explicit ``scripted`` model selects the local demo agent. Real model
    requests fail when their provider key is unavailable so results are never
    silently attributed to an implementation that did not run.
    """
    return make_agent(config, "negotiation")


def make_agent(config: AgentConfig, environment: str) -> Agent:
    """Resolve a provider implementation appropriate to the environment.

    The explicit ``scripted`` model selects the local demo agent. Real model
    requests fail when their provider key is unavailable so results are never
    silently attributed to an implementation that did not run.
    """
    providers = _PROVIDERS_BY_ENV.get(environment)
    if providers is None:
        raise ValueError(f"no agent implementation registered for environment {environment!r}")
    for prefix, api_key_env, agent_cls in providers:
        if config.model.startswith(prefix):
            if not os.environ.get(api_key_env):
                raise ValueError(
                    f"model {config.model!r} requires the {api_key_env} environment variable"
                )
            return agent_cls(config)
    if config.model == "scripted":
        return _SCRIPTED_BY_ENV[environment](config)
    raise ValueError(f"no provider registered for model {config.model!r}")
