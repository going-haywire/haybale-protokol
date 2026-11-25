"""The gamepad driver on a fake SDL: listing, OS ids, opening, events, rumble, unplugging."""

from __future__ import annotations

import threading
from typing import Any

import pytest

from haybale_protokol.devices import Device
from haybale_protokol.drivers import Message
from haybale_protokol.gates import Gate
import haybale_protokol_gamepad.gamepad_messages as gm
from haybale_protokol_gamepad.driver import GamepadConnection, GamepadDriver, PadInfo, os_ids
from tests.gamepad.fake_sdl import XBOX, FakeBackend, FakePad
from tests.osc.graphs import wait_until

GRID = "03008e773a3000002381000011010000"


def _open(driver: GamepadDriver, os_id: str) -> tuple[GamepadConnection, list[Message]]:
    gate = Gate("pad", "gamepad", "two-way", device="pad")
    device = Device("pad", "gamepad", os_id)
    connection = driver.open(driver.line_key(gate, device), gate, device)
    assert isinstance(connection, GamepadConnection)
    got: list[Message] = []
    connection.start(got.append)
    return connection, got


def _described(got: list[Message]) -> list[str]:
    return [gm.describe(message) for message in got]


def test_os_ids_number_alike_pads() -> None:
    pads = [PadInfo(0, XBOX, "a"), PadInfo(1, GRID, "grid"), PadInfo(2, XBOX, "b"), PadInfo(3, XBOX, "c")]
    assert [os_id for _, os_id in os_ids(pads)] == [XBOX, GRID, f"{XBOX}#2", f"{XBOX}#3"]


def test_lists_pads(sdl: FakeBackend) -> None:
    driver = GamepadDriver()
    assert driver.list_devices() == []
    sdl.plug(FakePad(name="X360 Controller"))
    sdl.plug(FakePad(name="Second pad"))
    sdl.plug(FakePad(GRID, "Intech Studio Grid", can_rumble=False))
    assert wait_until(lambda: len(driver.list_devices()) == 3)
    assert driver.list_devices() == [
        (XBOX, "X360 Controller"),
        (f"{XBOX}#2", "Second pad"),
        (GRID, "Intech Studio Grid"),
    ]


def test_no_sdl_lists_nothing_and_cannot_open(sdl: FakeBackend) -> None:
    sdl.fail_init = "SDL2 is not available (no library)"
    driver = GamepadDriver()
    assert driver.list_devices() == []
    with pytest.raises(OSError, match="no gamepad support on this machine"):
        _open(driver, XBOX)


def test_line_key() -> None:
    driver = GamepadDriver()
    device = Device("pad", "gamepad", XBOX)
    assert driver.line_key(Gate("a", "gamepad", "in", device="pad"), device).address == XBOX
    assert driver.line_key(Gate("b", "gamepad", "two-way", device="pad"), device).address == XBOX
    with pytest.raises(ValueError, match="in, or two-way"):
        driver.line_key(Gate("c", "gamepad", "out", device="pad"), device)
    with pytest.raises(ValueError, match="needs a device"):
        driver.line_key(Gate("d", "gamepad", "in"), None)


def test_open_delivers_the_state_first(sdl: FakeBackend) -> None:
    pad = FakePad()
    pad.axes[0] = 32767
    pad.buttons[13] = True  # d-pad left held
    sdl.plug(pad)
    connection, got = _open(GamepadDriver(), XBOX)
    assert wait_until(lambda: len(got) == 7)
    assert _described(got)[0] == "axis 0 leftx = 1.000 (at open)"
    assert _described(got)[-1] == "hat 0 dpad (-1, 0) (at open)"
    assert connection.status == "listening on 'X360 Controller'"
    connection.close()
    assert pad.opens == 0


def test_events_reach_only_their_pad(sdl: FakeBackend) -> None:
    first, second = FakePad(), FakePad()
    sdl.plug(first)
    sdl.plug(second)
    driver = GamepadDriver()
    one, got_one = _open(driver, XBOX)
    two, got_two = _open(driver, f"{XBOX}#2")
    assert wait_until(lambda: len(got_one) == 7 and len(got_two) == 7)
    got_one.clear()
    got_two.clear()
    sdl.move(second, 1, -32768)
    sdl.press(first, 0)
    assert wait_until(lambda: bool(got_one and got_two))
    assert _described(got_one) == ["button 0 a down"]
    assert _described(got_two) == ["axis 1 lefty = -1.000"]
    one.close()
    two.close()


