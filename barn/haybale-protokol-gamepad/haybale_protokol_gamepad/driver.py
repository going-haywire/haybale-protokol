"""The gamepad Protocol driver: one Line per Device, through SDL2's GameController API.

A gamepad gate is ``in`` or ``two-way`` and names a Device; the Device's OS id is the pad's SDL
GUID. A GUID names a model, not a unit, so two alike pads share one: the first in SDL's device
order is listed as the bare GUID, the next as ``<guid>#2``, then ``#3``. That order follows
plug order, so two alike pads can swap after a replug or a reboot.

SDL keeps one event queue per process, so the Lines cannot each read on a thread of their own.
One pump thread for the whole process (``_Pump``) makes every SDL call: it starts SDL, reads its
events, follows pads being plugged in and out, opens and closes pads, and rumbles them. Each
open pad's ``GamepadConnection`` is fed from it, so the pump is every gamepad Line's thread. It
starts with the first listing or open and stops when the driver is closed (the haybale disabled).
"""

from __future__ import annotations

import ctypes
import logging
import threading
import time
import warnings
from collections import deque
from collections.abc import Callable, Hashable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol, TypeVar

from haybale_protokol.devices import Device
from haybale_protokol.drivers import Connection, GateField, LineKey, Message
from haybale_protokol.gates import Gate
import haybale_protokol_gamepad.gamepad_messages as gamepad_messages

logger = logging.getLogger(__name__)

T = TypeVar("T")

#: Seconds the pump waits for work when SDL has no event queued.
POLL_S = 0.002
#: Seconds a caller waits for the pump to start SDL, or to run one of its calls.
CALL_TIMEOUT_S = 2.0


# -- what the pump needs of SDL ---------------------------------------------------------


@dataclass(frozen=True)
class PadInfo:
    """One game controller SDL sees now, by its device index."""

    index: int
    guid: str
    name: str


@dataclass(frozen=True)
class PadEvent:
    """One SDL event the pump acts on.

    ``kind`` is ``axis`` or ``button`` (``pad`` is the instance id, with ``control`` and
    ``value``), ``removed`` (``pad`` is the instance id), or ``changed`` (pads were added or
    removed: list them again).
    """

    kind: str
    pad: int = -1
    control: int = 0
    value: int = 0


class Backend(Protocol):
    """SDL's GameController API as the pump uses it; every call runs on the pump thread."""

    def init(self) -> None:
        """Start SDL's game controller subsystem.

        Raises:
            OSError: SDL is missing or cannot start.
        """
        ...

    def quit(self) -> None: ...

    def poll(self) -> list[PadEvent]:
        """Every event queued since the last call."""
        ...

    def pads(self) -> list[PadInfo]:
        """The game controllers plugged in now, in SDL's device order."""
        ...

    def open(self, index: int) -> tuple[Any, int]:
        """Open the pad at device ``index``; returns its handle and instance id.

        Raises:
            OSError: SDL cannot open it.
        """
        ...

    def close(self, handle: Any) -> None: ...

    def state(self, handle: Any) -> tuple[list[int], list[bool]]:
        """The pad's raw axis values and button states now, by index."""
        ...

    def rumble(self, handle: Any, low: int, high: int, duration_ms: int) -> bool:
        """Rumble the pad's low- and high-frequency motors (0…65535); ``False`` if it cannot."""
        ...


