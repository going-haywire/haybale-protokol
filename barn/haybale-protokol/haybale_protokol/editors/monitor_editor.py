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
from typing import Any

from haywire.core.access import AccessTier
from haywire.core.session.context import SessionContext
from haywire.core.session.handlers import react_on, redraw_on
from haywire.ui import elements as hui
from haywire.ui.editor.base import BaseEditor
from haywire.ui.editor.decorator import editor
from haywire.ui.editor.identity import SlotName
from nicegui import ui

from haybale_protokol.drivers import Message, message_parser
from haybale_protokol.editors.gate_form import GateForm
from haybale_protokol.gates import Gate
from haybale_protokol.monitor_export import MonitorRow, to_csv, to_jsonl
from haybale_protokol.signals import ProtokolChanged
from haybale_protokol.states.protokol_selection import ProtokolSelection
from haybale_protokol.states.protokol_state import LineUse, ProtokolState
from haybale_protokol.taps import Tap

logger = logging.getLogger(__name__)

#: Seconds between two redraws of the table, at most.
MONITOR_REFRESH_S = 0.2
#: Rows the table shows, newest first.
MONITOR_ROWS = 300

_COLUMNS = [
    {"name": "time", "label": "Time", "field": "time", "align": "left"},
    {"name": "source", "label": "Source", "field": "source", "align": "left"},
    {"name": "direction", "label": "", "field": "direction", "align": "left"},
    {"name": "description", "label": "Message", "field": "description", "align": "left"},
]


