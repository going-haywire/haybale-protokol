"""MonitorEditor — live traffic on Lines, filtered, with test-send and export (EDIT tab).

Each ticked source is a tap: a Line user that only appends to a bounded buffer, so watching
never slows a Line. The table is redrawn at most every ``MONITOR_REFRESH_S`` from the taps,
never from signals. Watching a Line that is already open is VIEW; opening one, a new Line,
test-send and "Save as gate…" are EDIT.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from html import escape
from typing import Any

from haywire.core.access import AccessTier
from haywire.core.session.context import SessionContext
from haywire.core.session.handlers import react_on
from haywire.ui import elements as hui
from haywire.ui.editor.base import BaseEditor
from haywire.ui.editor.decorator import editor
from haywire.ui.editor.identity import SlotName
from nicegui import ui

from haybale_protokol.drivers import Message, message_parser
from haybale_protokol.editor_layout import SPLITTER_SEPARATOR, list_block, scroll_area
from haybale_protokol.gate_form import GateForm
from haybale_protokol.gates import Gate
from haybale_protokol.icons import ProtokolIcon
from haybale_protokol.icons import icon as icons
from haybale_protokol.monitor_export import MonitorRow, to_csv, to_jsonl
from haybale_protokol.signals import ProtokolChanged
from haybale_protokol.states.protokol_selection import ProtokolSelection
from haybale_protokol.line_use import LineUse
from haybale_protokol.states.protokol_state import ProtokolState
from haybale_protokol.taps import Tap

logger = logging.getLogger(__name__)

#: Seconds between two redraws of the table, at most.
MONITOR_REFRESH_S = 0.2
#: Where the divider between the lines and the output starts, and how far it may go (percent).
SPLIT_START = 25
SPLIT_LIMITS = (10, 70)
#: Rows the table shows, newest first.
MONITOR_ROWS = 300


@editor(
    label="Monitor",
    icon=ProtokolIcon.monitor,
    default_slot=SlotName.EDIT,
    opens="on_context",
    requires=AccessTier.VIEW,
    description="Live traffic on Lines",
)
class MonitorEditor(BaseEditor):
    """Tick a gate or an open Line to watch it; the table shows the newest messages first.

    The filter matches the message text, case-insensitively. "New line…" opens a Line no gate
    uses yet, and "Save as gate…" turns it into a gate. A ticked output gate gets a test-send
    row: type a message in the protocol's own form (for OSC: ``/address 0.5 3 word``).
    Export writes every message the filter keeps, as JSONL or CSV.
    """

    def __init__(self, wrapper: Any) -> None:
        super().__init__(wrapper)
        self._context: SessionContext | None = None
        self._taps: dict[str, Tap] = {}
        self._gates: dict[str, Gate] = {}
        self._split: float = SPLIT_START
        """Where the user left the divider, kept across redraws."""
        self._newest_first = True
        """Order of the output: newest first, or oldest first like a log."""
        self._follow = True
        """In log order: keep the newest row in view; off while the user has scrolled up to read."""
        self._messages_area: ui.scroll_area | None = None
        self._order_button: ui.button | None = None
        self._send_text: dict[str, str] = {}
        """What was typed in each line's test-send field, kept across refreshes."""
        self._hidden: set[str] = set()
        """Watched lines whose messages the output hides."""
        self._senders: dict[str, LineUse] = {}
        self._filter = ""
        self._paused = False
        self._shown: tuple[Any, ...] = ()
        self._export_rows: list[MonitorRow] = []
        self._first_draw = True
        self._messages: ui.html | None = None
        self._view: list[dict[str, Any]] = []
        self._sources_box: ui.column | None = None
        self._counts: dict[str, ui.label] = {}
        self._status: ui.label | None = None
        self._dialog_host: ui.element | None = None
        self._dialog: ui.dialog | None = None

    # -- signals ---------------------------------------------------------------------------

    @react_on(ProtokolChanged)
    def _on_change(self, context: SessionContext, signal: Any) -> None:
        """Refresh the line list: gates or Lines changed (an open dialog and typed text stay)."""
        self._context = context
        self._draw_sources()

    @react_on(ProtokolSelection.gate, ProtokolSelection.line)
    def _on_selection(self, context: SessionContext, signal: Any) -> None:
        """Tick what the session selected when its Line is open, then show it."""
        self._context = context
        self._tick_selection()
        self._draw_sources()

    # -- drawing ---------------------------------------------------------------------------

    def draw(self, context: SessionContext, container: ui.element) -> None:
        self._context = context
        container.clear()
        if self._first_draw:
            self._first_draw = False
            self._tick_selection()
        with container:
            with ui.column().classes("w-full h-full gap-0") as root:
                with hui.editor_toolbar():
                    hui.input_field(
                        placeholder="Filter", value=self._filter, clearable=True, on_change=self._set_filter
                    ).classes("flex-1").mark("monitor-filter")
                    self._order_button = hui.icon_action(
                        icons.newest_first if self._newest_first else icons.oldest_first,
                        tooltip="Newest first or oldest first (like a log)",
                        on_click=self._toggle_order,
                    ).mark("monitor-order")
                    hui.icon_action(
                        hui.icon.resume if self._paused else hui.icon.pause,
                        tooltip="Resume" if self._paused else "Pause",
                        on_click=self._toggle_pause,
                    ).mark("monitor-pause")
                    hui.icon_action(hui.icon.clear, tooltip="Clear", on_click=self._clear).mark(
                        "monitor-clear"
                    )
                    hui.icon_action(
                        hui.icon.download,
                        tooltip="Export the shown lines as JSONL",
                        on_click=lambda: self._export("jsonl"),
                    ).mark("monitor-export-jsonl")
                    hui.icon_action(
                        icons.export_csv,
                        tooltip="Export the shown lines as CSV",
                        on_click=lambda: self._export("csv"),
                    ).mark("monitor-export-csv")
                    if self._can_edit():
                        hui.icon_action(
                            hui.icon.add, tooltip="New line…", on_click=self._open_new_line
                        ).mark("monitor-new-line")
                self._status = hui.hint("").classes("px-2").mark("monitor-status")
                with (
                    ui.splitter(value=self._split, limits=SPLIT_LIMITS, on_change=self._set_split)
                    .classes("w-full flex-1 min-h-0")
                    .props(SPLITTER_SEPARATOR)
                    .mark("monitor-splitter") as splitter
                ):
                    with splitter.before:
                        with ui.column().classes("w-full h-full gap-0"):
                            with scroll_area():
                                self._sources_box = ui.column().classes("w-full gap-0 p-1")
                    with splitter.after:
                        with ui.column().classes("w-full h-full min-w-0 gap-0"):
                            with scroll_area() as messages_area:
                                messages_area.on_scroll(self._on_messages_scroll)
                                self._messages_area = messages_area
                                self._messages = (
                                    ui.html("", sanitize=False)
                                    .classes("w-full p-1")
                                    .mark("monitor-messages")
                                )
                ui.timer(MONITOR_REFRESH_S, self._refresh)
            self._dialog_host = root
        self._shown = ()
        self._draw_sources()
        self._refresh()

    def _draw_sources(self) -> None:
        if self._sources_box is None:
            return
        self._sources_box.clear()
        self._counts = {}
        state = self._state()
        can_edit = self._can_edit()
        with self._sources_box:
            sources = self._sources()
            if not sources:
                hui.hint("No gates or open Lines.").classes("px-2")
            for key, gate in sources.items():
                tapped = key in self._taps
                shown = tapped and key not in self._hidden
                with list_block(active=shown).mark(f"monitor-source-{key}"):
                    with ui.row().classes("w-full items-center gap-1 no-wrap"):
                        ui.label(key).classes("text-sm font-medium truncate flex-1 min-w-0")
                        self._draw_visibility(key, gate, tapped, can_edit or state.line_of(gate) is not None)
                        if tapped:
                            self._draw_line_actions(key, can_edit, shown=shown)
                    if tapped:
                        self._counts[key] = (
                            ui.label("").classes("text-xs hw-text-dim").mark(f"monitor-count-{key}")
                        )
                if tapped and can_edit and gate.direction in ("out", "two-way"):
                    self._draw_send_row(key, gate)
        self._update_counts()

    def _draw_visibility(self, key: str, gate: Gate, tapped: bool, can_open: bool) -> None:
        """The line's eye: watch it (not yet watched), or show and hide it in the output."""
        if not tapped:
            button = hui.icon_action(
                hui.icon.hidden, tooltip="Watch this line", on_click=lambda: self._watch(key, gate)
            ).mark(f"monitor-visibility-{key}")
            if not can_open:
                # Design guide §2.11: disabled is opacity plus no pointer events, nothing else.
                button.classes("opacity-40 pointer-events-none").tooltip(
                    "Opening a closed Line needs edit access"
                )
            return
        hidden = key in self._hidden
        hui.icon_action(
            hui.icon.hidden if hidden else hui.icon.shown,
            tooltip="Show in the output" if hidden else "Hide from the output",
            on_click=lambda: self._toggle_hidden(key),
        ).mark(f"monitor-visibility-{key}")

    def _draw_line_actions(self, key: str, can_edit: bool, *, shown: bool) -> None:
        """Save as gate, Clear, Export and Stop watching; a hidden line keeps only Save and Stop."""
        if key.startswith("~") and can_edit:
            hui.icon_action(
                hui.icon.save, tooltip="Save as gate…", on_click=lambda: self._open_save_as(key)
            ).mark(f"monitor-save-as-{key}")
        if shown:
            hui.icon_action(
                hui.icon.clear, tooltip="Clear this line", on_click=lambda: self._clear(key)
            ).mark(f"monitor-clear-{key}")
            with hui.icon_action(hui.icon.download, tooltip="Export this line").mark(
                f"monitor-export-{key}"
            ):
                with ui.menu():
                    hui.menu_row("As JSONL", on_click=lambda: self._export("jsonl", key)).mark(
                        f"monitor-export-jsonl-{key}"
                    )
                    hui.menu_row(
                        "As CSV", icon=icons.export_csv, on_click=lambda: self._export("csv", key)
                    ).mark(f"monitor-export-csv-{key}")
        hui.icon_action(hui.icon.close, tooltip="Stop watching", on_click=lambda: self._stop(key)).mark(
            f"monitor-close-{key}"
        )

    def _draw_send_row(self, key: str, gate: Gate) -> None:
        driver = self._state().driver(gate.protocol)
        parse = message_parser(driver) if driver is not None else None
        with hui.indented().classes("w-full pb-1"):
            if parse is None:
                hui.hint(f"test-send not available for {gate.protocol}")
                return
            with ui.row().classes("w-full items-center gap-1 no-wrap"):
                field = (
                    hui.input_field(
                        placeholder="Test message",
                        value=self._send_text.get(key, ""),
                        on_change=lambda e: self._send_text.__setitem__(key, str(e.value or "")),
                    )
                    .classes("flex-1")
                    .mark(f"monitor-send-input-{key}")
                )
                hui.icon_action(
                    icons.send,
                    tooltip="Send",
                    on_click=lambda: self._send(key, gate, str(field.value or ""), error),
                ).mark(f"monitor-send-{key}")
            error = hui.error_label("").mark(f"monitor-send-error-{key}")
            error.set_visibility(False)

    # -- taps ------------------------------------------------------------------------------

    def _sources(self) -> dict[str, Gate]:
        """Every source to offer: the gates, tapped Lines without a gate, and other open Lines."""
        state = self._state()
        sources: dict[str, Gate] = dict(state.gates())
        for key, gate in self._gates.items():
            sources.setdefault(key, gate)
        for line in state.lines():
            if line.gate is not None and line.gate.name not in sources and line.is_open:
                sources.setdefault(f"~{line.key.address}", line.gate)
        return dict(sorted(sources.items()))

    def _watch(self, key: str, gate: Gate) -> None:
        if self._open_tap(key, gate):
            self._hidden.discard(key)
        self._draw_sources()

    def _stop(self, key: str) -> None:
        """Stop watching: give the Line back; its messages go."""
        self._close_tap(key)
        self._hidden.discard(key)
        self._draw_sources()
        self._refresh()

    def _toggle_hidden(self, key: str) -> None:
        """Hide or show the line's messages in the output; the tap keeps collecting."""
        if key in self._hidden:
            self._hidden.discard(key)
        else:
            self._hidden.add(key)
        self._draw_sources()
        self._refresh()

    def _open_tap(self, key: str, gate: Gate) -> bool:
        if key in self._taps:
            return True
        result = self._state().tap(gate, open_line=self._can_edit())
        if isinstance(result, str):
            self._set_status(f"{key}: {result}")
            return False
        result.paused = self._paused
        self._taps[key] = result
        self._gates[key] = gate
        self._set_status("")
        return True

    def _close_tap(self, key: str) -> None:
        tap = self._taps.pop(key, None)
        if tap is not None:
            tap.close()
        sender = self._senders.pop(key, None)
        if sender is not None:
            sender.release()
        self._gates.pop(key, None)

    def _tick_selection(self) -> None:
        if self._context is None:
            return
        selection = self._context.data[ProtokolSelection]
        state = self._state()
        if selection.gate is not None:
            # Selecting never opens a Line (a TCP client would connect): only an open one is ticked.
            gate = state.gates().get(selection.gate)
            if gate is not None and state.line_of(gate) is not None:
                self._open_tap(gate.name, gate)
        elif selection.line is not None:
            for line in state.lines():
                if line.key == selection.line and line.gate is not None:
                    self._open_tap(f"~{line.key.address}", line.gate)

    def cleanup(self) -> None:
        for key in list(self._taps):
            self._close_tap(key)
        for sender in self._senders.values():
            sender.release()
        self._senders.clear()

    async def handle_close_request(self) -> bool:
        self.cleanup()
        return True

    # -- refresh ---------------------------------------------------------------------------

    def _refresh(self) -> None:
        """Rebuild the message list from the taps, when something changed since the last time."""
        shown = (
            self._filter,
            self._newest_first,
            frozenset(self._hidden),
            *((key, tap.received, tap.dropped) for key, tap in self._taps.items()),
        )
        if shown == self._shown:
            return
        self._shown = shown
        rows = self._collect()
        self._export_rows = rows
        window = rows[:MONITOR_ROWS]
        if not self._newest_first:
            window.reverse()
        self._view = [_view_row(row) for row in window]
        if self._messages is not None and not self._messages.is_deleted:
            self._messages.set_content(_messages_html(self._view))
            if not self._newest_first and self._follow and self._messages_area is not None:
                self._messages_area.scroll_to(percent=1.0)
        self._update_counts()

    def _collect(self, only: str | None = None) -> list[MonitorRow]:
        """Every kept message of the shown lines (or of ``only``) that passes the filter, newest first."""
        state = self._state()
        needle = self._filter.lower()
        collected: list[MonitorRow] = []
        for key, tap in self._taps.items():
            if (only is not None and key != only) or (only is None and key in self._hidden):
                continue
            gate = self._gates[key]
            driver = state.driver(gate.protocol)
            for entry in tap.messages():
                message = entry.message
                text = driver.describe(message) if driver is not None else message.address
                if needle and needle not in text.lower():
                    continue
                collected.append(
                    MonitorRow(message.time, key, entry.direction, message.address, message.args, text)
                )
        # Newest first; equal times keep newest-first order, since the sort is stable.
        collected.reverse()
        collected.sort(key=lambda row: -row.time)
        return collected

    def _update_counts(self) -> None:
        for key, label in self._counts.items():
            tap = self._taps.get(key)
            if tap is not None and not label.is_deleted:
                label.set_text(f"received {tap.received} · dropped {tap.dropped}")

    # -- actions ---------------------------------------------------------------------------

    def _toggle_order(self) -> None:
        """Switch between newest first and oldest first; log order starts following the bottom."""
        self._newest_first = not self._newest_first
        self._follow = True
        icon = icons.newest_first if self._newest_first else icons.oldest_first
        if self._order_button is not None and not self._order_button.is_deleted:
            self._order_button.props(f"icon={icon}")
        self._refresh()
        if self._newest_first and self._messages_area is not None and not self._messages_area.is_deleted:
            self._messages_area.scroll_to(percent=0.0)  # the newest rows are at the top again

    def _on_messages_scroll(self, event: Any) -> None:
        """In log order, follow the newest row only while the user is at the bottom."""
        self._follow = float(event.vertical_percentage) >= 0.98

    def _set_split(self, event: Any) -> None:
        self._split = float(event.value)

    def _set_filter(self, event: Any) -> None:
        self._filter = str(event.value or "")
        self._refresh()

    def _toggle_pause(self) -> None:
        self._paused = not self._paused
        for tap in self._taps.values():
            tap.paused = self._paused
        self.wrapper.redraw()

    def _clear(self, key: str | None = None) -> None:
        """Clear one line, or every shown line."""
        for name, tap in self._taps.items():
            if (key is None and name not in self._hidden) or name == key:
                tap.clear()
        self._refresh()

    def _export(self, kind: str, key: str | None = None) -> None:
        """Export one line, or every shown line, as the filter keeps them, oldest first."""
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        rows = list(reversed(self._collect(key) if key is not None else self._export_rows))
        if key is not None:
            stamp = f"{_file_safe(key)}-{stamp}"
        content = to_jsonl(rows) if kind == "jsonl" else to_csv(rows)
        ui.download.content(content.encode("utf-8"), f"protokol-monitor-{stamp}.{kind}")

    def _send(self, key: str, gate: Gate, text: str, error: ui.label) -> None:
        if not self._can_edit():
            return
        state = self._state()
        driver = state.driver(gate.protocol)
        parse = message_parser(driver) if driver is not None else None
        if parse is None:
            return
        try:
            message = parse(text)
        except ValueError as exc:
            _show(error, str(exc))
            return
        sender = self._senders.get(key)
        if sender is None:
            result = state.use_gate(gate, "out")
            if isinstance(result, str):
                _show(error, result)
                return
            sender = self._senders[key] = result
        stamped = Message(message.address, message.args, time.time(), message.extra)
        if not sender.line.send(stamped):
            _show(error, f"dropped: {sender.line.status}")
            return
        error.set_visibility(False)
        self._refresh()

    # -- dialogs ---------------------------------------------------------------------------

    def _new_dialog(self, mark: str) -> ui.dialog:
        if self._dialog is not None and not self._dialog.is_deleted:
            self._dialog.delete()
        assert self._dialog_host is not None
        with self._dialog_host:
            self._dialog = ui.dialog().mark(mark)
        return self._dialog

    def _open_new_line(self) -> None:
        dialog = self._new_dialog("monitor-new-line-dialog")
        form = GateForm(self._state(), None, named=False)
        with dialog, hui.dialog_card("w-[480px] max-w-full"):
            hui.heading("Watch a new Line")
            form.draw()
            error = hui.error_label("").mark("monitor-new-line-error")
            error.set_visibility(False)
            with hui.action_row().classes("mt-2"):
                ui.button("Cancel", on_click=dialog.close).props("flat dense")
                hui.confirm_button("Open", on_click=lambda: self._open_ad_hoc(dialog, error, form)).mark(
                    "monitor-new-line-open"
                )
        dialog.open()

    def _open_ad_hoc(self, dialog: ui.dialog, error: ui.label, form: GateForm) -> None:
        try:
            filled = form.gate()
        except ValueError as exc:
            _show(error, str(exc))
            return
        gate = Gate("~new", filled.protocol, filled.direction, filled.device, filled.options)
        result = self._state().tap(gate, open_line=True)
        if isinstance(result, str):
            _show(error, result)
            return
        key = f"~{result.use.line.key.address}"
        if key in self._taps:
            result.close()
        else:
            result.paused = self._paused
            self._taps[key] = result
            self._gates[key] = gate
        dialog.close()
        self._draw_sources()

    def _open_save_as(self, key: str) -> None:
        gate = self._gates[key]
        dialog = self._new_dialog("gate-dialog")
        form = GateForm(self._state(), Gate("", gate.protocol, gate.direction, gate.device, gate.options))
        with dialog, hui.dialog_card("w-[480px] max-w-full"):
            hui.heading("Save as gate")
            form.draw()
            error = hui.error_label("").mark("gate-dialog-error")
            error.set_visibility(False)
            with hui.action_row().classes("mt-2"):
                ui.button("Cancel", on_click=dialog.close).props("flat dense")
                hui.confirm_button("Save", on_click=lambda: self._save_as(dialog, error, form, key)).mark(
                    "gate-dialog-save"
                )
        dialog.open()

    def _save_as(self, dialog: ui.dialog, error: ui.label, form: GateForm, key: str) -> None:
        try:
            gate = form.gate()
        except ValueError as exc:
            _show(error, str(exc))
            return
        state = self._state()
        problem = state.save_gate(gate)
        if problem is not None:
            _show(error, problem)
            return
        # Tap the saved gate before closing the ad-hoc tap, so the Line is handed over, not reopened.
        self._open_tap(gate.name, gate)
        self._close_tap(key)
        dialog.close()
        self._draw_sources()

    # -- helpers ---------------------------------------------------------------------------

    def _state(self) -> ProtokolState:
        assert self._context is not None
        return self._context.app_data[ProtokolState]

    def _can_edit(self) -> bool:
        return self._context is not None and bool(self._context.can_edit())

    def _set_status(self, text: str) -> None:
        if self._status is not None and not self._status.is_deleted:
            self._status.set_text(text)


