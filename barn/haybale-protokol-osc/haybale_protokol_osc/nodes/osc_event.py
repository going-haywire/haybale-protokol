"""OSC Event — runs its flow for each OSC message on an input gate that matches its address."""

from __future__ import annotations

import logging
import threading
import time
from functools import partial
from typing import Any

from haywire.api import (
    ADD,
    EXEC,
    FLOAT,
    STRING,
    BaseNode,
    ExecutionContext,
    NodeType,
    PortOrigin,
    StoreStrategy,
    TextWidget,
    bag,
    node,
)

from haybale_protokol.dispatch import ReceiveDispatchSettings, event_source_for, resolve_dispatch
from haybale_protokol.drivers import Message
from haybale_protokol.gate_names import gate_names, named_status
from haybale_protokol.gate_warning import GateBadge
from haybale_protokol.widgets.gate_menu_widget import GateMenuWidget
from haybale_protokol.receive import ReceiveBinding, get_protokol_state
from haybale_protokol_osc.arg_pins import ARG_ID, ArgPins
from haybale_protokol_osc.pattern import AddressPattern, compile_pattern
from haybale_protokol_osc.shape import ShapeError, Token, decode

logger = logging.getLogger(__name__)

GATE_HELP = (
    "One or more input (or two-way) gates from the project's Gate file, .haywire/protokol.toml; "
    "pick them from the list, which offers this project's OSC gates that can receive, or type a "
    "name and press Enter. Make gates in the Gates editor. The node opens each gate's Line when "
    "the graph starts and gives it back when it stops; messages from every gate run the same flow, "
    "and the From gate outlet says which one a message came in on. A gate that is missing, of "
    "another protocol or whose port is busy is reported in status; the others still work. A "
    "change applies on the next start."
)
ADDRESS_HELP = (
    "The OSC address pattern to listen to; empty takes every message on the gate. Wildcards: "
    "* (any text within one /part), ? (one character), [0-9] or [!a] (one character from a set), "
    "{left,right} (one of the words). Each wildcard adds a capture outlet, match_1, match_2 … from "
    "left to right. A capture starts as an empty + pin and takes the type of the inlet you connect "
    "it to (text, int, float or bool); a part that does not convert is reported in status. "
    "Changing the pattern rebuilds the match_ outlets; an invalid pattern is put back."
)
SHAPE_HELP = (
    "The Arg shape: the arguments the node expects, as tokens separated by spaces. i or h: int; "
    "f or d: float; s: text; b: blob; T: bool; r: colour; vi2–vi4 and vf2–vf4: 2 to 4 ints or "
    "floats as one vector; m3, m4: 9 or 16 floats as a matrix; _ skips one argument, _3 skips "
    "three. The args outlet always carries every argument as a list; each token adds its own "
    "outlet, in order. "
    "The shape and the pins follow each other: connecting the + pin at the bottom adds a token for "
    "the connected type, deleting the edge that grew a pin removes the pin and its token, and "
    "dragging pins into another order reorders the tokens. A message that does not fit is skipped "
    "and counted in status; extra arguments are ignored. An invalid shape is put back."
)

#: Shortest time between two status updates for skipped messages.
SKIP_STATUS_INTERVAL_S = 0.5

#: Ports this node rebuilds from its address and Arg shape, re-added in this order.
_REBUILT = r"^(args|arg_\d+|match_\d+|timetag|status)$"


