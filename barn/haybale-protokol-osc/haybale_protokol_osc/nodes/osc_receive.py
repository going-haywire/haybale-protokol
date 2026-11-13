"""OSC Receive — runs its flow for each OSC message on an input gate that matches its address."""

from __future__ import annotations

import logging
import threading
from typing import Any

from haywire.core.execution.execution_context import ExecutionContext
from haywire.core.node import BaseNode, NodeType, node
from haywire.core.settings import bag
from haywire.core.types import PortOrigin

from haybale_protokol.dispatch import ReceiveDispatchSettings, event_source_for, resolve_dispatch
from haybale_protokol.drivers import Message
from haybale_protokol.receive import ReceiveBinding, get_protokol_state
from haybale_protokol_osc.pattern import AddressPattern, compile_pattern
from haybale_protokol_osc.shape import ShapeError, Token, decode, parse_shape

logger = logging.getLogger(__name__)

#: Ports this node rebuilds from its address and Arg shape, re-added in this order.
_REBUILT = r"^(args|arg_\d+|match_\d+|timetag|status)$"


@node(
    label="OSC Receive",
    description="Triggered for each OSC message on an input gate that matches the address pattern",
    menu="protokol/osc",
    search_tags=["osc", "receive", "control", "network", "protokol", "touchosc"],
    node_type=NodeType.EVENT,
)
class OscReceiveNode(BaseNode):
    """Runs its flow for each OSC message on its gate that matches its address.

    `Gate` names an input gate in the project's Gate file (`.haywire/protokol.toml`). `Address`
    is an OSC address pattern (`*`, `?`, `[0-9]`, `{a,b}`); empty takes every message. Each
    wildcard gets a capture outlet, `match_1`, `match_2`..., which takes the type of what it is
    connected to. `Arg Shape` lists the arguments (`f i vf3 s`, `_` to skip one): empty gives
    one `args` list, otherwise one outlet per token. A message that does not fit the shape is
    skipped and counted in `status`.

    The outlets keep the latest values, so other flows can read them.

    Outputs:
        received: Control flow for each matching message
        address: The address that matched
        args / arg_N: The arguments
        match_N: What each wildcard matched
        timetag: The OSC bundle's timetag, 0 for a message outside a bundle
        status: The gate's state and how many messages were skipped
    """

    dispatch = bag(ReceiveDispatchSettings)

    def init(self) -> None:
        from haywire.barn.builtin.types import EXEC, STRING
        from haywire.barn.builtin.widgets import TextWidget

        commit = TextWidget.config(properties={"commit": True})
        self.add(STRING.as_config("gate", default="", label="Gate", widget=commit))
        self.add(
            STRING.as_config("address", default="", label="Address", widget=commit, on_change="hb_rebuild")
        )
        self.add(
            STRING.as_config(
                "arg_shape", default="", label="Arg Shape", widget=commit, on_change="hb_rebuild"
            )
        )
        self.add(EXEC.as_outlet("received", label="Received"))
        self.add(STRING.as_outlet("address_out", label="Address"))
        self._add_rebuilt_ports(compile_pattern(""), [], {})

    def post_init(self) -> None:
        self._lock = threading.Lock()
        self._binding: ReceiveBinding | None = None
        self._skipped = 0
        self._pattern = compile_pattern("")
        self._tokens: list[Token] | None = None
        self._read_config()
        self._subscribe()

    def on_assembly(self) -> tuple[bool, str | None]:
        self._subscribe()
        return True, None

    # -- ports -------------------------------------------------------------------

    def hb_rebuild(self, *_args: Any) -> None:
        """Rebuild the argument and capture outlets after the address or Arg shape changed."""
        try:
            pattern = compile_pattern(str(self.value("address") or ""))
            tokens = parse_shape(str(self.value("arg_shape") or ""), receive=True)
        except (ValueError, ShapeError) as exc:
            self.post_value("status", f"not applied: {exc}")
            return
        kept = {
            port_id: port.type_cls
            for port_id, port in self.ports.items()
            if port_id.startswith("match_") and port.origin is PortOrigin.RESOLVED
        }
        with self.rejig(include=_REBUILT):
            self._add_rebuilt_ports(pattern, tokens, kept)
        if hasattr(self, "_lock"):
            self._read_config()

    def hb_resolve_capture(self, port: Any, edge_wrapper: Any) -> None:
        """Give a bare capture outlet the type of the inlet it was connected to."""
        from haywire.barn.builtin.types import ADD

        if port.type_cls is None or not issubclass(port.type_cls, ADD):
            return
        inlet = edge_wrapper._inlet_port
        if inlet is None:
            return
        with self.rejig(include=[port.id]):
            self.add(self._capture_spec(port.id, inlet.stored_type, PortOrigin.RESOLVED))

    def release_pins(self, port_ids: list[str]) -> list[str]:
        """A capture outlet whose last edge was deleted turns back into a bare `ADD`."""
        from haywire.barn.builtin.types import ADD

        released: list[str] = []
        for port_id in port_ids:
            port = self.ports.get(port_id)
            if port is None or not port_id.startswith("match_") or port.is_linked():
                continue
            self._restored_types = getattr(self, "_restored_types", {})
            self._restored_types[port_id] = port.type_cls
            with self.rejig(include=[port_id]):
                self.add(self._capture_spec(port_id, ADD, PortOrigin.DECLARED))
            released.append(port_id)
        return released

    def restore_pins(self, port_ids: list[str]) -> None:
        restored = getattr(self, "_restored_types", {})
        for port_id in port_ids:
            type_cls = restored.pop(port_id, None)
            if type_cls is not None and port_id in self.ports:
                with self.rejig(include=[port_id]):
                    self.add(self._capture_spec(port_id, type_cls, PortOrigin.RESOLVED))

    def _add_rebuilt_ports(self, pattern: AddressPattern, tokens: list[Token], kept: dict[str, Any]) -> None:
        from haywire.barn.builtin.types import ADD, FLOAT, STRING
        from haywire.barn.builtin import types as builtin

        from haybale_core.types.specs import BYTES, LIST

        named = [token for token in tokens if token.haywire_type is not None]
        if not named:
            self.add(LIST.as_outlet("args", label="Args", description="Every argument of the message"))
        for index, token in enumerate(named, start=1):
            type_cls = BYTES if token.haywire_type == "BYTES" else getattr(builtin, str(token.haywire_type))
            self.add(type_cls.as_outlet(f"arg_{index}", label=f"{index}: {token.text}"))
        for index in range(1, pattern.captures + 1):
            port_id = f"match_{index}"
            type_cls = kept.get(port_id)
            origin = PortOrigin.DECLARED if type_cls is None else PortOrigin.RESOLVED
            self.add(self._capture_spec(port_id, type_cls or ADD, origin))
        self.add(FLOAT.as_outlet("timetag", label="Timetag", default=0.0))
        self.add(STRING.as_outlet("status", label="Status", default=""))

    def _capture_spec(self, port_id: str, type_cls: Any, origin: PortOrigin) -> Any:
        index = port_id.removeprefix("match_")
        return type_cls.as_outlet(
            port_id, label=f"Match {index}", on_connect="hb_resolve_capture", origin=origin
        )

    # -- running -----------------------------------------------------------------

    def on_startup(self, context: ExecutionContext) -> None:
        self._read_config()
        self._skipped = 0
        queue_mode, _size, start_value = resolve_dispatch(self.dispatch, stream=True)
        node_id = self.node_id

        def fire(payload: dict[str, Any]) -> None:
            context.emit_callback(event_name=node_id, payload=payload)

        self._binding = ReceiveBinding(
            get_protokol_state(),
            str(self.value("gate") or ""),
            self._accept,
            fire,
            start_value=start_value,
            block=queue_mode.name == "BLOCK",
        )
        self.post_value("status", self._binding.status)

    def on_shutdown(self, context: ExecutionContext) -> None:
        if self._binding is not None:
            self._binding.close()
            self._binding = None

    def worker(self, context: ExecutionContext) -> str | None:
        payload = context.trigger.payload if context.trigger else None
        if not isinstance(payload, dict):
            return None
        self.out("address_out", payload["address"])
        values = payload["values"]
        if "args" in self.ports:
            self.out("args", list(values))
        else:
            for index, value in enumerate(values, start=1):
                if f"arg_{index}" in self.ports:
                    self.out(f"arg_{index}", value)
        problems = self._write_captures(payload["captures"])
        self.out("timetag", float(payload["timetag"] or 0.0))
        self.out("status", self._status(problems))
        return "received"

    def _accept(self, message: Message) -> dict[str, Any] | None:
        with self._lock:
            pattern, tokens = self._pattern, self._tokens
        captures = pattern.match(message.address)
        if captures is None:
            return None
        values: list[Any] | None = list(message.args) if tokens is None else decode(tokens, message.args)
        if values is None:
            self._skipped += 1
            return None
        return {
            "address": message.address,
            "values": values,
            "captures": captures,
            "timetag": message.extra.get("timetag"),
        }

    def _write_captures(self, captures: tuple[str, ...]) -> list[str]:
        problems: list[str] = []
        for index, text in enumerate(captures, start=1):
            port = self.ports.get(f"match_{index}")
            if port is None or port.origin is not PortOrigin.RESOLVED:
                continue
            type_name = getattr(port.type_cls, "__name__", "")
            try:
                self.out(port.id, convert_capture(text, type_name))
            except ValueError:
                problems.append(f"{port.id}: '{text}' is not {type_name}")
        return problems

    def _status(self, problems: list[str]) -> str:
        base = self._binding.status if self._binding is not None else ""
        parts = [base] if base else []
        if self._skipped:
            parts.append(f"{self._skipped} skipped")
        parts.extend(problems)
        return " · ".join(parts)

    # -- helpers -----------------------------------------------------------------

    def _read_config(self) -> None:
        try:
            pattern = compile_pattern(str(self.value("address") or ""))
            tokens = parse_shape(str(self.value("arg_shape") or ""), receive=True)
        except (ValueError, ShapeError):
            return
        with self._lock:
            self._pattern = pattern
            self._tokens = tokens if any(t.haywire_type for t in tokens) else None

    def _subscribe(self) -> None:
        queue_mode, size, _start = resolve_dispatch(self.dispatch, stream=True)
        self.event_subscription = event_source_for(self.node_id, queue_mode, size)


def convert_capture(text: str, type_name: str) -> Any:
    """Convert a captured address part to the capture outlet's type.

    Raises:
        ValueError: ``text`` does not convert, or the type takes no text.
    """
    if type_name == "STRING":
        return text
    try:
        if type_name == "INT":
            return int(text)
        if type_name == "FLOAT":
            return float(text)
    except ValueError:
        raise ValueError(f"{text!r} is not {type_name}") from None
    if type_name == "BOOL":
        lowered = text.lower()
        if lowered in ("1", "true", "on", "yes"):
            return True
        if lowered in ("0", "false", "off", "no"):
            return False
    raise ValueError(f"{text!r} is not {type_name}")
