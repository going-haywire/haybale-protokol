"""A Protocol driver and Connection that need no network, for tests of the base."""

from __future__ import annotations

from collections.abc import Callable, Hashable

from haybale_protokol.devices import Device
from haybale_protokol.drivers import LineKey, Message
from haybale_protokol.gates import Gate


class FakeConnection:
    """Delivers what a test pushes; records what is sent."""

    def __init__(self, fail: str | None = None) -> None:
        self.fail = fail
        self.deliver: Callable[[Message], None] | None = None
        self.sent: list[Message] = []
        self.starts = 0
        self.closed = False
        self.status = "idle"

    def start(self, deliver: Callable[[Message], None]) -> None:
        if self.fail:
            raise OSError(self.fail)
        self.starts += 1
        self.deliver = deliver
        self.status = "open"

    def send(self, message: Message) -> bool:
        self.sent.append(message)
        return True

    def close(self) -> None:
        self.closed = True
        self.status = "closed"

    def push(self, address: str, *args: object) -> None:
        assert self.deliver is not None, "connection not started"
        self.deliver(Message(address, tuple(args), 0.0))


class FakeDriver:
    """Protocol ``fake``: one line per ``port`` option; keeps every connection it opened."""

    protocol = "fake"

    def __init__(self, fail: str | None = None) -> None:
        self.fail = fail
        self.connections: list[FakeConnection] = []

    def line_key(self, gate: Gate, device: Device | None) -> LineKey:
        return LineKey("fake", f"{gate.direction} {gate.options.get('port', 0)}")

    def open(self, key: LineKey, gate: Gate, device: Device | None) -> FakeConnection:
        connection = FakeConnection(self.fail)
        self.connections.append(connection)
        return connection

    def line_options(self, gate: Gate) -> dict[str, object]:
        return {}

    def cache_key(self, message: Message) -> Hashable:
        return message.address

    def describe(self, message: Message) -> str:
        return f"{message.address} {message.args}"
