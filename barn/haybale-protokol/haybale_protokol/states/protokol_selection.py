"""ProtokolSelection — the gate, Line or Device one session has selected."""

from __future__ import annotations

from haywire.api.workbench import SessionState, signal_field, state

from haybale_protokol.drivers import LineKey


@state(label="Protokol selection", description="The gate, Line or Device this session has selected")
class ProtokolSelection(SessionState):
    """What the Device editor follows. At most one of the three is set."""

    gate: str | None = signal_field(None)
    line: LineKey | None = signal_field(None)
    device: str | None = signal_field(None)

    def select_gate(self, name: str | None) -> None:
        self._set(gate=name)

    def select_line(self, key: LineKey | None) -> None:
        self._set(line=key)

    def select_device(self, name: str | None) -> None:
        self._set(device=name)

    def clear(self) -> None:
        self._set()

    def _set(
        self, *, gate: str | None = None, line: LineKey | None = None, device: str | None = None
    ) -> None:
        # Clear the others first, so a subscriber woken by the new value never sees two set.
        if gate is None:
            self.gate = None
        if line is None:
            self.line = None
        if device is None:
            self.device = None
        if gate is not None:
            self.gate = gate
        if line is not None:
            self.line = line
        if device is not None:
            self.device = device
