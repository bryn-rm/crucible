"""Bounded-concurrency tournament runner (Phase 5)."""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TypeVar

from sqlmodel import Session

from app.agents.registry import make_agent
from app.api.schemas import TournamentMatchResult
from app.contract.events import AgentConfig as ClientAgentConfig
from app.contract.interfaces import AgentConfig
from app.contract.models import Match
from app.db import engine
from app.environments.registry import get_environment
from app.environments.negotiation import NegotiationEnvironment
from app.orchestrator import MatchOrchestrator

T = TypeVar("T")


@dataclass
class TournamentJob:
    id: str
    requested: int
    concurrency: int
    status: str = "running"
    results: list[TournamentMatchResult] = field(default_factory=list)


_jobs: dict[str, TournamentJob] = {}
_tasks: set[asyncio.Task[None]] = set()
logger = logging.getLogger(__name__)


async def bounded_map(
    count: int, concurrency: int, worker: Callable[[int], Awaitable[T]]
) -> list[T]:
    """Run `count` jobs while keeping at most `concurrency` active."""
    semaphore = asyncio.Semaphore(concurrency)

    async def run_one(index: int) -> T:
        async with semaphore:
            return await worker(index)

    return list(await asyncio.gather(*(run_one(index) for index in range(count))))


def _agent_config(config: ClientAgentConfig) -> AgentConfig:
    return AgentConfig(
        id=config.id,
        label=config.label,
        model=config.model,
        strategy_prompt=config.strategy_prompt,
        temperature=config.temperature,
    )


async def run_tournament(
    environment: str,
    agent_configs: list[ClientAgentConfig],
    matches: int,
    concurrency: int,
    seed: int = 42,
    on_result: Callable[[TournamentMatchResult], None] | None = None,
) -> list[TournamentMatchResult]:
    """Run and persist independent matches, returning a compact batch summary."""

    async def run_match(index: int) -> TournamentMatchResult:
        match_id = str(uuid.uuid4())
        try:
            env = (
                NegotiationEnvironment(seed=seed + index // 2)
                if environment == "negotiation"
                else get_environment(environment)
            )
            # Swap seats every match so first-mover effects do not masquerade
            # as model/strategy effects. Each adjacent pair shares a seed.
            seated_configs = agent_configs if index % 2 == 0 else list(reversed(agent_configs))
            agents = [make_agent(_agent_config(config), environment) for config in seated_configs]
            orchestrator = MatchOrchestrator(environment=env, agents=agents)
            ended = None
            with Session(engine) as session:
                async for event in orchestrator.run(match_id, session=session):
                    if event.type == "match_ended":
                        ended = event
            if ended is None:
                raise RuntimeError("match ended without a terminal event")
            result = TournamentMatchResult(
                match_id=match_id,
                status="completed",
                outcome=ended.outcome,
                reason=ended.reason,
                final_scores=ended.final_scores,
            )
            if on_result is not None:
                on_result(result)
            return result
        except Exception as exc:  # one failed model call must not abort the whole batch
            with Session(engine) as session:
                persisted = session.get(Match, match_id)
                if persisted is not None:
                    persisted.status = "error"
                    persisted.reason = "error"
                    persisted.outcome = str(exc)
                    persisted.ended_at = datetime.now(UTC)
                    session.add(persisted)
                    session.commit()
            result = TournamentMatchResult(match_id=match_id, status="error", error=str(exc))
            if on_result is not None:
                on_result(result)
            return result

    return await bounded_map(matches, concurrency, run_match)


def start_tournament(
    environment: str,
    agent_configs: list[ClientAgentConfig],
    matches: int,
    concurrency: int,
    seed: int,
) -> TournamentJob:
    """Start a batch outside the request lifecycle and return its status handle."""
    job = TournamentJob(id=str(uuid.uuid4()), requested=matches, concurrency=concurrency)
    _jobs[job.id] = job

    async def execute() -> None:
        try:
            await run_tournament(
                environment,
                agent_configs,
                matches,
                concurrency,
                seed,
                on_result=job.results.append,
            )
            job.status = "completed"
        except Exception:  # protect the background job state from unexpected failures
            job.status = "error"
            logger.exception("Tournament job %s failed", job.id)

    task = asyncio.create_task(execute())
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return job


def get_tournament(tournament_id: str) -> TournamentJob | None:
    return _jobs.get(tournament_id)
