"""Gamepad input and rumble as protokol ``Message``s.

SDL's GameController API gives every supported pad one layout, so an index means the same
control on hundreds of pads. The ``address`` names what a filter matches and what the Line
cache keeps the last of: ``axis <i>``, ``button <i>``, ``hat 0`` and, outbound, ``rumble``.
``extra`` holds ``kind`` and ``index``, and ``initial`` on the state a pad reports when its
Line opens (where its sticks, triggers and d-pad are): the Line cache's start values, which a
Receive node takes only when its Start value is on.

- **axis**: ``(value,)``, a float. Sticks −1…1, with left and up negative as SDL reports
  them; triggers 0…1.
- **button**: ``(pressed,)``, a bool.
- **hat**: ``(Vec2i([x, y]),)``, the d-pad as one value: x −1 left … 1 right, y −1 up … 1
  down, the same directions as the sticks. The d-pad's four buttons also arrive as buttons.
- **rumble**: ``(low, high, duration_ms)``: the low- and high-frequency motors 0…1, and how
  long, in milliseconds.
"""

from __future__ import annotations

import time as _time
from typing import Any

from haywire.api import Vec2i

from haybale_protokol.drivers import Message

KINDS = ("axis", "button", "hat", "all")
#: Kinds whose value is a state (a stick, a trigger, the d-pad): Start value on, Drop with a queue of one.
STREAM_KINDS = ("axis", "hat")

#: SDL_GameControllerAxis, by index.
AXES = ("leftx", "lefty", "rightx", "righty", "lefttrigger", "righttrigger")
#: The axes that rest at 0 and go to 1 (the others are centred sticks).
TRIGGERS = (4, 5)
#: SDL_GameControllerButton, by index.
BUTTONS = (
    "a",
    "b",
    "x",
    "y",
    "back",
    "guide",
    "start",
    "leftstick",
    "rightstick",
    "leftshoulder",
    "rightshoulder",
    "dpup",
    "dpdown",
    "dpleft",
    "dpright",
    "misc1",
    "paddle1",
    "paddle2",
    "paddle3",
    "paddle4",
    "touchpad",
)
#: The d-pad buttons, by index: up, down, left, right.
DPAD = (11, 12, 13, 14)
#: Pads have one hat, the d-pad.
HATS = ("dpad",)

#: The highest index of each kind (``all`` covers the buttons, the most).
MAX_INDEX = {
    "axis": len(AXES) - 1,
    "button": len(BUTTONS) - 1,
    "hat": len(HATS) - 1,
    "all": len(BUTTONS) - 1,
}

#: SDL's axis range.
AXIS_MAX = 32767
#: The longest rumble, in milliseconds: a minute (SDL would take more; a control message should not).
RUMBLE_MAX_MS = 60_000


def index_name(kind: str, index: int) -> str:
    """The SDL name of ``kind``'s control ``index`` (``a``, ``leftx``), or ``str(index)`` if unknown."""
    names = {"axis": AXES, "button": BUTTONS, "hat": HATS}.get(kind, ())
    return names[index] if 0 <= index < len(names) else str(index)


def axis(index: int, raw: int, time: float, *, initial: bool = False) -> Message:
    """An axis motion with SDL's ``raw`` value (−32768…32767), scaled to −1…1 (a trigger 0…1)."""
    value = max(-1.0, min(1.0, raw / AXIS_MAX))
    if index in TRIGGERS:
        value = max(0.0, value)
    return Message(f"axis {index}", (value,), time, _extra("axis", index, initial))


def button(index: int, pressed: bool, time: float) -> Message:
    return Message(f"button {index}", (bool(pressed),), time, {"kind": "button", "index": index})


def hat(x: int, y: int, time: float, *, initial: bool = False) -> Message:
    return Message("hat 0", (Vec2i([int(x), int(y)]),), time, _extra("hat", 0, initial))


def dpad_hat(held: set[int]) -> tuple[int, int]:
    """The d-pad as ``(x, y)`` from the d-pad buttons held now; opposite buttons cancel."""
    x = (DPAD[3] in held) - (DPAD[2] in held)
    y = (DPAD[1] in held) - (DPAD[0] in held)
    return int(x), int(y)


def rumble(low: Any, high: Any, duration_ms: Any, time: float | None = None) -> Message:
    """A rumble message, checked.

    Raises:
        ValueError: A strength is not a number 0…1, or the duration not a whole number
            0…``RUMBLE_MAX_MS``.
    """
    strengths = (_strength("low", low), _strength("high", high))
    duration = _duration(duration_ms)
    when = _time.time() if time is None else time
    return Message("rumble", (*strengths, duration), when, {"kind": "rumble", "index": 0})


def parse_test_message(text: str) -> Message:
    """A Monitor test message: ``rumble <low> <high> [ms]`` (``rumble 0.5 1 200``), or ``stop``.

    Raises:
        ValueError: The text is not one of those.
    """
    words = text.split()
    try:
        if words == ["stop"]:
            return rumble(0.0, 0.0, 0)
        if words and words[0] == "rumble" and len(words) in (3, 4):
            duration = words[3] if len(words) == 4 else "200"
            return rumble(float(words[1]), float(words[2]), int(duration))
    except ValueError as exc:
        raise ValueError(f"cannot read {text!r} as a gamepad test message: {exc}") from None
    raise ValueError(f"cannot read {text!r} as a gamepad test message (try 'rumble 0.5 1 200' or 'stop')")


def describe(message: Message) -> str:
    """One line for the Monitor, e.g. ``axis 0 leftx = 0.52`` or ``button 0 a down``."""
    text = _describe(message)
    return f"{text} (at open)" if message.extra.get("initial") else text


def _describe(message: Message) -> str:
    kind = message.extra.get("kind")
    index = int(message.extra.get("index", 0))
    args = message.args
    if kind == "axis":
        return f"axis {index} {index_name('axis', index)} = {float(args[0]):.3f}"
    if kind == "button":
        return f"button {index} {index_name('button', index)} {'down' if args[0] else 'up'}"
    if kind == "hat":
        x, y = args[0]
        return f"hat {index} {index_name('hat', index)} ({x}, {y})"
    if kind == "rumble":
        low, high, duration = args
        if not low and not high:
            return "rumble stop"
        return f"rumble low {low:.2f} high {high:.2f} for {duration} ms"
    return f"{message.address} {args}"


def _extra(kind: str, index: int, initial: bool) -> dict[str, Any]:
    extra: dict[str, Any] = {"kind": kind, "index": index}
    if initial:
        extra["initial"] = True
    return extra


def _strength(field: str, value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a number 0…1, not {value!r}")
    if not 0.0 <= float(value) <= 1.0:
        raise ValueError(f"{field} must be 0…1, not {value}")
    return float(value)


def _duration(value: Any) -> int:
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"duration must be a whole number of milliseconds, not {value!r}")
    if not 0 <= value <= RUMBLE_MAX_MS:
        raise ValueError(f"duration must be 0…{RUMBLE_MAX_MS} ms, not {value}")
    return value
