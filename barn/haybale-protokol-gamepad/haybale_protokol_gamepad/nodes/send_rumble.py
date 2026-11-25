"""Send Rumble — rumbles the pads of its gates each time it runs."""

from __future__ import annotations

from haywire.api import (
    EXEC,
    FLOAT,
    INT,
    STRING,
    BaseNode,
    ExecutionContext,
    NodeType,
    NumberWidget,
    bag,
    node,
)

from haybale_protokol.gate_names import gate_names
from haybale_protokol.gate_sender import GateSender
from haybale_protokol.gate_warning import GateBadge
from haybale_protokol.receive import get_protokol_state
from haybale_protokol.sending import SendSettings
from haybale_protokol.widgets.gate_menu_widget import GateMenuWidget
from haybale_protokol_gamepad.gamepad_messages import RUMBLE_MAX_MS, rumble
from haybale_protokol_gamepad.gamepad_settings import NodeReport, show_status

GATE_HELP = (
    "One or more two-way gamepad gates from the project's Gate file; pick them from the list or "
    "type a name. Each rumble goes to every listed gate; a gate whose pad is unplugged, unknown or "
    "cannot rumble is reported in status and the others still get it. A rumble no gate could take "
    "counts as dropped, never queued. Applies on the next start."
)
STRENGTH = {"min": 0.0, "max": 1.0, "step": 0.05}
DURATION = {"min": 0, "max": RUMBLE_MAX_MS, "step": 50}


@node(
    label="Send Rumble",
    description="Rumbles the gamepads of its gates each time it runs",
    menu="protokol/gamepad",
    search_tags=["gamepad", "game controller", "rumble", "vibration", "haptic", "send", "protokol"],
    node_type=NodeType.CONTROL,
)
class SendRumbleNode(BaseNode):
    """Starts a rumble on every listed gate's pad on each control tick.

    Low and High are the strengths of the pad's low- and high-frequency motors, 0…1; Duration is
    how long it lasts. A new rumble replaces one still running, and strengths of 0 stop it. A
    value out of range drops the rumble and status names it. With Only send changes, a tick
    rumbles a gate only when the rumble differs from the last one that gate took.

    Outputs:
        next: Control flow after sending

    Status (a setting, off the card until promoted to a row or an outlet) says what was sent,
    skipped and dropped, and which gates cannot be used.
    """

    sending = bag(SendSettings)
    report = bag(NodeReport)

    def init(self) -> None:
        self.add(
            STRING.as_config(
                "gate",
                default="",
                label="Gate",
                description=GATE_HELP,
                widget=GateMenuWidget.config(properties={"protocol": "gamepad", "direction": "out"}),
                on_change="hb_gate_changed",
            )
        )
        self.add(EXEC.as_inlet("exec", label="Send"))
        self.add(
            FLOAT.as_inlet(
                "low",
                label="Low",
                default=0.5,
                description="The low-frequency (left, heavy) motor, 0…1",
                widget=NumberWidget.config(properties=STRENGTH),
            )
        )
        self.add(
            FLOAT.as_inlet(
                "high",
                label="High",
                default=0.5,
                description="The high-frequency (right, light) motor, 0…1",
                widget=NumberWidget.config(properties=STRENGTH),
            )
        )
        self.add(
            INT.as_inlet(
                "duration",
                label="Duration (ms)",
                default=200,
                description=f"How long the rumble lasts, 0…{RUMBLE_MAX_MS} ms",
                widget=NumberWidget.config(properties=DURATION),
            )
        )
        self.add(EXEC.as_outlet("next", label="Next"))

    def post_init(self) -> None:
        self._gate_badge = GateBadge(self)
        self._gate_badge.start()
        self._sender = GateSender()

    def on_assembly(self) -> tuple[bool, str | None]:
        self._gate_badge.refresh()
        return True, None

    def on_startup(self, context: ExecutionContext) -> None:
        self._sender.open(get_protokol_state(), gate_names(str(self.value("gate") or "")))
        show_status(self, self._sender.status())
        self._gate_badge.refresh()

    def on_shutdown(self, context: ExecutionContext) -> None:
        self._sender.close()

    def on_teardown(self) -> None:
        badge = getattr(self, "_gate_badge", None)  # absent when post_init never ran
        if badge is not None:
            badge.stop()

    def hb_gate_changed(self, *_args: object) -> None:
        """The gate setting changed: show its gates' health at once."""
        self._gate_badge.refresh()

    def worker(self, context: ExecutionContext) -> str | None:
        if self._sender.active:
            self._send()
        self.report.status = self._sender.status()
        return "next"

    def _send(self) -> None:
        try:
            message = rumble(self.value("low"), self.value("high"), self.value("duration"))
        except ValueError as exc:
            self._sender.drop(str(exc))
            return
        self._sender.send(message, message.args, only_changes=self.sending.only_changes)
