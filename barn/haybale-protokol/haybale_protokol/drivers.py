"""What a Protocol haybale hands the base: its Protocol driver, and the messages it carries.

Each Protocol haybale registers one ``ProtocolDriver`` with ``ProtokolState`` while it is
enabled. The driver says which Line a Gate uses, opens that Line's ``Connection``, and
describes messages for the Monitor. Everything here is called from a Line's own thread or
from ``ProtokolState``; nothing touches the UI.
"""

from __future__ import annotations

from collections.abc import Callable, Hashable, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

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

    def cache_key(self, message: Message) -> Hashable:
        """Return what the Line cache keeps the last message per (address, channel, axis)."""
        ...

    def describe(self, message: Message) -> str:
        """Return one line describing ``message`` for the Monitor."""
        ...
