"""The Gates editor (ACTION): the project's gates, their Lines and status; editing for EDIT."""

from pathlib import Path

import pytest
from nicegui.testing import User

from haybale_protokol.editors.gates_editor import GatesEditor
from haybale_protokol.gates import Gate, gate_file_path, load_gates
from haybale_protokol.states.protokol_selection import ProtokolSelection
from haybale_protokol.states.protokol_state import LineUse, ProtokolState
from haywire.core.access import AccessTier
from tests.editors.conftest import make_context, one, open_editor, set_value

pytestmark = pytest.mark.anyio


def _status(user: User, name: str) -> str:
    return str(one(user, f"gate-status-{name}").text)


def test_requires_view() -> None:
    assert GatesEditor.class_identity.requires == AccessTier.VIEW


def test_uses_the_network_icon() -> None:
    from haywire.ui import elements as hui

    assert GatesEditor.class_identity.icon == hui.icon.network


async def test_rows_show_status_kinds(
    user: User, protokol: ProtokolState, selection: ProtokolSelection, tmp_path: Path
) -> None:
    path = gate_file_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(
        '[gates.open]\nprotocol = "fake"\ndirection = "in"\nport = 1\n'
        '[gates.idle]\nprotocol = "fake"\ndirection = "in"\nport = 2\n'
        '[gates.midi]\nprotocol = "midi"\ndirection = "in"\ndevice = "desk"\n'
        '[gates.pad]\nprotocol = "fake"\ndirection = "in"\nport = 3\ndevice = "nowhere"\n'
        '[gates.bad]\nprotocol = "fake"\ndirection = "sideways"\n',
        encoding="utf-8",
    )
    keeper = protokol.use("open", "in")
    assert isinstance(keeper, LineUse)
    await open_editor(user, GatesEditor, make_context(protokol, selection))
    assert "1 users" in _status(user, "open")
    assert _status(user, "idle") == "closed"
    assert _status(user, "midi") == "protocol not installed"
    assert _status(user, "pad") == "unbound gate: no device 'nowhere' on this machine"
    assert "sideways" in _status(user, "bad")
    keeper.release()


async def test_gate_file_error_shows_once(
    user: User, protokol: ProtokolState, selection: ProtokolSelection, tmp_path: Path
) -> None:
    path = gate_file_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text("[gates.x\n", encoding="utf-8")
    await open_editor(user, GatesEditor, make_context(protokol, selection))
    assert "gate file" in str(one(user, "gates-file-error").text)


async def test_row_click_selects_gate(
    user: User, protokol: ProtokolState, selection: ProtokolSelection
) -> None:
    protokol.save_gate(Gate("in", "fake", "in", options={"port": 1}))
    await open_editor(user, GatesEditor, make_context(protokol, selection))
    user.find(marker="gate-row-in").click()
    assert selection.gate == "in"


async def test_add_gate_writes_file(
    user: User, protokol: ProtokolState, selection: ProtokolSelection, tmp_path: Path
) -> None:
    await open_editor(user, GatesEditor, make_context(protokol, selection))
    user.find(marker="gate-add").click()
    set_value(user, "gate-form-name", "lights")
    set_value(user, "gate-form-direction", "out")
    set_value(user, "gate-form-port", "9000")
    set_value(user, "gate-form-host", "10.0.0.2")
    user.find(marker="gate-dialog-save").click()
    gate = load_gates(gate_file_path(tmp_path))["lights"]
    assert (gate.protocol, gate.direction, dict(gate.options)) == (
        "fake",
        "out",
        {"port": 9000, "host": "10.0.0.2"},
    )
    assert not one(user, "gate-dialog").value
    await user.should_see(marker="gate-row-lights")


async def test_form_shows_fields_by_direction(
    user: User, protokol: ProtokolState, selection: ProtokolSelection
) -> None:
    await open_editor(user, GatesEditor, make_context(protokol, selection))
    user.find(marker="gate-add").click()
    set_value(user, "gate-form-direction", "in")
    await user.should_not_see(marker="gate-form-host")
    set_value(user, "gate-form-direction", "out")
    await user.should_see(marker="gate-form-host")


async def test_invalid_gate_keeps_dialog_open(
    user: User, protokol: ProtokolState, selection: ProtokolSelection, tmp_path: Path
) -> None:
    await open_editor(user, GatesEditor, make_context(protokol, selection))
    user.find(marker="gate-add").click()
    set_value(user, "gate-form-name", "x")
    user.find(marker="gate-dialog-save").click()
    assert one(user, "gate-dialog").value
    assert "needs a port" in str(one(user, "gate-dialog-error").text)
    assert not gate_file_path(tmp_path).exists()


