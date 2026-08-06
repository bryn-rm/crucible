"""Name -> Environment lookup used by the orchestrator and the setup screen.

Register a new environment here once it exists; nothing else in the
orchestrator changes.
"""

from __future__ import annotations

from app.contract.interfaces import Environment

ENVIRONMENTS: dict[str, type[Environment]] = {}


def get_environment(name: str) -> Environment:
    try:
        return ENVIRONMENTS[name]()
    except KeyError as exc:
        raise ValueError(f"Unknown environment: {name!r}. Known: {sorted(ENVIRONMENTS)}") from exc
