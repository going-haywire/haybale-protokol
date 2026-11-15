"""A machine without a MIDI system (Linux without ALSA's sequencer, a CI runner)."""

from pathlib import Path

import pytest

from haybale_protokol.devices import Device, device_list_path, save_devices
from haybale_protokol.gates import Gate, gate_file_path, save_gates
from haybale_protokol.states.protokol_state import ProtokolState
from haybale_protokol_midi.driver import MidiDriver


@pytest.fixture
def no_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    import haybale_protokol_midi.driver as driver_module

    def broken(*_args: object, **_kwargs: object) -> None:
        raise SystemError("MidiInAlsa::initialize: error creating ALSA sequencer client object.")

    monkeypatch.setattr(driver_module.rtmidi, "MidiIn", broken)
    monkeypatch.setattr(driver_module.rtmidi, "MidiOut", broken)


@pytest.mark.parametrize("direction", ["in", "out"])
def test_a_gate_says_there_is_no_midi_system(
    no_backend: None, direction: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    state = ProtokolState()
    state.project_root = tmp_path
    state.grace_s = lambda: 0.0
    state.register_driver(MidiDriver())
    save_gates(gate_file_path(tmp_path), [Gate("keys", "midi", direction, device="keys")])
    save_devices(device_list_path(), [Device("keys", "midi", "Keystation 49")])
    result = state.use("keys", direction)
    assert isinstance(result, str), result
    assert result.startswith("cannot open: no MIDI system on this machine")
