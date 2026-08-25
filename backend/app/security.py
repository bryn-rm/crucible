"""Authentication and request-boundary configuration for paid arena operations."""

from __future__ import annotations

import hmac
import os
from typing import Annotated

from fastapi import Header, HTTPException

DEFAULT_ALLOWED_MODELS = {
    "scripted",
    "claude-haiku-4-5",
    "claude-sonnet-4-20250514",
    "gpt-4o",
}


def allowed_models() -> set[str]:
    configured = os.environ.get("ALLOWED_MODELS")
    if configured is None:
        return DEFAULT_ALLOWED_MODELS
    return {model.strip() for model in configured.split(",") if model.strip()}


def configured_origins() -> set[str]:
    return {
        origin.strip()
        for origin in os.environ.get("ALLOWED_ORIGINS", "http://localhost:5173").split(",")
        if origin.strip()
    }


def token_is_valid(candidate: str | None) -> bool:
    expected = os.environ.get("ARENA_API_TOKEN")
    return bool(expected and candidate and hmac.compare_digest(candidate, expected))


def require_api_token(
    token: Annotated[str | None, Header(alias="X-Arena-Token")] = None,
) -> None:
    if not os.environ.get("ARENA_API_TOKEN"):
        raise HTTPException(status_code=503, detail="ARENA_API_TOKEN is not configured")
    if not token_is_valid(token):
        raise HTTPException(status_code=401, detail="invalid arena token")
