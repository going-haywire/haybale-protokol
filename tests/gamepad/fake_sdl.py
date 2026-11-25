"""A fake SDL for the gamepad driver: pads a test plugs, moves, presses and unplugs."""

from __future__ import annotations

import itertools
import threading
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from haybale_protokol_gamepad.driver import PadEvent, PadInfo
from haybale_protokol_gamepad.gamepad_messages import AXES, BUTTONS

XBOX = "030081b85e0400008e02000014010000"
_instances = itertools.count(100)


@dataclass(eq=False)
class FakePad:
    """One pad; ``axes`` and ``buttons`` are its state, as SDL would report it."""

    guid: str = XBOX
    name: str = "X360 Controller"
    can_rumble: bool = True
    instance: int = field(default_factory=lambda: next(_instances))
    axes: list[int] = field(default_factory=lambda: [0] * len(AXES))
    buttons: list[bool] = field(default_factory=lambda: [False] * len(BUTTONS))
    rumbles: list[tuple[int, int, int]] = field(default_factory=list)
    opens: int = 0


class FakeBackend:
    """``Backend`` without SDL. The test calls run on the test's thread; the rest on the pump's."""

    def __init__(self, *pads: FakePad, fail_init: str | None = None) -> None:
        self.fail_init = fail_init
        self.started = 0
        self.quits = 0
        self._lock = threading.Lock()
        self._pads: list[FakePad] = list(pads)
        self._events: deque[PadEvent] = deque()

    # -- Backend

    def init(self) -> None:
        if self.fail_init:
            raise OSError(self.fail_init)
        self.started += 1

    def quit(self) -> None:
        self.quits += 1

    def poll(self) -> list[PadEvent]:
        with self._lock:
            events, self._events = list(self._events), deque()
        return events

    def pads(self) -> list[PadInfo]:
        with self._lock:
            return [PadInfo(i, pad.guid, pad.name) for i, pad in enumerate(self._pads)]

    def open(self, index: int) -> tuple[Any, int]:
        with self._lock:
            pad = self._pads[index]
        pad.opens += 1
        return pad, pad.instance

    def close(self, handle: Any) -> None:
        handle.opens -= 1

    def state(self, handle: Any) -> tuple[list[int], list[bool]]:
        return list(handle.axes), list(handle.buttons)

    def rumble(self, handle: Any, low: int, high: int, duration_ms: int) -> bool:
        if not handle.can_rumble:
            return False
        handle.rumbles.append((low, high, duration_ms))
        return True

    # -- what a test does

    def plug(self, pad: FakePad) -> None:
        with self._lock:
            self._pads.append(pad)
            self._events.append(PadEvent("changed"))

    def unplug(self, pad: FakePad) -> None:
        with self._lock:
            self._pads.remove(pad)
            self._events.extend([PadEvent("removed", pad.instance), PadEvent("changed")])

    def move(self, pad: FakePad, axis: int, raw: int) -> None:
        pad.axes[axis] = raw
        with self._lock:
            self._events.append(PadEvent("axis", pad.instance, axis, raw))

    def press(self, pad: FakePad, button: int, pressed: bool = True) -> None:
        pad.buttons[button] = pressed
        with self._lock:
            self._events.append(PadEvent("button", pad.instance, button, int(pressed)))
