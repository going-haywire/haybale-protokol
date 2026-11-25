"""The outputs Gamepad Event offers: each is one outlet, read from the pad's state.

Every message from a pad carries the pad's whole state (``extra["state"]``: its axes −1…1 as
SDL reports them, and its buttons), so a node reads all its outputs from one message and
never mixes values from two moments: a stick's x and y always belong together.

Face buttons are by position on every brand: ``a`` is the bottom one (A on Xbox, cross on
PlayStation, B on Nintendo), ``b`` the right, ``x`` the left, ``y`` the top.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from haywire.api import Vec2f, Vec2i

from haybale_protokol_gamepad.gamepad_messages import BUTTONS, DPAD, dpad_hat


@dataclass(frozen=True)
class Output:
    """One selectable output: its outlet type and what it is made of."""

    name: str
    label: str
    type_name: str
    """The builtin type of its outlet: ``VEC2F``, ``FLOAT``, ``VEC2I`` or ``BOOL``."""
    axes: tuple[int, ...] = ()
    buttons: tuple[int, ...] = ()
    hat: bool = False


def _stick(side: str, x: int, y: int) -> tuple[Output, ...]:
    label = f"{side.capitalize()} stick"
    return (
        Output(f"{side}_stick_vec", f"{label} (x, y)", "VEC2F", axes=(x, y)),
        Output(f"{side}_stick_x", f"{label} x", "FLOAT", axes=(x, y)),
        Output(f"{side}_stick_y", f"{label} y", "FLOAT", axes=(x, y)),
    )


#: The labels of the buttons, by SDL name, where SDL's name needs one.
_BUTTON_LABELS = {
    "a": "A (bottom)",
    "b": "B (right)",
    "x": "X (left)",
    "y": "Y (top)",
    "guide": "Guide (home)",
    "leftstick": "Left stick press",
    "rightstick": "Right stick press",
    "leftshoulder": "Left shoulder",
    "rightshoulder": "Right shoulder",
    "dpup": "D-pad up",
    "dpdown": "D-pad down",
    "dpleft": "D-pad left",
    "dpright": "D-pad right",
    "misc1": "Misc (share, capture, mic)",
}
#: The outlet names of the buttons, by SDL name, where it is not the SDL name.
_BUTTON_NAMES = {
    "leftstick": "left_stick_press",
    "rightstick": "right_stick_press",
    "leftshoulder": "left_shoulder",
    "rightshoulder": "right_shoulder",
    "dpup": "dpad_up",
    "dpdown": "dpad_down",
    "dpleft": "dpad_left",
    "dpright": "dpad_right",
}

OUTPUTS: tuple[Output, ...] = (
    *_stick("left", 0, 1),
    *_stick("right", 2, 3),
    Output("left_trigger", "Left trigger", "FLOAT", axes=(4,)),
    Output("right_trigger", "Right trigger", "FLOAT", axes=(5,)),
    Output("dpad_vec", "D-pad (x, y)", "VEC2I", hat=True),
    *(
        Output(
            _BUTTON_NAMES.get(name, name),
            _BUTTON_LABELS.get(name, name.capitalize()),
            "BOOL",
            buttons=(index,),
        )
        for index, name in enumerate(BUTTONS)
    ),
)
BY_NAME = {output.name: output for output in OUTPUTS}
#: The menu's choices: outlet name → label.
CHOICES = {output.name: output.label for output in OUTPUTS}
DEFAULT = "left_stick_vec"


def names(text: str | None) -> list[str]:
    """The names in ``text`` (``"a, left_stick_vec"``), in order, without blanks or repeats."""
    found: list[str] = []
    for part in (text or "").split(","):
        name = part.strip()
        if name and name not in found:
            found.append(name)
    return found


def selected(text: str | None) -> list[Output]:
    """The outputs ``text`` names, in its order; unknown names left out."""
    return [BY_NAME[name] for name in names(text) if name in BY_NAME]


def unknown(text: str | None) -> list[str]:
    """The names in ``text`` that are no output."""
    return [name for name in names(text) if name not in BY_NAME]


def is_event(output: Output) -> bool:
    """A button: every press and release counts. Sticks, triggers and the d-pad are values."""
    return bool(output.buttons)


@dataclass(frozen=True)
class Shaping:
    """How a node shapes stick values: its dead zone and which way is up."""

    dead_zone: float = 0.2
    y_up: bool = True


def value(output: Output, axes: Sequence[float], buttons: Sequence[bool], shaping: Shaping) -> Any:
    """The value of ``output`` from a pad state."""
    if output.buttons:
        index = output.buttons[0]
        return bool(buttons[index]) if index < len(buttons) else False
    if output.hat:
        hat_x, hat_y = dpad_hat({i for i in DPAD if i < len(buttons) and buttons[i]})
        return Vec2i([hat_x, -hat_y if shaping.y_up else hat_y])
    if len(output.axes) == 1:
        index = output.axes[0]
        return float(axes[index]) if index < len(axes) else 0.0
    x, y = stick(axes[output.axes[0]], axes[output.axes[1]], shaping)
    if output.type_name == "VEC2F":
        return Vec2f([x, y])
    return x if output.name.endswith("_x") else y


def stick(x: float, y: float, shaping: Shaping) -> tuple[float, float]:
    """A stick's ``(x, y)`` after the radial dead zone, rescaled to reach 1 again, with y flipped for up."""
    zone = min(max(float(shaping.dead_zone), 0.0), 0.95)
    length = math.hypot(x, y)
    if length <= zone:
        x = y = 0.0
    elif zone > 0:
        scale = min(1.0, (length - zone) / (1.0 - zone)) / length
        x, y = x * scale, y * scale
    return float(x), float(-y if shaping.y_up else y)
