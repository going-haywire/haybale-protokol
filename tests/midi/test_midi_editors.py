"""The Plan 3 editors with the MIDI driver: devices, the gate form, test-send."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from nicegui.testing import User

from haybale_protokol.devices import Device, device_list_path, save_devices
from haybale_protokol.editors.device_editor import DeviceEditor
from haybale_protokol.editors.gates_editor import GatesEditor
from haybale_protokol.editors.monitor_editor import MonitorEditor
from haybale_protokol.gates import Gate
from haybale_protokol.line_use import LineUse
from haybale_protokol.states.protokol_selection import ProtokolSelection
from haybale_protokol.states.protokol_state import ProtokolState
from haybale_protokol_midi.driver import MidiDriver
from tests.editors.conftest import make_context, one, open_editor, set_value
from tests.midi.conftest import Sink, Source, needs_virtual, wait_for

pytestmark = [pytest.mark.anyio, needs_virtual]


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def user() -> Iterator[User]:  # type: ignore[misc]
    from nicegui.testing.user_simulation import user_simulation

    async with user_simulation() as u:
        yield u


@pytest.fixture
def midi(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[ProtokolState]:
    monkeypatch.setenv("HOME", str(tmp_path))
    state = ProtokolState()
    state.project_root = tmp_path
    state.grace_s = lambda: 0.0
    state.register_driver(MidiDriver())
    yield state
    state.on_disable()


@pytest.fixture
def selection() -> ProtokolSelection:
    chosen = ProtokolSelection()
    chosen.session = lambda: None  # type: ignore[assignment]
    return chosen


async def test_device_editor_maps_a_midi_port(
    user: User, midi: ProtokolState, selection: ProtokolSelection, source: Source
) -> None:
    midi.save_gate(Gate("keys", "midi", "in", device="keys"))
    assert midi.use("keys", "in") == "unbound gate: no device 'keys' on this machine"
    selection.select_device("keys")
    await open_editor(user, DeviceEditor, make_context(midi, selection, admin=True))
    user.find(marker="device-map").click()
    set_value(user, "device-form-protocol", "midi")
    assert source.name in one(user, "device-form-os_id").options
    set_value(user, "device-form-os_id", source.name)
    user.find(marker="device-dialog-save").click()
    use = midi.use("keys", "in")
    assert isinstance(use, LineUse), use
    use.release()


async def test_gate_form_offers_devices_for_midi(
    user: User, midi: ProtokolState, selection: ProtokolSelection
) -> None:
    save_devices(device_list_path(), [Device("keys", "midi", "IAC 1"), Device("pad", "gamepad", "x")])
    await open_editor(user, GatesEditor, make_context(midi, selection))
    user.find(marker="gate-add").click()
    set_value(user, "gate-form-protocol", "midi")
    assert list(one(user, "gate-form-device").options) == ["keys"]


async def test_monitor_test_send_midi(
    user: User, midi: ProtokolState, selection: ProtokolSelection, sink: Sink
) -> None:
    save_devices(device_list_path(), [Device("synth", "midi", sink.name)])
    midi.save_gate(Gate("synth", "midi", "out", device="synth"))
    editor = await open_editor(user, MonitorEditor, make_context(midi, selection))
    user.find(marker="monitor-visibility-synth").click()
    set_value(user, "monitor-send-input-synth", "cc 1 7 64")
    user.find(marker="monitor-send-synth").click()
    assert wait_for(lambda: sink.received == [[0xB0, 7, 64]])
    editor._refresh()
    assert editor._view[0]["description"] == "cc ch1 7 = 64"
    editor.cleanup()
