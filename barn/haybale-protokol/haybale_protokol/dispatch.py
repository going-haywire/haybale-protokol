"""How a Receive node's flow queues the messages its Line delivers.

Stream kinds (OSC, MIDI CC, gamepad axes) default to Drop with a queue of one and fire their
Start value; event kinds (notes, buttons) default to Block and do not. A MIDI node's kind can
change, so the defaults are an "Auto" choice resolved by kind, not fixed per class.
"""

from __future__ import annotations

from haywire.barn.builtin.types import CHOICES, INT
from haywire.core.execution import QueueMode
from haywire.core.execution.event_source import CallbackEvent
from haywire.core.settings import NodeSettings, Promotable, setting

AUTO = "Auto (by message kind)"
BLOCK = "Block (every message)"
DROP = "Drop (newest only)"
ON = "On"
OFF = "Off"


class ReceiveDispatchSettings(NodeSettings):
    """How incoming messages queue, and whether the Line cache fires at start. Applies on the next start."""

    queue_mode = setting[CHOICES](
        AUTO,
        label="Queue Mode",
        category="Dispatch",
        description=(
            "Block runs the flow for every message; a slow flow then falls behind, never the Line. "
            "Drop keeps only the newest message. Auto uses Drop for values (faders, axes, OSC) and "
            "Block for events (notes, buttons)."
        ),
        widget_config={"options": [AUTO, BLOCK, DROP]},
        promotable=Promotable.CONFIG,
    )
    max_queue_size = setting[INT](
        100,
        min=1,
        max=1024,
        label="Max Queue Size",
        category="Dispatch",
        description="How many messages Block holds while the flow runs behind. Drop always holds one.",
        promotable=Promotable.CONFIG,
    )
    start_value = setting[CHOICES](
        AUTO,
        label="Start Value",
        category="Dispatch",
        description=(
            "Fire once with the last message the Line saw when the graph starts. "
            "Auto: on for values, off for events."
        ),
        widget_config={"options": [AUTO, ON, OFF]},
        promotable=Promotable.CONFIG,
    )


def resolve_dispatch(dispatch: ReceiveDispatchSettings, *, stream: bool) -> tuple[QueueMode, int, bool]:
    """Return ``(queue mode, queue size, start value)`` for a node receiving a stream or event kind."""
    mode = str(dispatch.queue_mode)
    if mode == AUTO:
        mode = DROP if stream else BLOCK
    start = str(dispatch.start_value)
    start_value = stream if start == AUTO else start == ON
    if mode == DROP:
        return QueueMode.DROP, 1, start_value
    return QueueMode.BLOCK, int(dispatch.max_queue_size), start_value


def event_source_for(node_id: str, queue_mode: QueueMode, max_queue_size: int) -> CallbackEvent:
    """The event subscription of a Receive node: a callback named after the node."""
    return CallbackEvent(event_name=node_id, queue_mode=queue_mode, max_queue_size=max_queue_size)
