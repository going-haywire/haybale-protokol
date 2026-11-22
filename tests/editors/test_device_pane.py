"""The Device pane of the Gates editor: the Device list, and the selected device, gate or Line (§10.4)."""

from pathlib import Path

import pytest
from nicegui.testing import User

from haybale_protokol.devices import Device
from haybale_protokol.editors.gates_editor import GatesEditor
from haybale_protokol.gates import Gate
from haybale_protokol.states.protokol_selection import ProtokolSelection
from haybale_protokol.states.protokol_state import LineUse, ProtokolState
from haywire.core.access import AccessTier
from tests.editors.conftest import FormDriver, make_context, one, open_editor, set_value

pytestmark = pytest.mark.anyio


@pytest.fixture(autouse=True)
def _home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))


def test_the_device_editor_is_gone() -> None:
    """One editor for gates and devices: the Device editor is removed (design §10.4)."""
    import importlib
    import importlib.util
    import pkgutil

    import haybale_protokol.editors as editors

    assert importlib.util.find_spec("haybale_protokol.editors.device_editor") is None
    modules = [
        importlib.import_module(f"haybale_protokol.editors.{m.name}")
        for m in pkgutil.iter_modules(editors.__path__)
    ]
    assert not [m for m in modules if hasattr(m, "DeviceEditor")]


def test_gates_editor_requires_view() -> None:
    assert GatesEditor.class_identity.requires == AccessTier.VIEW


async def test_shows_device_list_by_default(
    user: User, protokol: ProtokolState, selection: ProtokolSelection
) -> None:
    protokol.save_device(Device("desk", "fake", "IAC 1"))
    await open_editor(user, GatesEditor, make_context(protokol, selection))
    await user.should_see(marker="device-row-desk")
    assert "IAC 1" in str(one(user, "device-status-desk").text)


async def test_device_not_connected_hint(user: User, selection: ProtokolSelection, tmp_path: Path) -> None:
    protokol = ProtokolState()
    protokol.project_root = tmp_path
    protokol.register_driver(FormDriver(devices=(("IAC 1", "IAC Driver Bus 1"),)))
    protokol.save_device(Device("here", "fake", "IAC 1"))
    protokol.save_device(Device("gone", "fake", "IAC 9"))
    await open_editor(user, GatesEditor, make_context(protokol, selection))
    assert "not plugged in" not in str(one(user, "device-status-here").text)
    assert "not plugged in" in str(one(user, "device-status-gone").text)
    assert "hw-text-danger" in one(user, "device-status-gone").classes


async def test_device_seen_under_a_new_name(
    user: User, selection: ProtokolSelection, tmp_path: Path
) -> None:
    class RenamingDriver(FormDriver):
        def match_device(self, os_id: str, names: list[str]) -> str | None:
            return "Synth 24:0" if os_id == "Synth 20:0" and "Synth 24:0" in names else None

    protokol = ProtokolState()
    protokol.project_root = tmp_path
    protokol.register_driver(RenamingDriver(devices=(("Synth 24:0", "input"),)))
    protokol.save_device(Device("synth", "fake", "Synth 20:0"))
    await open_editor(user, GatesEditor, make_context(protokol, selection))
    text = str(one(user, "device-status-synth").text)
    assert "not plugged in" not in text
    assert "now 'Synth 24:0'" in text


async def test_gate_selection_shows_line_and_cache(
    user: User, protokol: ProtokolState, selection: ProtokolSelection, driver: FormDriver
) -> None:
    protokol.save_gate(Gate("in", "fake", "in", options={"port": 1}))
    keeper = protokol.use("in", "in")
    assert isinstance(keeper, LineUse)
    driver.connections[0].push("/fader", 0.5)
    selection.select_gate("in")
    await open_editor(user, GatesEditor, make_context(protokol, selection))
    assert "1 users" in str(one(user, "device-line-status").text)
    await user.should_see("/fader (0.5,)")
    keeper.release()


async def test_line_selection_shows_line(
    user: User, protokol: ProtokolState, selection: ProtokolSelection
) -> None:
    protokol.save_gate(Gate("in", "fake", "in", options={"port": 1}))
    keeper = protokol.use("in", "in")
    assert isinstance(keeper, LineUse)
    selection.select_line(keeper.line.key)
    await open_editor(user, GatesEditor, make_context(protokol, selection))
    assert "1 users" in str(one(user, "device-line-status").text)
    keeper.release()


async def test_map_unbound_device_admin_only(
    user: User, protokol: ProtokolState, selection: ProtokolSelection
) -> None:
    selection.select_device("nowhere")
    await open_editor(user, GatesEditor, make_context(protokol, selection, admin=True))
    user.find(marker="device-map").click()
    set_value(user, "device-form-protocol", "fake")
    set_value(user, "device-form-os_id", "IAC 2")
    user.find(marker="device-dialog-save").click()
    assert protokol.devices()["nowhere"].os_id == "IAC 2"


