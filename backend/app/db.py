"""SQLite engine + session helper. One file, no infra."""

from __future__ import annotations

import os
from collections.abc import Generator

from sqlmodel import Session, SQLModel, create_engine

DB_PATH = os.environ.get("ARENA_DB_PATH", "arena.db")
DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False, "timeout": 30},
)


def init_db() -> None:
    # Import models so their tables are registered on SQLModel.metadata
    # before create_all runs.
    from app.contract import models  # noqa: F401

    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA journal_mode=WAL")
        connection.exec_driver_sql("PRAGMA busy_timeout=30000")
    SQLModel.metadata.create_all(engine)
    # create_all does not add indexes to an existing SQLite table.
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_matches_status ON matches (status)"
        )


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
