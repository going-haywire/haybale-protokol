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


def _rows(editor: Any) -> list[dict[str, Any]]:
    return list(editor._view)


def test_requires_view_and_opens_on_context() -> None:
    assert MonitorEditor.class_identity.requires == AccessTier.VIEW
    assert str(MonitorEditor.class_identity.opens.value) == "on_context"


async def test_monitor_draws_a_bounded_window(
    user: User, protokol: ProtokolState, selection: ProtokolSelection, driver: FormDriver
) -> None:
    editor = await _monitor(user, protokol, selection)
    user.find(marker="monitor-visibility-in").click()
    for i in range(5000):
        driver.connections[0].push("/a", i)
    editor._refresh()
    rows = _rows(editor)
    assert len(rows) == MONITOR_ROWS
    assert rows[0]["description"].endswith("(4999,)")
    assert "5000" in str(one(user, "monitor-count-in").text)


async def test_filter_matches_description(
    user: User, protokol: ProtokolState, selection: ProtokolSelection, driver: FormDriver
) -> None:
    editor = await _monitor(user, protokol, selection)
    user.find(marker="monitor-visibility-in").click()
    driver.connections[0].push("/alpha", 1)
    driver.connections[0].push("/beta", 2)
    set_value(user, "monitor-filter", "BETA")
    editor._refresh()
    assert [row["address"] for row in _rows(editor)] == ["/beta"]


async def test_view_only_cannot_open_closed_lines(
    user: User, protokol: ProtokolState, selection: ProtokolSelection
) -> None:
    editor = await _monitor(user, protokol, selection, edit=False)
    assert "pointer-events-none" in one(user, "monitor-visibility-in").classes
    await user.should_not_see(marker="monitor-new-line")
    assert editor._taps == {}


async def test_view_only_taps_open_line(
    user: User, protokol: ProtokolState, selection: ProtokolSelection, driver: FormDriver
) -> None:
    _gates(protokol)
    keeper = protokol.use("in", "in")
    assert isinstance(keeper, LineUse)
    editor = await open_editor(user, MonitorEditor, make_context(protokol, selection, edit=False))
    user.find(marker="monitor-visibility-in").click()
    assert "in" in editor._taps
    driver.connections[0].push("/a", 1)
    editor._refresh()
    assert len(_rows(editor)) == 1
    await user.should_not_see(marker="monitor-send-out")
    editor.cleanup()
    keeper.release()


async def test_test_send_reaches_fake_connection(
    user: User, protokol: ProtokolState, selection: ProtokolSelection, driver: FormDriver
) -> None:
    editor = await _monitor(user, protokol, selection)
    user.find(marker="monitor-visibility-out").click()
    set_value(user, "monitor-send-input-out", "/x 1")
    user.find(marker="monitor-send-out").click()
    assert [m.address for m in driver.connections[0].sent] == ["/x"]
    editor._refresh()
    assert [(row["address"], row["direction"]) for row in _rows(editor)] == [("/x", "out")]


async def test_test_send_error_inline(
    user: User, protokol: ProtokolState, selection: ProtokolSelection
) -> None:
    await _monitor(user, protokol, selection)
    user.find(marker="monitor-visibility-out").click()
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
    user.find(marker="monitor-visibility-in").click()
    user.find(marker="monitor-visibility-out").click()
    assert len(protokol.lines()) == 2
    assert await editor.handle_close_request()
    assert protokol.lines() == []
    assert editor._taps == {}


async def test_stop_watching_releases_tap(
    user: User, protokol: ProtokolState, selection: ProtokolSelection
) -> None:
    editor = await _monitor(user, protokol, selection)
    user.find(marker="monitor-visibility-in").click()
    user.find(marker="monitor-close-in").click()
    assert editor._taps == {}
    assert protokol.lines() == []


async def test_hiding_a_line_keeps_its_entries(
    user: User, protokol: ProtokolState, selection: ProtokolSelection, driver: FormDriver
) -> None:
    editor = await _monitor(user, protokol, selection)
    user.find(marker="monitor-visibility-in").click()
    driver.connections[0].push("/a", 1)
    user.find(marker="monitor-visibility-in").click()
    editor._refresh()
    assert _rows(editor) == []
    assert "in" in editor._taps
    assert len(editor._taps["in"].messages()) == 1
    assert one(user, "monitor-visibility-in").props["icon"] == "visibility_off"
    user.find(marker="monitor-visibility-in").click()
    editor._refresh()
    assert len(_rows(editor)) == 1


