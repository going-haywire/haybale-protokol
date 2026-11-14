"""DeviceEditor — the device, gate or Line in the Protokol selection (CONTEXT slot).

With nothing selected it lists this machine's Device list. Editing the Device list changes
the machine, so it needs ADMIN; everything else here only reads.
"""

from __future__ import annotations

import logging
from typing import Any

from haywire.core.access import AccessTier
from haywire.core.session.context import SessionContext
from haywire.core.session.handlers import redraw_on
from haywire.ui import elements as hui
from haywire.ui.editor.base import BaseEditor
from haywire.ui.editor.decorator import editor
from haywire.ui.editor.identity import SlotName
from nicegui import ui

from haybale_protokol.devices import Device
from haybale_protokol.drivers import list_devices
from haybale_protokol.editors.gates_editor import gate_status
from haybale_protokol.editors.layout import list_row, scroll_area
from haybale_protokol.gates import Gate
from haybale_protokol.icons import ProtokolIcon
from haybale_protokol.icons import icon as icons
from haybale_protokol.line import Line
from haybale_protokol.signals import ProtokolChanged
from haybale_protokol.states.protokol_selection import ProtokolSelection
from haybale_protokol.states.protokol_state import ProtokolState

logger = logging.getLogger(__name__)


@editor(
    label="Device",
    icon=ProtokolIcon.device,
    default_slot=SlotName.CONTEXT,
    requires=AccessTier.VIEW,
    description="The device or Line in the Protokol selection",
)
class DeviceEditor(BaseEditor):
    """Follows the Protokol selection.

    - A device: its OS name, and whether the protocol sees it connected. With ADMIN: edit or
      delete it, or map a gate's device name that this machine does not know yet.
    - A gate: its options, its Line's status and users, and the Line cache.
    - A Line: its key, status, users and cache.
    - Nothing: the Device list.
    """

    def __init__(self, wrapper: Any) -> None:
        super().__init__(wrapper)
        self._context: SessionContext | None = None
        self._body: ui.column | None = None
        self._dialog_host: ui.element | None = None
        self._dialog: ui.dialog | None = None

    @redraw_on(ProtokolChanged, ProtokolSelection.gate, ProtokolSelection.line, ProtokolSelection.device)
    def _on_change(self, context: SessionContext, signal: Any) -> None:
        """Redraw: the selection, the Device list or a Line changed."""

    def draw(self, context: SessionContext, container: ui.element) -> None:
        self._context = context
        container.clear()
        with container:
            with ui.column().classes("w-full h-full gap-0") as root:
                with hui.slot_header("Device", icon=ProtokolIcon.device):
                    if self._can_admin():
                        hui.icon_action(
                            hui.icon.add, tooltip="Add a device", on_click=lambda: self._open_form(None)
                        ).mark("device-add")
                with scroll_area():
                    self._body = ui.column().classes("w-full gap-1 p-2")
            self._dialog_host = root
            self._draw_body()

    def _draw_body(self) -> None:
        if self._body is None:
            return
        self._body.clear()
        selection = self._selection()
        with self._body:
            if selection.device is not None:
                self._draw_device(selection.device)
            elif selection.gate is not None:
                self._draw_gate(selection.gate)
            elif selection.line is not None:
                self._draw_line_selection()
            else:
                self._draw_device_list()

    # -- views ----------------------------------------------------------------------------

    def _draw_device_list(self) -> None:
        state = self._state()
        devices = state.devices()
        if state.device_list_error is not None:
            hui.error_label(f"device list: {state.device_list_error}").mark("device-list-error")
        if not devices:
            hui.hint("No devices on this machine yet.")
        for name, device in sorted(devices.items()):
            with list_row().classes("cursor-default").mark(f"device-row-{name}"):
                with ui.column().classes("gap-0 flex-1 min-w-0"):
                    with ui.row().classes("items-center gap-1 no-wrap"):
                        hui.subject(name).classes("truncate")
                        hui.tag(device.protocol)
                    hui.hint(self._device_status(device)).classes("truncate w-full").mark(
                        f"device-status-{name}"
                    )
                if self._can_admin():
                    hui.icon_action(
                        hui.icon.edit, tooltip="Edit", on_click=lambda d=device: self._open_form(d)
                    ).mark(f"device-edit-{name}")
                    hui.icon_action(
                        hui.icon.delete, tooltip="Delete", on_click=lambda n=name: self._confirm_delete(n)
                    ).mark(f"device-delete-{name}")

    def _draw_device(self, name: str) -> None:
        self._back()
        device = self._state().devices().get(name)
        with ui.column().classes("w-full gap-1").mark("device-detail"):
            hui.heading(name)
            if device is None:
                hui.hint("This machine has no device by this name: gates that use it are unbound.")
                if self._can_admin():
                    hui.button(
                        "Map device…",
                        icon=icons.bind,
                        on_click=lambda: self._open_form(Device(name, "", ""), mapping=True),
                    ).mark("device-map")
                return
            hui.info_row("Protocol", device.protocol, label_width="w-24", copyable=False)
            hui.info_row("OS name", device.os_id, label_width="w-24")
            hui.info_row("Status", self._device_status(device), label_width="w-24", copyable=False)
            if self._can_admin():
                with hui.action_row():
                    hui.button("Edit", icon=hui.icon.edit, on_click=lambda: self._open_form(device)).mark(
                        f"device-edit-{name}"
                    )

    def _draw_gate(self, name: str) -> None:
        self._back()
        state = self._state()
        gate = state.gates().get(name)
        hui.heading(name)
        if gate is None:
            hui.hint(state.gate_errors.get(name, "This gate is no longer in the Gate file."))
            return
        hui.info_row("Protocol", gate.protocol, label_width="w-24", copyable=False)
        hui.info_row("Direction", gate.direction, label_width="w-24", copyable=False)
        if gate.device:
            hui.info_row("Device", gate.device, label_width="w-24", copyable=False)
        for key, value in gate.options.items():
            hui.info_row(key, str(value), label_width="w-24", copyable=False)
        hui.section_label("Line")
        line = state.line_of(gate)
        hui.hint(gate_status(state, gate)).mark("device-line-status")
        if line is not None:
            self._draw_cache(line, gate)

    def _draw_line_selection(self) -> None:
        self._back()
        state = self._state()
        key = self._selection().line
        line = next((line for line in state.lines() if line.key == key), None)
        hui.heading("Line")
        if line is None or key is None:
            hui.hint("This Line is closed.").mark("device-line-status")
            return
        hui.info_row("Protocol", key.protocol, label_width="w-24", copyable=False)
        hui.info_row("Address", key.address, label_width="w-24")
        hui.hint(f"{line.status} · {line.users} users").mark("device-line-status")
        self._draw_cache(line, line.gate)

    def _draw_cache(self, line: Line, gate: Gate | None) -> None:
        driver = self._state().driver(line.key.protocol)
        cached = line.cached()
        hui.section_label(f"Last values ({len(cached)})")
        with ui.column().classes("w-full gap-0").mark("device-cache"):
            for message in reversed(cached[-50:]):
                text = driver.describe(message) if driver is not None else message.address
                hui.subject(text, mono=True).classes("truncate w-full text-xs")

    def _back(self) -> None:
        hui.button("Device list", icon=icons.back, on_click=self._selection().clear).mark("device-back")

    def _device_status(self, device: Device) -> str:
        driver = self._state().driver(device.protocol)
        if driver is None:
            return f"{device.os_id} · protocol not installed"
        seen = list_devices(driver)
        if seen is not None and device.os_id not in {os_id for os_id, _ in seen}:
            return f"{device.os_id} · not connected"
        return device.os_id

    # -- dialogs ---------------------------------------------------------------------------

    def _new_dialog(self) -> ui.dialog:
        if self._dialog is not None and not self._dialog.is_deleted:
            self._dialog.delete()
        assert self._dialog_host is not None
        with self._dialog_host:
            self._dialog = ui.dialog().mark("device-dialog")
        return self._dialog

    def _open_form(self, device: Device | None, *, mapping: bool = False) -> None:
        state = self._state()
        dialog = self._new_dialog()
        values: dict[str, Any] = {
            "name": device.name if device else "",
            "protocol": (device.protocol if device else "") or None,
            "os_id": (device.os_id if device else "") or None,
        }
        replaces = device.name if device is not None and not mapping else None
        with dialog, hui.dialog_card("w-[420px] max-w-full"):
            hui.heading("Map device" if mapping else ("Edit device" if device else "Add a device"))
            name = (
                hui.input_field(label="Name", value=values["name"])
                .props('autocomplete="off"')
                .mark("device-form-name")
            )
            protocols = sorted({*state.protocols(), *([values["protocol"]] if values["protocol"] else [])})

            def draw_os_ids() -> None:
                os_box.clear()
                driver = state.driver(str(values["protocol"] or ""))
                seen = list_devices(driver) if driver is not None else None
                options = {os_id: f"{os_id} — {label}" for os_id, label in seen or ()}
                if values["os_id"]:
                    options.setdefault(values["os_id"], values["os_id"])
                with os_box:
                    hui.select_field(
                        label="OS name",
                        options=options,
                        value=values["os_id"],
                        on_change=lambda e: values.__setitem__("os_id", e.value),
                        new_value_mode="add-unique",
                    ).classes("w-full").mark("device-form-os_id")

            def set_protocol(event: Any) -> None:
                values["protocol"] = event.value
                draw_os_ids()

            hui.select_field(
                label="Protocol", options=protocols, value=values["protocol"], on_change=set_protocol
            ).classes("w-full").mark("device-form-protocol")
            os_box = ui.column().classes("w-full gap-0")
            draw_os_ids()
            error = hui.error_label("").mark("device-dialog-error")
            error.set_visibility(False)

            def save() -> None:
                if not self._can_admin():
                    _show(error, "Changing the Device list needs admin access.")
                    return
                changed = Device(
                    str(name.value or "").strip(), str(values["protocol"] or ""), str(values["os_id"] or "")
                )
                problem = state.save_device(changed, replaces=replaces)
                if problem is not None:
                    _show(error, problem)
                    return
                dialog.close()
                self._draw_body()

            with hui.action_row().classes("mt-2"):
                ui.button("Cancel", on_click=dialog.close).props("flat dense")
                hui.confirm_button("Save", on_click=save).mark("device-dialog-save")
        dialog.open()

    def _confirm_delete(self, name: str) -> None:
        dialog = self._new_dialog()
        with dialog, hui.dialog_card("w-[360px] max-w-full"):
            hui.heading(f"Delete device '{name}'?")
            hui.hint("Gates that name it become unbound on this machine.")
            with hui.action_row().classes("mt-2"):
                ui.button("Cancel", on_click=dialog.close).props("flat dense")
                ui.button("Delete", on_click=lambda: self._delete(dialog, name)).props("flat dense").classes(
                    "hw-text-danger"
                ).mark("device-delete-confirm")
        dialog.open()

    def _delete(self, dialog: ui.dialog, name: str) -> None:
        if self._can_admin():
            self._state().delete_device(name)
        dialog.close()
        self._draw_body()

    # -- helpers ---------------------------------------------------------------------------

    def _state(self) -> ProtokolState:
        assert self._context is not None
        return self._context.app_data[ProtokolState]

    def _selection(self) -> ProtokolSelection:
        assert self._context is not None
        return self._context.data[ProtokolSelection]

    def _can_admin(self) -> bool:
        return self._context is not None and bool(self._context.can_admin())


def _show(error: ui.label, message: str) -> None:
    error.set_text(message)
    error.set_visibility(True)
