"""Fixtures for the OSC haybale's tests: free ports and a listening test socket."""

from __future__ import annotations

import socket
import threading
from collections.abc import Iterator

import pytest


def free_udp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


@pytest.fixture
def udp_port() -> int:
    return free_udp_port()


@pytest.fixture
def listener() -> Iterator[socket.socket]:
    """A bound UDP socket on 127.0.0.1 with a 2 s timeout, standing in for a remote OSC peer."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    sock.settimeout(2.0)
    yield sock
    sock.close()


class TestPeer:
    """A TCP OSC peer for tests: listens on 127.0.0.1, records packets, sends to its clients."""

    __test__ = False

    def __init__(self, framing: str, port: int = 0) -> None:
        from haybale_protokol_osc.framing import FrameReader

        self.framing = framing
        self._reader_cls = FrameReader
        self.packets: list[bytes] = []
        self.accepts = 0
        self.clients: list[socket.socket] = []
        self._lock = threading.Lock()
        self._listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._listener.bind(("127.0.0.1", port))
        self._listener.listen(8)
        self._listener.settimeout(0.1)
        self.port = int(self._listener.getsockname()[1])
        self._stop = threading.Event()
        self._threads = [threading.Thread(target=self._accept, daemon=True)]
        self._threads[0].start()

    def _accept(self) -> None:
        while not self._stop.is_set():
            try:
                conn, _ = self._listener.accept()
            except (TimeoutError, OSError):
                continue
            conn.settimeout(0.1)
            with self._lock:
                self.accepts += 1
                self.clients.append(conn)
            thread = threading.Thread(target=self._read, args=(conn,), daemon=True)
            self._threads.append(thread)
            thread.start()

    def _read(self, conn: socket.socket) -> None:
        reader = self._reader_cls(self.framing)  # type: ignore[arg-type]
        while not self._stop.is_set():
            try:
                data = conn.recv(65536)
            except TimeoutError:
                continue
            except OSError:
                return
            if not data:
                return
            with self._lock:
                self.packets.extend(reader.feed(data))

    def send(self, address: str, *args: object) -> None:
        from haybale_protokol_osc.driver import build_message
        from haybale_protokol_osc.framing import encode_frame

        frame = encode_frame(build_message(address, tuple(args), None), self.framing)  # type: ignore[arg-type]
        with self._lock:
            for conn in self.clients:
                conn.sendall(frame)

    def send_raw(self, data: bytes) -> None:
        with self._lock:
            for conn in self.clients:
                conn.sendall(data)

    def messages(self) -> list[tuple[str, list[object]]]:
        from pythonosc.osc_message import OscMessage

        with self._lock:
            return [(m.address, m.params) for m in (OscMessage(p) for p in self.packets)]

    def stop(self) -> None:
        self._stop.set()
        with self._lock:
            for conn in self.clients:
                try:
                    conn.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                conn.close()
            self.clients.clear()
        self._listener.close()
        for thread in self._threads:
            thread.join(timeout=1.0)


@pytest.fixture(params=["1.0", "1.1"])
def peer(request: pytest.FixtureRequest) -> Iterator[TestPeer]:
    server = TestPeer(request.param)
    yield server
    server.stop()