async def test_line_clear_only_clears_that_line(
    user: User, protokol: ProtokolState, selection: ProtokolSelection, driver: FormDriver
) -> None:
    editor = await _monitor(user, protokol, selection)
    user.find(marker="monitor-visibility-in").click()
    user.find(marker="monitor-visibility-out").click()
    driver.connections[0].push("/in", 1)
    set_value(user, "monitor-send-input-out", "/out 1")
    user.find(marker="monitor-send-out").click()
    user.find(marker="monitor-clear-in").click()
    editor._refresh()
    assert [row["address"] for row in _rows(editor)] == ["/out"]


async def test_line_export_only_that_line(
    user: User,
    protokol: ProtokolState,
    selection: ProtokolSelection,
    driver: FormDriver,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import json

    from nicegui import ui

    downloads: list[tuple[bytes, str]] = []
    monkeypatch.setattr(
        ui.download,
        "content",
        lambda content, filename=None, media_type="": downloads.append((content, filename)),
    )
    editor = await _monitor(user, protokol, selection)
    user.find(marker="monitor-visibility-in").click()
    user.find(marker="monitor-visibility-out").click()
    driver.connections[0].push("/in", 1)
    set_value(user, "monitor-send-input-out", "/out 1")
    user.find(marker="monitor-send-out").click()
    editor._refresh()
    user.find(marker="monitor-export-jsonl-in").click()
    content, filename = downloads[-1]
    assert [json.loads(line)["address"] for line in content.decode().splitlines()] == ["/in"]
    assert "-in-" in filename


async def test_messages_render_with_theme_tokens(
    user: User, protokol: ProtokolState, selection: ProtokolSelection, driver: FormDriver
) -> None:
    from nicegui import ui

    editor = await _monitor(user, protokol, selection)
    user.find(marker="monitor-visibility-in").click()
    driver.connections[0].push("/a<b>", 1)
    editor._refresh()
    with pytest.raises(AssertionError):
        _ = user.find(kind=ui.table).elements  # design guide: no raw Quasar table
    content = str(one(user, "monitor-messages").content)
    assert "hw-text-body" in content
    assert "font-mono" in content
    assert "/a&lt;b&gt;" in content, "message text is escaped"


async def test_tapped_source_row_is_active(
    user: User, protokol: ProtokolState, selection: ProtokolSelection
) -> None:
    await _monitor(user, protokol, selection)
    user.find(marker="monitor-visibility-in").click()
    assert "hw-list-item-active" in one(user, "monitor-source-in").classes
    assert "hw-list-item-active" not in one(user, "monitor-source-out").classes
    assert one(user, "monitor-visibility-in").props["icon"] == "visibility"


async def test_hidden_line_has_no_clear_or_export(
    user: User, protokol: ProtokolState, selection: ProtokolSelection
) -> None:
    await _monitor(user, protokol, selection)
    user.find(marker="monitor-visibility-in").click()
    await user.should_see(marker="monitor-clear-in")
    await user.should_see(marker="monitor-export-in")
    user.find(marker="monitor-visibility-in").click()
    await user.should_not_see(marker="monitor-clear-in")
    await user.should_not_see(marker="monitor-export-in")
    await user.should_see(marker="monitor-close-in")


async def test_only_shown_lines_are_highlighted(
    user: User, protokol: ProtokolState, selection: ProtokolSelection
) -> None:
    await _monitor(user, protokol, selection)
    user.find(marker="monitor-visibility-in").click()
    assert "hw-list-item-active" in one(user, "monitor-source-in").classes
    user.find(marker="monitor-visibility-in").click()
    assert "hw-list-item-active" not in one(user, "monitor-source-in").classes


async def test_divider_between_lines_and_output_is_draggable(
    user: User, protokol: ProtokolState, selection: ProtokolSelection
) -> None:
    from nicegui import ui

    editor = await _monitor(user, protokol, selection)
    splitter = one(user, "monitor-splitter")
    assert isinstance(splitter, ui.splitter)
    splitter.set_value(40)
    assert editor._split == 40
    with user:
        editor.draw(editor._context, ui.column())
    assert editor._split == 40
    assert [s.value for s in user.find(kind=ui.splitter).elements] == [40, 40]