def test_dpad_buttons_also_move_the_hat(sdl: FakeBackend) -> None:
    pad = FakePad()
    sdl.plug(pad)
    connection, got = _open(GamepadDriver(), XBOX)
    assert wait_until(lambda: len(got) == 7)
    got.clear()
    sdl.press(pad, 11)
    sdl.press(pad, 14)
    sdl.press(pad, 11, False)
    assert wait_until(lambda: len(got) == 6)
    assert _described(got) == [
        "button 11 dpup down",
        "hat 0 dpad (0, -1)",
        "button 14 dpright down",
        "hat 0 dpad (1, -1)",
        "button 11 dpup up",
        "hat 0 dpad (1, 0)",
    ]
    connection.close()


def test_rumble(sdl: FakeBackend) -> None:
    pad = FakePad()
    grid = FakePad(GRID, "Intech Studio Grid", can_rumble=False)
    sdl.plug(pad)
    sdl.plug(grid)
    driver = GamepadDriver()
    connection, _ = _open(driver, XBOX)
    assert connection.send(gm.rumble(1.0, 0.5, 250))
    assert pad.rumbles == [(0xFFFF, 0x8000, 250)]
    assert not connection.send(gm.axis(0, 1, 0.0)), "only rumble goes out"
    assert connection.status == "listening on 'X360 Controller' · rumbled 1 · dropped 1"
    no_motors, _ = _open(driver, GRID)
    assert not no_motors.send(gm.rumble(1.0, 1.0, 100))
    connection.close()
    no_motors.close()


def test_missing_pad_cannot_open(sdl: FakeBackend) -> None:
    sdl.plug(FakePad())
    with pytest.raises(OSError, match=f"no gamepad '{XBOX}#2'"):
        _open(GamepadDriver(), f"{XBOX}#2")


def test_unplugged_pad_is_gone(sdl: FakeBackend) -> None:
    pad = FakePad()
    sdl.plug(pad)
    driver = GamepadDriver()
    connection, _ = _open(driver, XBOX)
    sdl.unplug(pad)
    assert wait_until(lambda: connection.gone)
    assert connection.status == "pad gone: 'X360 Controller' (plug it in again)"
    assert not connection.send(gm.rumble(0.5, 0.5, 100))
    assert wait_until(lambda: driver.list_devices() == [])
    connection.close()


def test_a_slow_subscriber_while_opening_does_not_deadlock(sdl: FakeBackend) -> None:
    """``start`` runs under the Line's lock; the pump delivering then must not wait for the opener."""
    pad = FakePad()
    sdl.plug(pad)
    lock = threading.Lock()
    got: list[Any] = []

    def deliver(message: Message) -> None:
        with lock:
            got.append(message)

    gate = Gate("pad", "gamepad", "in", device="pad")
    device = Device("pad", "gamepad", XBOX)
    driver = GamepadDriver()
    connection = driver.open(driver.line_key(gate, device), gate, device)
    with lock:  # as Line.add_user holds its lock around start
        connection.start(deliver)
        sdl.move(pad, 0, 100)
    assert wait_until(lambda: len(got) == 8)
    connection.close()


def test_close_stops_sdl(sdl: FakeBackend) -> None:
    driver = GamepadDriver()
    driver.list_devices()
    assert sdl.started == 1
    driver.close()
    assert sdl.quits == 1
    driver.close()  # safe twice
    driver.list_devices()
    assert sdl.started == 2, "the next listing starts it again"


def test_every_message_carries_the_whole_pad(sdl: FakeBackend) -> None:
    pad = FakePad()
    pad.buttons[2] = True  # x held at open
    sdl.plug(pad)
    connection, got = _open(GamepadDriver(), XBOX)
    assert wait_until(lambda: len(got) == 7)
    axes, buttons = got[0].extra["state"]
    assert (buttons[0], buttons[2]) == (False, True)
    got.clear()
    sdl.move(pad, 0, 32767)
    sdl.move(pad, 1, -32768)
    sdl.press(pad, 0)
    assert wait_until(lambda: len(got) == 3)
    axes, buttons = got[1].extra["state"]
    assert (axes[0], axes[1]) == (1.0, -1.0), "y's message knows x"
    assert not buttons[0], "not yet pressed then"
    axes, buttons = got[2].extra["state"]
    assert (buttons[0], buttons[2]) == (True, True)
    connection.close()
