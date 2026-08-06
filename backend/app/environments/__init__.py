"""Pluggable environments. Each implements app.contract.interfaces.Environment.

Phase 1 ships `negotiation` first (objective payoffs, de-risks the
orchestrator without LLM latency). `role_play` follows in Phase 5.
"""

from app.environments.registry import ENVIRONMENTS, get_environment

__all__ = ["ENVIRONMENTS", "get_environment"]
