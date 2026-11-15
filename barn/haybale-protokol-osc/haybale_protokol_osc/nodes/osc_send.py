"""OSC Send — sends one OSC message to an output gate each time it runs."""

from __future__ import annotations

import time
from typing import Any

from haywire.api import (
    ADD,
    EXEC,
    STRING,
    BaseNode,
    ExecutionContext,
    NodeType,
    PortOrigin,
    TextWidget,
    bag,
    node,
)

from haybale_protokol.drivers import Message
from haybale_protokol.gate_names import gate_names
from haybale_protokol.gate_sender import GateSender
from haybale_protokol.sending import SendSettings
from haybale_protokol.receive import get_protokol_state
from haybale_protokol.widgets.gate_select_widget import GateSelectWidget
from haybale_protokol_osc.arg_pins import ARG_ID, ArgPins
from haybale_protokol_osc.shape import ShapeError, encode


GATE_HELP = (
    "One or more output (or two-way) gates from the project's Gate file, .haywire/protokol.toml; "
    "pick them from the list, which offers this project's OSC gates that can send, or type a name "
    "and press Enter. Make gates in the Gates editor. Each send goes to every listed gate. The node "
    "opens each gate's Line when the graph starts and gives it back when it stops. A gate that is "
    "missing, of another protocol or cannot reach its peer is reported in status and the others "
    "still get the message; a message no gate could take counts as dropped, never queued. A change "
    "applies on the next start."
)
SHAPE_HELP = (
    "The Arg shape: one token per argument inlet, in inlet order. i: int; f: float; s: text; "
    "b: blob; T: bool; r: colour; vi2–vi4 and vf2–vf4: a vector, sent as its components; m3, m4: "
    "a matrix, sent as 9 or 16 floats. Use d or h instead of f or i for 64-bit numbers. There is "
    "no _: every inlet is sent, and an unconnected inlet sends its own value. Typing the shape "
    "rebuilds the inlets; connecting the + pin at the bottom adds a token for the connected type, "
    "deleting the edge that grew a pin removes the pin and its token, and dragging pins into "
    "another order reorders the tokens. An int too large for i is dropped and named in status; "
    "an invalid shape is put back."
)


@node(
    label="OSC Send",
    description="Sends one OSC message to an output gate each time it runs",
    menu="protokol/osc",
    search_tags=["osc", "send", "control", "network", "protokol", "touchosc"],
    node_type=NodeType.CONTROL,
)
class OscSendNode(ArgPins, BaseNode):
    """Sends `Address` with one argument per argument inlet, in inlet order, to its gate.

    `Gate` names an output gate in the project's Gate file. Connect anything to the empty
    inlet at the bottom to add an argument; `Arg Shape` lists the arguments (`f i vf3 s`) and
    follows the inlets. A vector goes out as its components (`vf3` → three `f`); use `d` or `h`
    in the shape for 64-bit numbers. An unconnected inlet sends its own value.

    Outputs:
        next: Control flow after sending
        shape: The OSC type tags sent last
        status: What was sent and dropped, or why nothing can be sent
    """

    sending = bag(SendSettings)

    def init(self) -> None:
        commit = TextWidget.config(properties={"commit": True})
        self.add(
            STRING.as_config(
                "gate",
                default="",
                label="Gate",
                description=GATE_HELP,
                widget=GateSelectWidget.config(properties={"protocol": "osc", "direction": "out"}),
            )
        )
        self.add(
            STRING.as_config(
                "arg_shape",
                default="",
                label="Arg Shape",
                description=SHAPE_HELP,
                widget=commit,
                on_change="hb_rebuild",
            )
        )
        self.add(EXEC.as_inlet("exec", label="Send"))
        self.add(STRING.as_inlet("address", label="Address", default="/"))
        self.add(self._arg_spec("arg_1", ADD, PortOrigin.DECLARED, "+"))
        self.add(EXEC.as_outlet("next", label="Next"))
        self.add(STRING.as_outlet("shape", label="Shape", default=""))
        self.add(STRING.as_outlet("status", label="Status", default=""))

    def post_init(self) -> None:
        self._sender = GateSender()

    # -- ports -------------------------------------------------------------------

    def hb_rebuild(self, port: Any = None, *_args: Any) -> None:
        """Rebuild the argument inlets from the Arg shape; an invalid shape is put back."""
        if self._quiet_write():
            return
        try:
            tokens = self._tokens()
        except ShapeError as exc:
            self._reject_text(port, exc)
            return
        with self.rejig(include=ARG_ID.pattern):
            self._add_arg_ports(tokens)
            self._move_slot_last()
        self._accept_text()

    def _arg_spec(self, port_id: str, type_cls: Any, origin: PortOrigin, label: str) -> Any:
        return type_cls.as_inlet(port_id, label=label, on_connect="hb_grow", origin=origin)

    # -- running -----------------------------------------------------------------

    def on_startup(self, context: ExecutionContext) -> None:
        self._sender.open(get_protokol_state(), gate_names(str(self.value("gate") or "")))
        self.post_value("status", self._sender.status())

    def on_shutdown(self, context: ExecutionContext) -> None:
        self._sender.close()

    def worker(self, context: ExecutionContext) -> str | None:
        if self._sender.active:
            self._send_to_gates()
        self.out("status", self._sender.status())
        return "next"

    def _send_to_gates(self) -> None:
        mismatch = self._pins_mismatch()
        if mismatch is not None:
            self._sender.drop(mismatch)
            return
        try:
            tokens = self._tokens()
            tags, args = encode(tokens, [self.value(port.id) for port in self._arg_ports()])
        except ShapeError as exc:
            self._sender.drop(str(exc))
            return
        address = str(self.value("address") or "/")
        message = Message(address, args, time.time(), {"types": tags})
        if self._sender.send(message, (address, tags, args), only_changes=self.sending.only_changes):
            self.out("shape", tags)
