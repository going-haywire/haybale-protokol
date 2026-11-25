"""Gamepad Event — runs its flow for each gamepad control change on its gates that passes its filter."""

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
    MenuWidget,
    NodeType,
    NumberWidget,
    StoreStrategy,
    bag,
    node,
)

from haybale_protokol.dispatch import ReceiveDispatchSettings, event_source_for, resolve_dispatch
from haybale_protokol.drivers import Message
from haybale_protokol.gate_names import gate_names, named_status
from haybale_protokol.gate_warning import GateBadge
from haybale_protokol.receive import ReceiveBinding, get_protokol_state
from haybale_protokol.widgets.gate_menu_widget import GateMenuWidget
from haybale_protokol_gamepad.gamepad_messages import KINDS, STREAM_KINDS
from haybale_protokol_gamepad.gamepad_pins import (
    INDEX_HELP,
    INDEX_RANGE,
    KIND_PINS,
    filter_problem,
    index_filter,
    show_filter_problem,
)

logger = logging.getLogger(__name__)

#: Display order of every outlet the filter can bring.
_OUTLET_ORDER = ("control", "index", "value", "pressed", "hat", "status")
_REBUILT = r"^(control|index|value|pressed|hat|status)$"

GATE_HELP = (
    "One or more gamepad gates from the project's Gate file; pick them from the list or type a "
    "name. A gamepad gate names a Device, which the Gates editor's Device pane maps to a pad on "
    "this machine. Changes from every gate run the same flow; From gate says which one. A gate "
    "whose pad is unplugged waits for it and listens again when it is back. Applies on the next start."
)
KIND_HELP = (
    "What to listen for. axis: a stick (−1…1, left and up negative) or a trigger (0…1); button: "
    "pressed or released; hat: the d-pad as one vector (x −1 left … 1 right, y −1 up … 1 down); "
    "all: every control, with a control outlet saying which kind. The outlets change with the kind."
)


@node(
    label="Gamepad Event",
    description="Triggered for each change of a gamepad axis, button or d-pad that passes its filter",
    menu="protokol/gamepad",
    search_tags=["gamepad", "game controller", "joystick", "receive", "axis", "button", "protokol"],
    node_type=NodeType.EVENT,
)
class GamepadEventNode(BaseNode):
    """Runs its flow for each change of a gamepad control of its kind (and index) on its gates.

    Kind and Index are the node's filter, and its outlets follow it. Axes and the d-pad fire their
    last value when the graph starts and keep only the newest change when the flow runs behind;
    buttons queue every press and release.

    Outputs:
        received: Control flow for each change that passes the filter
        from_gate: The gate the change came in on
        control: For all, which kind of control changed (axis, button or hat)
        index: The control's index, when the filter leaves it open
        value: An axis (−1…1, a trigger 0…1); for all, a button as 0 or 1
        pressed: Whether a button is down
        hat: The d-pad as (x, y)
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
                widget=GateMenuWidget.config(properties={"protocol": "gamepad", "direction": "in"}),
                on_change="hb_gate_changed",
            )
        )
        self.add(
            STRING.as_config(
                "kind",
                default="axis",
                label="Kind",
                description=KIND_HELP,
                widget=MenuWidget.config(properties={"options": list(KINDS)}),
                on_change="hb_rebuild",
            )
        )
        self.add(
            INT.as_config(
                "filter_index",
                default=0,
                label="Index",
                description=INDEX_HELP,
                widget=NumberWidget.config(properties=INDEX_RANGE),
                on_change="hb_rebuild",
            )
        )
        self.add(EXEC.as_outlet("received", label="Received"))
        self.add(
            STRING.as_outlet("from_gate", label="From gate", description="The gate the change came in on")
        )
        self._add_filter_outlets("axis", 0)

    def post_init(self) -> None:
        self._gate_badge = GateBadge(self)
        self._gate_badge.start()
        self._bindings: list[ReceiveBinding] = []
        self._start_value = False
        self._subscribe()
        show_filter_problem(self, self._filter_problem())

    def on_assembly(self) -> tuple[bool, str | None]:
        self._gate_badge.refresh()
        self._subscribe()
        show_filter_problem(self, self._filter_problem())
        return True, None

    # -- ports -------------------------------------------------------------------

    def hb_rebuild(self, *_args: Any) -> None:
        """Rebuild the outlets after the kind or index changed."""
        kind, index = self._filter()
        with self.rejig(include=_REBUILT):
            self._add_filter_outlets(kind, index)
        self._subscribe()
        show_filter_problem(self, self._filter_problem())

    def _add_filter_outlets(self, kind: str, index: int) -> None:
        import haywire.api as builtin

        if kind == "all" or index < 0:
            self.add(builtin.INT.as_outlet("index", label="Index"))
        for port_id, type_name in KIND_PINS.get(kind, ()):
            self.add(getattr(builtin, type_name).as_outlet(port_id, label=port_id.capitalize()))
        self.add(STRING.as_outlet("status", label="Status", default="", store_strategy=StoreStrategy.NEVER))
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
        self._start_value = start_value

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
                on_status=lambda: self.post_value("status", self._status()),
            )
            for name in gate_names(str(self.value("gate") or ""))
        ]
        self.post_value("status", self._status())
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
        self.out("from_gate", payload["gate"])
        for port_id, value in payload["values"].items():
            if port_id in self.ports:
                self.out(port_id, value)
        self.out("status", self._status())
        return "received"

    def _accept(self, message: Message, gate: str) -> dict[str, Any] | None:
        if message.extra.get("initial") and not self._start_value:
            return None  # the pad's state when its Line opened: a start value
        kind, index = self._filter()
        got = message.extra.get("kind")
        if got not in ("axis", "button", "hat"):
            return None
        if kind != "all" and (got != kind or (index >= 0 and message.extra.get("index") != index)):
            return None
        value = message.args[0]
        values: dict[str, Any] = {"control": got, "index": message.extra.get("index")}
        if got == "axis":
            values["value"] = value
        elif got == "button":
            values["pressed"] = value
            if kind == "all":
                values["value"] = 1.0 if value else 0.0
        else:
            values["hat"] = value
        return {"gate": gate, "values": values}

    def _status(self) -> str:
        parts = [named_status(binding.gate_name, binding.status) for binding in self._bindings]
        problem = self._filter_problem()
        return " · ".join([problem, *parts] if problem else parts) or "no gate set"

    def _filter_problem(self) -> str | None:
        """Why no control can pass the filter, or ``None``: such a node would never fire."""
        return filter_problem(*self._filter())

    # -- helpers -----------------------------------------------------------------

    def _filter(self) -> tuple[str, int]:
        kind = str(self.value("kind") or "axis")
        return kind if kind in KINDS else "axis", index_filter(self.value("filter_index"))

    def _single_source(self) -> bool:
        """One control (the d-pad is one) and one gate."""
        kind, index = self._filter()
        if kind == "all" or (kind != "hat" and index < 0):
            return False
        return len(gate_names(str(self.value("gate") or ""))) <= 1

    def _is_stream(self) -> bool:
        return self._filter()[0] in STREAM_KINDS

    def _subscribe(self) -> None:
        queue_mode, size, _start = resolve_dispatch(
            self.dispatch, stream=self._is_stream(), single_source=self._single_source()
        )
        self.event_subscription = event_source_for(self.node_id, queue_mode, size)
