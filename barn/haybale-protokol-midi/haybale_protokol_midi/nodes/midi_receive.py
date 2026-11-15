"""MIDI Receive — runs its flow for each MIDI message on its gates that passes its filter."""

from __future__ import annotations

import logging
from functools import partial
from typing import Any

from haywire.api import (
    EXEC,
    INT,
    STRING,
    BaseNode,
    ExecutionContext,
    NodeType,
    SelectWidget,
    bag,
    node,
)

from haybale_protokol.dispatch import ReceiveDispatchSettings, event_source_for, resolve_dispatch
from haybale_protokol.drivers import Message
from haybale_protokol.gate_names import gate_names, named_status
from haybale_protokol.receive import ReceiveBinding, get_protokol_state
from haybale_protokol.widgets.gate_select_widget import GateSelectWidget
from haybale_protokol_midi.midi_messages import CHANNEL_KINDS, KINDS, STREAM_KINDS
from haybale_protokol_midi.midi_pins import ARG_NAMES, KIND_PINS, NUMBER_PIN, number_filter

logger = logging.getLogger(__name__)

#: Display order of every outlet the filter can bring.
_OUTLET_ORDER = (
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
    "status",
)
_REBUILT = r"^(channel|note|controller|velocity|on|value|program|data|event|position|bytes|status)$"

GATE_HELP = (
    "One or more MIDI input gates from the project's Gate file; pick them from the list or type a "
    "name. A MIDI gate names a Device, which the Device editor maps to a port on this machine. "
    "Messages from every gate run the same flow; From gate says which one. A gate whose device is "
    "unplugged or unknown is reported in status; the others still work. Applies on the next start."
)
KIND_HELP = (
    "What to listen for. note: note on and off (on is False for note off and velocity 0); cc: a "
    "controller; pitchbend: −8192…8191; aftertouch: channel pressure; program: program change; "
    "sysex: the data without F0/F7; transport: clock, start, continue, stop and song position; raw: "
    "every message as bytes, including polyphonic aftertouch. The outlets change with the kind."
)
CHANNEL_HELP = (
    "The MIDI channel, 1–16, or 0 for any; with any, a channel outlet says which. "
    "Not used by sysex, transport and raw."
)
NUMBER_HELP = (
    "For note and cc: the note or controller number, 0–127, or −1 for any; with any, an outlet says which."
)


