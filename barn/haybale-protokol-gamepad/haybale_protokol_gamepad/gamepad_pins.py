"""The outlets of Gamepad Event, by kind, and the check of its Index filter."""

from __future__ import annotations

from typing import Any

from haywire.api import NodeWarning

from haybale_protokol_gamepad.gamepad_messages import AXES, BUTTONS, MAX_INDEX

#: The outlets each kind has besides ``index``, in order: (port id, builtin type name).
KIND_PINS: dict[str, tuple[tuple[str, str], ...]] = {
    "axis": (("value", "FLOAT"),),
    "button": (("pressed", "BOOL"),),
    "hat": (("hat", "VEC2I"),),
    "all": (("control", "STRING"), ("value", "FLOAT"), ("pressed", "BOOL"), ("hat", "VEC2I")),
}

#: The Index field's limits: −1 is any.
INDEX_RANGE = {"min": -1, "max": max(MAX_INDEX.values())}

#: The ``NodeWarning.kind`` of an index no control has.
FILTER_WARNING = "protokol-gamepad-filter"

INDEX_HELP = (
    "Which control, by SDL's GameController layout, or −1 for any (an index outlet then says "
    "which). Axes: "
    + ", ".join(f"{i} {name}" for i, name in enumerate(AXES))
    + ". Buttons: "
    + ", ".join(f"{i} {name}" for i, name in enumerate(BUTTONS))
    + ". Hat: 0, the d-pad. Not used by all, which passes every control."
)


def index_filter(value: Any) -> int:
    """The Index filter; ``None`` (unset) means any. ``0`` is a real control."""
    return -1 if value is None else int(value)


def filter_problem(kind: str, index: int) -> str | None:
    """Why no control of ``kind`` has ``index``, else ``None``."""
    if kind == "all" or index == -1:
        return None
    if not 0 <= index <= MAX_INDEX.get(kind, -1):
        return f"Index must be −1 (any) or 0–{MAX_INDEX[kind]} for {kind}, not {index}"
    return None


def show_filter_problem(node: Any, problem: str | None) -> None:
    """Put ``problem`` on ``node``'s card as a warning badge, or clear it when ``None``."""
    wrapper = getattr(node, "wrapper", None)
    if wrapper is None:
        return
    warnings = [NodeWarning(problem, None, kind=FILTER_WARNING)] if problem else []
    wrapper.replace_warnings(FILTER_WARNING, warnings)
