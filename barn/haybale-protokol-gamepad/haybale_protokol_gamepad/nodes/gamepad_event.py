"""Gamepad Event — runs its flow when one of its outputs changes on its gates; one outlet per output."""

from __future__ import annotations

import logging
import threading
from functools import partial
from typing import Any

from haywire.api import (
    EXEC,
    STRING,
    BaseNode,
    ExecutionContext,
    NodeType,
    NodeWarning,
    bag,
    node,
)

from haybale_protokol.dispatch import ReceiveDispatchSettings, event_source_for, resolve_dispatch
from haybale_protokol.drivers import Message
from haybale_protokol.gate_names import gate_names, named_status
from haybale_protokol.gate_warning import GateBadge
from haybale_protokol.receive import ReceiveBinding, get_protokol_state
from haybale_protokol.widgets.gate_menu_widget import GateMenuWidget
from haybale_protokol_gamepad.gamepad_outputs import (
    BY_NAME,
    DEFAULT,
    Output,
    Shaping,
    changes,
    is_event,
    selected,
    unknown,
    value,
)
from haybale_protokol_gamepad.gamepad_settings import NodeReport, StickShaping, show_status
from haybale_protokol_gamepad.widgets.outputs_menu_widget import OutputsMenuWidget

logger = logging.getLogger(__name__)

#: Every port id an output can bring, for ``rejig``.
_REBUILT = "^(" + "|".join(BY_NAME) + ")$"
#: The ``NodeWarning.kind`` of output names the node does not know.
OUTPUTS_WARNING = "protokol-gamepad-outputs"

GATE_HELP = (
    "One or more gamepad gates from the project's Gate file; pick them from the list or type a "
    "name. A gamepad gate names a Device, which the Gates editor's Device pane maps to a pad on "
    "this machine. Changes from every gate run the same flow; From gate says which one. A gate "
    "whose pad is unplugged waits for it and listens again when it is back. Applies on the next start."
)
OUTPUTS_HELP = (
    "What to read from the pad: each chosen output becomes an outlet, in the order chosen, and the "
    "flow runs when any of them changes. Sticks as a vector (left_stick_vec, VEC2F) or one axis "
    "(left_stick_x, FLOAT), triggers 0…1, the d-pad as a vector (dpad_vec, VEC2I), and each button "
    "(BOOL). Face buttons go by position on every brand: a is the bottom one. All outlets are read "
    "from the same moment, so a stick's x and y always belong together."
)


