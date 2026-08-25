import pytest

from app.agents.claude_agent import ClaudeNegotiationAgent
from app.contract.interfaces import AgentConfig


class _FakeStream:
    def __init__(self, chunks: list[str]) -> None:
        self._chunks = chunks

    async def __aenter__(self) -> "_FakeStream":
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    @property
    def text_stream(self):
        return self._agen()

    async def _agen(self):
        for chunk in self._chunks:
            yield chunk


class _FakeMessages:
    def __init__(self, chunks: list[str], calls: list[dict]) -> None:
        self._chunks = chunks
        self._calls = calls

    def stream(self, **kwargs: object) -> _FakeStream:
        self._calls.append(kwargs)
        return _FakeStream(self._chunks)


class _FakeClient:
    def __init__(self, chunks: list[str]) -> None:
        self.calls: list[dict] = []
        self.messages = _FakeMessages(chunks, self.calls)


def make_agent(
    chunks: list[str], temperature: float = 1.0
) -> tuple[ClaudeNegotiationAgent, _FakeClient]:
    client = _FakeClient(chunks)
    agent = ClaudeNegotiationAgent(
        AgentConfig(
            id="agent_a",
            label="Alice",
            model="claude-haiku-4-5",
            strategy_prompt="greedy",
            temperature=temperature,
        ),
        client=client,
    )
    return agent, client


OBSERVATION = {
    "items": {"books": 3},
    "valuation": {"books": 10},
    "history": [],
    "standing_offer": None,
    "turns_taken": 0,
    "max_turns": 10,
}


@pytest.mark.asyncio
async def test_parses_trailing_json_action():
    agent, _ = make_agent(['I will offer generously. ', '{"type": "offer", "split": {"books": 1}}'])

    action = await agent.act(OBSERVATION)

    assert action == {"type": "offer", "split": {"books": 1}}


@pytest.mark.asyncio
async def test_parses_json_action_inside_markdown_fence():
    agent, _ = make_agent(['Reasoning\n```json\n{"type":"accept"}\n```'])

    assert await agent.act(OBSERVATION) == {"type": "accept"}


@pytest.mark.asyncio
async def test_parses_final_json_action_after_earlier_json_in_reasoning():
    agent, _ = make_agent(
        ['The standing offer is {"books": 2}.\n', '{"type": "offer", "split": {"books": 1}}']
    )

    action = await agent.act(OBSERVATION)

    assert action == {"type": "offer", "split": {"books": 1}}


@pytest.mark.asyncio
async def test_streams_chunks_live_via_on_chunk():
    chunks = ["thinking... ", '{"type": "accept"}']
    agent, _ = make_agent(chunks)
    seen: list[str] = []

    async def on_chunk(text: str) -> None:
        seen.append(text)

    await agent.act(OBSERVATION, on_chunk=on_chunk)

    assert seen == chunks


@pytest.mark.asyncio
async def test_raises_on_missing_json_action():
    agent, _ = make_agent(["I have decided not to decide."])

    with pytest.raises(ValueError):
        await agent.act(OBSERVATION)


@pytest.mark.asyncio
async def test_retry_hint_is_appended_to_the_user_message_and_not_json_dumped():
    agent, client = make_agent(['{"type": "accept"}'])
    observation = {**OBSERVATION, "retry_hint": "no standing offer to accept"}

    await agent.act(observation)

    sent = client.calls[0]["messages"][0]["content"]
    assert "no standing offer to accept" in sent
    assert '"retry_hint"' not in sent


@pytest.mark.asyncio
async def test_passes_configured_temperature_to_claude():
    agent, client = make_agent(['{"type": "accept"}'], temperature=0.35)

    await agent.act(OBSERVATION)

    assert client.calls[0]["temperature"] == 0.35
