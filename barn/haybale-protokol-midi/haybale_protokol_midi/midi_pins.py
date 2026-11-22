"""The pins of the MIDI nodes, by kind: shared by MIDI Event and Send MIDI."""

from __future__ import annotations

from typing import Any

from haywire.api import NodeWarning

from haybale_protokol_midi.midi_messages import CHANNEL_KINDS

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


#: The Channel and Number fields' limits: 0 and −1 are the open choice (any, or from an inlet).
#: The field clamps to them; ``filter_problem`` still badges a value that got past the field
#: (a graph saved before, an agent through Farmhand, a promoted setting fed by a wire).
CHANNEL_RANGE = {"min": 0, "max": 16}
NUMBER_RANGE = {"min": -1, "max": 127}

#: The ``NodeWarning.kind`` of a filter no message can pass (MIDI Event) or no message fits (Send MIDI).
FILTER_WARNING = "protokol-midi-filter"


def filter_problem(kind: str, channel: int, number: int, *, open_word: str) -> str | None:
    """Why ``channel`` or ``number`` is impossible for ``kind``, else ``None``.

    MIDI has 16 channels and 128 note or controller numbers; ``0`` and ``−1`` mean the open
    choice, which ``open_word`` names (``any`` on MIDI Event, ``from an inlet`` on Send MIDI).
    Only the fields ``kind`` uses are checked: sysex has no channel, pitchbend no number.
    """
    if kind in CHANNEL_KINDS and not 0 <= channel <= 16:
        return f"Channel must be 0 ({open_word}) or 1–16, not {channel}"
    if kind in NUMBER_PIN and not -1 <= number <= 127:
        return f"Number must be −1 ({open_word}) or 0–127, not {number}"
    return None


def show_filter_problem(node: Any, problem: str | None) -> None:
    """Put ``problem`` on ``node``'s card as a warning badge, or clear it when ``None``."""
    wrapper = getattr(node, "wrapper", None)
    if wrapper is None:
        return
    warnings = [NodeWarning(problem, None, kind=FILTER_WARNING)] if problem else []
    wrapper.replace_warnings(FILTER_WARNING, warnings)