@node(
    label="Gamepad Event",
    description="Triggered when one of its chosen sticks, triggers, d-pad or buttons changes",
    menu="protokol/gamepad",
    search_tags=["gamepad", "game controller", "joystick", "receive", "stick", "button", "protokol"],
    node_type=NodeType.EVENT,
)
class GamepadEventNode(BaseNode):
    """Runs its flow when one of its chosen outputs changes on its gates.

    Outputs is the node's filter: each output chosen is one outlet, and the flow runs when any of
    them changes, with every outlet read from the pad's state at that moment. Sticks, triggers and
    the d-pad fire their value when the graph starts, and keep only the newest change when the flow
    runs behind; with a button among the outputs, every press and release is kept.

    Outputs:
        received: Control flow for each change of a chosen output
        from_gate: The gate the change came in on
        changed: Which chosen output changed
        (one outlet per chosen output): sticks VEC2F or FLOAT, triggers FLOAT 0…1, the d-pad VEC2I,
            buttons BOOL
    """

    shaping = bag(StickShaping)
    dispatch = bag(ReceiveDispatchSettings)
    report = bag(NodeReport)

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
                "outputs",
                default=DEFAULT,
                label="Outputs",
                description=OUTPUTS_HELP,
                widget=OutputsMenuWidget.config(),
                on_change="hb_rebuild",
            )
        )
        self.add(EXEC.as_outlet("received", label="Received"))
        self.add(
            STRING.as_outlet("from_gate", label="From gate", description="The gate the change came in on")
        )
        self.add(STRING.as_outlet("changed", label="Changed", description="Which chosen output changed"))
        self._add_outputs(selected(DEFAULT))

    def post_init(self) -> None:
        self._gate_badge = GateBadge(self)
        self._gate_badge.start()
        self._bindings: list[ReceiveBinding] = []
        self._lock = threading.Lock()
        self._outputs: tuple[Output, ...] = tuple(self._chosen())
        """The chosen outputs, read by the Line's thread; replaced whole under ``_lock``."""
        self._start_value = False
        self._subscribe()
        self._show_unknown()

    def on_assembly(self) -> tuple[bool, str | None]:
        self._gate_badge.refresh()
        self._subscribe()
        self._show_unknown()
        return True, None

    # -- ports -------------------------------------------------------------------

    def hb_rebuild(self, *_args: Any) -> None:
        """Rebuild the outlets after the outputs changed."""
        outputs = self._chosen()
        with self.rejig(include=_REBUILT):
            self._add_outputs(outputs)
        with self._lock:
            self._outputs = tuple(outputs)
        self._subscribe()
        self._show_unknown()

    def _add_outputs(self, outputs: list[Output]) -> None:
        import haywire.api as builtin

        for output in outputs:
            self.add(getattr(builtin, output.type_name).as_outlet(output.name, label=output.name))
        fixed = [port.order for port_id, port in self.ports.items() if port_id not in BY_NAME]
        base = max(fixed, default=0) + 1
        for offset, output in enumerate(outputs):
            self.ports[output.name].order = base + offset  # in the order chosen
        wrapper = getattr(self, "wrapper", None)
        if wrapper is not None:
            wrapper.mark_layout_changed()

    def _show_unknown(self) -> None:
        """Badge output names the node does not know (a hand-edited graph, an agent's typo)."""
        wrapper = getattr(self, "wrapper", None)
        if wrapper is None:
            return
        names = unknown(str(self.value("outputs") or ""))
        warnings = [NodeWarning(f"Unknown outputs: {', '.join(names)}", None, kind=OUTPUTS_WARNING)]
        wrapper.replace_warnings(OUTPUTS_WARNING, warnings if names else [])

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
                on_status=lambda: show_status(self, self._status()),
            )
            for name in gate_names(str(self.value("gate") or ""))
        ]
        show_status(self, self._status())
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
        self.out("changed", payload["changed"])
        shaping = Shaping(float(self.shaping.dead_zone or 0.0), bool(self.shaping.y_up))
        axes, buttons = payload["state"]
        for output in self._outputs:
            if output.name in self.ports:
                self.out(output.name, value(output, axes, buttons, shaping))
        self.report.status = self._status()
        return "received"

    def _accept(self, message: Message, gate: str) -> dict[str, Any] | None:
        """On the Line's thread: a payload when ``message`` changed a chosen output."""
        state = message.extra.get("state")
        if state is None:
            return None
        if message.extra.get("initial") and not self._start_value:
            return None  # the pad's state when its Line opened: a start value
        with self._lock:
            outputs = self._outputs
        hit = next((output for output in outputs if changes(output, message)), None)
        if hit is None:
            return None
        return {"gate": gate, "changed": hit.name, "state": state}

    def _status(self) -> str:
        parts = [named_status(binding.gate_name, binding.status) for binding in self._bindings]
        return " · ".join(parts) or "no gate set"

    # -- helpers -----------------------------------------------------------------

    def _chosen(self) -> list[Output]:
        return selected(str(self.value("outputs") or ""))

    def _single_source(self) -> bool:
        """One gate: every message carries the whole pad, so the newest says everything."""
        return len(gate_names(str(self.value("gate") or ""))) <= 1

    def _is_stream(self) -> bool:
        """No button chosen: only values (sticks, triggers, d-pad), whose newest state is enough."""
        return not any(is_event(output) for output in self._chosen())

    def _subscribe(self) -> None:
        queue_mode, size, _start = resolve_dispatch(
            self.dispatch, stream=self._is_stream(), single_source=self._single_source()
        )
        self.event_subscription = event_source_for(self.node_id, queue_mode, size)