async def test_edit_hint_when_line_in_use(
    user: User, protokol: ProtokolState, selection: ProtokolSelection
) -> None:
    protokol.save_gate(Gate("in", "fake", "in", options={"port": 1}))
    keeper = protokol.use("in", "in")
    assert isinstance(keeper, LineUse)
    await open_editor(user, GatesEditor, make_context(protokol, selection))
    user.find(marker="gate-edit-in").click()
    assert "applies when its users restart" in str(one(user, "gate-dialog-hint").text)
    keeper.release()


async def test_rename_through_edit(
    user: User, protokol: ProtokolState, selection: ProtokolSelection, tmp_path: Path
) -> None:
    protokol.save_gate(Gate("old", "fake", "in", options={"port": 1}))
    await open_editor(user, GatesEditor, make_context(protokol, selection))
    user.find(marker="gate-edit-old").click()
    set_value(user, "gate-form-name", "new")
    user.find(marker="gate-dialog-save").click()
    assert set(load_gates(gate_file_path(tmp_path))) == {"new"}


async def test_delete_gate_after_confirm(
    user: User, protokol: ProtokolState, selection: ProtokolSelection, tmp_path: Path
) -> None:
    protokol.save_gate(Gate("in", "fake", "in", options={"port": 1}))
    await open_editor(user, GatesEditor, make_context(protokol, selection))
    user.find(marker="gate-delete-in").click()
    assert "in" in load_gates(gate_file_path(tmp_path))
    user.find(marker="gate-delete-confirm").click()
    assert load_gates(gate_file_path(tmp_path)) == {}


async def test_view_only_has_no_edit_controls(
    user: User, protokol: ProtokolState, selection: ProtokolSelection
) -> None:
    protokol.save_gate(Gate("in", "fake", "in", options={"port": 1}))
    await open_editor(user, GatesEditor, make_context(protokol, selection, edit=False))
    await user.should_see(marker="gate-row-in")
    await user.should_not_see(marker="gate-add")
    await user.should_not_see(marker="gate-delete-in")
    user.find(marker="gate-edit-in").click()
    await user.should_not_see(marker="gate-dialog-save")


async def test_bind_selects_device(
    user: User, protokol: ProtokolState, selection: ProtokolSelection
) -> None:
    protokol.save_gate(Gate("pad", "fake", "in", device="nowhere", options={"port": 3}))
    await open_editor(user, GatesEditor, make_context(protokol, selection))
    user.find(marker="gate-bind-pad").click()
    assert selection.device == "nowhere"


async def test_monitor_button_selects_and_reveals(
    user: User, protokol: ProtokolState, selection: ProtokolSelection
) -> None:
    from haybale_protokol.editors.monitor_editor import MonitorEditor
    from haywire.core.signals import Reveal

    protokol.save_gate(Gate("in", "fake", "in", options={"port": 1}))
    context = make_context(protokol, selection, edit=False)
    await open_editor(user, GatesEditor, context)
    user.find(marker="gate-monitor-in").click()
    assert selection.gate == "in"
    published = context.session.publish.call_args.args[0]
    assert isinstance(published, Reveal)
    assert published.editor is MonitorEditor


async def test_selected_row_uses_the_active_token(
    user: User, protokol: ProtokolState, selection: ProtokolSelection
) -> None:
    protokol.save_gate(Gate("in", "fake", "in", options={"port": 1}))
    protokol.save_gate(Gate("out", "fake", "out", options={"port": 2, "host": "h"}))
    selection.select_gate("in")
    await open_editor(user, GatesEditor, make_context(protokol, selection))
    assert "hw-list-item-active" in one(user, "gate-row-in").classes
    assert "hw-list-item-active" not in one(user, "gate-row-out").classes
    assert not any(c.startswith("bg-") for c in one(user, "gate-row-in").classes)


async def test_row_puts_name_tags_and_icons_in_one_row_status_below(
    user: User, protokol: ProtokolState, selection: ProtokolSelection
) -> None:
    protokol.save_gate(Gate("in", "fake", "in", options={"port": 1}))
    await open_editor(user, GatesEditor, make_context(protokol, selection))
    block = one(user, "gate-row-in")
    head = one(user, "gate-edit-in").parent_slot.parent
    assert head.parent_slot.parent is block
    assert one(user, "gate-monitor-in").parent_slot.parent is head
    assert one(user, "gate-delete-in").parent_slot.parent is head
    assert one(user, "gate-status-in").parent_slot.parent is block
