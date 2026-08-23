"""Claude-backed negotiation agent (Phase 2).

Provider-specific half of LLMNegotiationAgent: streams a Claude response via
the Anthropic Messages API. Prompt-building and action parsing are shared —
see app/agents/llm_negotiation.py.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import anthropic

from app.agents.llm_negotiation import LLMNegotiationAgent
from app.contract.interfaces import AgentConfig

MAX_TOKENS = 1024
PROVIDER_TIMEOUT_SECONDS = 60.0
PROVIDER_MAX_RETRIES = 2


class ClaudeNegotiationAgent(LLMNegotiationAgent):
    def __init__(self, config: AgentConfig, client: anthropic.AsyncAnthropic | None = None) -> None:
        super().__init__(config)
        self._client = client or anthropic.AsyncAnthropic(
            timeout=PROVIDER_TIMEOUT_SECONDS,
            max_retries=PROVIDER_MAX_RETRIES,
        )

    async def _stream_reasoning(
        self,
        system: str,
        user_message: str,
        on_chunk: Callable[[str], Awaitable[None]] | None,
    ) -> str:
        chunks: list[str] = []
        async with self._client.messages.stream(
            model=self.config.model,
            max_tokens=MAX_TOKENS,
            temperature=self.config.temperature,
            system=system,
            messages=[{"role": "user", "content": user_message}],
        ) as stream:
            async for text in stream.text_stream:
                chunks.append(text)
                if on_chunk is not None:
                    await on_chunk(text)

        return "".join(chunks)