async def test_view_only_cannot_edit_devices(
    user: User, protokol: ProtokolState, selection: ProtokolSelection
) -> None:
    protokol.save_device(Device("desk", "fake", "IAC 1"))
    await open_editor(user, GatesEditor, make_context(protokol, selection, edit=True, admin=False))
    await user.should_see(marker="device-row-desk")
    await user.should_not_see(marker="device-add")
    await user.should_not_see(marker="device-delete-desk")


async def test_view_only_cannot_map_devices(
    user: User, protokol: ProtokolState, selection: ProtokolSelection
) -> None:
    selection.select_device("nowhere")
    await open_editor(user, GatesEditor, make_context(protokol, selection, edit=True, admin=False))
    await user.should_see(marker="device-detail")
    await user.should_not_see(marker="device-map")


async def test_admin_edits_and_deletes(
    user: User, protokol: ProtokolState, selection: ProtokolSelection
) -> None:
    protokol.save_device(Device("desk", "fake", "IAC 1"))
    await open_editor(user, GatesEditor, make_context(protokol, selection, admin=True))
    user.find(marker="device-edit-desk").click()
    set_value(user, "device-form-name", "mixer")
    user.find(marker="device-dialog-save").click()
    assert set(protokol.devices()) == {"mixer"}
    user.find(marker="device-delete-mixer").click()
    user.find(marker="device-delete-confirm").click()
    assert protokol.devices() == {}


async def test_change_signal_keeps_an_open_dialog(
    user: User, protokol: ProtokolState, selection: ProtokolSelection
) -> None:
    editor = await open_editor(user, GatesEditor, make_context(protokol, selection, admin=True))
    user.find(marker="device-add").click()
    dialog = one(user, "device-dialog")
    editor._on_change(editor._context, None)
    assert not dialog.is_deleted
    assert dialog.value


async def test_the_pane_sits_below_the_gates_behind_a_divider(
    user: User, protokol: ProtokolState, selection: ProtokolSelection
) -> None:
    editor = await open_editor(user, GatesEditor, make_context(protokol, selection))
    splitter = one(user, "gates-splitter")
    assert splitter.props.get("horizontal") is True
    assert list(splitter.props.get("limits")) == [20, 80]
    assert one(user, "device-pane") is not None
    editor._set_split(type("E", (), {"value": 35.0})())
    editor._on_change(editor._context, None)
    assert editor._split == 35.0


async def test_selecting_a_gate_fills_the_device_pane(
    user: User, protokol: ProtokolState, selection: ProtokolSelection
) -> None:
    protokol.save_gate(Gate("in", "fake", "in", options={"port": 1}))
    editor = await open_editor(user, GatesEditor, make_context(protokol, selection))
    await user.should_not_see(marker="device-line-status")
    user.find(marker="gate-select-in").click()
    editor._on_change(editor._context, None)  # the selection signal, as the session would deliver it
    await user.should_see(marker="device-line-status")
    assert str(one(user, "device-line-status").text) == "closed"


async def test_map_an_unbound_gates_device_from_the_gate_view(
    user: User, protokol: ProtokolState, selection: ProtokolSelection
) -> None:
    protokol.save_gate(Gate("pad", "fake", "in", device="nowhere", options={"port": 3}))
    selection.select_gate("pad")
    await open_editor(user, GatesEditor, make_context(protokol, selection, admin=True))
    await user.should_see(marker="device-gate-unbound")
    user.find(marker="device-map").click()
    assert one(user, "device-form-name").value == "nowhere"
    set_value(user, "device-form-os_id", "IAC 2")
    user.find(marker="device-dialog-save").click()
    assert protokol.devices()["nowhere"] == Device("nowhere", "fake", "IAC 2")


async def test_port_picker_read_only_without_admin(
    user: User, protokol: ProtokolState, selection: ProtokolSelection
) -> None:
    protokol.save_gate(Gate("pad", "fake", "in", device="nowhere", options={"port": 3}))
    selection.select_gate("pad")
    await open_editor(user, GatesEditor, make_context(protokol, selection, edit=True, admin=False))
    await user.should_not_see(marker="device-map")
    assert "needs an admin" in str(one(user, "device-map-needs-admin").text)


async def test_refresh_button_checks_devices(
    user: User, selection: ProtokolSelection, tmp_path: Path
) -> None:
    from tests.fakes import FakeDeviceDriver

    protokol = ProtokolState()
    protokol.project_root = tmp_path
    fake = FakeDeviceDriver(present=["Grid MIDI 1"])
    protokol.register_driver(fake)
    protokol.save_device(Device("grid", "fakedev", "Grid MIDI 1"))
    try:
        await open_editor(user, GatesEditor, make_context(protokol, selection))
        assert "not plugged in" not in str(one(user, "device-status-grid").text)
        fake.present = []
        user.find(marker="device-refresh").click()
        assert "not plugged in" in str(one(user, "device-status-grid").text)
    finally:
        protokol.on_disable()
