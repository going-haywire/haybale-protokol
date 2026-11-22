"""One line on whether a gate can be used and how its Line is doing, for the editors."""

from __future__ import annotations

from haybale_protokol.gates import Gate
from haybale_protokol.states.protokol_state import ProtokolState


def gate_status(state: ProtokolState, gate: Gate) -> str:
    """The reason of ``gate``'s health (``ProtokolState.health``)."""
    return state.health(gate).reason