@node(
    label="MIDI Receive",
    description="Triggered for each MIDI message on its gates that passes its kind, channel and number",
    menu="protokol/midi",
    search_tags=["midi", "receive", "note", "cc", "controller", "protokol"],
    node_type=NodeType.EVENT,
)
class MidiReceiveNode(BaseNode):
    """Runs its flow for each MIDI message of its kind (and channel and number) on its gates.

    Kind, Channel and Number are the node's filter, and its outlets follow it. Values (cc, pitch
    bend, aftertouch) fire their last value when the graph starts and keep only the newest message
    when the flow runs behind; events (notes, programs, transport) queue every message.

    Outputs:
        received: Control flow for each message that passes the filter
        from_gate: The gate the message came in on
        channel / note / controller: What the filter leaves open
        velocity, on, value, program, data, event, position, bytes: The message, by kind
        status: Each gate's state
    """

    dispatch = bag(ReceiveDispatchSettings)

    def init(self) -> None:
        self.add(
            STRING.as_config(
                "gate",
                default="",
                label="Gate",
                description=GATE_HELP,
                widget=GateSelectWidget.config(properties={"protocol": "midi", "direction": "in"}),
            )
        )
        self.add(
            STRING.as_config(
                "kind",
                default="cc",
                label="Kind",
                description=KIND_HELP,
                widget=SelectWidget.config(properties={"options": list(KINDS)}),
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
        self.add(EXEC.as_outlet("received", label="Received"))
        self.add(
            STRING.as_outlet("from_gate", label="From gate", description="The gate the message came in on")
        )
        self._add_filter_outlets("cc", 1, -1)

    def post_init(self) -> None:
        self._bindings: list[ReceiveBinding] = []
        self._subscribe()

    def on_assembly(self) -> tuple[bool, str | None]:
        self._subscribe()
        return True, None

    # -- ports -------------------------------------------------------------------

    def hb_rebuild(self, *_args: Any) -> None:
        """Rebuild the outlets after the kind, channel or number changed."""
        kind, channel, number = self._filter()
        with self.rejig(include=_REBUILT):
            self._add_filter_outlets(kind, channel, number)
        self._subscribe()

    def _add_filter_outlets(self, kind: str, channel: int, number: int) -> None:
        import haywire.api as builtin

        from haybale_core.types.specs import BYTES

        if kind in CHANNEL_KINDS and channel == 0:
            self.add(builtin.INT.as_outlet("channel", label="Channel"))
        if kind in NUMBER_PIN and number < 0:
            outlet = NUMBER_PIN[kind]
            self.add(builtin.INT.as_outlet(outlet, label=outlet.capitalize()))
        for port_id, type_name in KIND_PINS.get(kind, ()):
            type_cls = BYTES if type_name == "BYTES" else getattr(builtin, type_name)
            self.add(type_cls.as_outlet(port_id, label=port_id.capitalize()))
        self.add(STRING.as_outlet("status", label="Status", default=""))
        self._order_rebuilt()

    def _order_rebuilt(self) -> None:
        """Order the rebuilt outlets after the fixed ones: a re-added port keeps its old place."""
        rebuilt = [port_id for port_id in _OUTLET_ORDER if port_id in self.ports]
        fixed = [port.order for port_id, port in self.ports.items() if port_id not in rebuilt]
        base = max(fixed, default=0) + 1
        for offset, port_id in enumerate(rebuilt):
            self.ports[port_id].order = base + offset
        wrapper = getattr(self, "wrapper", None)
        if wrapper is not None:
            wrapper.mark_layout_changed()

    # -- running -----------------------------------------------------------------

    def on_startup(self, context: ExecutionContext) -> None:
        queue_mode, _size, start_value = resolve_dispatch(
            self.dispatch, stream=self._is_stream(), single_source=self._single_source()
        )
        node_id = self.node_id

        def fire(payload: dict[str, Any]) -> None:
            context.emit_callback(event_name=node_id, payload=payload)

        state = get_protokol_state()
        self._bindings = [
            ReceiveBinding(
                state,
                name,
                partial(self._accept, gate=name),
                fire,
                start_value=start_value,
                block=queue_mode.name == "BLOCK",
            )
            for name in gate_names(str(self.value("gate") or ""))
        ]
        self.post_value("status", self._status())

    def on_shutdown(self, context: ExecutionContext) -> None:
        for binding in self._bindings:
            binding.close()
        self._bindings = []

    def worker(self, context: ExecutionContext) -> str | None:
        payload = context.trigger.payload if context.trigger else None
        if not isinstance(payload, dict):
            return None
        self.out("from_gate", payload["gate"])
        for port_id, value in payload["values"].items():
            if port_id in self.ports:
                self.out(port_id, value)
        if "channel" in self.ports and payload["channel"] is not None:
            self.out("channel", payload["channel"])
        self.out("status", self._status())
        return "received"

    def _accept(self, message: Message, gate: str) -> dict[str, Any] | None:
        kind, channel, number = self._filter()
        if message.extra.get("kind") != kind:
            return None
        if kind in CHANNEL_KINDS and channel != 0 and message.extra.get("channel") != channel:
            return None
        if kind in NUMBER_PIN and number >= 0 and message.extra.get("number") != number:
            return None
        values = dict(zip(ARG_NAMES[kind], message.args, strict=False))
        return {"gate": gate, "values": values, "channel": message.extra.get("channel")}

    def _status(self) -> str:
        parts = [named_status(binding.gate_name, binding.status) for binding in self._bindings]
        return " · ".join(parts) or "no gate set"

    # -- helpers -----------------------------------------------------------------

    def _filter(self) -> tuple[str, int, int]:
        kind = str(self.value("kind") or "cc")
        return (
            kind if kind in KINDS else "cc",
            int(self.value("filter_channel") or 0),
            number_filter(self.value("filter_number")),
        )

    def _single_source(self) -> bool:
        """One channel, one number (where the kind has them) and one gate."""
        kind, channel, number = self._filter()
        if kind in CHANNEL_KINDS and channel == 0:
            return False
        if kind in NUMBER_PIN and number < 0:
            return False
        return len(gate_names(str(self.value("gate") or ""))) <= 1

    def _is_stream(self) -> bool:
        return self._filter()[0] in STREAM_KINDS

    def _subscribe(self) -> None:
        queue_mode, size, _start = resolve_dispatch(
            self.dispatch, stream=self._is_stream(), single_source=self._single_source()
        )
        self.event_subscription = event_source_for(self.node_id, queue_mode, size)