def _view_row(row: MonitorRow) -> dict[str, Any]:
    stamp = datetime.fromtimestamp(row.time).strftime("%H:%M:%S.%f")[:-3]
    return {
        "time": stamp,
        "source": row.source,
        "direction": row.direction,
        "address": row.address,
        "description": row.description,
    }


def _messages_html(view: list[dict[str, Any]]) -> str:
    """The message list as one block of rows; theme tokens only (design guide §1.2, §3.3)."""
    if not view:
        return '<div class="text-xs hw-text-dim px-1">No messages yet.</div>'
    lines = []
    for row in view:
        direction = "out" if row["direction"] == "out" else "in "
        lines.append(
            '<div class="flex gap-2 font-mono text-xs whitespace-nowrap min-w-0">'
            f'<span class="hw-text-dim flex-shrink-0">{escape(row["time"])}</span> '
            f'<span class="hw-text-muted flex-shrink-0">{escape(row["source"])}</span> '
            f'<span class="hw-text-dim flex-shrink-0">{direction}</span> '
            f'<span class="hw-text-body truncate">{escape(row["description"])}</span>'
            "</div>"
        )
    return "".join(lines)


def _file_safe(text: str) -> str:
    return "".join(c if c.isalnum() or c in "._-" else "_" for c in text).strip("_") or "line"


def _show(error: ui.label, message: str) -> None:
    error.set_text(message)
    error.set_visibility(True)
