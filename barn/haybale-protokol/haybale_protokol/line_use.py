"""LineUse — one user's hold on a Line, as ``ProtokolState.use`` hands it out."""

from __future__ import annotations

from dataclasses import dataclass, field

from haybale_protokol.gates import Gate
from haybale_protokol.line import Line


@dataclass(eq=False)
class LineUse:
    """One user's hold on a Line, through a Gate. Give it back with ``release()``."""

    line: Line
    token: int
    gate: Gate
    _released: bool = field(default=False, repr=False)

    def release(self) -> None:
        """Give the Line back; a second call does nothing."""
        if not self._released:
            self._released = True
            self.line.remove_user(self.token)