class SdlBackend:
    """``Backend`` on pysdl2, with the SDL2 library from pysdl2-dll."""

    def __init__(self) -> None:
        self._sdl: Any = None

    def init(self) -> None:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")  # pysdl2-dll announces which SDL it loads
                import sdl2  # type: ignore[import-untyped]
        except Exception as exc:  # ImportError, or pysdl2's RuntimeError when no SDL2 library loads
            raise OSError(f"SDL2 is not available ({exc})") from exc
        # Pads keep reporting while no window of this process has focus (there is none).
        sdl2.SDL_SetHint(sdl2.SDL_HINT_JOYSTICK_ALLOW_BACKGROUND_EVENTS, b"1")
        sdl2.SDL_SetHint(sdl2.SDL_HINT_JOYSTICK_THREAD, b"1")
        if sdl2.SDL_Init(sdl2.SDL_INIT_GAMECONTROLLER | sdl2.SDL_INIT_EVENTS) != 0:
            raise OSError(f"SDL cannot start game controllers: {_error(sdl2)}")
        self._sdl = sdl2

    def quit(self) -> None:
        if self._sdl is not None:
            self._sdl.SDL_QuitSubSystem(self._sdl.SDL_INIT_GAMECONTROLLER)
            self._sdl = None

    def poll(self) -> list[PadEvent]:
        sdl2 = self._sdl
        events: list[PadEvent] = []
        event = sdl2.SDL_Event()
        while sdl2.SDL_PollEvent(ctypes.byref(event)):
            kind = event.type
            if kind == sdl2.SDL_CONTROLLERAXISMOTION:
                axis = event.caxis
                events.append(PadEvent("axis", axis.which, axis.axis, axis.value))
            elif kind in (sdl2.SDL_CONTROLLERBUTTONDOWN, sdl2.SDL_CONTROLLERBUTTONUP):
                pressed = event.cbutton
                events.append(PadEvent("button", pressed.which, pressed.button, pressed.state))
            elif kind == sdl2.SDL_CONTROLLERDEVICEREMOVED:
                events.append(PadEvent("removed", event.cdevice.which))
                events.append(PadEvent("changed"))
            elif kind in (
                sdl2.SDL_CONTROLLERDEVICEADDED,
                sdl2.SDL_JOYDEVICEADDED,
                sdl2.SDL_JOYDEVICEREMOVED,
            ):
                events.append(PadEvent("changed"))
        return events

    def pads(self) -> list[PadInfo]:
        sdl2 = self._sdl
        found = []
        for index in range(sdl2.SDL_NumJoysticks()):
            if not sdl2.SDL_IsGameController(index):
                continue
            text = ctypes.create_string_buffer(33)
            sdl2.SDL_JoystickGetGUIDString(sdl2.SDL_JoystickGetDeviceGUID(index), text, 33)
            name = sdl2.SDL_GameControllerNameForIndex(index) or b"game controller"
            found.append(PadInfo(index, text.value.decode(), name.decode(errors="replace")))
        return found

    def open(self, index: int) -> tuple[Any, int]:
        sdl2 = self._sdl
        handle = sdl2.SDL_GameControllerOpen(index)
        if not handle:
            raise OSError(f"SDL cannot open the pad: {_error(sdl2)}")
        joystick = sdl2.SDL_GameControllerGetJoystick(handle)
        return handle, int(sdl2.SDL_JoystickInstanceID(joystick))

    def close(self, handle: Any) -> None:
        self._sdl.SDL_GameControllerClose(handle)

    def state(self, handle: Any) -> tuple[list[int], list[bool]]:
        sdl2 = self._sdl
        axes = [int(sdl2.SDL_GameControllerGetAxis(handle, i)) for i in range(len(gamepad_messages.AXES))]
        buttons = [
            bool(sdl2.SDL_GameControllerGetButton(handle, i)) for i in range(len(gamepad_messages.BUTTONS))
        ]
        return axes, buttons

    def rumble(self, handle: Any, low: int, high: int, duration_ms: int) -> bool:
        return self._sdl.SDL_GameControllerRumble(handle, low, high, duration_ms) == 0


def _error(sdl2: Any) -> str:
    message = sdl2.SDL_GetError()
    return message.decode(errors="replace") if message else "unknown error"


def os_ids(pads: Sequence[PadInfo]) -> list[tuple[PadInfo, str]]:
    """Each pad with its OS id: its GUID, and ``#2``, ``#3``… for the next pads with the same GUID."""
    seen: dict[str, int] = {}
    named = []
    for pad in pads:
        seen[pad.guid] = seen.get(pad.guid, 0) + 1
        count = seen[pad.guid]
        named.append((pad, pad.guid if count == 1 else f"{pad.guid}#{count}"))
    return named


# -- the pump ---------------------------------------------------------------------------


