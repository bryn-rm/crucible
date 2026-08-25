"""Environment action schemas.

Actions are the structured payload an Agent.act() returns and an
Environment.step() consumes. Each environment defines its own action union;
this module holds the ones shared or specced by the build plan (negotiation,
role-play). New environments add their own action models here (or in their
own environments/<name>/actions.py) and are validated the same way: parse,
retry once on failure, forfeit the turn on repeat.
"""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field

# --- Negotiation ---


class OfferAction(BaseModel):
    type: Literal["offer"] = "offer"
    split: dict[str, int]  # item -> quantity proposed for the acting agent


class AcceptAction(BaseModel):
    type: Literal["accept"] = "accept"


class WalkAction(BaseModel):
    type: Literal["walk"] = "walk"


class ForfeitAction(BaseModel):
    """Synthetic action recorded when an agent exhausts its action retries."""

    type: Literal["forfeit"] = "forfeit"


NegotiationAction = Annotated[
    Union[OfferAction, AcceptAction, WalkAction, ForfeitAction],
    Field(discriminator="type"),
]


# --- Role-play ---


class SayAction(BaseModel):
    type: Literal["say"] = "say"
    text: str = Field(max_length=10_000)


class EndInterviewAction(BaseModel):
    type: Literal["end_interview"] = "end_interview"


RolePlayAction = Annotated[
    Union[SayAction, EndInterviewAction, ForfeitAction],
    Field(discriminator="type"),
]
