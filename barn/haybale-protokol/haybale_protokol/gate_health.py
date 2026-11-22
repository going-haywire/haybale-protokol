"""Gate health: whether a gate works now, and why not (design §10.2).

``ProtokolState.health`` works it out; every view reads it (editor rows and icon, node badges,
gate chips), so they never disagree.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

HealthState = Literal["working", "closed", "unbound", "not plugged in", "error"]

#: The states in which a gate can be used: its Line is open, or it would open.
HEALTHY: frozenset[str] = frozenset({"working", "closed"})


@dataclass(frozen=True)
class GateHealth:
    """One gate's state and the reason shown to the user.

    - ``working``: its Line is open and has users.
    - ``closed``: it can open; nothing uses it now.
    - ``unbound``: it names a Device this machine's Device list does not have.
    - ``not plugged in``: its Device is mapped, but no port matches the Device's OS name now.
    - ``error``: it cannot be used; ``reason`` says why (protocol not installed, a bad gate entry,
      the last failed open).
    """

    state: HealthState
    reason: str

    @property
    def healthy(self) -> bool:
        return self.state in HEALTHY
