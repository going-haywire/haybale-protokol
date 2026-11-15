"""ProtokolState — the app-wide owner of drivers, the Gate file and the open Lines."""

from __future__ import annotations

import logging
import re
import threading
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from haywire.api import get_workspace_root
from haywire.api.workbench import AppState, state

from haybale_protokol.devices import (
    Device,
    DeviceListError,
    device_list_path,
    load_devices,
    save_devices,
)
from haybale_protokol.drivers import LineKey, Message, ProtocolDriver
from haybale_protokol.gates import (
    Gate,
    GateFileError,
    gate_file_path,
    load_gates_leniently,
    remove_gate,
    write_gate,
)
from haybale_protokol.line import Line, LineOpenError
from haybale_protokol.line_use import LineUse
from haybale_protokol.signals import ProtokolChanged

if TYPE_CHECKING:
    from haybale_protokol.taps import Tap

logger = logging.getLogger(__name__)

_GATE_NAME = re.compile(r"[A-Za-z0-9._-]+")

#: The grace period when the setting cannot be read.
DEFAULT_GRACE_S = 2.0


@state(
    label="Protokol",
    description="Protocol drivers, the project's gates and the Lines they share",
)
class ProtokolState(AppState):
    """Owns the Protocol drivers and the open Lines; reads the Gate file and the Device list.

    One per app, shared by every session and by execution. Lines run on their own threads, so
    every change is published as a payload-free ``ProtokolChanged`` scheduled onto the loop.
    """

    def __init__(self) -> None:
        super().__init__()
        self.project_root: Path | None = None
        """The project whose Gate file is read; ``None`` reads the workspace root at first use."""
        self.grace_s: Callable[[], float] = _grace_from_settings
        """Seconds a Line stays open after its last user leaves."""
        self.gate_file_error: str | None = None
        """Why the Gate file could not be read, or ``None``."""
        self.gate_errors: dict[str, str] = {}
        """Why each malformed gate was left out, by gate name."""
        self.device_list_error: str | None = None
        """Why the Device list could not be read, or ``None``."""
        self._drivers: dict[str, ProtocolDriver] = {}
        self._lines: dict[LineKey, Line] = {}
        self._lock = threading.RLock()
        self._gates: dict[str, Gate] = {}
        self._gates_stamp: tuple[float, int] | None = None

    def on_disable(self) -> None:
        for line in self.lines():
            line.close()

    # -- drivers -----------------------------------------------------------------

    def register_driver(self, driver: ProtocolDriver) -> None:
        """Add (or replace) the driver for ``driver.protocol``."""
        with self._lock:
            previous = self._drivers.get(driver.protocol)
            self._drivers[driver.protocol] = driver
        if previous is not None and previous is not driver:
            self._close_lines(driver.protocol)
        self._changed()

    def unregister_driver(self, protocol: str) -> None:
        """Remove the driver for ``protocol`` and close its Lines at once."""
        with self._lock:
            self._drivers.pop(protocol, None)
        self._close_lines(protocol)
        self._changed()

    def protocols(self) -> list[str]:
        """The protocols with a driver registered, sorted."""
        with self._lock:
            return sorted(self._drivers)

    def driver(self, protocol: str) -> ProtocolDriver | None:
        with self._lock:
            return self._drivers.get(protocol)

    # -- gates and lines -----------------------------------------------------------

    def gates(self) -> dict[str, Gate]:
        """The project's gates, re-read when the Gate file changed; ``{}`` if it is malformed."""
        path = gate_file_path(self._project_root())
        try:
            info = path.stat()
            stamp: tuple[float, int] | None = (info.st_mtime, info.st_size)
        except OSError:
            stamp = None
        with self._lock:
            if stamp == self._gates_stamp and stamp is not None:
                return dict(self._gates)
            try:
                self._gates, self.gate_errors = load_gates_leniently(path)
                self.gate_file_error = None
            except GateFileError as exc:
                self._gates, self.gate_errors = {}, {}
                self.gate_file_error = str(exc)
            self._gates_stamp = stamp
            return dict(self._gates)

    def gate_choices(self, protocol: str, direction: Literal["in", "out"]) -> list[str]:
        """Names of the project's ``protocol`` gates that can ``direction`` (two-way can both), sorted."""
        return sorted(
            name
            for name, gate in self.gates().items()
            if gate.protocol == protocol and gate.direction in (direction, "two-way")
        )

    def use(
        self,
        gate_name: str,
        direction: Literal["in", "out"],
        subscriber: Callable[[Message], None] | None = None,
    ) -> LineUse | str:
        """Take a hold on the Line of ``gate_name``; returns a status text when that is not possible."""
        gates = self.gates()
        if self.gate_file_error is not None:
            return f"gate file: {self.gate_file_error}"
        gate = gates.get(gate_name)
        if gate is None:
            if gate_name in self.gate_errors:
                return f"gate '{gate_name}': {self.gate_errors[gate_name]}"
            return f"no gate named '{gate_name}'"
        return self.use_gate(gate, direction, subscriber)

    def use_gate(
        self,
        gate: Gate,
        direction: Literal["in", "out"],
        subscriber: Callable[[Message], None] | None = None,
        *,
        outbound: Callable[[Message], None] | None = None,
    ) -> LineUse | str:
        """Take a hold on the Line of ``gate``, saved or not; returns a status text when it cannot.

        ``outbound`` also receives every message the Line sends (Monitor taps).
        """
        if gate.direction != "two-way" and gate.direction != direction:
            return f"'{gate.name}' is an {'input' if gate.direction == 'in' else 'output'} gate"
        resolved = self._resolve(gate)
        if isinstance(resolved, str):
            return resolved
        driver, device, key = resolved
        with self._lock:
            line = self._lines.get(key)
            if line is not None and not line.is_closed and getattr(line.connection, "gone", False):
                line.close()  # its port went away (a Device unplugged): a new Line opens it afresh
            if line is not None and line.is_closed:
                self._lines.pop(key, None)
                line = None
            if line is None:
                try:
                    connection = driver.open(key, gate, device)
                except ValueError as exc:
                    return f"gate '{gate.name}': {exc}"
                line = Line(key, connection, driver.cache_key, self.grace_s)
                line.gate = gate
                line.on_closed = self._forget
                line.on_changed = lambda _line: self._changed()
                self._lines[key] = line
            conflict = _line_conflict(driver, gate, line)
            if conflict is not None:
                return conflict
            try:
                token = line.add_user(subscriber, outbound=outbound)
            except LineOpenError:
                self._lines.pop(key, None)
                return line.status
        return LineUse(line, token, gate)

    def line_of(self, gate: Gate) -> Line | None:
        """The open Line ``gate`` resolves to, without opening one."""
        resolved = self._resolve(gate)
        if isinstance(resolved, str):
            return None
        with self._lock:
            line = self._lines.get(resolved[2])
        return line if line is not None and line.is_open else None

    def tap(self, gate: Gate, *, open_line: bool) -> Tap | str:
        """A Monitor tap on ``gate``'s Line, in whatever directions the gate has.

        With ``open_line=False`` only a Line that is already open is tapped (``"line not open"``).
        """
        from haybale_protokol.taps import Tap

        if not open_line and self.line_of(gate) is None:
            return "line not open"
        tap = Tap()
        direction: Literal["in", "out"] = "out" if gate.direction == "out" else "in"
        result = self.use_gate(
            gate,
            direction,
            tap.on_in if gate.direction != "out" else None,
            outbound=tap.on_out if gate.direction != "in" else None,
        )
        if isinstance(result, str):
            return result
        tap.use = result
        return tap

    # -- editing the Gate file -----------------------------------------------------------

    def save_gate(self, gate: Gate, *, replaces: str | None = None) -> str | None:
        """Write ``gate`` to the Gate file; returns why it was refused, or ``None``.

        The gate's driver checks its options; a gate whose protocol is not installed is
        saved unchecked. ``replaces`` names the gate this one renames.
        """
        if not _GATE_NAME.fullmatch(gate.name):
            return "a gate name uses letters, digits, '.', '_' and '-' only"
        gates = self.gates()
        if self.gate_file_error is not None:
            return f"gate file: {self.gate_file_error}"
        taken = set(gates) | set(self.gate_errors)
        if gate.name in taken and gate.name != replaces:
            return f"a gate named '{gate.name}' already exists"
        driver = self.driver(gate.protocol)
        if driver is not None:
            device = None
            if gate.device is not None:
                try:
                    device = load_devices(device_list_path()).get(gate.device)
                except DeviceListError:
                    device = None
            if gate.device is None or device is not None:
                try:
                    driver.line_key(gate, device)
                except ValueError as exc:
                    return str(exc)
        write_gate(gate_file_path(self._project_root()), gate, replaces=replaces)
        self._reread_gates()
        return None

    def delete_gate(self, name: str) -> None:
        """Remove ``name`` from the Gate file."""
        remove_gate(gate_file_path(self._project_root()), name)
        self._reread_gates()

    # -- editing the Device list ---------------------------------------------------------

    def devices(self) -> dict[str, Device]:
        """This machine's Devices; ``{}`` when the Device list cannot be read (see ``device_list_error``)."""
        try:
            devices = load_devices(device_list_path())
        except DeviceListError as exc:
            self.device_list_error = str(exc)
            return {}
        self.device_list_error = None
        return devices

    def save_device(self, device: Device, *, replaces: str | None = None) -> str | None:
        """Write ``device`` to the Device list; returns why it was refused, or ``None``."""
        if not _GATE_NAME.fullmatch(device.name):
            return "a device name uses letters, digits, '.', '_' and '-' only"
        if not device.protocol:
            return "a device needs a protocol"
        if not device.os_id.strip():
            return "a device needs the OS name or id of the hardware"
        devices = self.devices()
        if self.device_list_error is not None:
            return f"device list: {self.device_list_error}"
        if device.name in devices and device.name != replaces:
            return f"a device named '{device.name}' already exists"
        kept = [d for name, d in devices.items() if name not in (device.name, replaces)]
        save_devices(device_list_path(), [*kept, device])
        self._changed()
        return None

    def delete_device(self, name: str) -> None:
        """Remove ``name`` from the Device list."""
        devices = self.devices()
        if name in devices:
            save_devices(device_list_path(), [d for n, d in devices.items() if n != name])
            self._changed()

    # -- internals -------------------------------------------------------------------

    def _resolve(self, gate: Gate) -> tuple[ProtocolDriver, Device | None, LineKey] | str:
        driver = self.driver(gate.protocol)
        if driver is None:
            return "protocol not installed"
        device = None
        if gate.device is not None:
            try:
                device = load_devices(device_list_path()).get(gate.device)
            except DeviceListError as exc:
                return f"device list: {exc}"
            if device is None:
                return f"unbound gate: no device '{gate.device}' on this machine"
        try:
            key = driver.line_key(gate, device)
        except ValueError as exc:
            return f"gate '{gate.name}': {exc}"
        return driver, device, key

    def _reread_gates(self) -> None:
        with self._lock:
            self._gates_stamp = None
        self._changed()

    def lines(self) -> list[Line]:
        """Every Line currently open or in its grace period."""
        with self._lock:
            return list(self._lines.values())

    def _project_root(self) -> Path:
        if self.project_root is None:
            self.project_root = get_workspace_root()
        return self.project_root

    def _forget(self, line: Line) -> None:
        with self._lock:
            if self._lines.get(line.key) is line:
                del self._lines[line.key]

    def _close_lines(self, protocol: str) -> None:
        for line in [line for line in self.lines() if line.key.protocol == protocol]:
            line.close()

    def _changed(self) -> None:
        """Publish ``ProtokolChanged`` on the event loop; dropped while no loop runs or unbound.

        Called from Line threads and under locks, so it only schedules.
        """
        from nicegui import core

        if not hasattr(self, "_dispatcher"):
            return  # not bound to an app (a standalone instance): nobody to tell
        loop = core.loop
        if loop is None or not loop.is_running():
            return
        loop.call_soon_threadsafe(self._signal_emit, ProtokolChanged())


def _line_conflict(driver: ProtocolDriver, gate: Gate, line: Line) -> str | None:
    """Why ``gate`` cannot share ``line`` with the gate that opened it, or ``None``."""
    first = line.gate
    if first is None or first.name == gate.name:
        return None
    mine, theirs = driver.line_options(gate), driver.line_options(first)
    for option in sorted(set(mine) | set(theirs)):
        if mine.get(option) != theirs.get(option):
            return f"gate '{gate.name}': {option} differs from gate '{first.name}' on the same line"
    return None


def _grace_from_settings() -> float:
    from haybale_protokol.settings.protokol_settings import ProtokolSettings

    try:
        return float(ProtokolSettings().grace_period_s)
    except Exception:
        logger.debug("grace_period_s unreadable; using %s", DEFAULT_GRACE_S, exc_info=True)
        return DEFAULT_GRACE_S
