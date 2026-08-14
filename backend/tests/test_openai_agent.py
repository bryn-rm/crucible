import pytest

from app.agents.openai_agent import OpenAINegotiationAgent
from app.contract.interfaces import AgentConfig


class _FakeChunk:
    def __init__(self, text: str | None) -> None:
        self.choices = [_FakeChoice(text)]


class _FakeChoice:
    def __init__(self, text: str | None) -> None:
        self.delta = _FakeDelta(text)


class _FakeDelta:
    def __init__(self, text: str | None) -> None:
        self.content = text


class _FakeStream:
    def __init__(self, chunks: list[str]) -> None:
        self._chunks = chunks

    def __aiter__(self):
        return self._agen()

    async def _agen(self):
        for chunk in self._chunks:
            yield _FakeChunk(chunk)
        yield _FakeChunk(None)  # a trailing empty delta, as real streams send


class _FakeCompletions:
    def __init__(self, chunks: list[str], calls: list[dict]) -> None:
        self._chunks = chunks
        self._calls = calls

    async def create(self, **kwargs: object) -> _FakeStream:
        self._calls.append(kwargs)
        return _FakeStream(self._chunks)


class _FakeChat:
    def __init__(self, chunks: list[str], calls: list[dict]) -> None:
        self.completions = _FakeCompletions(chunks, calls)


class _FakeClient:
    def __init__(self, chunks: list[str]) -> None:
        self.calls: list[dict] = []
        self.chat = _FakeChat(chunks, self.calls)


def make_agent(
    chunks: list[str], temperature: float = 1.0
) -> tuple[OpenAINegotiationAgent, _FakeClient]:
    client = _FakeClient(chunks)
    agent = OpenAINegotiationAgent(
        AgentConfig(
            id="agent_a",
            label="Alice",
            model="gpt-4o",
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
async def test_uses_max_completion_tokens_not_max_tokens():
    agent, client = make_agent(['{"type": "accept"}'])

    await agent.act(OBSERVATION)

    assert "max_completion_tokens" in client.calls[0]
    assert "max_tokens" not in client.calls[0]


@pytest.mark.asyncio
async def test_passes_configured_temperature_to_openai():
    agent, client = make_agent(['{"type": "accept"}'], temperature=0.35)

    await agent.act(OBSERVATION)

    assert client.calls[0]["temperature"] == 0.35