@editor(
    label="Monitor",
    icon="monitor_heart",
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
        self._senders: dict[str, LineUse] = {}
        self._filter = ""
        self._paused = False
        self._shown: tuple[Any, ...] = ()
        self._export_rows: list[MonitorRow] = []
        self._first_draw = True
        self._table: ui.table | None = None
        self._sources_box: ui.column | None = None
        self._counts: dict[str, ui.label] = {}
        self._status: ui.label | None = None
        self._dialog_host: ui.element | None = None
        self._dialog: ui.dialog | None = None

    # -- signals ---------------------------------------------------------------------------

    @redraw_on(ProtokolChanged)
    def _on_change(self, context: SessionContext, signal: Any) -> None:
        """Redraw: gates or Lines changed."""

    @react_on(ProtokolSelection.gate, ProtokolSelection.line)
    def _on_selection(self, context: SessionContext, signal: Any) -> None:
        """Tick what the session selected, then show it."""
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
            with ui.column().classes("w-full h-full gap-1 p-1") as root:
                with ui.row().classes("w-full items-center gap-1 no-wrap"):
                    hui.input_field(
                        placeholder="Filter", value=self._filter, clearable=True, on_change=self._set_filter
                    ).classes("flex-1").mark("monitor-filter")
                    hui.icon_action(
                        "play_arrow" if self._paused else hui.icon.pause,
                        tooltip="Resume" if self._paused else "Pause",
                        on_click=self._toggle_pause,
                    ).mark("monitor-pause")
                    hui.icon_action(hui.icon.clear, tooltip="Clear", on_click=self._clear).mark(
                        "monitor-clear"
                    )
                    hui.icon_action(
                        hui.icon.download, tooltip="Export as JSONL", on_click=lambda: self._export("jsonl")
                    ).mark("monitor-export-jsonl")
                    hui.icon_action(
                        "table_view", tooltip="Export as CSV", on_click=lambda: self._export("csv")
                    ).mark("monitor-export-csv")
                    if self._can_edit():
                        hui.icon_action(
                            hui.icon.add, tooltip="New line…", on_click=self._open_new_line
                        ).mark("monitor-new-line")
                self._status = hui.hint("").mark("monitor-status")
                with ui.row().classes("w-full flex-1 gap-2 no-wrap min-h-0"):
                    with ui.scroll_area().classes("w-72 flex-shrink-0 h-full"):
                        self._sources_box = ui.column().classes("w-full gap-1")
                    self._table = (
                        ui.table(columns=_COLUMNS, rows=[], row_key="id")
                        .props("dense flat virtual-scroll")
                        .classes("flex-1 h-full")
                        .mark("monitor-table")
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
            for key, gate in self._sources().items():
                tapped = key in self._taps
                is_open = tapped or state.line_of(gate) is not None
                with ui.column().classes("w-full gap-0"):
                    with ui.row().classes("w-full items-center gap-1 no-wrap"):
                        ui.checkbox(
                            key, value=tapped, on_change=lambda e, k=key, g=gate: self._toggle(k, g, e.value)
                        ).props("dense").classes("flex-1 min-w-0").mark(f"monitor-source-{key}").set_enabled(
                            tapped or can_edit or is_open
                        )
                        if key.startswith("~") and tapped and can_edit:
                            hui.icon_action(
                                "save", tooltip="Save as gate…", on_click=lambda k=key: self._open_save_as(k)
                            ).mark(f"monitor-save-as-{key}")
                    if tapped:
                        self._counts[key] = hui.hint("").classes("pl-6").mark(f"monitor-count-{key}")
                        if can_edit and gate.direction in ("out", "two-way"):
                            self._draw_send_row(key, gate)
        self._update_counts()

    def _draw_send_row(self, key: str, gate: Gate) -> None:
        driver = self._state().driver(gate.protocol)
        parse = message_parser(driver) if driver is not None else None
        with ui.column().classes("w-full gap-0 pl-6"):
            if parse is None:
                hui.hint(f"test-send not available for {gate.protocol}")
                return
            with ui.row().classes("w-full items-center gap-1 no-wrap"):
                field = (
                    hui.input_field(placeholder="Test message")
                    .classes("flex-1")
                    .mark(f"monitor-send-input-{key}")
                )
                error = hui.error_label("").mark(f"monitor-send-error-{key}")
                error.set_visibility(False)
                hui.icon_action(
                    "send",
                    tooltip="Send",
                    on_click=lambda: self._send(key, gate, str(field.value or ""), error),
                ).mark(f"monitor-send-{key}")

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

    def _toggle(self, key: str, gate: Gate, on: bool) -> None:
        if on:
            self._open_tap(key, gate)
        else:
            self._close_tap(key)
        self._draw_sources()

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
            gate = state.gates().get(selection.gate)
            if gate is not None:
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
        """Rebuild the table from the taps, when something changed since the last time."""
        shown = (self._filter, *((key, tap.received, tap.dropped) for key, tap in self._taps.items()))
        if shown == self._shown:
            return
        self._shown = shown
        rows = self._collect()
        self._export_rows = rows
        if self._table is not None:
            self._table.rows = [_table_row(index, row) for index, row in enumerate(rows[:MONITOR_ROWS])]
            self._table.update()
        self._update_counts()

    def _collect(self) -> list[MonitorRow]:
        """Every kept message that passes the filter, newest first."""
        state = self._state()
        needle = self._filter.lower()
        collected: list[MonitorRow] = []
        for key, tap in self._taps.items():
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

    def _set_filter(self, event: Any) -> None:
        self._filter = str(event.value or "")
        self._refresh()

    def _toggle_pause(self) -> None:
        self._paused = not self._paused
        for tap in self._taps.values():
            tap.paused = self._paused
        self.wrapper.redraw()

    def _clear(self) -> None:
        for tap in self._taps.values():
            tap.clear()
        self._refresh()

    def _export(self, kind: str) -> None:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        rows = list(reversed(self._export_rows))
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


def _table_row(index: int, row: MonitorRow) -> dict[str, Any]:
    stamp = datetime.fromtimestamp(row.time).strftime("%H:%M:%S.%f")[:-3]
    return {
        "id": index,
        "time": stamp,
        "source": row.source,
        "direction": row.direction,
        "address": row.address,
        "description": row.description,
    }


def _show(error: ui.label, message: str) -> None:
    error.set_text(message)
    error.set_visibility(True)
