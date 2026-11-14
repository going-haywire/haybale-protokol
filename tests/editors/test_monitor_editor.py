"""The Monitor (EDIT tab): taps on Lines, a bounded and filtered view, test-send, export."""

from pathlib import Path
from typing import Any

import pytest
from nicegui.testing import User

from haybale_protokol.editors.monitor_editor import MONITOR_ROWS, MonitorEditor
from haybale_protokol.gates import Gate, gate_file_path, load_gates
from haybale_protokol.states.protokol_selection import ProtokolSelection
from haybale_protokol.states.protokol_state import LineUse, ProtokolState
from haywire.core.access import AccessTier
from tests.editors.conftest import FormDriver, make_context, one, open_editor, set_value

pytestmark = pytest.mark.anyio


def _gates(protokol: ProtokolState) -> None:
    assert protokol.save_gate(Gate("in", "fake", "in", options={"port": 1})) is None
    assert protokol.save_gate(Gate("out", "fake", "out", options={"port": 2, "host": "h"})) is None


async def _monitor(user: User, protokol: ProtokolState, selection: ProtokolSelection, **access: Any) -> Any:
    _gates(protokol)
    return await open_editor(user, MonitorEditor, make_context(protokol, selection, **access))


def _rows(user: User) -> list[dict[str, Any]]:
    return list(one(user, "monitor-table").rows)


def test_requires_view_and_opens_on_context() -> None:
    assert MonitorEditor.class_identity.requires == AccessTier.VIEW
    assert str(MonitorEditor.class_identity.opens.value) == "on_context"


async def test_monitor_draws_a_bounded_window(
    user: User, protokol: ProtokolState, selection: ProtokolSelection, driver: FormDriver
) -> None:
    editor = await _monitor(user, protokol, selection)
    set_value(user, "monitor-source-in", True)
    for i in range(5000):
        driver.connections[0].push("/a", i)
    editor._refresh()
    rows = _rows(user)
    assert len(rows) == MONITOR_ROWS
    assert rows[0]["description"].endswith("(4999,)")
    assert "5000" in str(one(user, "monitor-count-in").text)


async def test_filter_matches_description(
    user: User, protokol: ProtokolState, selection: ProtokolSelection, driver: FormDriver
) -> None:
    editor = await _monitor(user, protokol, selection)
    set_value(user, "monitor-source-in", True)
    driver.connections[0].push("/alpha", 1)
    driver.connections[0].push("/beta", 2)
    set_value(user, "monitor-filter", "BETA")
    editor._refresh()
    assert [row["address"] for row in _rows(user)] == ["/beta"]


async def test_view_only_cannot_open_closed_lines(
    user: User, protokol: ProtokolState, selection: ProtokolSelection
) -> None:
    editor = await _monitor(user, protokol, selection, edit=False)
    assert not one(user, "monitor-source-in").enabled
    await user.should_not_see(marker="monitor-new-line")
    assert editor._taps == {}


async def test_view_only_taps_open_line(
    user: User, protokol: ProtokolState, selection: ProtokolSelection, driver: FormDriver
) -> None:
    _gates(protokol)
    keeper = protokol.use("in", "in")
    assert isinstance(keeper, LineUse)
    editor = await open_editor(user, MonitorEditor, make_context(protokol, selection, edit=False))
    set_value(user, "monitor-source-in", True)
    assert "in" in editor._taps
    driver.connections[0].push("/a", 1)
    editor._refresh()
    assert len(_rows(user)) == 1
    await user.should_not_see(marker="monitor-send-out")
    editor.cleanup()
    keeper.release()


async def test_test_send_reaches_fake_connection(
    user: User, protokol: ProtokolState, selection: ProtokolSelection, driver: FormDriver
) -> None:
    editor = await _monitor(user, protokol, selection)
    set_value(user, "monitor-source-out", True)
    set_value(user, "monitor-send-input-out", "/x 1")
    user.find(marker="monitor-send-out").click()
    assert [m.address for m in driver.connections[0].sent] == ["/x"]
    editor._refresh()
    assert [(row["address"], row["direction"]) for row in _rows(user)] == [("/x", "out")]


async def test_test_send_error_inline(
    user: User, protokol: ProtokolState, selection: ProtokolSelection
) -> None:
    await _monitor(user, protokol, selection)
    set_value(user, "monitor-source-out", True)
    set_value(user, "monitor-send-input-out", "no address")
    user.find(marker="monitor-send-out").click()
    assert "needs an address" in str(one(user, "monitor-send-error-out").text)


async def test_new_line_and_save_as_gate(
    user: User, protokol: ProtokolState, selection: ProtokolSelection, tmp_path: Path
) -> None:
    editor = await _monitor(user, protokol, selection)
    user.find(marker="monitor-new-line").click()
    set_value(user, "gate-form-port", "7")
    user.find(marker="monitor-new-line-open").click()
    assert "~in 7" in editor._taps
    user.find(marker="monitor-save-as-~in 7").click()
    set_value(user, "gate-form-name", "seven")
    user.find(marker="gate-dialog-save").click()
    assert "seven" in load_gates(gate_file_path(tmp_path))
    assert "seven" in editor._taps
    assert "~in 7" not in editor._taps
    assert len(protokol.lines()) == 1, "the Line was handed over, not reopened"


async def test_selection_ticks_source(
    user: User, protokol: ProtokolState, selection: ProtokolSelection
) -> None:
    editor = await _monitor(user, protokol, selection)
    selection.select_gate("in")
    editor._on_selection(editor._context, None)
    assert "in" in editor._taps


async def test_closing_monitor_releases_taps(
    user: User, protokol: ProtokolState, selection: ProtokolSelection
) -> None:
    editor = await _monitor(user, protokol, selection)
    set_value(user, "monitor-source-in", True)
    set_value(user, "monitor-source-out", True)
    assert len(protokol.lines()) == 2
    assert await editor.handle_close_request()
    assert protokol.lines() == []
    assert editor._taps == {}


async def test_untick_releases_tap(
    user: User, protokol: ProtokolState, selection: ProtokolSelection
) -> None:
    editor = await _monitor(user, protokol, selection)
    set_value(user, "monitor-source-in", True)
    set_value(user, "monitor-source-in", False)
    assert editor._taps == {}
    assert protokol.lines() == []
