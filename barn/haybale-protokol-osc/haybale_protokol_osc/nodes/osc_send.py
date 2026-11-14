"""OSC Send — sends one OSC message to an output gate each time it runs."""

from __future__ import annotations

import time
from typing import Any

from haywire.core.execution.execution_context import ExecutionContext
from haywire.barn.builtin.types import BOOL
from haywire.core.node import BaseNode, NodeType, node
from haywire.core.settings import NodeSettings, Promotable, bag, setting
from haywire.core.types import PortOrigin

from haybale_protokol.drivers import Message
from haybale_protokol.receive import get_protokol_state
from haybale_protokol.states.protokol_state import LineUse
from haybale_protokol_osc.arg_pins import ARG_ID, ArgPins
from haybale_protokol_osc.shape import ShapeError, encode


GATE_HELP = (
    "The name of an output (or two-way) gate in the project's Gate file, .haywire/protokol.toml; "
    "make gates in the Gates editor. The node opens the gate's Line when the graph starts and gives "
    "it back when it stops. While the gate is missing, belongs to another protocol or cannot reach "
    "its peer, sends are dropped and counted in the status outlet, never queued. A change applies "
    "on the next start."
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


class SendSettings(NodeSettings):
    """When a control tick sends."""

    only_changes = setting[BOOL](
        False,
        label="Only send changes",
        category="Sending",
        description=(
            "Off: every control tick sends the message. On: a tick sends only when the address, "
            "type tags or values differ from the last message sent; the first tick of a run always "
            "sends, and a dropped send is retried on the next tick. Skipped ticks are counted as "
            "'unchanged' in status."
        ),
        promotable=Promotable.CONFIG,
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
        from haywire.barn.builtin.types import ADD, EXEC, STRING
        from haywire.barn.builtin.widgets import TextWidget

        commit = TextWidget.config(properties={"commit": True})
        self.add(STRING.as_config("gate", default="", label="Gate", description=GATE_HELP, widget=commit))
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
        self._use: LineUse | None = None
        self._sent = 0
        self._dropped = 0
        self._unchanged = 0
        self._last_sent: tuple[Any, ...] | None = None
        self._problem = ""

    # -- ports -------------------------------------------------------------------

    def hb_rebuild(self, port: Any = None, *_args: Any) -> None:
        """Rebuild the argument inlets from the Arg shape; an invalid shape is put back."""
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
        self._sent = self._dropped = self._unchanged = 0
        self._last_sent = None
        self._problem = ""
        result = get_protokol_state().use(str(self.value("gate") or ""), "out")
        self._use = result if isinstance(result, LineUse) else None
        self._problem = "" if self._use is not None else str(result)
        self.post_value("status", self._status())

    def on_shutdown(self, context: ExecutionContext) -> None:
        if self._use is not None:
            self._use.release()
            self._use = None

    def worker(self, context: ExecutionContext) -> str | None:
        mismatch = self._pins_mismatch() if self._use is not None else None
        if mismatch is not None:
            self._dropped += 1
            self._problem = mismatch
        elif self._use is not None:
            try:
                tokens = self._tokens()
                tags, args = encode(tokens, [self.value(port.id) for port in self._arg_ports()])
            except ShapeError as exc:
                self._dropped += 1
                self._problem = str(exc)
            else:
                address = str(self.value("address") or "/")
                sent_as = (address, tags, args)
                if self.sending.only_changes and sent_as == self._last_sent:
                    self._unchanged += 1
                elif self._use.line.send(Message(address, args, time.time(), {"types": tags})):
                    self._last_sent = sent_as
                    self._sent += 1
                    self._problem = ""
                    self.out("shape", tags)
                else:
                    self._dropped += 1
                    self._problem = self._use.line.status
        self.out("status", self._status())
        return "next"

    def _status(self) -> str:
        if self._use is None:
            return self._problem
        parts = [f"sent {self._sent}"]
        if self._unchanged:
            parts.append(f"unchanged {self._unchanged}")
        parts.append(f"dropped {self._dropped}")
        if self._problem:
            parts.append(self._problem)
        return " · ".join(parts)
