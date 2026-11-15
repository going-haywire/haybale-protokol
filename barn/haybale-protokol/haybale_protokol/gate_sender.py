"""GateSender — a Send node's hold on its gates while its graph runs.

One Line use per listed gate; each message goes to every gate (with Only send changes, only to the
gates whose last message differs). Counts what was sent, skipped and dropped, and names the gates
that cannot be used in its status.
"""

from __future__ import annotations

from collections.abc import Hashable

from haybale_protokol.drivers import Message
from haybale_protokol.gate_names import named_status
from haybale_protokol.line_use import LineUse
from haybale_protokol.states.protokol_state import ProtokolState


class GateSender:
    """Open with ``open``, send with ``send``, give back with ``close``."""

    def __init__(self) -> None:
        self.sent = 0
        self.unchanged = 0
        self.dropped = 0
        self.problem = ""
        """Why the last message could not go out, for status."""
        self._uses: dict[str, LineUse] = {}
        self._gate_problems: dict[str, str] = {}
        self._last: dict[str, Hashable] = {}
        self._listed = False

    @property
    def active(self) -> bool:
        """Whether at least one gate is in use."""
        return bool(self._uses)

    def open(self, state: ProtokolState, names: list[str]) -> None:
        """Take each gate's Line; a gate that cannot be used is kept for status."""
        self.close()
        self.sent = self.unchanged = self.dropped = 0
        self.problem = ""
        self._gate_problems = {}
        self._last = {}
        self._listed = bool(names)
        for name in names:
            result = state.use(name, "out")
            if isinstance(result, LineUse):
                self._uses[name] = result
            else:
                self._gate_problems[name] = named_status(name, str(result))

    def close(self) -> None:
        for use in self._uses.values():
            use.release()
        self._uses = {}

    def send(self, message: Message, key: Hashable, *, only_changes: bool) -> bool | None:
        """Send ``message`` (identified by ``key``) to the gates; ``None`` when no gate needed it.

        Returns ``True`` when at least one gate took it, ``False`` when every gate it went to dropped it.
        """
        targets = [name for name in self._uses if not only_changes or self._last.get(name) != key]
        if not targets:
            self.unchanged += 1
            return None
        failed = []
        for name in targets:
            if self._uses[name].line.send(message):
                self._last[name] = key
            else:
                failed.append(name)
        self.problem = " · ".join(f"{name}: {self._uses[name].line.status}" for name in failed)
        if len(failed) == len(targets):
            self.dropped += 1
            return False
        self.sent += 1
        return True

    def drop(self, problem: str) -> None:
        """Count a message that could not even be built, and say why."""
        self.dropped += 1
        self.problem = problem

    def status(self) -> str:
        notes = list(self._gate_problems.values())
        if self.problem:
            notes.append(self.problem)
        if not self._listed:
            return "no gate set"
        if not self._uses:
            return " · ".join(notes)
        parts = [f"sent {self.sent}"]
        if self.unchanged:
            parts.append(f"unchanged {self.unchanged}")
        parts.append(f"dropped {self.dropped}")
        return " · ".join(parts + notes)