class _Pump:
    """The one thread that talks to SDL; see the module docstring."""

    def __init__(self, backend: Backend) -> None:
        self._backend = backend
        self._lock = threading.Lock()
        self._calls: deque[Callable[[], None]] = deque()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._thread: threading.Thread | None = None
        self.error: str | None = None
        """Why SDL could not start; then nothing opens and nothing is listed."""
        self._listing: tuple[tuple[str, str], ...] = ()
        self._indices: dict[str, int] = {}
        self._pads: dict[int, list[GamepadConnection]] = {}
        """The connections fed from each open pad, by SDL instance id."""

    # -- from any thread

    def start(self) -> None:
        """Start the thread and wait until SDL is up (or could not start). Safe to call again."""
        with self._lock:
            if self._thread is None:
                self._thread = threading.Thread(target=self._run, name="protokol-gamepad-sdl", daemon=True)
                self._thread.start()
        self._ready.wait(CALL_TIMEOUT_S)

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=CALL_TIMEOUT_S)

    def listing(self) -> tuple[tuple[str, str], ...]:
        """``(os id, name)`` of every pad plugged in now."""
        self.start()
        with self._lock:
            return self._listing

    def call(self, work: Callable[[], T]) -> T:
        """Run ``work`` on the pump thread and return what it returns (or raise what it raised).

        Raises:
            OSError: The pump is not running, or did not answer in time.
        """
        if threading.current_thread() is self._thread:
            return work()
        if self._stop.is_set() or self._thread is None:
            raise OSError("the gamepad pump is not running")
        done = threading.Event()
        outcome: list[Any] = []

        def run() -> None:
            try:
                outcome.append((True, work()))
            except BaseException as exc:  # handed back to the caller's thread
                outcome.append((False, exc))
            done.set()

        with self._lock:
            self._calls.append(run)
        self._wake.set()
        if not done.wait(CALL_TIMEOUT_S):
            raise OSError("the gamepad pump did not answer")
        ok, value = outcome[0]
        if not ok:
            raise value
        return value  # type: ignore[no-any-return]

    # -- on the pump thread

    def open_pad(self, os_id: str, connection: GamepadConnection) -> tuple[Any, int, str]:
        """Open the pad ``os_id`` names now for ``connection``; returns handle, instance id and name."""
        self._relist()
        index = self._indices.get(os_id)
        if index is None:
            raise OSError(f"no gamepad '{os_id}'")
        handle, instance = self._backend.open(index)
        self._pads.setdefault(instance, []).append(connection)
        name = next((n for i, n in self._listing if i == os_id), os_id)
        axes, buttons = self._backend.state(handle)
        # Delivered next, still before any event: the caller holds its Line's lock until this
        # call returns, so delivering here would wait for it while it waits for the pump.
        with self._lock:
            self._calls.appendleft(lambda: connection.seed(axes, buttons))
        return handle, instance, name

    def close_pad(self, handle: Any, instance: int, connection: GamepadConnection) -> None:
        users = self._pads.get(instance, [])
        if connection in users:
            users.remove(connection)
        if not users:
            self._pads.pop(instance, None)
        self._backend.close(handle)  # SDL counts opens of one pad

    def rumble(self, handle: Any, low: float, high: float, duration_ms: int) -> bool:
        return self._backend.rumble(handle, round(low * 0xFFFF), round(high * 0xFFFF), duration_ms)

    def _run(self) -> None:
        try:
            self._backend.init()
        except OSError as exc:
            self.error = exc.strerror or str(exc)
            logger.info("gamepads unavailable: %s", self.error)
            self._ready.set()
            return
        try:
            self._relist()
            self._ready.set()
            while not self._stop.is_set():
                self._run_calls()
                for event in self._backend.poll():
                    self._handle(event)
                self._wake.wait(POLL_S)
                self._wake.clear()
            self._run_calls()
        except Exception:
            logger.exception("the gamepad pump stopped")
        finally:
            self._ready.set()
            for users in self._pads.values():
                for connection in users:
                    connection.gone = True
            self._pads.clear()
            try:
                self._backend.quit()
            except Exception:
                logger.debug("stopping SDL failed", exc_info=True)

    def _run_calls(self) -> None:
        while True:
            with self._lock:
                if not self._calls:
                    return
                run = self._calls.popleft()
            run()

    def _handle(self, event: PadEvent) -> None:
        if event.kind == "changed":
            self._relist()
            return
        users = self._pads.get(event.pad, ())
        if event.kind == "removed":
            for connection in users:
                connection.gone = True
            return
        for connection in tuple(users):
            connection.feed(event)

    def _relist(self) -> None:
        named = os_ids(self._backend.pads())
        with self._lock:
            self._listing = tuple((os_id, pad.name) for pad, os_id in named)
            self._indices = {os_id: pad.index for pad, os_id in named}


#: How the pump reaches SDL; tests put a fake here before the first listing or open.
backend_factory: Callable[[], Backend] = SdlBackend
_pump: _Pump | None = None
_pump_lock = threading.Lock()


def _the_pump() -> _Pump:
    global _pump
    with _pump_lock:
        if _pump is None:
            _pump = _Pump(backend_factory())
        return _pump


def stop_pump() -> None:
    """Stop the pump and SDL; the next listing or open starts them again. Safe to call twice."""
    global _pump
    with _pump_lock:
        pump, _pump = _pump, None
    if pump is not None:
        pump.stop()


# -- the driver -------------------------------------------------------------------------


