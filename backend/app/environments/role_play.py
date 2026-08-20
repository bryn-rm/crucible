"""Concrete interviewer/interviewee role-play environment.

The scenario intentionally stays fixed for v1: agent 0 is the interviewer and
agent 1 is the candidate. Each receives role-specific private context while the
public state contains only the spoken transcript.
"""

from __future__ import annotations

import copy
from typing import Any

from app.contract.actions import RolePlayAction
from app.contract.interfaces import Action, Environment, Observation, State, StepResult

DEFAULT_MAX_TURNS = 8
DEFAULT_JOB_DESCRIPTION = (
    "Backend engineer building reliable Python APIs and asynchronous LLM workflows. "
    "The role values clear communication, testing, and pragmatic system design."
)
DEFAULT_CV = (
    "Software engineer with Python, FastAPI, TypeScript, and applied LLM experience. "
    "Built streaming services and evaluation pipelines, with an emphasis on reliability."
)


class InterviewRolePlayEnvironment(Environment):
    name = "role_play"

    def __init__(
        self,
        job_description: str = DEFAULT_JOB_DESCRIPTION,
        candidate_cv: str = DEFAULT_CV,
        max_turns: int = DEFAULT_MAX_TURNS,
    ) -> None:
        self.job_description = job_description
        self.candidate_cv = candidate_cv
        self.max_turns = max_turns

    def reset(self, agent_ids: list[str]) -> State:
        if len(agent_ids) != 2:
            raise ValueError(f"role_play requires exactly 2 agents, got {len(agent_ids)}")
        interviewer, candidate = agent_ids
        return {
            "agent_ids": list(agent_ids),
            "roles": {interviewer: "interviewer", candidate: "candidate"},
            "private_context": {
                interviewer: {"job_description": self.job_description},
                candidate: {"cv": self.candidate_cv},
            },
            "transcript": [],
            "status": "open",
            "max_turns": self.max_turns,
        }

    def observe(self, state: State, agent_id: str) -> Observation:
        if agent_id not in state["roles"]:
            raise ValueError(f"unknown agent {agent_id!r}")
        return {
            "scenario": "job_interview",
            "role": state["roles"][agent_id],
            "private_context": copy.deepcopy(state["private_context"][agent_id]),
            "transcript": copy.deepcopy(state["transcript"]),
            "turns_taken": len(state["transcript"]),
            "max_turns": state["max_turns"],
        }

    def action_schema(self, agent_id: str) -> type:
        return RolePlayAction

    def step(self, state: State, agent_id: str, action: Action) -> StepResult:
        new_state = copy.deepcopy(state)
        if action["type"] == "say":
            text = action["text"].strip()
            if not text:
                raise ValueError("utterance cannot be empty")
            new_state["transcript"].append(
                {
                    "turn_no": len(state["transcript"]) + 1,
                    "agent_id": agent_id,
                    "role": state["roles"][agent_id],
                    "text": text,
                }
            )
        elif action["type"] == "end_interview":
            if state["roles"][agent_id] != "interviewer":
                raise ValueError("only the interviewer may end the interview")
            new_state["status"] = "completed"
        else:
            raise ValueError(f"unknown action type {action['type']!r}")
        return StepResult(state=new_state)

    def is_terminal(self, state: State) -> bool:
        return state["status"] != "open" or len(state["transcript"]) >= state["max_turns"]

    def score(self, state: State) -> dict[str, float]:
        return {}

    def public_view(self, state: State) -> dict[str, Any]:
        return {
            "scenario": "job_interview",
            "roles": dict(state["roles"]),
            "transcript": copy.deepcopy(state["transcript"]),
            "status": state["status"],
            "turns_taken": len(state["transcript"]),
            "max_turns": state["max_turns"],
        }
