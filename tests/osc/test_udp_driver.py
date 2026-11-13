"""The OSC driver over UDP: receiving, splitting OSC bundles, sending, and port errors."""

import socket
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from pythonosc.osc_bundle_builder import OscBundleBuilder
from pythonosc.osc_message import OscMessage
from pythonosc.osc_message_builder import OscMessageBuilder
from pythonosc.udp_client import SimpleUDPClient

from haybale_protokol.drivers import LineKey, Message
from haybale_protokol.gates import Gate, gate_file_path, save_gates
from haybale_protokol.states.protokol_state import LineUse, ProtokolState
from haybale_protokol_osc.driver import OscDriver, UdpInConnection


def _in_gate(port: int) -> Gate:
    return Gate("in", "osc", "in", options={"transport": "udp", "port": port, "bind": "127.0.0.1"})


def _collect(connection: UdpInConnection) -> list[Message]:
    received: list[Message] = []
    connection.start(received.append)
    return received


def _wait_for(items: list[Any], count: int, timeout: float = 2.0) -> None:
    deadline = time.monotonic() + timeout
    while len(items) < count and time.monotonic() < deadline:
        time.sleep(0.01)
    assert len(items) >= count, f"got {len(items)} of {count}"


@pytest.fixture
def connection(udp_port: int) -> Iterator[UdpInConnection]:
    driver = OscDriver()
    gate = _in_gate(udp_port)
    conn = driver.open(driver.line_key(gate, None), gate, None)
    assert isinstance(conn, UdpInConnection)
    yield conn
    conn.close()


def test_line_keys() -> None:
    driver = OscDriver()
    assert driver.line_key(_in_gate(8000), None) == LineKey("osc", "udp-in 127.0.0.1:8000")
    out = Gate("out", "osc", "out", options={"port": 9000, "host": "10.0.0.2"})
    assert driver.line_key(out, None) == LineKey("osc", "udp-out 10.0.0.2:9000")
    assert driver.line_key(Gate("x", "osc", "in", options={"port": 1}), None).address == "udp-in 0.0.0.0:1"


@pytest.mark.parametrize(
    ("direction", "options", "text"),
    [
        ("in", {}, "port"),
        ("in", {"port": "x"}, "port"),
        ("out", {"port": 1}, "host"),
        ("in", {"port": 1, "transport": "sctp"}, "sctp"),
        ("two-way", {"port": 1}, "two-way"),
    ],
)
def test_bad_options_raise(direction: str, options: dict[str, Any], text: str) -> None:
    with pytest.raises(ValueError, match=text):
        OscDriver().line_key(Gate("g", "osc", direction, options=options), None)  # type: ignore[arg-type]


def test_receives_message_on_loopback(connection: UdpInConnection, udp_port: int) -> None:
    received = _collect(connection)
    SimpleUDPClient("127.0.0.1", udp_port).send_message("/fader/1", [0.5, 3])
    _wait_for(received, 1)
    assert received[0].address == "/fader/1"
    assert received[0].args == (0.5, 3)
    assert "timetag" not in received[0].extra


def test_bundle_is_split_with_timetag(connection: UdpInConnection, udp_port: int) -> None:
    received = _collect(connection)
    bundle = OscBundleBuilder(1700000000.25)
    for address in ("/a", "/b"):
        message = OscMessageBuilder(address)
        message.add_arg(1)
        bundle.add_content(message.build())
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.sendto(bundle.build().dgram, ("127.0.0.1", udp_port))
    _wait_for(received, 2)
    assert [m.address for m in received] == ["/a", "/b"]
    assert all(m.extra["timetag"] == 1700000000.25 for m in received)


def test_bad_datagram_is_counted(connection: UdpInConnection, udp_port: int) -> None:
    received = _collect(connection)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.sendto(b"garbage", ("127.0.0.1", udp_port))
    SimpleUDPClient("127.0.0.1", udp_port).send_message("/ok", 1)
    _wait_for(received, 1)
    assert connection.bad_packets == 1
    assert "1 bad" in connection.status


def test_close_stops_thread(connection: UdpInConnection) -> None:
    _collect(connection)
    thread = connection.thread
    assert thread is not None
    assert thread.is_alive()
    connection.close()
    connection.close()
    assert not thread.is_alive()


def test_port_in_use_is_status(tmp_path: Path, udp_port: int) -> None:
    blocker = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    blocker.bind(("127.0.0.1", udp_port))
    try:
        state = ProtokolState()
        state.project_root = tmp_path
        state.register_driver(OscDriver())
        save_gates(gate_file_path(tmp_path), [_in_gate(udp_port)])
        result = state.use("in", "in")
        assert isinstance(result, str)
        assert result.startswith("cannot open: ")
        assert not any(t.name.startswith("protokol-osc") and t.is_alive() for t in threading.enumerate())
    finally:
        blocker.close()


def test_bad_gate_options_is_status(tmp_path: Path) -> None:
    state = ProtokolState()
    state.project_root = tmp_path
    state.register_driver(OscDriver())
    save_gates(gate_file_path(tmp_path), [Gate("in", "osc", "in")])
    assert state.use("in", "in") == "gate 'in': OSC gate needs a port"


def test_send_reaches_socket(tmp_path: Path, listener: socket.socket) -> None:
    state = ProtokolState()
    state.project_root = tmp_path
    state.grace_s = lambda: 0.0
    state.register_driver(OscDriver())
    port = listener.getsockname()[1]
    gate = Gate("out", "osc", "out", options={"port": port, "host": "127.0.0.1"})
    save_gates(gate_file_path(tmp_path), [gate])
    use = state.use("out", "out")
    assert isinstance(use, LineUse)
    assert use.line.send(Message("/x", (0.5, 3), 0.0, {"types": "fi"}))
    data, _ = listener.recvfrom(4096)
    message = OscMessage(data)
    assert message.address == "/x"
    assert message.params == [0.5, 3]
    assert data[4:8] == b",fi\x00"
    use.release()


def test_send_without_types_infers(tmp_path: Path, listener: socket.socket) -> None:
    driver = OscDriver()
    gate = Gate("out", "osc", "out", options={"port": listener.getsockname()[1], "host": "127.0.0.1"})
    connection = driver.open(driver.line_key(gate, None), gate, None)
    connection.start(lambda m: None)
    assert connection.send(Message("/y", ("hi",), 0.0))
    assert OscMessage(listener.recvfrom(4096)[0]).params == ["hi"]
    assert not connection.send(Message("/y", (2**40,), 0.0, {"types": "i"})), "unbuildable is dropped"
    connection.close()


@pytest.mark.integration
def test_osc_state_registers_driver(library_system: Any) -> None:
    from haywire.core.di.context import get_library_state_container

    state = get_library_state_container().get(ProtokolState)
    assert state is not None
    assert isinstance(state.driver("osc"), OscDriver)
