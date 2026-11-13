"""OscState — registers the OSC Protocol driver while haybale-protokol-osc is enabled."""

from __future__ import annotations

from haywire.core.state.base import AppState
from haywire.core.state.decorator import state

from haybale_protokol.states.protokol_state import ProtokolState
from haybale_protokol_osc.driver import OscDriver


@state(label="Protokol OSC", description="Registers the OSC driver with Protokol")
class OscState(AppState):
    """Hands ``OscDriver`` to ``ProtokolState`` on enable and takes it back on disable."""

    def on_enable(self) -> None:
        protokol = _protokol()
        if protokol is not None:
            protokol.register_driver(OscDriver())

    def on_disable(self) -> None:
        protokol = _protokol()
        if protokol is not None:
            protokol.unregister_driver(OscDriver.protocol)


def _protokol() -> ProtokolState | None:
    from haywire.core.di.context import get_library_state_container

    return get_library_state_container().get(ProtokolState)
