"""The Device editor (CONTEXT): the Device list, and the selected device, gate or Line."""

from pathlib import Path

import pytest
from nicegui.testing import User

from haybale_protokol.devices import Device
from haybale_protokol.editors.device_editor import DeviceEditor
from haybale_protokol.gates import Gate
from haybale_protokol.states.protokol_selection import ProtokolSelection
from haybale_protokol.states.protokol_state import LineUse, ProtokolState
from haywire.core.access import AccessTier
from tests.editors.conftest import FormDriver, make_context, one, open_editor, set_value

pytestmark = pytest.mark.anyio


@pytest.fixture(autouse=True)
def _home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))


def test_requires_view() -> None:
    assert DeviceEditor.class_identity.requires == AccessTier.VIEW


async def test_shows_device_list_by_default(
    user: User, protokol: ProtokolState, selection: ProtokolSelection
) -> None:
    protokol.save_device(Device("desk", "fake", "IAC 1"))
    await open_editor(user, DeviceEditor, make_context(protokol, selection))
    await user.should_see(marker="device-row-desk")
    assert "IAC 1" in str(one(user, "device-status-desk").text)


async def test_device_not_connected_hint(user: User, selection: ProtokolSelection, tmp_path: Path) -> None:
    protokol = ProtokolState()
    protokol.project_root = tmp_path
    protokol.register_driver(FormDriver(devices=(("IAC 1", "IAC Driver Bus 1"),)))
    protokol.save_device(Device("here", "fake", "IAC 1"))
    protokol.save_device(Device("gone", "fake", "IAC 9"))
    await open_editor(user, DeviceEditor, make_context(protokol, selection))
    assert "not connected" not in str(one(user, "device-status-here").text)
    assert "not connected" in str(one(user, "device-status-gone").text)


async def test_gate_selection_shows_line_and_cache(
    user: User, protokol: ProtokolState, selection: ProtokolSelection, driver: FormDriver
) -> None:
    protokol.save_gate(Gate("in", "fake", "in", options={"port": 1}))
    keeper = protokol.use("in", "in")
    assert isinstance(keeper, LineUse)
    driver.connections[0].push("/fader", 0.5)
    selection.select_gate("in")
    await open_editor(user, DeviceEditor, make_context(protokol, selection))
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
    await open_editor(user, DeviceEditor, make_context(protokol, selection))
    assert "1 users" in str(one(user, "device-line-status").text)
    keeper.release()


async def test_map_unbound_device_admin_only(
    user: User, protokol: ProtokolState, selection: ProtokolSelection
) -> None:
    selection.select_device("nowhere")
    await open_editor(user, DeviceEditor, make_context(protokol, selection, admin=True))
    user.find(marker="device-map").click()
    set_value(user, "device-form-protocol", "fake")
    set_value(user, "device-form-os_id", "IAC 2")
    user.find(marker="device-dialog-save").click()
    assert protokol.devices()["nowhere"].os_id == "IAC 2"


async def test_view_only_cannot_edit_devices(
    user: User, protokol: ProtokolState, selection: ProtokolSelection
) -> None:
    protokol.save_device(Device("desk", "fake", "IAC 1"))
    await open_editor(user, DeviceEditor, make_context(protokol, selection, edit=True, admin=False))
    await user.should_see(marker="device-row-desk")
    await user.should_not_see(marker="device-add")
    await user.should_not_see(marker="device-delete-desk")


async def test_view_only_cannot_map_devices(
    user: User, protokol: ProtokolState, selection: ProtokolSelection
) -> None:
    selection.select_device("nowhere")
    await open_editor(user, DeviceEditor, make_context(protokol, selection, edit=True, admin=False))
    await user.should_see(marker="device-detail")
    await user.should_not_see(marker="device-map")


async def test_admin_edits_and_deletes(
    user: User, protokol: ProtokolState, selection: ProtokolSelection
) -> None:
    protokol.save_device(Device("desk", "fake", "IAC 1"))
    await open_editor(user, DeviceEditor, make_context(protokol, selection, admin=True))
    user.find(marker="device-edit-desk").click()
    set_value(user, "device-form-name", "mixer")
    user.find(marker="device-dialog-save").click()
    assert set(protokol.devices()) == {"mixer"}
    user.find(marker="device-delete-mixer").click()
    user.find(marker="device-delete-confirm").click()
    assert protokol.devices() == {}
