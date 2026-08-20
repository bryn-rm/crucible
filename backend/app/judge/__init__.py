"""Rubric-based LLM judge (Phase 4).

Scores a finished trajectory along per-environment dimensions. Runs as a
separate pass after the match ends (app/api/routes.py's `/matches/{id}/judge`
endpoint), so it never contaminates the objective `payoff` scores the
orchestrator writes during the match. This is the sole scorer for
judge-only environments like the Phase 5 role-play scenario; for negotiation
it's an optional, additional lens on top of the objective payoff.
"""

from __future__ import annotations

import json
import os
from typing import Any

import anthropic
from pydantic import BaseModel

DEFAULT_JUDGE_MODEL = "claude-sonnet-4-20250514"
MAX_TOKENS = 1024

RUBRICS: dict[str, dict[str, str]] = {
    "negotiation": {
        "toughness": "1 (caved immediately, gave away most value) to 10 (held firm, conceded little).",
        "fairness": "1 (offers were consistently one-sided) to 10 (offers were consistently balanced).",
        "clarity": "1 (reasoning was incoherent or contradictory) to 10 (reasoning was precise and easy to follow).",
    }
}


class AgentJudgment(BaseModel):
    scores: dict[str, float]
    rationale: str


class JudgeResult(BaseModel):
    dimensions: list[str]
    agents: dict[str, AgentJudgment]


def rubric_for(environment: str) -> dict[str, str]:
    dims = RUBRICS.get(environment)
    if dims is None:
        raise ValueError(f"no judge rubric registered for environment {environment!r}")
    return dims


def _build_prompt(
    environment: str, agents: list[dict], turns: list[dict], outcome: str | None
) -> tuple[str, str]:
    dims = rubric_for(environment)
    system = (
        "You are an impartial judge scoring a finished multi-agent match. "
        "Score each agent on every listed dimension using the given scale. "
        "Respond with ONLY a JSON object of this exact shape, and nothing else:\n"
        '{"<agent_id>": {"scores": {"<dimension>": <number>, ...}, '
        '"rationale": "<one or two sentences>"}, ...}'
    )
    dims_text = "\n".join(f"- {name}: {desc}" for name, desc in dims.items())
    roster = "\n".join(
        f"- {a['agent_id']} ({a['label']}): strategy = {a['strategy']!r}" for a in agents
    )
    transcript = "\n".join(
        f"[turn {t['turn_no']}] {t['agent_id']}: {t['reasoning_text']}\n"
        f"  action: {json.dumps(t['action_json'])}"
        for t in turns
    )
    user = (
        f"Environment: {environment}\nOutcome: {outcome}\n\n"
        f"Agents:\n{roster}\n\nDimensions:\n{dims_text}\n\nTranscript:\n{transcript}"
    )
    return system, user


def _parse_json_object(text: str) -> dict[str, Any]:
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"judge response contained no JSON object: {text!r}")
    return json.loads(text[start : end + 1])


async def judge_match(
    environment: str,
    agents: list[dict],
    turns: list[dict],
    outcome: str | None,
    client: anthropic.AsyncAnthropic | None = None,
) -> JudgeResult:
    dims = rubric_for(environment)
    system, user = _build_prompt(environment, agents, turns, outcome)

    client = client or anthropic.AsyncAnthropic()
    response = await client.messages.create(
        model=os.environ.get("JUDGE_MODEL", DEFAULT_JUDGE_MODEL),
        max_tokens=MAX_TOKENS,
        temperature=0,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    text = "".join(block.text for block in response.content if block.type == "text")
    raw = _parse_json_object(text)

    expected_agents = {agent["agent_id"] for agent in agents}
    if set(raw) != expected_agents:
        raise ValueError(
            "judge response agent IDs did not match the roster: "
            f"expected {sorted(expected_agents)}, got {sorted(raw)}"
        )

    expected_dimensions = set(dims)
    for agent_id, payload in raw.items():
        if not isinstance(payload, dict) or not isinstance(payload.get("scores"), dict):
            raise ValueError(f"judge response for {agent_id!r} did not contain a scores object")
        scores = payload["scores"]
        if set(scores) != expected_dimensions:
            raise ValueError(
                f"judge dimensions for {agent_id!r} did not match the rubric: "
                f"expected {sorted(expected_dimensions)}, got {sorted(scores)}"
            )
        for dimension, value in scores.items():
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not 1 <= value <= 10:
                raise ValueError(
                    f"judge score for {agent_id!r}/{dimension!r} must be a number from 1 to 10"
                )

    parsed_agents = {
        agent_id: AgentJudgment(scores=payload["scores"], rationale=payload.get("rationale", ""))
        for agent_id, payload in raw.items()
    }
    return JudgeResult(dimensions=list(dims), agents=parsed_agents)
