"""GamepadState — registers the gamepad Protocol driver while haybale-protokol-gamepad is enabled."""

from __future__ import annotations

from haywire.api.workbench import AppState, get_library_state_container, state

from haybale_protokol.states.protokol_state import ProtokolState
from haybale_protokol_gamepad.driver import GamepadDriver


@state(label="Protokol Gamepad", description="Registers the gamepad driver with Protokol")
class GamepadState(AppState):
    """Hands ``GamepadDriver`` to ``ProtokolState`` on enable and takes it back on disable."""

    def on_enable(self) -> None:
        protokol = _protokol()
        if protokol is not None:
            protokol.register_driver(GamepadDriver())

    def on_disable(self) -> None:
        protokol = _protokol()
        if protokol is not None:
            protokol.unregister_driver(GamepadDriver.protocol)


def _protokol() -> ProtokolState | None:
    return get_library_state_container().get(ProtokolState)
