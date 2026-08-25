"""Bounded-concurrency tournament runner (Phase 5)."""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TypeVar

from sqlmodel import Session, select

from app.agents.registry import make_agent
from app.api.schemas import TournamentMatchResult
from app.contract.events import AgentConfig as ClientAgentConfig
from app.contract.interfaces import AgentConfig
from app.contract.models import Match, Tournament, TournamentResult
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


_tasks: set[asyncio.Task[None]] = set()
logger = logging.getLogger(__name__)
MAX_RETAINED_TOURNAMENTS = 100


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
    on_result: Callable[[TournamentMatchResult], Awaitable[None]] | None = None,
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
                await on_result(result)
            return result
        except Exception as exc:  # one failed model call must not abort the whole batch
            logger.exception("Tournament match %s failed", match_id)
            def mark_failed() -> None:
                with Session(engine) as session:
                    persisted = session.get(Match, match_id)
                    if persisted is not None:
                        persisted.status = "error"
                        persisted.reason = "error"
                        persisted.outcome = str(exc)
                        persisted.ended_at = datetime.now(UTC)
                        session.add(persisted)
                        session.commit()

            await asyncio.to_thread(mark_failed)
            result = TournamentMatchResult(match_id=match_id, status="error", error=str(exc))
            if on_result is not None:
                await on_result(result)
            return result

    return await bounded_map(matches, concurrency, run_match)


async def start_tournament(
    environment: str,
    agent_configs: list[ClientAgentConfig],
    matches: int,
    concurrency: int,
    seed: int,
) -> TournamentJob:
    """Start a batch outside the request lifecycle and return its status handle."""
    job = TournamentJob(id=str(uuid.uuid4()), requested=matches, concurrency=concurrency)

    def create_record() -> None:
        with Session(engine) as session:
            session.add(
                Tournament(id=job.id, requested=job.requested, concurrency=job.concurrency)
            )
            session.commit()

    await asyncio.to_thread(create_record)

    async def record_result(result: TournamentMatchResult) -> None:
        job.results.append(result)

        def persist_result() -> None:
            with Session(engine) as session:
                session.add(
                    TournamentResult(
                        tournament_id=job.id,
                        position=len(job.results) - 1,
                        result_json=result.model_dump(mode="json"),
                    )
                )
                session.commit()

        await asyncio.to_thread(persist_result)

    async def set_status(status: str) -> None:
        job.status = status

        def persist_status() -> None:
            with Session(engine) as session:
                persisted = session.get(Tournament, job.id)
                if persisted is not None:
                    persisted.status = status
                    if status != "running":
                        persisted.ended_at = datetime.now(UTC)
                    session.add(persisted)
                    session.commit()

        await asyncio.to_thread(persist_status)

    async def execute() -> None:
        try:
            await run_tournament(
                environment,
                agent_configs,
                matches,
                concurrency,
                seed,
                on_result=record_result,
            )
            await set_status("completed")
        except asyncio.CancelledError:
            await set_status("error")
            raise
        except Exception:  # protect the background job state from unexpected failures
            await set_status("error")
            logger.exception("Tournament job %s failed", job.id)
        finally:
            await asyncio.to_thread(prune_tournaments)

    task = asyncio.create_task(execute())
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return job


def get_tournament(tournament_id: str) -> TournamentJob | None:
    with Session(engine) as session:
        record = session.get(Tournament, tournament_id)
        if record is None:
            return None
        rows = session.exec(
            select(TournamentResult)
            .where(TournamentResult.tournament_id == tournament_id)
            .order_by(TournamentResult.position)
        ).all()
        return TournamentJob(
            id=record.id,
            requested=record.requested,
            concurrency=record.concurrency,
            status=record.status,
            results=[TournamentMatchResult.model_validate(row.result_json) for row in rows],
        )


def prune_tournaments(limit: int = MAX_RETAINED_TOURNAMENTS) -> None:
    """Bound durable job history while never evicting active work."""
    with Session(engine) as session:
        completed = session.exec(
            select(Tournament)
            .where(Tournament.status != "running")
            .order_by(Tournament.created_at.desc())
        ).all()
        for record in completed[limit:]:
            results = session.exec(
                select(TournamentResult).where(TournamentResult.tournament_id == record.id)
            ).all()
            for result in results:
                session.delete(result)
            session.delete(record)
        session.commit()


async def stop_tournaments() -> None:
    """Gracefully mark in-process jobs interrupted during application shutdown."""
    tasks = list(_tasks)
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
