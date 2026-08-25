"""Points the app at a fresh temp SQLite file for the whole test session.

Must set ARENA_DB_PATH before app.db is imported anywhere (its engine is
built at import time from that env var), so this runs as a pytest_configure
hook rather than a fixture.
"""

from __future__ import annotations

import os
import tempfile

import pytest


def pytest_configure(config) -> None:  # noqa: ARG001
    fd, path = tempfile.mkstemp(suffix=".db", prefix="arena-test-")
    os.close(fd)
    os.environ["ARENA_DB_PATH"] = path

    from app.db import init_db

    init_db()


@pytest.fixture(autouse=True)
def _clean_db():
    """Each test starts with an empty DB, so tests hitting the shared
    app.db.engine (e.g. via TestClient) don't see other tests' matches."""
    yield
    from sqlmodel import Session, select

    from app.contract.models import Match, MatchAgent, Score, Tournament, TournamentResult, Turn
    from app.db import engine, init_db

    init_db()
    with Session(engine) as session:
        for model in (TournamentResult, Tournament, Score, Turn, MatchAgent, Match):
            for row in session.exec(select(model)):
                session.delete(row)
        session.commit()
