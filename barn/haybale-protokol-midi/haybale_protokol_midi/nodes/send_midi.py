"""Send MIDI — sends one MIDI message to its gates each time it runs."""

from __future__ import annotations

import time
from typing import Any

from haywire.api import (
    EXEC,
    INT,
    STRING,
    BaseNode,
    ExecutionContext,
    NodeType,
    MenuWidget,
    bag,
    node,
)

from haybale_protokol.gate_names import gate_names
from haybale_protokol.gate_sender import GateSender
from haybale_protokol.receive import get_protokol_state
from haybale_protokol.sending import SendSettings
from haybale_protokol.widgets.gate_menu_widget import GateMenuWidget
from haybale_protokol_midi.midi_messages import CHANNEL_KINDS, KINDS, decode, encode
from haybale_protokol_midi.midi_pins import KIND_PINS, NUMBER_PIN, number_filter

#: Display order of every inlet the filter can bring.
_INLET_ORDER = (
    "channel",
    "note",
    "controller",
    "velocity",
    "on",
    "value",
    "program",
    "data",
    "event",
    "position",
    "bytes",
)
_REBUILT = r"^(channel|note|controller|velocity|on|value|program|data|event|position|bytes)$"

GATE_HELP = (
    "One or more MIDI output gates from the project's Gate file; pick them from the list or type a "
    "name. A MIDI gate names a Device, which the Device editor maps to a port on this machine. Each "
    "message goes to every listed gate; a gate whose device is unplugged or unknown is reported in "
    "status and the others still get it. A message no gate could take counts as dropped, never "
    "queued. Applies on the next start."
)
KIND_HELP = (
    "What to send. note: note on or off (the on inlet); cc: a controller; pitchbend: −8192…8191; "
    "aftertouch: channel pressure; program: program change; sysex: the data without F0/F7; "
    "transport: clock, start, continue, stop or songpos (with position); raw: bytes as they are. "
    "The inlets change with the kind."
)
CHANNEL_HELP = (
    "The MIDI channel, 1–16, or 0 to take it from a channel inlet. Not used by sysex, transport and raw."
)
NUMBER_HELP = "For note and cc: the note or controller number, 0–127, or −1 to take it from an inlet."


@node(
    label="Send MIDI",
    description="Sends one MIDI message to its gates each time it runs",
    menu="protokol/midi",
    search_tags=["midi", "send", "note", "cc", "controller", "protokol"],
    node_type=NodeType.CONTROL,
)
class SendMidiNode(BaseNode):
    """Sends one message of its kind to every listed gate on each control tick.

    Kind, Channel and Number say what to send; the inlets follow them, and a channel or number left
    open comes from its own inlet. A value out of range drops the message and status names it.
    With Only send changes, a tick sends to a gate only when the message differs from the last one
    that gate took.

    Outputs:
        next: Control flow after sending
        status: What was sent, skipped and dropped, and which gates cannot be used
    """

    sending = bag(SendSettings)

    def init(self) -> None:
        self.add(
            STRING.as_config(
                "gate",
                default="",
                label="Gate",
                description=GATE_HELP,
                widget=GateMenuWidget.config(properties={"protocol": "midi", "direction": "out"}),
            )
        )
        self.add(
            STRING.as_config(
                "kind",
                default="cc",
                label="Kind",
                description=KIND_HELP,
                widget=MenuWidget.config(properties={"options": list(KINDS)}),
                on_change="hb_rebuild",
            )
        )
        self.add(
            INT.as_config(
                "filter_channel",
                default=1,
                label="Channel",
                description=CHANNEL_HELP,
                on_change="hb_rebuild",
            )
        )
        self.add(
            INT.as_config(
                "filter_number", default=-1, label="Number", description=NUMBER_HELP, on_change="hb_rebuild"
            )
        )
        self.add(EXEC.as_inlet("exec", label="Send"))
        self.add(EXEC.as_outlet("next", label="Next"))
        self.add(STRING.as_outlet("status", label="Status", default=""))
        self._add_inlets("cc", 1, -1)

    def post_init(self) -> None:
        self._sender = GateSender()

    # -- ports -------------------------------------------------------------------

    def hb_rebuild(self, *_args: Any) -> None:
        """Rebuild the inlets after the kind, channel or number changed."""
        kind, channel, number = self._filter()
        with self.rejig(include=_REBUILT):
            self._add_inlets(kind, channel, number)

    def _add_inlets(self, kind: str, channel: int, number: int) -> None:
        import haywire.api as builtin

        from haybale_core.types.specs import BYTES

        if kind in CHANNEL_KINDS and channel == 0:
            self.add(builtin.INT.as_inlet("channel", label="Channel", default=1))
        if kind in NUMBER_PIN and number < 0:
            inlet = NUMBER_PIN[kind]
            self.add(
                builtin.INT.as_inlet(inlet, label=inlet.capitalize(), default=60 if kind == "note" else 1)
            )
        for port_id, type_name in KIND_PINS.get(kind, ()):
            type_cls = BYTES if type_name == "BYTES" else getattr(builtin, type_name)
            default: Any = {"on": True, "velocity": 100, "event": "clock"}.get(port_id)
            kwargs = {"default": default} if default is not None else {}
            self.add(type_cls.as_inlet(port_id, label=port_id.capitalize(), **kwargs))
        rebuilt = [port_id for port_id in _INLET_ORDER if port_id in self.ports]
        fixed = [port.order for port_id, port in self.ports.items() if port_id not in rebuilt]
        base = max(fixed, default=0) + 1
        for offset, port_id in enumerate(rebuilt):
            self.ports[port_id].order = base + offset

    # -- running -----------------------------------------------------------------

    def on_startup(self, context: ExecutionContext) -> None:
        self._sender.open(get_protokol_state(), gate_names(str(self.value("gate") or "")))
        self.post_value("status", self._sender.status())

    def on_shutdown(self, context: ExecutionContext) -> None:
        self._sender.close()

    def worker(self, context: ExecutionContext) -> str | None:
        if self._sender.active:
            self._send()
        self.out("status", self._sender.status())
        return "next"

    def _send(self) -> None:
        kind, channel, number = self._filter()
        values = {port_id: self.value(port_id) for port_id in _INLET_ORDER if port_id in self.ports}
        try:
            data = encode(
                kind,
                int(values.get("channel", channel)) if kind in CHANNEL_KINDS else None,
                number if number >= 0 else None,
                values,
            )
        except (ValueError, TypeError) as exc:
            self._sender.drop(str(exc))
            return
        message = decode(data, time.time())
        if message is not None:
            self._sender.send(message, data, only_changes=self.sending.only_changes)

    def _filter(self) -> tuple[str, int, int]:
        kind = str(self.value("kind") or "cc")
        return (
            kind if kind in KINDS else "cc",
            int(self.value("filter_channel") or 0),
            number_filter(self.value("filter_number")),
        )
