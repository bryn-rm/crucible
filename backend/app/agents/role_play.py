"""Role-play agents for the fixed interview scenario."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable

import anthropic
import openai

from app.agents.llm_negotiation import _parse_action
from app.contract.interfaces import Action, Agent, AgentConfig, Observation

MAX_TOKENS = 1024


def _prompt(config: AgentConfig, observation: Observation) -> tuple[str, str]:
    role = observation["role"]
    system = f"""You are {config.label}, playing the {role} in a realistic job interview.

Role strategy: {config.strategy_prompt}

Stay in character and use your private context without explicitly calling it private. Keep each
turn focused and conversational. End with exactly one JSON action on its own line and nothing after:
- {{"type": "say", "text": "your next spoken utterance"}}
- {{"type": "end_interview"}} (interviewer only, when the interview is complete)
"""
    payload = {k: v for k, v in observation.items() if k != "retry_hint"}
    user = json.dumps(payload)
    if observation.get("retry_hint"):
        user += f"\nYour previous action was invalid: {observation['retry_hint']}. Return a valid action."
    return system, user


class ScriptedRolePlayAgent(Agent):
    async def act(
        self,
        observation: Observation,
        on_chunk: Callable[[str], Awaitable[None]] | None = None,
    ) -> Action:
        role = observation["role"]
        turns = observation["turns_taken"]
        if role == "interviewer":
            text = (
                "Welcome. Could you describe a project where you designed a reliable asynchronous system?"
                if turns == 0
                else "What trade-off did you make, and how did you verify the system behaved correctly?"
            )
        else:
            text = (
                "I built a streaming FastAPI service and focused on cancellation, validation, and observability."
                if turns <= 1
                else "I kept one writer per stream, added failure-path tests, and measured latency before optimizing."
            )
        if on_chunk is not None:
            await on_chunk(f"[{self.config.label}] preparing a focused {role} response... ")
        return {"type": "say", "text": text}


class ClaudeRolePlayAgent(Agent):
    def __init__(self, config: AgentConfig, client: anthropic.AsyncAnthropic | None = None) -> None:
        super().__init__(config)
        self._client = client or anthropic.AsyncAnthropic()

    async def act(self, observation: Observation, on_chunk=None) -> Action:
        system, user = _prompt(self.config, observation)
        chunks: list[str] = []
        async with self._client.messages.stream(
            model=self.config.model,
            max_tokens=MAX_TOKENS,
            temperature=self.config.temperature,
            system=system,
            messages=[{"role": "user", "content": user}],
        ) as stream:
            async for text in stream.text_stream:
                chunks.append(text)
                if on_chunk is not None:
                    await on_chunk(text)
        return _parse_action("".join(chunks))


class OpenAIRolePlayAgent(Agent):
    def __init__(self, config: AgentConfig, client: openai.AsyncOpenAI | None = None) -> None:
        super().__init__(config)
        self._client = client or openai.AsyncOpenAI()

    async def act(self, observation: Observation, on_chunk=None) -> Action:
        system, user = _prompt(self.config, observation)
        chunks: list[str] = []
        stream = await self._client.chat.completions.create(
            model=self.config.model,
            max_completion_tokens=MAX_TOKENS,
            temperature=self.config.temperature,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            stream=True,
        )
        async for event in stream:
            text = event.choices[0].delta.content
            if not text:
                continue
            chunks.append(text)
            if on_chunk is not None:
                await on_chunk(text)
        return _parse_action("".join(chunks))