@node(
    label="OSC Event",
    description="Triggered for each OSC message on an input gate that matches the address pattern",
    menu="protokol/osc",
    search_tags=["osc", "receive", "control", "network", "protokol", "touchosc"],
    node_type=NodeType.EVENT,
)
class OscEventNode(ArgPins, BaseNode):
    """Runs its flow for each OSC message on its gate that matches its address.

    `Gate` names an input gate in the project's Gate file (`.haywire/protokol.toml`). `Address`
    is an OSC address pattern (`*`, `?`, `[0-9]`, `{a,b}`); empty takes every message. Each
    wildcard gets a capture outlet, `match_1`, `match_2`..., which takes the type of what it is
    connected to. `args` always carries every argument as a list. `Arg Shape` lists the
    arguments (`f i vf3 s`, `_` to skip one), each token adding its own outlet. A message that
    does not fit the shape is skipped and counted in `status`.

    The outlets keep the latest values, so other flows can read them.

    Outputs:
        received: Control flow for each matching message
        address: The address that matched
        args: Every argument, as a list
        arg_N: One argument (or a group, such as a vector) per Arg Shape token
        match_N: What each wildcard matched
        timetag: The OSC bundle's timetag, 0 for a message outside a bundle
        status: The gate's state and how many messages were skipped
    """

    receive = True
    dispatch = bag(ReceiveDispatchSettings)

    def init(self) -> None:
        commit = TextWidget.config(properties={"commit": True})
        self.add(
            STRING.as_config(
                "gate",
                default="",
                label="Gate",
                description=GATE_HELP,
                widget=GateMenuWidget.config(properties={"protocol": "osc", "direction": "in"}),
                on_change="hb_gate_changed",
            )
        )
        self.add(
            STRING.as_config(
                "address",
                default="",
                label="Address",
                description=ADDRESS_HELP,
                widget=commit,
                on_change="hb_rebuild",
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
        self.add(EXEC.as_outlet("received", label="Received"))
        self.add(STRING.as_outlet("address_out", label="Address"))
        self.add(
            STRING.as_outlet("from_gate", label="From gate", description="The gate the message came in on")
        )
        self._add_rebuilt_ports(compile_pattern(""), [], {})

    def post_init(self) -> None:
        self._gate_badge = GateBadge(self)
        self._gate_badge.start()
        self._lock = threading.Lock()
        self._bindings: list[ReceiveBinding] = []
        self._skipped = 0
        self._skip_shown = -SKIP_STATUS_INTERVAL_S
        self._pattern = compile_pattern("")
        self._decode_tokens: list[Token] | None = None
        self._read_config()
        self._subscribe()

    def on_assembly(self) -> tuple[bool, str | None]:
        self._gate_badge.refresh()
        self._subscribe()
        return True, None

    # -- ports -------------------------------------------------------------------

    def hb_rebuild(self, port: Any = None, *_args: Any) -> None:
        """Rebuild the argument and capture outlets after the address or Arg shape changed.

        An invalid address or shape is put back to the last one that applied.
        """
        if self._quiet_write():
            return
        try:
            pattern = compile_pattern(str(self.value("address") or ""))
            tokens = self._tokens()
        except (ValueError, ShapeError) as exc:
            self._reject_text(port, exc)
            return
        kept = {
            port_id: port.type_cls
            for port_id, port in self.ports.items()
            if port_id.startswith("match_") and port.origin is PortOrigin.RESOLVED
        }
        with self.rejig(include=_REBUILT):
            self._add_rebuilt_ports(pattern, tokens, kept)
        self._accept_text()
        if hasattr(self, "_lock"):
            self._read_config()

    def hb_resolve_capture(self, port: Any, edge_wrapper: Any) -> None:
        """Give a bare capture outlet the type of the inlet it was connected to."""

        if port.type_cls is None or not issubclass(port.type_cls, ADD):
            return
        inlet = edge_wrapper._inlet_port
        if inlet is None:
            return
        with self.rejig(include=[port.id]):
            self.add(self._capture_spec(port.id, inlet.stored_type, PortOrigin.RESOLVED))

    def release_pins(self, port_ids: list[str]) -> list[str]:
        """Grown argument pins go with their edge; a capture outlet left bare turns back into `ADD`."""

        released = ArgPins.release_pins(self, [p for p in port_ids if ARG_ID.fullmatch(p)])
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
        ArgPins.restore_pins(self, [p for p in port_ids if ARG_ID.fullmatch(p)])
        restored = getattr(self, "_restored_types", {})
        for port_id in port_ids:
            type_cls = restored.pop(port_id, None)
            if type_cls is not None and port_id in self.ports:
                with self.rejig(include=[port_id]):
                    self.add(self._capture_spec(port_id, type_cls, PortOrigin.RESOLVED))

    def _add_rebuilt_ports(self, pattern: AddressPattern, tokens: list[Token], kept: dict[str, Any]) -> None:
        from haybale_core.types.specs import LIST

        self.add(
            LIST.as_outlet("args", label="Args", description="Every argument of the message, as a list")
        )
        self._add_arg_ports(tokens)
        for index in range(1, pattern.captures + 1):
            port_id = f"match_{index}"
            type_cls = kept.get(port_id)
            origin = PortOrigin.DECLARED if type_cls is None else PortOrigin.RESOLVED
            self.add(self._capture_spec(port_id, type_cls or ADD, origin))
        self.add(FLOAT.as_outlet("timetag", label="Timetag", default=0.0))
        self.add(STRING.as_outlet("status", label="Status", default="", store_strategy=StoreStrategy.NEVER))
        self._order_rebuilt(pattern.captures)

    def _order_rebuilt(self, captures: int) -> None:
        """Put the rebuilt outlets in their order after the fixed ones; a re-added port keeps its old place.

        args, the argument pins, the captures, timetag, status, then the empty slot.
        """
        rebuilt = [
            "args",
            *(port.id for port in self._arg_ports()),
            *(f"match_{index}" for index in range(1, captures + 1)),
            "timetag",
            "status",
            self._slot_id(),
        ]
        fixed = [port.order for port_id, port in self.ports.items() if port_id not in rebuilt]
        base = max(fixed, default=0) + 1
        for offset, port_id in enumerate(port_id for port_id in rebuilt if port_id in self.ports):
            self.ports[port_id].order = base + offset
        wrapper = getattr(self, "wrapper", None)
        if wrapper is not None:
            wrapper.mark_layout_changed()

    def _arg_spec(self, port_id: str, type_cls: Any, origin: PortOrigin, label: str) -> Any:
        return type_cls.as_outlet(port_id, label=label, on_connect="hb_grow", origin=origin)

    def _capture_spec(self, port_id: str, type_cls: Any, origin: PortOrigin) -> Any:
        index = port_id.removeprefix("match_")
        return type_cls.as_outlet(
            port_id, label=f"Match {index}", on_connect="hb_resolve_capture", origin=origin
        )

    # -- running -----------------------------------------------------------------

    def on_startup(self, context: ExecutionContext) -> None:
        self._read_config()
        with self._lock:
            self._skipped = 0
            self._skip_shown = -SKIP_STATUS_INTERVAL_S
        queue_mode, _size, start_value = resolve_dispatch(
            self.dispatch, stream=True, single_source=self._single_source()
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
        self.post_value("status", self._status([]))
        self._gate_badge.refresh()

    def on_shutdown(self, context: ExecutionContext) -> None:
        for binding in self._bindings:
            binding.close()
        self._bindings = []

    def on_teardown(self) -> None:
        badge = getattr(self, "_gate_badge", None)  # absent when post_init never ran
        if badge is not None:
            badge.stop()

    def hb_gate_changed(self, *_args: object) -> None:
        """The gate setting changed: show its gates' health at once."""
        self._gate_badge.refresh()

    def worker(self, context: ExecutionContext) -> str | None:
        payload = context.trigger.payload if context.trigger else None
        if not isinstance(payload, dict):
            return None
        self.out("address_out", payload["address"])
        self.out("from_gate", payload["gate"])
        self.out("args", list(payload["args"]))
        values = payload["values"]
        mismatch = self._pins_mismatch() if values else None
        if values and mismatch is None:
            for port, value in zip(self._arg_ports(), values, strict=True):
                self.out(port.id, value)
        problems = self._write_captures(payload["captures"])
        if mismatch is not None:
            problems.insert(0, mismatch)
        self.out("timetag", float(payload["timetag"] or 0.0))
        self.out("status", self._status(problems))
        return "received"

    def _accept(self, message: Message, gate: str) -> dict[str, Any] | None:
        with self._lock:
            pattern, tokens = self._pattern, self._decode_tokens
        captures = pattern.match(message.address)
        if captures is None:
            return None
        values: list[Any] | None = [] if tokens is None else decode(tokens, message.args)
        if values is None:
            self._count_skip()
            return None
        return {
            "address": message.address,
            "gate": gate,
            "args": list(message.args),
            "values": values,
            "captures": captures,
            "timetag": message.extra.get("timetag"),
        }

    def _count_skip(self) -> None:
        """Count a message that did not fit, and show it at once, at most twice a second (Line thread)."""
        now = time.monotonic()
        with self._lock:
            self._skipped += 1
            show = now - self._skip_shown >= SKIP_STATUS_INTERVAL_S
            if show:
                self._skip_shown = now
        if show:
            self.post_value("status", self._status([]))

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
        parts = [named_status(binding.gate_name, binding.status) for binding in self._bindings] or [
            "no gate set"
        ]
        if self._skipped:
            parts.append(f"{self._skipped} skipped")
        parts.extend(problems)
        return " · ".join(parts)

    # -- helpers -----------------------------------------------------------------

    def _read_config(self) -> None:
        try:
            pattern = compile_pattern(str(self.value("address") or ""))
            tokens = self._tokens()
        except (ValueError, ShapeError):
            return
        with self._lock:
            self._pattern = pattern
            self._decode_tokens = tokens if any(t.haywire_type for t in tokens) else None

    def _shape_applied(self) -> None:
        """A pin-menu removal or its undo changed the Arg shape: decode by the new one."""
        self._read_config()

    def _single_source(self) -> bool:
        """One exact address on one gate."""
        try:
            exact = compile_pattern(str(self.value("address") or "")).is_exact
        except ValueError:
            exact = False
        return exact and len(gate_names(str(self.value("gate") or ""))) <= 1

    def _subscribe(self) -> None:
        queue_mode, size, _start = resolve_dispatch(
            self.dispatch, stream=True, single_source=self._single_source()
        )
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
