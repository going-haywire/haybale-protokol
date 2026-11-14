"""The MIDI Protocol driver: one Line per Device and direction, through python-rtmidi."""

from __future__ import annotations

from collections.abc import Hashable, Mapping
from typing import Any

from haybale_protokol.devices import Device
from haybale_protokol.drivers import Connection, LineKey, Message
from haybale_protokol.gates import Gate


class MidiDriver:
    """``ProtocolDriver`` for ``protocol = "midi"``."""

    protocol = "midi"
    uses_devices = True

    def line_key(self, gate: Gate, device: Device | None) -> LineKey:
        raise ValueError("MIDI gates are not available yet")

    def open(self, key: LineKey, gate: Gate, device: Device | None) -> Connection:
        raise ValueError("MIDI gates are not available yet")

    def line_options(self, gate: Gate) -> Mapping[str, Any]:
        return {}

    def cache_key(self, message: Message) -> Hashable:
        return message.address

    def describe(self, message: Message) -> str:
        return message.address
