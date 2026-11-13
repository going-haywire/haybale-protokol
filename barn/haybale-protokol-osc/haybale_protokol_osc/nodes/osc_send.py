"""OSC Send — sends one OSC message to an output gate each time it runs."""

from __future__ import annotations

import re
import time
from typing import Any

from haywire.core.execution.execution_context import ExecutionContext
from haywire.core.node import BaseNode, NodeType, node
from haywire.core.types import PortOrigin

from haybale_protokol.drivers import Message
from haybale_protokol.receive import get_protokol_state
from haybale_protokol.states.protokol_state import LineUse
from haybale_protokol_osc.shape import ShapeError, encode, parse_shape, token_for_type

_ARG = re.compile(r"arg_(\d+)")


@node(
    label="OSC Send",
    description="Sends one OSC message to an output gate each time it runs",
    menu="protokol/osc",
    search_tags=["osc", "send", "control", "network", "protokol", "touchosc"],
    node_type=NodeType.CONTROL,
)
class OscSendNode(BaseNode):
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

    def init(self) -> None:
        from haywire.barn.builtin.types import ADD, EXEC, STRING
        from haywire.barn.builtin.widgets import TextWidget

        commit = TextWidget.config(properties={"commit": True})
        self.add(STRING.as_config("gate", default="", label="Gate", widget=commit))
        self.add(
            STRING.as_config(
                "arg_shape", default="", label="Arg Shape", widget=commit, on_change="hb_rebuild"
            )
        )
        self.add(EXEC.as_inlet("exec", label="Send"))
        self.add(STRING.as_inlet("address", label="Address", default="/"))
        self.add(self._arg_spec(1, ADD, PortOrigin.DECLARED))
        self.add(EXEC.as_outlet("next", label="Next"))
        self.add(STRING.as_outlet("shape", label="Shape", default=""))
        self.add(STRING.as_outlet("status", label="Status", default=""))

    def post_init(self) -> None:
        self._use: LineUse | None = None
        self._sent = 0
        self._dropped = 0
        self._problem = ""

    # -- ports -------------------------------------------------------------------

    def hb_rebuild(self, *_args: Any) -> None:
        """Rebuild the argument inlets from the Arg shape; an invalid shape changes nothing."""
        from haywire.barn.builtin import types as builtin
        from haywire.barn.builtin.types import ADD

        from haybale_core.types.specs import BYTES

        try:
            tokens = parse_shape(str(self.value("arg_shape") or ""), receive=False)
        except ShapeError as exc:
            self.post_value("status", f"not applied: {exc}")
            return
        with self.rejig(include=_ARG.pattern):
            for index, token in enumerate(tokens, start=1):
                name = str(token.haywire_type)
                type_cls = BYTES if name == "BYTES" else getattr(builtin, name)
                self.add(self._arg_spec(index, type_cls, PortOrigin.RESOLVED, token.text))
            self.add(self._arg_spec(len(tokens) + 1, ADD, PortOrigin.DECLARED))

    def hb_resolve(self, port: Any, edge_wrapper: Any) -> None:
        """An edge on the empty slot adds an argument of the edge's type to the Arg shape."""
        from haywire.barn.builtin.types import ADD

        if port.type_cls is None or not issubclass(port.type_cls, ADD):
            return
        outlet = edge_wrapper._outlet_port
        if outlet is None:
            return
        token = token_for_type(getattr(outlet.stored_type, "__name__", ""))
        if token is None:
            self.post_value("status", f"OSC cannot carry {outlet.stored_type.__name__}")
            return
        shape = str(self.value("arg_shape") or "").split()
        self.ports["arg_shape"].set_value(" ".join([*shape, token]))

    def _arg_spec(self, index: int, type_cls: Any, origin: PortOrigin, token: str = "") -> Any:
        label = f"{index}: {token}" if token else "+"
        return type_cls.as_inlet(f"arg_{index}", label=label, on_connect="hb_resolve", origin=origin)

    def _arg_ports(self) -> list[Any]:
        from haywire.barn.builtin.types import ADD

        ports = [
            port
            for port_id, port in self.ports.items()
            if _ARG.fullmatch(port_id) and not issubclass(port.type_cls, ADD)
        ]
        return sorted(ports, key=lambda port: port.order)

    # -- running -----------------------------------------------------------------

    def on_startup(self, context: ExecutionContext) -> None:
        self._sent = self._dropped = 0
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
        if self._use is not None:
            try:
                tokens = parse_shape(str(self.value("arg_shape") or ""), receive=False)
                tags, args = encode(tokens, [self.value(port.id) for port in self._arg_ports()])
            except ShapeError as exc:
                self._dropped += 1
                self._problem = str(exc)
            else:
                address = str(self.value("address") or "/")
                if self._use.line.send(Message(address, args, time.time(), {"types": tags})):
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
        parts = [f"sent {self._sent}", f"dropped {self._dropped}"]
        if self._problem:
            parts.append(self._problem)
        return " · ".join(parts)
