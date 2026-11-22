"""GatesEditor — the project's gates above, the Device pane below (ACTION slot; design §10.4).

Everyone who can view sees the gates; editing them needs EDIT (gates are project content, like
graphs), editing the Device list needs ADMIN. Clicking a row selects the gate, and the Device pane
below shows it. A gate that does not work shows red with the reason, cannot be opened in the
Monitor, and puts a red dot on the editor's icon. The divider between the panes moves and never
collapses; its place is kept while the page is open.
"""

from __future__ import annotations

import logging
from typing import Any

from haywire.api.workbench import (
    AccessTier,
    BaseEditor,
    Reveal,
    SessionContext,
    SlotName,
    editor,
    hui,
    react_on,
)
from nicegui import ui

from haybale_protokol.device_pane import DevicePane
from haybale_protokol.editor_layout import SPLITTER_SEPARATOR, list_block, scroll_area
from haybale_protokol.gate_form import GateForm
from haybale_protokol.gate_health import GateHealth
from haybale_protokol.gates import Gate
from haybale_protokol.icons import icon as icons
from haybale_protokol.signals import ProtokolChanged
from haybale_protokol.states.protokol_selection import ProtokolSelection
from haybale_protokol.states.protokol_state import ProtokolState

logger = logging.getLogger(__name__)

#: A small round dot in the current text colour (the tone's theme class sets the colour).
_DOT = "display: inline-block; border-radius: 50%; background: currentColor; flex-shrink: 0"
#: An icon action that cannot be used now (``hui.icon_action``'s disabled rule).
_DISABLED = "opacity: 0.4; pointer-events: none"
#: Where the divider starts (percent of the height given to the gates), and how far it moves:
#: never so far that either pane disappears.
SPLIT_START = 60.0
SPLIT_LIMITS = (20, 80)


def any_unhealthy(state: ProtokolState) -> bool:
    """Whether any gate does not work now, or the Gate file has a broken entry: the icon's red dot."""
    gates = state.gates()
    if state.gate_file_error is not None or state.gate_errors:
        return True
    return any(not state.health(gate).healthy for gate in gates.values())


