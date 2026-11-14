"""MidiState — registers the MIDI Protocol driver while haybale-protokol-midi is enabled."""

from __future__ import annotations

from haywire.core.state.base import AppState
from haywire.core.state.decorator import state

from haybale_protokol.states.protokol_state import ProtokolState
from haybale_protokol_midi.driver import MidiDriver


@state(label="Protokol MIDI", description="Registers the MIDI driver with Protokol")
class MidiState(AppState):
    """Hands ``MidiDriver`` to ``ProtokolState`` on enable and takes it back on disable."""

    def on_enable(self) -> None:
        protokol = _protokol()
        if protokol is not None:
            protokol.register_driver(MidiDriver())

    def on_disable(self) -> None:
        protokol = _protokol()
        if protokol is not None:
            protokol.unregister_driver(MidiDriver.protocol)


def _protokol() -> ProtokolState | None:
    from haywire.core.di.context import get_library_state_container

    return get_library_state_container().get(ProtokolState)
