import pytest

from collections.abc import Awaitable, Callable

from app.agents.role_play import ScriptedRolePlayAgent
from app.contract.interfaces import Action, Agent, AgentConfig, Observation
from app.environments.role_play import InterviewRolePlayEnvironment
from app.orchestrator import MatchOrchestrator

AGENTS = ["interviewer", "candidate"]


class EndingInterviewer(Agent):
    async def act(
        self,
        observation: Observation,
        on_chunk: Callable[[str], Awaitable[None]] | None = None,
    ) -> Action:
        return {"type": "end_interview"}


def test_private_context_is_role_scoped_and_redacted_from_public_view():
    env = InterviewRolePlayEnvironment(job_description="SECRET JD", candidate_cv="SECRET CV")
    state = env.reset(AGENTS)

    interviewer = env.observe(state, "interviewer")
    candidate = env.observe(state, "candidate")
    public = env.public_view(state)

    assert interviewer["private_context"] == {"job_description": "SECRET JD"}
    assert candidate["private_context"] == {"cv": "SECRET CV"}
    assert "SECRET JD" not in str(candidate)
    assert "SECRET CV" not in str(interviewer)
    assert "private_context" not in public
    assert "SECRET" not in str(public)


def test_reset_rejects_duplicate_agent_ids():
    with pytest.raises(ValueError, match="unique"):
        InterviewRolePlayEnvironment().reset(["same", "same"])


def test_say_appends_public_transcript_without_mutating_input():
    env = InterviewRolePlayEnvironment()
    state = env.reset(AGENTS)
    result = env.step(state, "interviewer", {"type": "say", "text": "Tell me about yourself."})

    assert state["transcript"] == []
    assert result.state["transcript"][0]["role"] == "interviewer"
    assert result.state["transcript"][0]["text"] == "Tell me about yourself."


def test_say_enforces_turn_order_and_length_limit():
    env = InterviewRolePlayEnvironment()
    state = env.reset(AGENTS)
    with pytest.raises(ValueError, match="expected"):
        env.step(state, "candidate", {"type": "say", "text": "Going first"})
    with pytest.raises(ValueError, match="exceeds"):
        env.step(state, "interviewer", {"type": "say", "text": "x" * 10_001})


def test_only_interviewer_can_end_interview():
    env = InterviewRolePlayEnvironment()
    state = env.reset(AGENTS)
    with pytest.raises(ValueError):
        env.step(state, "candidate", {"type": "end_interview"})
    ended = env.step(state, "interviewer", {"type": "end_interview"}).state
    assert env.is_terminal(ended)


@pytest.mark.asyncio
async def test_scripted_role_play_runs_and_has_no_objective_scores():
    env = InterviewRolePlayEnvironment(max_turns=4)
    agents = [
        ScriptedRolePlayAgent(AgentConfig(id="interviewer", label="Iris", model="scripted", strategy_prompt="probe")),
        ScriptedRolePlayAgent(AgentConfig(id="candidate", label="Casey", model="scripted", strategy_prompt="be specific")),
    ]
    events = [event async for event in MatchOrchestrator(env, agents).run("role-match")]

    assert events[0].environment == "role_play"
    assert events[-2].type == "score_update"
    assert events[-2].scores == {}
    assert events[-1].final_scores == {}
    states = [event.state for event in events if event.type == "state_update"]
    assert len(states[-1]["transcript"]) == 4
    assert "private_context" not in str(states)


@pytest.mark.asyncio
async def test_explicit_end_interview_emits_completed_reason_and_outcome():
    env = InterviewRolePlayEnvironment()
    agents = [
        EndingInterviewer(AgentConfig(id="interviewer", label="Iris", model="scripted", strategy_prompt="finish")),
        ScriptedRolePlayAgent(AgentConfig(id="candidate", label="Casey", model="scripted", strategy_prompt="answer")),
    ]

    events = [event async for event in MatchOrchestrator(env, agents).run("ended-role-match")]
    ended = events[-1]

    assert ended.type == "match_ended"
    assert ended.reason == "completed"
    assert ended.outcome == "Interview completed"
    assert ended.final_scores == {}
