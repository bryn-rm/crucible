"""OpenAI-backed negotiation agent (Phase 2).

Provider-specific half of LLMNegotiationAgent: streams a response via
OpenAI's Chat Completions API. Prompt-building and action parsing are
shared — see app/agents/llm_negotiation.py. Targets standard chat models
(gpt-*); the o-series reasoning models have different parameter and role
constraints and aren't handled here.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import openai

from app.agents.llm_negotiation import LLMNegotiationAgent
from app.contract.interfaces import AgentConfig

MAX_COMPLETION_TOKENS = 1024


class OpenAINegotiationAgent(LLMNegotiationAgent):
    def __init__(self, config: AgentConfig, client: openai.AsyncOpenAI | None = None) -> None:
        super().__init__(config)
        self._client = client or openai.AsyncOpenAI()

    async def _stream_reasoning(
        self,
        system: str,
        user_message: str,
        on_chunk: Callable[[str], Awaitable[None]] | None,
    ) -> str:
        chunks: list[str] = []
        stream = await self._client.chat.completions.create(
            model=self.config.model,
            max_completion_tokens=MAX_COMPLETION_TOKENS,
            temperature=self.config.temperature,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_message},
            ],
            stream=True,
        )
        async for event in stream:
            delta = event.choices[0].delta.content
            if not delta:
                continue
            chunks.append(delta)
            if on_chunk is not None:
                await on_chunk(delta)

        return "".join(chunks)
