"""MIDI 1.0 messages as protokol ``Message``s, and back.

The ``address`` names what a filter matches and what the Line cache keeps the last of:
``note <ch> <note>``, ``cc <ch> <controller>``, ``pitchbend <ch>``, ``aftertouch <ch>``,
``program <ch>``, ``sysex``, ``transport`` or ``raw``. Channels are 1–16, as musicians count
them. ``extra`` holds ``kind``, ``channel`` (``None`` for system messages), ``number`` (note or
controller) and the wire ``bytes``.
"""

from __future__ import annotations

import time as _time
from collections.abc import Mapping, Sequence
from typing import Any

import mido  # type: ignore[import-untyped]

from haybale_protokol.drivers import Message

KINDS = ("note", "cc", "pitchbend", "aftertouch", "program", "sysex", "transport", "raw")
CHANNEL_KINDS = ("note", "cc", "pitchbend", "aftertouch", "program")
#: Kinds whose value is a state (a fader, a wheel): Start value on, Drop with a queue of one.
STREAM_KINDS = ("cc", "pitchbend", "aftertouch")
TRANSPORT_EVENTS = ("clock", "start", "continue", "stop", "songpos")

_TEST_ALIASES = {"pb": "pitchbend", "at": "aftertouch", "pc": "program"}


def decode(data: Sequence[int], time: float) -> Message | None:
    """The message ``data`` holds, or ``None`` for no bytes; anything unknown is ``raw``."""
    if not data:
        return None
    raw = bytes(data)
    try:
        parsed = mido.Message.from_bytes(list(data))
    except (ValueError, TypeError):
        return _message("raw", "raw", (raw,), raw, time)
    kind = parsed.type
    if kind in ("note_on", "note_off"):
        on = kind == "note_on" and parsed.velocity > 0
        return _message(
            f"note {parsed.channel + 1} {parsed.note}",
            "note",
            (parsed.note, parsed.velocity, on),
            raw,
            time,
            parsed.channel + 1,
            parsed.note,
        )
    if kind == "control_change":
        channel = parsed.channel + 1
        return _message(
            f"cc {channel} {parsed.control}",
            "cc",
            (parsed.control, parsed.value),
            raw,
            time,
            channel,
            parsed.control,
        )
    if kind == "pitchwheel":
        channel = parsed.channel + 1
        return _message(f"pitchbend {channel}", "pitchbend", (parsed.pitch,), raw, time, channel)
    if kind == "aftertouch":
        channel = parsed.channel + 1
        return _message(f"aftertouch {channel}", "aftertouch", (parsed.value,), raw, time, channel)
    if kind == "program_change":
        channel = parsed.channel + 1
        return _message(f"program {channel}", "program", (parsed.program,), raw, time, channel)
    if kind == "sysex":
        return _message("sysex", "sysex", (bytes(parsed.data),), raw, time)
    if kind in ("clock", "start", "continue", "stop"):
        return _message("transport", "transport", (kind, 0), raw, time)
    if kind == "songpos":
        return _message("transport", "transport", ("songpos", parsed.pos), raw, time)
    return _message("raw", "raw", (raw,), raw, time)


def encode(kind: str, channel: int | None, number: int | None, values: Mapping[str, Any]) -> bytes:
    """The wire bytes of one message.

    ``number`` is the note or controller when the node's filter fixes it, else ``values`` holds it.

    Raises:
        ValueError: A value out of range; the message names the field.
    """
    if kind in CHANNEL_KINDS:
        ch = _ranged("channel", channel, 1, 16) - 1
    if kind == "note":
        note = _ranged("note", number if number is not None else values.get("note"), 0, 127)
        velocity = _ranged("velocity", values.get("velocity", 0), 0, 127)
        on = bool(values.get("on", True))
        built = mido.Message("note_on" if on else "note_off", channel=ch, note=note, velocity=velocity)
    elif kind == "cc":
        control = _ranged("controller", number if number is not None else values.get("controller"), 0, 127)
        built = mido.Message(
            "control_change",
            channel=ch,
            control=control,
            value=_ranged("value", values.get("value"), 0, 127),
        )
    elif kind == "pitchbend":
        built = mido.Message(
            "pitchwheel", channel=ch, pitch=_ranged("value", values.get("value"), -8192, 8191)
        )
    elif kind == "aftertouch":
        built = mido.Message("aftertouch", channel=ch, value=_ranged("value", values.get("value"), 0, 127))
    elif kind == "program":
        built = mido.Message(
            "program_change", channel=ch, program=_ranged("program", values.get("program"), 0, 127)
        )
    elif kind == "sysex":
        data = bytes(values.get("data") or b"")
        if any(byte > 127 for byte in data):
            raise ValueError("data bytes must be 0..127 (without the F0/F7 framing)")
        built = mido.Message("sysex", data=list(data))
    elif kind == "transport":
        event = values.get("event")
        if event not in TRANSPORT_EVENTS:
            raise ValueError(f"event must be one of {', '.join(TRANSPORT_EVENTS)}, not {event!r}")
        if event == "songpos":
            built = mido.Message("songpos", pos=_ranged("position", values.get("position", 0), 0, 16383))
        else:
            built = mido.Message(str(event))
    elif kind == "raw":
        data = bytes(values.get("bytes") or b"")
        if not data:
            raise ValueError("bytes must not be empty")
        return data
    else:
        raise ValueError(f"kind must be one of {', '.join(KINDS)}, not {kind!r}")
    return bytes(built.bytes())


