"""The TCP client reconnect tests with TestPeer's accept thread scheduled late, as on a busy runner (#17).

The kernel completes the handshake before the server's accept thread has taken the connection, so
``client.connected`` alone does not mean the server can send yet. These failed before the tests
waited for ``server.accepts == 1`` as well.
"""

import time

import pytest

import tests.osc.conftest as conftest
from tests.osc import test_tcp_client


@pytest.fixture(autouse=True)
def slow_accept(monkeypatch: pytest.MonkeyPatch) -> None:
    """The accept thread starts late; the kernel completes the handshake anyway."""
    real_accept = conftest.TestPeer._accept

    def late(self: object) -> None:
        time.sleep(0.5)
        real_accept(self)  # type: ignore[arg-type]

    monkeypatch.setattr(conftest.TestPeer, "_accept", late)


def test_bad_frame_reconnects() -> None:
    test_tcp_client.test_bad_frame_reconnects()


def test_invalid_slip_escape_reconnects() -> None:
    test_tcp_client.test_invalid_slip_escape_reconnects()
