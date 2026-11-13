"""A Line: opened by its first user, closed after the last one plus the grace period."""

import time

import pytest

from haybale_protokol.drivers import LineKey, Message
from haybale_protokol.line import Line, LineOpenError
from tests.fakes import FakeConnection


def _line(connection: FakeConnection, grace: float = 0.05) -> Line:
    return Line(LineKey("fake", "in 1"), connection, lambda m: m.address, lambda: grace)


def test_first_user_opens_last_closes_after_grace() -> None:
    connection = FakeConnection()
    line = _line(connection)
    assert not line.is_open
    token = line.add_user()
    assert line.is_open
    assert connection.starts == 1
    line.remove_user(token)
    assert line.is_open, "closes only after the grace period"
    time.sleep(0.15)
    assert not line.is_open
    assert connection.closed


def test_zero_grace_closes_at_once() -> None:
    connection = FakeConnection()
    closed: list[Line] = []
    line = _line(connection, grace=0)
    line.on_closed = closed.append
    line.remove_user(line.add_user())
    assert not line.is_open
    assert closed == [line]


def test_reacquire_within_grace_keeps_line() -> None:
    connection = FakeConnection()
    line = _line(connection)
    line.remove_user(line.add_user(lambda m: None))
    connection.push("/a", 1)
    line.add_user()
    time.sleep(0.15)
    assert line.is_open
    assert connection.starts == 1
    assert not connection.closed
    assert [m.args for m in line.cached()] == [(1,)]


def test_released_subscriber_gets_nothing() -> None:
    connection = FakeConnection()
    line = _line(connection)
    seen: list[Message] = []
    keep = line.add_user()
    line.remove_user(line.add_user(seen.append))
    connection.push("/a", 1)
    assert seen == []
    assert line.users == 1
    line.remove_user(keep)


def test_cache_keeps_last_per_key() -> None:
    connection = FakeConnection()
    line = _line(connection)
    line.add_user()
    for address, value in (("/a", 1), ("/b", 2), ("/a", 3)):
        connection.push(address, value)
    assert sorted((m.address, m.args) for m in line.cached()) == [("/a", (3,)), ("/b", (2,))]


def test_raising_subscriber_does_not_stop_others() -> None:
    connection = FakeConnection()
    line = _line(connection)
    seen: list[str] = []

    def broken(message: Message) -> None:
        raise RuntimeError("boom")

    line.add_user(broken)
    line.add_user(lambda m: seen.append(m.address))
    connection.push("/a")
    connection.push("/b")
    assert seen == ["/a", "/b"]


def test_open_error_sets_status_and_no_user_kept() -> None:
    line = _line(FakeConnection(fail="in use"))
    with pytest.raises(LineOpenError):
        line.add_user()
    assert line.status == "cannot open: in use"
    assert line.users == 0
    assert not line.is_open


def test_send_goes_to_connection() -> None:
    connection = FakeConnection()
    line = _line(connection)
    line.add_user()
    assert line.send(Message("/x", (1,), 0.0))
    assert [m.address for m in connection.sent] == ["/x"]


def test_send_on_closed_line_is_refused() -> None:
    connection = FakeConnection()
    assert not _line(connection).send(Message("/x", (), 0.0))
    assert connection.sent == []


def test_removing_a_token_twice_is_ignored() -> None:
    connection = FakeConnection()
    line = _line(connection, grace=0.05)
    keep = line.add_user()
    gone = line.add_user()
    line.remove_user(gone)
    line.remove_user(gone)
    assert line.users == 1
    time.sleep(0.15)
    assert line.is_open
    line.remove_user(keep)
