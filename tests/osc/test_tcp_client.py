"""The OSC TCP client connection: receive, send, drop while disconnected, reconnect."""

import socket
import time
from collections.abc import Callable

from haybale_protokol.drivers import Message
from haybale_protokol_osc.driver import TcpClientConnection
from tests.osc.conftest import TestPeer


def _wait(predicate: Callable[[], bool], timeout: float = 3.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


def _client(port: int, framing: str) -> tuple[TcpClientConnection, list[Message]]:
    received: list[Message] = []
    client = TcpClientConnection("127.0.0.1", port, framing)  # type: ignore[arg-type]
    client.start(received.append)
    return client, received


def _free_tcp_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def test_client_receives_from_server(peer: TestPeer) -> None:
    client, received = _client(peer.port, peer.framing)
    try:
        assert _wait(lambda: peer.accepts == 1 and client.connected)
        peer.send("/fader", 0.5)
        assert _wait(lambda: len(received) == 1)
        assert (received[0].address, received[0].args) == ("/fader", (0.5,))
    finally:
        client.close()


def test_client_sends_to_server(peer: TestPeer) -> None:
    client, _ = _client(peer.port, peer.framing)
    try:
        assert _wait(lambda: client.connected)
        assert client.send(Message("/x", (1, "a"), 0.0, {"types": "is"}))
        assert _wait(lambda: peer.messages() == [("/x", [1, "a"])])
        assert "sent 1" in client.status
    finally:
        client.close()


def test_sends_while_disconnected_are_dropped_and_counted() -> None:
    client, _ = _client(_free_tcp_port(), "1.1")
    try:
        assert not client.send(Message("/x", (1,), 0.0))
        assert not client.send(Message("/x", (2,), 0.0))
        assert "dropped 2" in client.status
    finally:
        client.close()


def test_reconnecting_status_counts_attempts() -> None:
    client, _ = _client(_free_tcp_port(), "1.1")
    try:
        assert _wait(lambda: "reconnecting (2)" in client.status, timeout=3.0)
    finally:
        client.close()


def test_reconnects_after_peer_restart() -> None:
    first = TestPeer("1.1")
    port = first.port
    client, received = _client(port, "1.1")
    try:
        assert _wait(lambda: client.connected)
        first.stop()
        assert _wait(lambda: "reconnecting" in client.status)
        assert not client.send(Message("/lost", (), 0.0))
        second = TestPeer("1.1", port=port)
        try:
            assert _wait(lambda: client.connected and second.accepts == 1, timeout=5.0)
            second.send("/back", 1)
            assert _wait(lambda: [m.address for m in received] == ["/back"])
        finally:
            second.stop()
    finally:
        client.close()


def test_close_while_connecting() -> None:
    for host in ("127.0.0.1", "10.255.255.1"):
        client = TcpClientConnection(host, _free_tcp_port() if host == "127.0.0.1" else 9, "1.1")
        client.start(lambda m: None)
        time.sleep(0.1)
        started = time.monotonic()
        client.close()
        assert time.monotonic() - started < 1.5
        assert client.thread is not None
        assert not client.thread.is_alive()


def test_bad_frame_reconnects() -> None:
    server = TestPeer("1.0")
    client, received = _client(server.port, "1.0")
    try:
        assert _wait(lambda: client.connected)
        server.send_raw(b"\xff\xff\xff\xff")
        assert _wait(lambda: server.accepts == 2, timeout=3.0), "client should drop and reconnect"
        assert "1 bad" in client.status
        server.send("/ok", 1)
        assert _wait(lambda: [m.address for m in received] == ["/ok"])
    finally:
        client.close()
        server.stop()



def test_invalid_slip_escape_reconnects() -> None:
    server = TestPeer("1.1")
    client, received = _client(server.port, "1.1")
    try:
        assert _wait(lambda: client.connected)
        server.send_raw(b"\xc0\xdb\x00\xc0")
        assert _wait(lambda: server.accepts == 2, timeout=3.0), "client should drop and reconnect"
        assert "1 bad" in client.status
        server.send("/ok", 1)
        assert _wait(lambda: [m.address for m in received] == ["/ok"])
    finally:
        client.close()
        server.stop()


def test_client_socket_has_keepalive() -> None:
    server = TestPeer("1.1")
    client, _ = _client(server.port, "1.1")
    try:
        assert _wait(lambda: client.connected)
        sock = client._sock
        assert sock is not None
        assert sock.getsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE) != 0
    finally:
        client.close()
        server.stop()
