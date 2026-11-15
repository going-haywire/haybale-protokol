"""The pins of the MIDI nodes, by kind: shared by MIDI Receive and MIDI Send."""

from __future__ import annotations

from typing import Any

#: The pins each kind has (Receive outlets, Send inlets), in order: (port id, builtin type name).
KIND_PINS: dict[str, tuple[tuple[str, str], ...]] = {
    "note": (("velocity", "INT"), ("on", "BOOL")),
    "cc": (("value", "INT"),),
    "pitchbend": (("value", "INT"),),
    "aftertouch": (("value", "INT"),),
    "program": (("program", "INT"),),
    "sysex": (("data", "BYTES"),),
    "transport": (("event", "STRING"), ("position", "INT")),
    "raw": (("bytes", "BYTES"),),
}
#: The number a note or cc filter fixes, and the pin it gets when the filter is "any".
NUMBER_PIN = {"note": "note", "cc": "controller"}
#: The message arguments of each kind, by name (see ``midi_messages.decode``).
ARG_NAMES: dict[str, tuple[str, ...]] = {
    "note": ("note", "velocity", "on"),
    "cc": ("controller", "value"),
    "pitchbend": ("value",),
    "aftertouch": ("value",),
    "program": ("program",),
    "sysex": ("data",),
    "transport": ("event", "position"),
    "raw": ("bytes",),
}


def number_filter(value: Any) -> int:
    """The number filter; ``None`` (unset) means any. ``0`` is a real note or controller."""
    return -1 if value is None else int(value)
