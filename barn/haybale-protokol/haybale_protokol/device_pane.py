"""The Device pane: the lower half of the Gates editor (design §10.4).

It follows the Protokol selection, as the Device editor it replaces did:

- a gate: its options, Device mapping and health, its Line and the Line cache;
- a device: its OS name and whether it is plugged in;
- a Line (from the Monitor): its key, status, users and cache;
- nothing: this machine's Device list.

Editing the Device list changes the machine, so it needs ADMIN; everything else here only reads.
A gate whose Device this machine does not have is mapped from its own view ("Map device…").
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from haywire.api.workbench import SessionContext, hui
from nicegui import ui

from haybale_protokol.devices import Device
from haybale_protokol.drivers import find_device, list_devices
from haybale_protokol.editor_layout import list_row, scroll_area
from haybale_protokol.gates import Gate
from haybale_protokol.icons import ProtokolIcon
from haybale_protokol.icons import icon as icons
from haybale_protokol.line import Line
from haybale_protokol.states.protokol_selection import ProtokolSelection
from haybale_protokol.states.protokol_state import ProtokolState

logger = logging.getLogger(__name__)

#: Shown where a Device list change needs ADMIN and the viewer has less.
NEEDS_ADMIN = "Mapping a device changes this machine: it needs an admin."


class DevicePane:
    """Draws the Device pane of the Gates editor; the editor owns one and redraws it on changes."""

    def __init__(self, context: Callable[[], SessionContext | None]) -> None:
        self._get_context = context
        self._body: ui.column | None = None
        self._dialog_host: ui.element | None = None
        self._dialog: ui.dialog | None = None

    # -- drawing ---------------------------------------------------------------------------

    def draw_header(self) -> None:
        """The pane's header: its title, refresh, and (ADMIN) add a device."""
        with hui.slot_header("Device", icon=ProtokolIcon.device):
            hui.icon_action(
                hui.icon.refresh, tooltip="Check which devices are plugged in", on_click=self._refresh
            ).mark("device-refresh")
            if self._can_admin():
                hui.icon_action(
                    hui.icon.add, tooltip="Add a device", on_click=lambda: self._open_form(None)
                ).mark("device-add")

    def draw(self, dialog_host: ui.element) -> None:
        """The pane's header and body; dialogs open in ``dialog_host``."""
        self._dialog_host = dialog_host
        self.draw_header()
        with scroll_area():
            self._body = ui.column().classes("w-full gap-1 p-2").mark("device-pane")
        self.draw_body()

    def draw_body(self) -> None:
        """Redraw only the body (an open dialog stays)."""
        if self._body is None or self._body.is_deleted:
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
                    status, plugged = self._device_status(device)
                    hint = hui.hint(status).classes("truncate w-full").mark(f"device-status-{name}")
                    if plugged is False:
                        hint.classes("hw-text-danger")
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
                self._map_button(name)
                return
            hui.info_row("Protocol", device.protocol, label_width="w-24", copyable=False)
            hui.info_row("OS name", device.os_id, label_width="w-24")
            hui.info_row("Status", self._device_status(device)[0], label_width="w-24", copyable=False)
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
        for key, value in gate.options.items():
            hui.info_row(key, str(value), label_width="w-24", copyable=False)
        health = state.health(gate)
        if gate.device:
            hui.section_label("Device")
            device = state.devices().get(gate.device)
            hui.info_row("Device", gate.device, label_width="w-24", copyable=False)
            if device is None:
                hui.hint("This machine has no device by this name.").mark("device-gate-unbound")
                self._map_button(gate.device, protocol=gate.protocol)
            else:
                hui.info_row("OS name", device.os_id, label_width="w-24")
        hui.section_label("Line")
        hint = hui.hint(health.reason).mark("device-line-status")
        if not health.healthy:
            hint.classes("hw-text-danger")
        line = state.line_of(gate)
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

    def _map_button(self, name: str, *, protocol: str = "") -> None:
        """ "Map device…" for ADMIN; for anyone else, why it is not offered."""
        if self._can_admin():
            hui.button(
                "Map device…",
                icon=icons.bind,
                on_click=lambda: self._open_form(Device(name, protocol, ""), mapping=True),
            ).mark("device-map")
        else:
            hui.hint(NEEDS_ADMIN).mark("device-map-needs-admin")

    def _back(self) -> None:
        hui.button("Device list", icon=icons.back, on_click=self._selection().clear).mark("device-back")

    def _device_status(self, device: Device) -> tuple[str, bool | None]:
        """What to show for ``device``, and whether it is plugged in (``None``: cannot tell).

        Read from the device watch's last listing, so drawing never lists ports.
        """
        state = self._state()
        driver = state.driver(device.protocol)
        if driver is None:
            return f"{device.os_id} · protocol not installed", None
        seen = state.device_listing(device.protocol)
        if seen is None:  # a driver that lists devices but does not say its gates use them
            listed = list_devices(driver)
            seen = tuple(listed) if listed is not None else None
        if seen is None:
            return device.os_id, None
        found = find_device(driver, device.os_id, seen)
        if found is None:
            return f"{device.os_id} · not plugged in", False
        return (device.os_id if found == device.os_id else f"{device.os_id} · now '{found}'"), True

    def _refresh(self) -> None:
        self._state().refresh_devices()
        self.draw_body()

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
                seen = list_devices(driver) if driver is not None else None  # fresh: the user is choosing
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
                self.draw_body()

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
        self.draw_body()

    # -- helpers ---------------------------------------------------------------------------

    def _context(self) -> SessionContext:
        context = self._get_context()
        assert context is not None
        return context

    def _state(self) -> ProtokolState:
        return self._context().app_data[ProtokolState]

    def _selection(self) -> ProtokolSelection:
        return self._context().data[ProtokolSelection]

    def _can_admin(self) -> bool:
        context = self._get_context()
        return context is not None and bool(context.can_admin())


def _show(error: ui.label, message: str) -> None:
    error.set_text(message)
    error.set_visibility(True)
