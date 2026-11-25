"""Gamepad test fixtures: a fake SDL in place of the real one, so no pad is needed."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

import haybale_protokol_gamepad.driver as gamepad_driver
from tests.gamepad.fake_sdl import FakeBackend


@pytest.fixture
def sdl() -> Iterator[FakeBackend]:
    """A fake SDL with no pad plugged in; the pump starts afresh on it and stops after the test."""
    backend = FakeBackend()
    gamepad_driver.stop_pump()
    saved = gamepad_driver.backend_factory
    gamepad_driver.backend_factory = lambda: backend
    yield backend
    gamepad_driver.stop_pump()
    gamepad_driver.backend_factory = saved
