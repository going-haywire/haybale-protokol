"""ProtokolState — the app-wide owner of drivers, the Gate file and the open Lines."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from haywire.core.state.base import AppState
from haywire.core.state.decorator import state

from haybale_protokol.devices import DeviceListError, device_list_path, load_devices
from haybale_protokol.drivers import LineKey, Message, ProtocolDriver
from haybale_protokol.gates import Gate, GateFileError, gate_file_path, load_gates_leniently
from haybale_protokol.line import Line, LineOpenError
from haybale_protokol.signals import ProtokolChanged

logger = logging.getLogger(__name__)

#: The grace period when the setting cannot be read.
DEFAULT_GRACE_S = 2.0


@dataclass(eq=False)
class LineUse:
    """One user's hold on a Line, through a Gate. Give it back with ``release()``."""

    line: Line
    token: int
    gate: Gate
    _released: bool = field(default=False, repr=False)

    def release(self) -> None:
        """Give the Line back; a second call does nothing."""
        if not self._released:
            self._released = True
            self.line.remove_user(self.token)


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
        if gate.direction != "two-way" and gate.direction != direction:
            return f"'{gate_name}' is an {'input' if gate.direction == 'in' else 'output'} gate"
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
            return f"gate '{gate_name}': {exc}"
        with self._lock:
            line = self._lines.get(key)
            if line is not None and line.is_closed:
                self._lines.pop(key, None)
                line = None
            if line is None:
                try:
                    connection = driver.open(key, gate, device)
                except ValueError as exc:
                    return f"gate '{gate_name}': {exc}"
                line = Line(key, connection, driver.cache_key, self.grace_s)
                line.gate = gate
                line.on_closed = self._forget
                line.on_changed = lambda _line: self._changed()
                self._lines[key] = line
            conflict = _line_conflict(driver, gate, line)
            if conflict is not None:
                return conflict
            try:
                token = line.add_user(subscriber)
            except LineOpenError:
                self._lines.pop(key, None)
                return line.status
        return LineUse(line, token, gate)

    def lines(self) -> list[Line]:
        """Every Line currently open or in its grace period."""
        with self._lock:
            return list(self._lines.values())

    # -- internals -------------------------------------------------------------------

    def _project_root(self) -> Path:
        if self.project_root is None:
            from haywire.core.di.context import get_workspace_root

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
        """Publish ``ProtokolChanged`` on the event loop; dropped while no loop runs.

        Called from Line threads and under locks, so it only schedules.
        """
        from nicegui import core

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