def parse_test_message(text: str) -> Message:
    """A Monitor test message: ``note 1 60 100``, ``note 1 60 off``, ``cc 1 7 64``, ``pb 1 -200``,
    ``at 1 64``, ``pc 1 5``, ``sysex 7D 01 02``, ``clock``/``start``/``continue``/``stop``,
    ``raw 90 3C 64`` (hex bytes).

    Raises:
        ValueError: Not one of those forms, or a value out of range.
    """
    words = text.split()
    if not words:
        raise ValueError("a test message starts with a kind: note, cc, pb, at, pc, sysex, clock, raw …")
    kind = _TEST_ALIASES.get(words[0].lower(), words[0].lower())
    args = words[1:]
    try:
        if kind == "note" and len(args) == 3:
            off = args[2].lower() == "off"
            values: dict[str, Any] = {"velocity": 0 if off else int(args[2]), "on": not off}
            data = encode("note", int(args[0]), int(args[1]), values)
        elif kind == "cc" and len(args) == 3:
            data = encode("cc", int(args[0]), int(args[1]), {"value": int(args[2])})
        elif kind in ("pitchbend", "aftertouch") and len(args) == 2:
            data = encode(kind, int(args[0]), None, {"value": int(args[1])})
        elif kind == "program" and len(args) == 2:
            data = encode("program", int(args[0]), None, {"program": int(args[1])})
        elif kind == "sysex":
            data = encode("sysex", None, None, {"data": bytes(int(b, 16) for b in args)})
        elif kind in TRANSPORT_EVENTS and kind != "songpos" and not args:
            data = encode("transport", None, None, {"event": kind})
        elif kind == "raw" and args:
            data = encode("raw", None, None, {"bytes": bytes(int(b, 16) for b in args)})
        else:
            raise ValueError(f"cannot read {text!r} as a MIDI test message")
    except ValueError as exc:
        if str(exc).startswith("cannot read"):
            raise
        raise ValueError(f"cannot read {text!r} as a MIDI test message: {exc}") from None
    message = decode(data, _time.time())
    assert message is not None
    return message


def describe(message: Message) -> str:
    """One line for the Monitor, e.g. ``note on ch1 60 vel 100``."""
    kind = message.extra.get("kind", "raw")
    channel = message.extra.get("channel")
    args = message.args
    if kind == "note":
        note, velocity, on = args
        return f"note on ch{channel} {note} vel {velocity}" if on else f"note off ch{channel} {note}"
    if kind == "cc":
        return f"cc ch{channel} {args[0]} = {args[1]}"
    if kind in ("pitchbend", "aftertouch", "program"):
        return f"{kind} ch{channel} {args[0]}"
    if kind == "transport":
        event, position = args
        return f"songpos {position}" if event == "songpos" else str(event)
    data = args[0] if args else b""
    return f"{kind} {bytes(data).hex(' ')}".rstrip()


def _message(
    address: str,
    kind: str,
    args: tuple[Any, ...],
    raw: bytes,
    time: float,
    channel: int | None = None,
    number: int | None = None,
) -> Message:
    return Message(address, args, time, {"kind": kind, "channel": channel, "number": number, "bytes": raw})


def _ranged(field: str, value: Any, low: int, high: int) -> int:
    """``value`` as an int in ``low..high``; a whole float (``3.0``) counts, ``3.7`` never rounds."""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field} must be a whole number {low}..{high}, not {value!r}")
    if not low <= value <= high:
        raise ValueError(f"{field} must be {low}..{high}, not {value}")
    return value
