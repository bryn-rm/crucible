"""Match orchestrator (Phase 1).

Runs a single match: reset env -> loop turns -> for the active agent,
observe -> agent.act -> validate action -> env.step -> emit events ->
check terminal -> score. Emits ServerEvent instances; the caller (the
WebSocket handler) is responsible for the single-writer queue that
serializes them onto the socket.

Malformed or illegal actions (bad JSON shape, or legal-shape-but-illegal-in-
context like accepting a nonexistent offer) get one retry against the same
observation, then forfeit the turn — the match continues, never crashes.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from datetime import datetime

from pydantic import TypeAdapter, ValidationError
from sqlmodel import Session, select

from app.contract.events import (
    ActionEvent,
    AgentRosterEntry,
    ErrorEvent,
    MatchEnded,
    MatchStarted,
    ReasoningDelta,
    ScoreUpdate,
    ServerEvent,
    StateUpdate,
    TurnStarted,
)
from app.contract.interfaces import Action, Agent, Environment
from app.contract.models import Match, MatchAgent, Score, Turn

MAX_ACT_ATTEMPTS = 2


class MatchOrchestrator:
    def __init__(self, environment: Environment, agents: list[Agent], max_rounds: int = 20) -> None:
        self.environment = environment
        self.agents = agents
        self.max_rounds = max_rounds

    async def run(self, match_id: str, session: Session | None = None) -> AsyncIterator[ServerEvent]:
        agent_ids = [agent.id for agent in self.agents]
        state = self.environment.reset(agent_ids)

        roster = [
            AgentRosterEntry(
                id=agent.id,
                label=agent.config.label,
                model=agent.config.model,
                strategy=agent.config.strategy_prompt,
            )
            for agent in self.agents
        ]
        yield MatchStarted(match_id=match_id, environment=self.environment.name, agents=roster)

        if session is not None:
            session.add(Match(id=match_id, environment=self.environment.name, status="running"))
            for agent in self.agents:
                session.add(
                    MatchAgent(
                        match_id=match_id,
                        agent_id=agent.id,
                        label=agent.config.label,
                        model=agent.config.model,
                        strategy=agent.config.strategy_prompt,
                    )
                )
            session.commit()

        turn_no = 0
        schema_cache: dict[str, TypeAdapter] = {}

        while turn_no < self.max_rounds and not self.environment.is_terminal(state):
            turn_no += 1
            agent = self.agents[(turn_no - 1) % len(self.agents)]
            yield TurnStarted(match_id=match_id, agent_id=agent.id, turn_no=turn_no)

            observation = self.environment.observe(state, agent.id)
            adapter = schema_cache.setdefault(
                agent.id, TypeAdapter(self.environment.action_schema(agent.id))
            )

            start = time.monotonic()
            action, new_state, chunks, forfeited, last_error = await self._act_with_retry(
                agent, observation, state, adapter
            )
            latency_ms = int((time.monotonic() - start) * 1000)

            for chunk in chunks:
                yield ReasoningDelta(match_id=match_id, agent_id=agent.id, turn_no=turn_no, chunk=chunk)

            if forfeited:
                yield ErrorEvent(
                    match_id=match_id,
                    recoverable=True,
                    message=f"{agent.id} forfeited turn {turn_no}: {last_error}",
                )

            yield ActionEvent(match_id=match_id, agent_id=agent.id, turn_no=turn_no, action=action)
            state = new_state
            yield StateUpdate(match_id=match_id, state=self.environment.public_view(state))

            if session is not None:
                session.add(
                    Turn(
                        match_id=match_id,
                        agent_id=agent.id,
                        turn_no=turn_no,
                        observation_json=observation,
                        reasoning_text="".join(chunks),
                        action_json=action,
                        state_after_json=self.environment.public_view(state),
                        latency_ms=latency_ms,
                    )
                )
                session.commit()

        final_scores = self.environment.score(state)
        # The contract's MatchEndedReason has no "walked" bucket; both a
        # walkaway and hitting the turn cap are "no agreement" outcomes.
        reason = "agreement" if state.get("status") == "agreement" else "round_limit"
        outcome = ", ".join(f"{agent_id}={value:g}" for agent_id, value in final_scores.items())

        yield ScoreUpdate(match_id=match_id, scores=final_scores)
        yield MatchEnded(match_id=match_id, outcome=outcome, final_scores=final_scores, reason=reason)

        if session is not None:
            for agent_id, value in final_scores.items():
                session.add(Score(match_id=match_id, agent_id=agent_id, dimension="payoff", value=value))
            match = session.get(Match, match_id)
            if match is not None:
                match.status = "completed"
                match.outcome = outcome
                match.reason = reason
                match.ended_at = datetime.utcnow()
                session.add(match)
            for agent_id, value in final_scores.items():
                match_agent = session.exec(
                    select(MatchAgent).where(
                        MatchAgent.match_id == match_id, MatchAgent.agent_id == agent_id
                    )
                ).first()
                if match_agent is not None:
                    match_agent.final_score = value
                    session.add(match_agent)
            session.commit()

    async def _act_with_retry(
        self,
        agent: Agent,
        observation: dict,
        state: dict,
        adapter: TypeAdapter,
    ) -> tuple[Action, dict, list[str], bool, str | None]:
        """Try to get a legal action from `agent`, retrying once on a bad
        shape or an illegal-in-context move (env.step raising ValueError).
        Returns (action, new_state, reasoning_chunks, forfeited, last_error).
        On forfeit, `action` is a synthetic marker and `new_state` is the
        unchanged input state — the turn is skipped, the match continues.
        """
        last_error: str | None = None
        all_chunks: list[str] = []
        obs = observation

        for attempt in range(MAX_ACT_ATTEMPTS):
            if attempt > 0:
                obs = {**observation, "retry_hint": last_error}
            reasoning_stream, raw_action = await agent.act(obs)
            async for chunk in reasoning_stream:
                all_chunks.append(chunk)
            try:
                validated = adapter.validate_python(raw_action)
                candidate: Action = (
                    validated.model_dump() if hasattr(validated, "model_dump") else validated
                )
                step_result = self.environment.step(state, agent.id, candidate)
            except (ValidationError, ValueError) as exc:
                last_error = str(exc)
                continue
            return candidate, step_result.state, all_chunks, False, None

        return {"type": "forfeit"}, state, all_chunks, True, last_error