class GamepadDriver:
    """``ProtocolDriver`` for ``protocol = "gamepad"``."""

    protocol = "gamepad"
    uses_devices = True

    def close(self) -> None:
        """Stop the pump; the next listing or open starts it again. Safe to call twice."""
        stop_pump()

    def gate_fields(self) -> tuple[GateField, ...]:
        """Gamepad gates have no options of their own: the Device says which pad."""
        return ()

    def line_key(self, gate: Gate, device: Device | None) -> LineKey:
        if gate.direction == "out":
            raise ValueError("a gamepad gate is in, or two-way to rumble too")
        if device is None:
            raise ValueError("a gamepad gate needs a device")
        return LineKey("gamepad", device.os_id)

    def line_options(self, gate: Gate) -> Mapping[str, Any]:
        return {}

    def open(self, key: LineKey, gate: Gate, device: Device | None) -> Connection:
        return GamepadConnection(_the_pump, key.address)

    def cache_key(self, message: Message) -> Hashable:
        return message.address

    def describe(self, message: Message) -> str:
        return gamepad_messages.describe(message)

    def parse_test_message(self, text: str) -> Message:
        return gamepad_messages.parse_test_message(text)

    def list_devices(self) -> list[tuple[str, str]]:
        """Every game controller plugged in now, as ``(os id, name)``; none when SDL cannot start."""
        return list(_the_pump().listing())


class GamepadConnection:
    """One open pad; its messages come from the pump thread."""

    def __init__(self, pump: Callable[[], _Pump], os_id: str) -> None:
        self._get_pump = pump
        self.os_id = os_id
        self.name = os_id
        """The pad's name as SDL reports it, once open."""
        self.sent = 0
        self.dropped = 0
        self.gone = False
        """True once the pad was unplugged (or SDL stopped); sends are then dropped."""
        self._pump: _Pump | None = None
        self._handle: Any = None
        self._instance = -1
        self._deliver: Callable[[Message], None] | None = None
        self._held: set[int] = set()
        """The d-pad buttons held now, for the hat."""

    @property
    def status(self) -> str:
        if self.gone:
            return f"pad gone: '{self.name}' (plug it in again)"
        text = f"listening on '{self.name}'"
        if self.sent or self.dropped:
            text += f" · rumbled {self.sent} · dropped {self.dropped}"
        return text

    def start(self, deliver: Callable[[Message], None]) -> None:
        pump = self._get_pump()
        pump.start()
        if pump.error is not None:
            raise OSError(f"no gamepad support on this machine ({pump.error})")
        self._deliver = deliver
        self._handle, self._instance, self.name = pump.call(lambda: pump.open_pad(self.os_id, self))
        self._pump = pump

    def send(self, message: Message) -> bool:
        pump = self._pump
        if message.extra.get("kind") != "rumble" or pump is None or self.gone:
            self.dropped += 1
            return False
        low, high, duration = message.args
        try:
            ok = pump.call(lambda: pump.rumble(self._handle, low, high, duration))
        except OSError as exc:
            logger.debug("rumble on %s dropped: %s", self.name, exc)
            ok = False
        if ok:
            self.sent += 1
        else:
            self.dropped += 1
        return ok

    def close(self) -> None:
        pump, self._pump = self._pump, None
        if pump is None:
            return
        try:
            pump.call(lambda: pump.close_pad(self._handle, self._instance, self))
        except OSError:
            logger.debug("closing gamepad %s: the pump is gone", self.name)

    # -- on the pump thread

    def seed(self, axes: list[int], buttons: list[bool]) -> None:
        """Deliver the pad's state at open, its axes and d-pad: the Line cache's start values."""
        deliver = self._deliver
        if deliver is None:
            return
        now = time.time()
        self._held = {index for index in gamepad_messages.DPAD if index < len(buttons) and buttons[index]}
        for index, raw in enumerate(axes):
            deliver(gamepad_messages.axis(index, raw, now, initial=True))
        deliver(gamepad_messages.hat(*gamepad_messages.dpad_hat(self._held), now, initial=True))

    def feed(self, event: PadEvent) -> None:
        deliver = self._deliver
        if deliver is None:
            return
        now = time.time()
        if event.kind == "axis":
            deliver(gamepad_messages.axis(event.control, event.value, now))
        elif event.kind == "button":
            pressed = bool(event.value)
            deliver(gamepad_messages.button(event.control, pressed, now))
            if event.control in gamepad_messages.DPAD:
                if pressed:
                    self._held.add(event.control)
                else:
                    self._held.discard(event.control)
                deliver(gamepad_messages.hat(*gamepad_messages.dpad_hat(self._held), now))
