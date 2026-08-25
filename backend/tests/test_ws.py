import asyncio

import pytest

from app.api.ws import _writer
from app.contract.events import ErrorEvent


class ClosedSocket:
    def __init__(self) -> None:
        self.closed = False

    async def send_text(self, text: str) -> None:
        raise RuntimeError("socket is closed")

    async def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_writer_closes_socket_when_send_fails():
    socket = ClosedSocket()
    queue = asyncio.Queue()
    await queue.put(ErrorEvent(recoverable=True, message="test"))

    await _writer(socket, queue)

    assert socket.closed
