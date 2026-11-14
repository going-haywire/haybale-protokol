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


async def test_line_row_puts_eye_title_and_icons_in_one_row_status_below(
    user: User, protokol: ProtokolState, selection: ProtokolSelection
) -> None:
    await _monitor(user, protokol, selection)
    user.find(marker="monitor-visibility-in").click()
    block = one(user, "monitor-source-in")
    head = one(user, "monitor-visibility-in").parent_slot.parent
    assert head.parent_slot.parent is block
    assert one(user, "monitor-clear-in").parent_slot.parent is head
    assert one(user, "monitor-close-in").parent_slot.parent is head
    assert one(user, "monitor-count-in").parent_slot.parent is block


async def test_divider_is_drawn_in_a_theme_colour(
    user: User, protokol: ProtokolState, selection: ProtokolSelection
) -> None:
    await _monitor(user, protokol, selection)
    style = one(user, "monitor-splitter").props.get("separator-style")
    assert isinstance(style, str)
    assert "var(--hw-separator" in style


async def test_eye_sits_with_the_icons_and_status_aligns_with_name(
    user: User, protokol: ProtokolState, selection: ProtokolSelection
) -> None:
    await _monitor(user, protokol, selection)
    user.find(marker="monitor-visibility-in").click()
    head = one(user, "monitor-visibility-in").parent_slot.parent
    children = list(head.default_slot.children)
    eye = children.index(one(user, "monitor-visibility-in"))
    name = next(i for i, c in enumerate(children) if getattr(c, "text", None) == "in")
    assert name < eye < children.index(one(user, "monitor-clear-in"))
    assert not any(c.startswith(("pl-", "ml-")) for c in one(user, "monitor-count-in").classes)


async def test_change_signal_keeps_dialog_and_send_text(
    user: User, protokol: ProtokolState, selection: ProtokolSelection
) -> None:
    editor = await _monitor(user, protokol, selection)
    user.find(marker="monitor-visibility-out").click()
    set_value(user, "monitor-send-input-out", "/typed 1")
    user.find(marker="monitor-new-line").click()
    dialog = one(user, "monitor-new-line-dialog")
    editor._on_change(editor._context, None)
    assert not dialog.is_deleted
    assert dialog.value
    assert one(user, "monitor-send-input-out").value == "/typed 1"


async def test_selecting_a_closed_gate_does_not_open_its_line(
    user: User, protokol: ProtokolState, selection: ProtokolSelection
) -> None:
    editor = await _monitor(user, protokol, selection)
    selection.select_gate("in")
    editor._on_selection(editor._context, None)
    assert editor._taps == {}
    assert protokol.lines() == []


async def test_selecting_an_open_gate_ticks_it(
    user: User, protokol: ProtokolState, selection: ProtokolSelection
) -> None:
    editor = await _monitor(user, protokol, selection)
    keeper = protokol.use("in", "in")
    assert isinstance(keeper, LineUse)
    selection.select_gate("in")
    editor._on_selection(editor._context, None)
    assert "in" in editor._taps
    editor.cleanup()
    keeper.release()


def test_copied_rows_keep_their_columns_apart() -> None:
    from haybale_protokol.editors.monitor_editor import _messages_html

    row = {"time": "16:00:28.479", "source": "Mix", "direction": "out", "address": "/t", "description": "x"}
    html = _messages_html([row])
    assert "16:00:28.479</span> <span" in html
    assert "Mix</span> <span" in html


async def test_order_toggle_shows_oldest_first_like_a_log(
    user: User, protokol: ProtokolState, selection: ProtokolSelection, driver: FormDriver
) -> None:
    editor = await _monitor(user, protokol, selection)
    user.find(marker="monitor-visibility-in").click()
    for i in range(3):
        driver.connections[0].push("/a", i)
    editor._refresh()
    assert [row["description"][-4:] for row in _rows(editor)] == ["(2,)", "(1,)", "(0,)"]
    user.find(marker="monitor-order").click()
    editor._refresh()
    assert [row["description"][-4:] for row in _rows(editor)] == ["(0,)", "(1,)", "(2,)"]
    user.find(marker="monitor-order").click()
    editor._refresh()
    assert _rows(editor)[0]["description"].endswith("(2,)")


async def test_log_order_keeps_the_newest_rows(
    user: User, protokol: ProtokolState, selection: ProtokolSelection, driver: FormDriver
) -> None:
    editor = await _monitor(user, protokol, selection)
    user.find(marker="monitor-visibility-in").click()
    user.find(marker="monitor-order").click()
    for i in range(MONITOR_ROWS + 50):
        driver.connections[0].push("/a", i)
    editor._refresh()
    rows = _rows(editor)
    assert len(rows) == MONITOR_ROWS
    assert rows[-1]["description"].endswith(f"({MONITOR_ROWS + 49},)")


async def test_log_order_follows_the_bottom_unless_scrolled_up(
    user: User, protokol: ProtokolState, selection: ProtokolSelection, driver: FormDriver
) -> None:
    editor = await _monitor(user, protokol, selection)
    user.find(marker="monitor-visibility-in").click()
    user.find(marker="monitor-order").click()
    scrolls: list[float | None] = []
    editor._messages_area.scroll_to = lambda **kw: scrolls.append(kw.get("percent"))
    driver.connections[0].push("/a", 1)
    editor._refresh()
    assert scrolls == [1.0]
    editor._on_messages_scroll(type("E", (), {"vertical_percentage": 0.4})())
    driver.connections[0].push("/a", 2)
    editor._refresh()
    assert scrolls == [1.0], "scrolled up to read: stay put"
    editor._on_messages_scroll(type("E", (), {"vertical_percentage": 1.0})())
    driver.connections[0].push("/a", 3)
    editor._refresh()
    assert scrolls == [1.0, 1.0]


async def test_toggling_scrolls_to_where_the_newest_rows_are(
    user: User, protokol: ProtokolState, selection: ProtokolSelection, driver: FormDriver
) -> None:
    editor = await _monitor(user, protokol, selection)
    user.find(marker="monitor-visibility-in").click()
    driver.connections[0].push("/a", 1)
    scrolls: list[float | None] = []
    editor._messages_area.scroll_to = lambda **kw: scrolls.append(kw.get("percent"))
    user.find(marker="monitor-order").click()
    assert scrolls[-1] == 1.0, "log order: to the bottom"
    user.find(marker="monitor-order").click()
    assert scrolls[-1] == 0.0, "newest first: back to the top"
