"""The driver on the real SDL with a real pad: run with ``PROTOKOL_GAMEPAD_HARDWARE=1`` and a pad plugged in.

Skipped otherwise, and in CI. It opens every game controller SDL lists, checks each reports its
state on open, and rumbles the ones that can (briefly).
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from functools import partial

import pytest

import haybale_protokol_gamepad.driver as gamepad_driver
from haybale_protokol.devices import Device
from haybale_protokol.drivers import Message
from haybale_protokol.gates import Gate
from haybale_protokol_gamepad.gamepad_messages import AXES, rumble
from tests.osc.graphs import wait_until

pytestmark = pytest.mark.skipif(
    os.environ.get("PROTOKOL_GAMEPAD_HARDWARE") != "1", reason="set PROTOKOL_GAMEPAD_HARDWARE=1 with a pad"
)


@pytest.fixture
def real_sdl() -> Iterator[None]:
    gamepad_driver.stop_pump()
    saved = gamepad_driver.backend_factory
    gamepad_driver.backend_factory = gamepad_driver.SdlBackend
    yield
    gamepad_driver.stop_pump()
    gamepad_driver.backend_factory = saved


def _has_state(got: list[Message]) -> bool:
    """Every axis and the d-pad reported."""
    return len(got) >= len(AXES) + 1


def test_real_pads(real_sdl: None) -> None:
    driver = gamepad_driver.GamepadDriver()
    pads = driver.list_devices()
    assert pads, "no game controller plugged in"
    rumbled = 0
    for os_id, name in pads:
        gate = Gate("pad", "gamepad", "two-way", device="pad")
        device = Device("pad", "gamepad", os_id)
        connection = driver.open(driver.line_key(gate, device), gate, device)
        got: list[Message] = []
        connection.start(got.append)
        try:
            assert wait_until(partial(_has_state, got)), f"{name}: no state on open"
            assert all(m.extra.get("initial") for m in got[: len(AXES) + 1])
            rumbled += connection.send(rumble(0.2, 0.2, 100))
        finally:
            connection.close()
    print(f"{len(pads)} pads: {pads}; {rumbled} rumbled")
