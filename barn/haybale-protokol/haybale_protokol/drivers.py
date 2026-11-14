"""What a Protocol haybale hands the base: its Protocol driver, and the messages it carries.

Each Protocol haybale registers one ``ProtocolDriver`` with ``ProtokolState`` while it is
enabled. The driver says which Line a Gate uses, opens that Line's ``Connection``, and
describes messages for the Monitor. Everything here is called from a Line's own thread or
from ``ProtokolState``; nothing touches the UI.
"""

from __future__ import annotations

from collections.abc import Callable, Hashable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from haybale_protokol.devices import Device
from haybale_protokol.gates import Gate


@dataclass(frozen=True)
class LineKey:
    """Which Line: one per protocol and port, or per Device. ``address`` is driver-defined."""

    protocol: str
    address: str


@dataclass(frozen=True, slots=True)
class Message:
    """One message on a Line, in either direction."""

    address: str
    """The OSC address, or the driver's equivalent (``note 1``, ``axis 0``)."""
    args: tuple[Any, ...]
    time: float
    """``time.time()`` when it arrived or was sent."""
    extra: Mapping[str, Any] = field(default_factory=dict)
    """Driver-specific details: an OSC bundle member's ``timetag``, the ``types`` to send."""


class Connection(Protocol):
    """One open port or device connection; the driver's half of a Line."""

    @property
    def status(self) -> str:
        """Short text for the Line's status while open (``open``, ``reconnecting (2)``)."""
        ...

    def start(self, deliver: Callable[[Message], None]) -> None:
        """Open, and start the daemon thread that calls ``deliver`` for each message.

        Raises:
            OSError: The port or device cannot be opened.
        """
        ...

    def send(self, message: Message) -> bool:
        """Send ``message``; ``False`` when it was dropped (never queued)."""
        ...

    def close(self) -> None:
        """Stop the thread and release the port. Safe to call twice."""
        ...


class ProtocolDriver(Protocol):
    """How the base opens, reads, sends and describes one protocol."""

    protocol: str

    def line_key(self, gate: Gate, device: Device | None) -> LineKey:
        """Return the Line ``gate`` uses; gates with equal keys share one Line."""
        ...

    def open(self, key: LineKey, gate: Gate, device: Device | None) -> Connection:
        """Build the (not yet started) Connection for the Line ``key``."""
        ...

    def line_options(self, gate: Gate) -> Mapping[str, Any]:
        """Options every gate sharing a Line must agree on (a TCP framing); usually none."""
        ...

    def cache_key(self, message: Message) -> Hashable:
        """Return what the Line cache keeps the last message per (address, channel, axis)."""
        ...

    def describe(self, message: Message) -> str:
        """Return one line describing ``message`` for the Monitor."""
        ...


# -- optional driver features ---------------------------------------------------------
#
# A driver may also offer these; the editors read them with the helpers below, so a driver
# without one still works (no form fields, no test-send, no device list).


@dataclass(frozen=True)
class GateField:
    """One protocol option in the gate form."""

    key: str
    label: str
    kind: Literal["text", "int", "choice"]
    default: Any = None
    choices: tuple[str, ...] = ()
    applies: tuple[Mapping[str, tuple[Any, ...]], ...] = ()
    """When the field shows: any one of these conditions holds (none means always).

    A condition holds when, for each key, the gate's value (or that field's default) is listed.
    Keys are option keys or ``direction``.
    """

    def applies_to(self, values: Mapping[str, Any], defaults: Mapping[str, Any]) -> bool:
        if not self.applies:
            return True
        return any(
            all(values.get(key, defaults.get(key)) in allowed for key, allowed in condition.items())
            for condition in self.applies
        )


def gate_fields(driver: Any) -> Sequence[GateField]:
    """The driver's gate-form fields, or none."""
    describe = getattr(driver, "gate_fields", None)
    return tuple(describe()) if callable(describe) else ()


def message_parser(driver: Any) -> Callable[[str], Message] | None:
    """The driver's ``parse_test_message``, or ``None`` when it offers no test-send."""
    parse = getattr(driver, "parse_test_message", None)
    return parse if callable(parse) else None


def list_devices(driver: Any) -> Sequence[tuple[str, str]]:
    """``(os_id, description)`` of the devices the driver sees on this machine, or none."""
    listing = getattr(driver, "list_devices", None)
    return tuple(listing()) if callable(listing) else ()


def uses_devices(driver: Any) -> bool:
    """Whether the driver's gates name a Device."""
    return bool(getattr(driver, "uses_devices", False))
