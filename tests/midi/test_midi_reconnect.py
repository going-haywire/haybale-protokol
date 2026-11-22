"""Receive reconnect with real MIDI ports: unplug and replug a virtual port (Plan 4b, task 3)."""

from collections.abc import Iterator
from pathlib import Path

import pytest

from haybale_protokol.devices import Device, device_list_path, save_devices
from haybale_protokol.drivers import Message
from haybale_protokol.gates import Gate, gate_file_path, save_gates
from haybale_protokol.receive import ReceiveBinding
from haybale_protokol.states.protokol_state import ProtokolState
from haybale_protokol_midi.driver import MidiDriver
from tests.midi.conftest import Source, needs_virtual, wait_for

pytestmark = needs_virtual


@pytest.fixture
def state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[ProtokolState]:
    monkeypatch.setenv("HOME", str(tmp_path))
    protokol = ProtokolState()
    protokol.project_root = tmp_path
    protokol.grace_s = lambda: 5.0
    protokol.watch_s = lambda: 0.1
    protokol.register_driver(MidiDriver())
    yield protokol
    protokol.on_disable()
    protokol.unregister_driver("midi")


def _bind(tmp_path: Path, os_id: str) -> None:
    save_gates(gate_file_path(tmp_path), [Gate("keys", "midi", "in", device="keys")])
    save_devices(device_list_path(), [Device("keys", "midi", os_id)])


def test_unplug_and_replug_a_port_while_receiving(state: ProtokolState, tmp_path: Path) -> None:
    first = Source()
    _bind(tmp_path, first.name)
    got: list[Message] = []
    binding = ReceiveBinding(
        state, "keys", lambda m: {"m": m}, lambda p: got.append(p["m"]), start_value=False, block=False
    )
    second: Source | None = None
    try:
        assert binding.is_bound
        first.send(0xB0, 7, 1)
        assert wait_for(lambda: len(got) == 1)
        first.close()
        assert wait_for(lambda: binding.status == "waiting for 'keys'", timeout=4.0)
        assert state.health("keys").state == "not plugged in"
        second = Source(first.port)  # the same device again; ALSA may give it another client number
        assert wait_for(lambda: binding.is_bound, timeout=4.0)
        second.send(0xB0, 7, 2)
        assert wait_for(lambda: [m.args for m in got][-1:] == [(7, 2)], timeout=2.0)
    finally:
        binding.close()
        if second is not None:
            second.close()


def test_start_unplugged_then_plug_in(state: ProtokolState, tmp_path: Path) -> None:
    probe = Source()
    port, name = probe.port, probe.name
    probe.close()
    _bind(tmp_path, name)
    state.refresh_devices()
    got: list[Message] = []
    binding = ReceiveBinding(
        state, "keys", lambda m: {"m": m}, lambda p: got.append(p["m"]), start_value=False, block=False
    )
    source: Source | None = None
    try:
        assert binding.status == "waiting for 'keys'"
        source = Source(port)
        assert wait_for(lambda: binding.is_bound, timeout=4.0)
        source.send(0x90, 60, 100)
        assert wait_for(lambda: len(got) == 1, timeout=2.0)
    finally:
        binding.close()
        if source is not None:
            source.close()
