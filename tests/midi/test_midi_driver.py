"""The MIDI driver through rtmidi virtual ports."""

import time
from pathlib import Path

import pytest

from haybale_protokol.devices import Device, device_list_path, save_devices
from haybale_protokol.drivers import LineKey, Message
from haybale_protokol.gates import Gate, gate_file_path, save_gates
from haybale_protokol.line_use import LineUse
from haybale_protokol.states.protokol_state import ProtokolState
from haybale_protokol_midi.driver import MidiDriver, MidiInConnection, MidiOutConnection
from tests.midi.conftest import Sink, Source, needs_virtual, wait_for

pytestmark = needs_virtual


@pytest.fixture
def state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ProtokolState:
    monkeypatch.setenv("HOME", str(tmp_path))
    protokol = ProtokolState()
    protokol.project_root = tmp_path
    protokol.grace_s = lambda: 0.0
    protokol.register_driver(MidiDriver())
    return protokol


def _bind(tmp_path: Path, *pairs: tuple[Gate, Device]) -> None:
    save_gates(gate_file_path(tmp_path), [gate for gate, _ in pairs])
    save_devices(device_list_path(), list({device.name: device for _, device in pairs}.values()))


def test_line_key_and_rules() -> None:
    driver = MidiDriver()
    device = Device("desk", "midi", "IAC 1")
    assert driver.line_key(Gate("g", "midi", "in", device="desk"), device) == LineKey("midi", "in IAC 1")
    with pytest.raises(ValueError, match="in or out"):
        driver.line_key(Gate("g", "midi", "two-way", device="desk"), device)
    with pytest.raises(ValueError, match="device"):
        driver.line_key(Gate("g", "midi", "in"), None)


def test_receives_from_virtual_port(state: ProtokolState, tmp_path: Path, source: Source) -> None:
    _bind(tmp_path, (Gate("keys", "midi", "in", device="keys"), Device("keys", "midi", source.name)))
    got: list[Message] = []
    use = state.use("keys", "in", got.append)
    assert isinstance(use, LineUse), use
    source.send(0x90, 60, 100)
    source.send(0xB0, 7, 64)
    assert wait_for(lambda: len(got) == 2)
    assert [m.address for m in got] == ["note 1 60", "cc 1 7"]
    assert "listening on MIDI" in use.line.status
    use.release()


def test_sends_to_virtual_port(state: ProtokolState, tmp_path: Path, sink: Sink) -> None:
    _bind(tmp_path, (Gate("synth", "midi", "out", device="synth"), Device("synth", "midi", sink.name)))
    use = state.use("synth", "out")
    assert isinstance(use, LineUse), use
    message = MidiDriver().parse_test_message("cc 2 7 99")
    assert use.line.send(message)
    assert wait_for(lambda: sink.received == [[0xB1, 7, 99]])
    use.release()


def test_missing_port_is_cannot_open(state: ProtokolState, tmp_path: Path) -> None:
    _bind(tmp_path, (Gate("gone", "midi", "in", device="gone"), Device("gone", "midi", "no such port")))
    assert state.use("gone", "in") == "cannot open: no MIDI port 'no such port'"


def test_two_gates_on_one_device_share_a_line(state: ProtokolState, tmp_path: Path, source: Source) -> None:
    device = Device("keys", "midi", source.name)
    _bind(
        tmp_path,
        (Gate("a", "midi", "in", device="keys"), device),
        (Gate("b", "midi", "in", device="keys"), device),
    )
    first, second = state.use("a", "in"), state.use("b", "in")
    assert isinstance(first, LineUse)
    assert isinstance(second, LineUse)
    assert first.line is second.line
    first.release()
    second.release()


def test_list_devices_sees_virtual_ports(source: Source, sink: Sink) -> None:
    devices = dict(MidiDriver().list_devices())
    assert devices[source.name] == "input"
    assert devices[sink.name] == "output"


@pytest.mark.timeout(60)
def test_open_close_under_a_stream_never_hangs(source: Source) -> None:
    """Closing an input while messages flow must not deadlock (rtmidi callback vs the GIL)."""
    import threading

    stop = threading.Event()

    def stream() -> None:
        value = 0
        while not stop.is_set():
            source.send(0xF8)
            source.send(0xB0, 7, value)
            value = (value + 1) % 128
            time.sleep(0.0005)

    sender = threading.Thread(target=stream, daemon=True)
    sender.start()
    try:
        for _ in range(150):
            connection = MidiInConnection(source.name)
            connection.start(lambda message: None)
            time.sleep(0.003)
            connection.close()
    finally:
        stop.set()
        sender.join()


def test_an_unplugged_input_says_so_and_a_new_use_reopens(state: ProtokolState, tmp_path: Path) -> None:
    first = Source()
    name = first.name
    _bind(tmp_path, (Gate("keys", "midi", "in", device="keys"), Device("keys", "midi", name)))
    state.grace_s = lambda: 5.0
    use = state.use("keys", "in")
    assert isinstance(use, LineUse), use
    first.close()
    assert wait_for(lambda: "port gone" in use.line.status, timeout=4.0)
    use.release()
    second = Source(name)
    try:
        got: list[Message] = []
        again = state.use("keys", "in", got.append)
        assert isinstance(again, LineUse), again
        assert again.line is not use.line, "a Line whose port went away is replaced"
        second.send(0xB0, 7, 1)
        assert wait_for(lambda: len(got) == 1)
        again.release()
    finally:
        second.close()


def test_an_unplugged_output_drops_and_says_so(sink: Sink) -> None:
    connection = MidiOutConnection(sink.name)
    connection.start(lambda message: None)
    sink.close()
    message = MidiDriver().parse_test_message("cc 1 7 1")
    assert wait_for(lambda: not connection.send(message) and "port gone" in connection.status, timeout=4.0)
    connection.close()


def test_listing_devices_without_a_midi_backend_is_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    import haybale_protokol_midi.driver as driver_module

    def broken() -> None:
        raise SystemError("no MIDI backend")

    monkeypatch.setattr(driver_module.rtmidi, "MidiIn", broken)
    assert MidiDriver().list_devices() == []
