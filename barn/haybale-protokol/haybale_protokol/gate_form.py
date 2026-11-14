"""The gate form: name, protocol, direction, device, and the protocol's own fields.

Protocol-neutral: the fields come from the driver's ``gate_fields()``, and a field shows only
while its ``applies`` conditions hold, so changing the direction or a choice redraws them.
"""

from __future__ import annotations

from typing import Any

from haywire.ui import elements as hui
from nicegui import ui

from haybale_protokol.devices import DeviceListError, device_list_path, load_devices
from haybale_protokol.drivers import GateField, gate_fields, uses_devices
from haybale_protokol.gates import Gate
from haybale_protokol.states.protokol_state import ProtokolState

DIRECTIONS = ("in", "out", "two-way")


class GateForm:
    """Draws the form into the current NiceGUI context; ``gate()`` reads it back."""

    def __init__(self, state: ProtokolState, gate: Gate | None, *, named: bool = True) -> None:
        self._state = state
        self._named = named
        protocols = state.protocols()
        start = gate or Gate("", protocols[0] if protocols else "", "in")
        self._values: dict[str, Any] = {
            "name": start.name,
            "protocol": start.protocol,
            "direction": start.direction,
            "device": start.device,
            **dict(start.options),
        }
        self._protocols = sorted({*protocols, start.protocol} - {""})
        self._fields_box: ui.column | None = None

    def draw(self) -> None:
        if self._named:
            hui.input_field(
                label="Name", value=str(self._values["name"]), on_change=self._setter("name")
            ).props('autocomplete="off"').mark("gate-form-name")
        hui.select_field(
            label="Protocol",
            options=self._protocols,
            value=self._values["protocol"] or None,
            on_change=self._setter("protocol", redraw=True),
        ).classes("w-full").mark("gate-form-protocol")
        hui.select_field(
            label="Direction",
            options=list(DIRECTIONS),
            value=self._values["direction"],
            on_change=self._setter("direction", redraw=True),
        ).classes("w-full").mark("gate-form-direction")
        self._fields_box = ui.column().classes("w-full gap-1")
        self._draw_fields()

    def gate(self) -> Gate:
        """The gate as filled in.

        Raises:
            ValueError: A number field holds something else.
        """
        options: dict[str, Any] = {}
        described = {field.key for field in self._fields()}
        for key, value in self._values.items():
            if key in ("name", "protocol", "direction", "device") or key in described:
                continue
            options[key] = value  # an option the driver does not describe: kept as it was
        for field in self._shown_fields():
            value = self._values.get(field.key)
            if value is None or value == "":
                continue
            if field.kind == "int":
                try:
                    value = int(str(value).strip())
                except ValueError:
                    raise ValueError(f"{field.label} must be a whole number") from None
            options[field.key] = value
        device = self._values.get("device") if self._needs_device() else None
        return Gate(
            str(self._values["name"]).strip(),
            str(self._values["protocol"] or ""),
            self._values["direction"],
            device or None,
            options,
        )

    # -- internals -------------------------------------------------------------------------

    def _draw_fields(self) -> None:
        if self._fields_box is None:
            return
        self._fields_box.clear()
        with self._fields_box:
            if self._needs_device():
                names = _device_names(str(self._values["protocol"]))
                current = self._values.get("device")
                options = sorted({*names, *([current] if current else [])})
                hui.select_field(
                    label="Device",
                    options=options,
                    value=current,
                    on_change=self._setter("device"),
                    new_value_mode="add-unique",
                ).classes("w-full").mark("gate-form-device")
            for field in self._shown_fields():
                self._draw_field(field)

    def _draw_field(self, field: GateField) -> None:
        value = self._values.get(field.key, field.default)
        if field.kind == "choice":
            hui.select_field(
                label=field.label,
                options=list(field.choices),
                value=value,
                on_change=self._setter(field.key, redraw=True),
            ).classes("w-full").mark(f"gate-form-{field.key}")
            self._values.setdefault(field.key, value)
            return
        text = "" if value is None else str(value)
        hui.input_field(label=field.label, value=text, on_change=self._setter(field.key)).props(
            'autocomplete="off"'
        ).classes("w-full").mark(f"gate-form-{field.key}")

    def _fields(self) -> tuple[GateField, ...]:
        driver = self._state.driver(str(self._values["protocol"] or ""))
        return tuple(gate_fields(driver)) if driver is not None else ()

    def _shown_fields(self) -> list[GateField]:
        fields = self._fields()
        defaults = {field.key: field.default for field in fields}
        return [field for field in fields if field.applies_to(self._values, defaults)]

    def _needs_device(self) -> bool:
        driver = self._state.driver(str(self._values["protocol"] or ""))
        return driver is not None and uses_devices(driver)

    def _setter(self, key: str, *, redraw: bool = False) -> Any:
        def set_value(event: Any) -> None:
            self._values[key] = event.value
            if redraw:
                self._draw_fields()

        return set_value


def _device_names(protocol: str) -> list[str]:
    try:
        devices = load_devices(device_list_path())
    except DeviceListError:
        return []
    return [name for name, device in devices.items() if device.protocol == protocol]
