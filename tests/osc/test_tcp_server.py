"""The OSC TCP server connection: many peers in, one send out to all."""

import socket
import threading
import time
from collections.abc import Callable, Iterator

import pytest
from pythonosc.osc_message import OscMessage

from haybale_protokol.drivers import Message
from haybale_protokol_osc.driver import TcpServerConnection, build_message
from haybale_protokol_osc.framing import FrameReader, encode_frame


def _wait(predicate: Callable[[], bool], timeout: float = 3.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


@pytest.fixture(params=["1.0", "1.1"])
def server(request: pytest.FixtureRequest) -> Iterator[tuple[TcpServerConnection, list[Message]]]:
    connection = TcpServerConnection("127.0.0.1", 0, request.param)
    received: list[Message] = []
    connection.start(received.append)
    yield connection, received
    connection.close()


def _peer(connection: TcpServerConnection) -> socket.socket:
    sock = socket.create_connection(("127.0.0.1", connection.port), timeout=2.0)
    return sock


def _send(sock: socket.socket, framing: str, address: str, *args: object) -> None:
    sock.sendall(encode_frame(build_message(address, tuple(args), None), framing))  # type: ignore[arg-type]


def _recv(sock: socket.socket, framing: str) -> OscMessage:
    reader = FrameReader(framing)  # type: ignore[arg-type]
    while True:
        packets = reader.feed(sock.recv(4096))
        if packets:
            return OscMessage(packets[0])


def test_server_receives_from_two_peers(server: tuple[TcpServerConnection, list[Message]]) -> None:
    connection, received = server
    a, b = _peer(connection), _peer(connection)
    try:
        _send(a, connection.framing, "/a", 1)
        _send(b, connection.framing, "/b", 2)
        assert _wait(lambda: sorted(m.address for m in received) == ["/a", "/b"])
    finally:
        a.close()
        b.close()


def test_send_goes_to_all_peers(server: tuple[TcpServerConnection, list[Message]]) -> None:
    connection, _ = server
    a, b = _peer(connection), _peer(connection)
    try:
        assert _wait(lambda: connection.peers == 2)
        assert connection.send(Message("/all", (0.5,), 0.0, {"types": "f"}))
        for sock in (a, b):
            message = _recv(sock, connection.framing)
            assert (message.address, message.params) == ("/all", [0.5])
        assert "2 peers" in connection.status
    finally:
        a.close()
        b.close()


def test_send_without_peers_is_dropped(server: tuple[TcpServerConnection, list[Message]]) -> None:
    connection, _ = server
    assert not connection.send(Message("/x", (), 0.0))
    assert "dropped 1" in connection.status


def test_peer_disconnect_is_removed(server: tuple[TcpServerConnection, list[Message]]) -> None:
    connection, _ = server
    a = _peer(connection)
    assert _wait(lambda: connection.peers == 1)
    a.close()
    assert _wait(lambda: connection.peers == 0)


def test_garbage_peer_is_dropped() -> None:
    connection = TcpServerConnection("127.0.0.1", 0, "1.0")
    received: list[Message] = []
    connection.start(received.append)
    good, bad = _peer(connection), _peer(connection)
    try:
        assert _wait(lambda: connection.peers == 2)
        bad.sendall(b"\xff\xff\xff\xff")
        assert _wait(lambda: connection.peers == 1)
        assert "1 bad" in connection.status
        _send(good, "1.0", "/still", 1)
        assert _wait(lambda: [m.address for m in received] == ["/still"])
    finally:
        good.close()
        bad.close()
        connection.close()


def test_port_in_use_is_status() -> None:
    blocker = socket.socket()
    blocker.bind(("127.0.0.1", 0))
    blocker.listen(1)
    try:
        connection = TcpServerConnection("127.0.0.1", blocker.getsockname()[1], "1.1")
        with pytest.raises(OSError, match="in use"):
            connection.start(lambda m: None)
    finally:
        blocker.close()


def test_close_stops_all_threads() -> None:
    connection = TcpServerConnection("127.0.0.1", 0, "1.1")
    connection.start(lambda m: None)
    peers = [_peer(connection) for _ in range(3)]
    assert _wait(lambda: connection.peers == 3)
    started = time.monotonic()
    connection.close()
    connection.close()
    assert time.monotonic() - started < 1.5
    assert not any(t.name.startswith("protokol-osc-tcp-") and t.is_alive() for t in threading.enumerate())
    for sock in peers:
        sock.close()


def test_restart_on_same_port_after_peers() -> None:
    first = TcpServerConnection("127.0.0.1", 0, "1.1")
    first.start(lambda m: None)
    port = first.port
    peers = [_peer(first) for _ in range(2)]
    assert _wait(lambda: first.peers == 2)
    first.close()
    for sock in peers:
        sock.close()
    second = TcpServerConnection("127.0.0.1", port, "1.1")
    second.start(lambda m: None)
    second.close()


def test_peer_sockets_have_keepalive(server: tuple[TcpServerConnection, list[Message]]) -> None:
    connection, _ = server
    sock = _peer(connection)
    try:
        assert _wait(lambda: connection.peers == 1)
        peer = next(iter(connection._peers))
        assert peer.getsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE) != 0
    finally:
        sock.close()


class _SlowPeer:
    """Stands in for a peer socket whose sendall hands over its bytes in two parts."""

    def __init__(self) -> None:
        self.data = bytearray()

    def sendall(self, frame: bytes) -> None:
        half = len(frame) // 2
        self.data.extend(frame[:half])
        time.sleep(0.001)
        self.data.extend(frame[half:])


def test_concurrent_sends_do_not_interleave() -> None:
    connection = TcpServerConnection("127.0.0.1", 0, "1.0")
    slow = _SlowPeer()
    connection._peers[slow] = threading.current_thread()  # type: ignore[index]

    def burst(n: int) -> None:
        for i in range(50):
            connection.send(Message(f"/t{n}", (i,), 0.0))

    threads = [threading.Thread(target=burst, args=(n,)) for n in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    packets = FrameReader("1.0").feed(bytes(slow.data))
    assert len(packets) == 200
    assert all(OscMessage(p).address.startswith("/t") for p in packets)