@editor(
    label="Gates",
    icon=hui.icon.network,
    default_slot=SlotName.ACTION,
    requires=AccessTier.VIEW,
    description="The project's gates and their Lines",
)
class GatesEditor(BaseEditor):
    """One row per gate: its name, protocol and direction, and below them its status.

    The status says whether its Line is open (and by how many users), closed, or why the gate
    cannot be used: protocol not installed, unbound device, or a malformed entry. With EDIT a
    row can be edited or deleted and the header adds a gate. An unbound gate offers "Bind…",
    which selects its device for the Device editor.
    """

    def __init__(self, wrapper: Any) -> None:
        super().__init__(wrapper)
        self._context: SessionContext | None = None
        self._rows: ui.column | None = None
        self._dialog_host: ui.element | None = None
        self._dialog: ui.dialog | None = None
        self._split: float = SPLIT_START
        """Where the user left the divider, kept across redraws (not across reloads, §10.6.3)."""
        self._pane = DevicePane(lambda: self._context)

    @react_on(ProtokolChanged, ProtokolSelection.gate, ProtokolSelection.line, ProtokolSelection.device)
    def _on_change(self, context: SessionContext, signal: Any) -> None:
        """Refresh the rows and the icon's dot: the gates, their health or the selection changed.

        Only the rows: a full redraw would destroy an open dialog and what was typed in it.
        """
        self._context = context
        self._draw_rows()
        self._pane.draw_body()
        self.wrapper.refresh_tab_bar()

    def draw_tab(self, context: SessionContext, *, orientation: str) -> None:
        """The icon (and label in a tab slot), with a red dot while any gate does not work."""
        label = self.wrapper.label or self.class_identity.label
        try:
            broken = any_unhealthy(context.app_data[ProtokolState])
        except Exception:  # haybale-protokol not ready: no dot rather than no icon
            broken = False
        with ui.row().classes("items-center gap-1 no-wrap"):
            with ui.element("div").classes("relative inline-flex"):
                if orientation == "vertical":
                    ui.icon(self.class_identity.icon).tooltip(label)
                else:
                    ui.icon(self.class_identity.icon, size="14px")
                if broken:
                    ui.element("span").classes("hw-text-danger absolute").style(
                        f"{_DOT}; width: 7px; height: 7px; top: -1px; right: -2px"
                    ).tooltip("A gate does not work").mark("gates-tab-dot")
            if orientation != "vertical":
                ui.label(label)

    def draw(self, context: SessionContext, container: ui.element) -> None:
        self._context = context
        container.clear()
        with container:
            with ui.column().classes("w-full h-full gap-0") as root:
                with (
                    ui.splitter(
                        horizontal=True, value=self._split, limits=SPLIT_LIMITS, on_change=self._set_split
                    )
                    .classes("w-full flex-1 min-h-0")
                    .props(SPLITTER_SEPARATOR)
                    .mark("gates-splitter") as splitter
                ):
                    with splitter.before:
                        with ui.column().classes("w-full h-full gap-0"):
                            with hui.slot_header("Gates", icon=hui.icon.network):
                                if self._can_edit():
                                    hui.icon_action(
                                        hui.icon.add, tooltip="Add a gate", on_click=self._open_add
                                    ).mark("gate-add")
                            with scroll_area():
                                self._rows = ui.column().classes("w-full gap-0 p-1")
                    with splitter.after:
                        with ui.column().classes("w-full h-full gap-0") as pane:
                            self._pane.draw(dialog_host=pane)
            self._dialog_host = root
            self._draw_rows()

    def _set_split(self, event: Any) -> None:
        self._split = float(event.value)

    # -- rows ---------------------------------------------------------------------------

    def _state(self) -> ProtokolState:
        assert self._context is not None
        return self._context.app_data[ProtokolState]

    def _selection(self) -> ProtokolSelection:
        assert self._context is not None
        return self._context.data[ProtokolSelection]

    def _can_edit(self) -> bool:
        return self._context is not None and bool(self._context.can_edit())

    def _draw_rows(self) -> None:
        if self._rows is None:
            return
        self._rows.clear()
        state = self._state()
        gates = state.gates()
        with self._rows:
            if state.gate_file_error is not None:
                hui.error_label(f"gate file: {state.gate_file_error}").mark("gates-file-error")
            if not gates and not state.gate_errors and state.gate_file_error is None:
                hui.hint("No gates yet.").classes("px-2")
            for name in sorted({*gates, *state.gate_errors}):
                gate = gates.get(name)
                if gate is None:
                    self._draw_broken_row(name, state.gate_errors[name])
                else:
                    self._draw_row(gate, state.health(gate))

    def _draw_row(self, gate: Gate, health: GateHealth) -> None:
        """A health dot, name, tags and actions on one row; the health's reason on a line below."""
        status = health.reason
        tone = "hw-text-success" if health.healthy else "hw-text-danger"
        selected = self._selection().gate == gate.name
        select = lambda _e=None, g=gate: self._selection().select_gate(g.name)  # noqa: E731
        with list_block(active=selected).mark(f"gate-row-{gate.name}"):
            with ui.row().classes("w-full items-center gap-1 no-wrap"):
                # Only the name area selects: a click on an icon would bubble to a row-wide handler.
                with (
                    ui.row()
                    .classes("flex-1 min-w-0 items-center gap-1 no-wrap cursor-pointer")
                    .on("click", select)
                    .mark(f"gate-select-{gate.name}")
                ):
                    ui.element("span").classes(tone).style(f"{_DOT}; width: 6px; height: 6px").tooltip(
                        health.state
                    ).mark(f"gate-health-{gate.name}")
                    hui.subject(gate.name).classes("truncate min-w-0")
                    hui.tag(gate.protocol)
                    hui.tag(gate.direction)
                if health.state == "unbound":
                    hui.icon_action(
                        icons.bind,
                        tooltip="Bind…",
                        on_click=lambda g=gate: self._selection().select_device(g.device),
                    ).mark(f"gate-bind-{gate.name}")
                if health.healthy:
                    hui.icon_action(
                        icons.monitor, tooltip="Monitor", on_click=lambda g=gate: self._open_monitor(g)
                    ).mark(f"gate-monitor-{gate.name}")
                else:
                    # The tooltip sits on a wrapper: a button without pointer events shows none.
                    with ui.element("span").classes("inline-flex").tooltip(f"Cannot monitor: {status}"):
                        hui.icon_action(icons.monitor).style(_DISABLED).mark(f"gate-monitor-{gate.name}")
                editable = self._can_edit()
                hui.icon_action(
                    hui.icon.edit if editable else hui.icon.view,
                    tooltip="Edit" if editable else "Details",
                    on_click=lambda g=gate: self._open_edit(g),
                ).mark(f"gate-edit-{gate.name}")
                if editable:
                    hui.icon_action(
                        hui.icon.delete,
                        tooltip="Delete",
                        on_click=lambda n=gate.name: self._confirm_delete(n),
                    ).mark(f"gate-delete-{gate.name}")
            hint = hui.hint(status).classes("truncate w-full cursor-pointer").tooltip(status)
            if not health.healthy:
                hint.classes("hw-text-danger")
            hint.on("click", select).mark(f"gate-status-{gate.name}")

    def _draw_broken_row(self, name: str, error: str) -> None:
        with list_block().mark(f"gate-row-{name}"):
            with ui.row().classes("w-full items-center gap-1 no-wrap"):
                hui.subject(name).classes("truncate min-w-0")
                ui.space()
                if self._can_edit():
                    hui.icon_action(
                        hui.icon.delete, tooltip="Delete", on_click=lambda n=name: self._confirm_delete(n)
                    ).mark(f"gate-delete-{name}")
            hui.error_label(error).classes("truncate w-full").tooltip(error).mark(f"gate-status-{name}")

    def _open_monitor(self, gate: Gate) -> None:
        """Select the gate and open the Monitor, which ticks the selection."""
        from haybale_protokol.editors.monitor_editor import MonitorEditor

        assert self._context is not None
        self._selection().select_gate(gate.name)
        self._context.session.publish(Reveal(editor=MonitorEditor))

    # -- dialogs ------------------------------------------------------------------------

    def _new_dialog(self) -> ui.dialog:
        if self._dialog is not None and not self._dialog.is_deleted:
            self._dialog.delete()
        assert self._dialog_host is not None
        with self._dialog_host:
            self._dialog = ui.dialog().mark("gate-dialog")
        return self._dialog

    def _open_add(self) -> None:
        self._open_form(None)

    def _open_edit(self, gate: Gate) -> None:
        self._open_form(gate)

    def _open_form(self, gate: Gate | None) -> None:
        state = self._state()
        editable = self._can_edit()
        dialog = self._new_dialog()
        form = GateForm(state, gate)
        with dialog, hui.dialog_card("w-[480px] max-w-full"):
            hui.heading("Add a gate" if gate is None else gate.name)
            if not editable and gate is not None:
                _draw_gate_details(gate)
                with hui.action_row().classes("mt-2"):
                    ui.button("Close", on_click=dialog.close).props("flat dense")
                dialog.open()
                return
            form.draw()
            line = state.line_of(gate) if gate is not None else None
            if line is not None and line.users:
                hui.hint(
                    f"Its Line is in use ({line.users}): a change applies when its users restart."
                ).mark("gate-dialog-hint")
            error = hui.error_label("").classes("whitespace-pre-line").mark("gate-dialog-error")
            error.set_visibility(False)
            with hui.action_row().classes("mt-2"):
                ui.button("Cancel", on_click=dialog.close).props("flat dense")
                hui.confirm_button(
                    "Save", on_click=lambda: self._save(dialog, error, form, gate.name if gate else None)
                ).mark("gate-dialog-save")
        dialog.open()

    def _save(self, dialog: ui.dialog, error: ui.label, form: GateForm, replaces: str | None) -> None:
        if not self._can_edit():
            _show(error, "Changing gates needs edit access.")
            return
        try:
            gate = form.gate()
        except ValueError as exc:
            _show(error, str(exc))
            return
        problem = self._state().save_gate(gate, replaces=replaces)
        if problem is not None:
            _show(error, problem)
            return
        dialog.close()
        self._draw_rows()

    def _confirm_delete(self, name: str) -> None:
        dialog = self._new_dialog()
        with dialog, hui.dialog_card("w-[360px] max-w-full"):
            hui.heading(f"Delete gate '{name}'?")
            hui.hint("Graphs that use it will show 'no gate named' until a gate with this name exists.")
            with hui.action_row().classes("mt-2"):
                ui.button("Cancel", on_click=dialog.close).props("flat dense")
                ui.button("Delete", on_click=lambda: self._delete(dialog, name)).props("flat dense").classes(
                    "hw-text-danger"
                ).mark("gate-delete-confirm")
        dialog.open()

    def _delete(self, dialog: ui.dialog, name: str) -> None:
        if self._can_edit():
            self._state().delete_gate(name)
        dialog.close()
        self._draw_rows()


def _draw_gate_details(gate: Gate) -> None:
    with ui.column().classes("w-full gap-0"):
        hui.info_row("Protocol", gate.protocol, label_width="w-24", copyable=False)
        hui.info_row("Direction", gate.direction, label_width="w-24", copyable=False)
        if gate.device:
            hui.info_row("Device", gate.device, label_width="w-24", copyable=False)
        for key, value in gate.options.items():
            hui.info_row(key, str(value), label_width="w-24", copyable=False)


def _show(error: ui.label, message: str) -> None:
    error.set_text(message)
    error.set_visibility(True)
