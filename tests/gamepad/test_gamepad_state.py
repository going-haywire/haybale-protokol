"""haybale-protokol-gamepad registers its driver while enabled."""

from typing import Any

import pytest

pytestmark = pytest.mark.integration


def test_gamepad_state_registers_driver(library_system: Any) -> None:
    from haybale_protokol.states.protokol_state import ProtokolState
    from haybale_protokol_gamepad.driver import GamepadDriver
    from haywire.core.di.context import get_library_state_container

    state = get_library_state_container().get(ProtokolState)
    assert state is not None
    assert isinstance(state.driver("gamepad"), GamepadDriver)
