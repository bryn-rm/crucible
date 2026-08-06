"""REST routes: match history, replay, leaderboard (Phase 4)."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/environments")
def list_environments() -> list[str]:
    from app.environments import ENVIRONMENTS

    return sorted(ENVIRONMENTS)


@router.get("/matches")
def list_matches() -> list[dict]:
    # Phase 4: query app.contract.models.Match, paginated, newest first.
    return []
