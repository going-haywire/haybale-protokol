"""SendSettings — when a Send node's control tick sends; shared by every protocol's Send node."""

from __future__ import annotations

from haywire.barn.builtin.types import BOOL
from haywire.core.settings import NodeSettings, Promotable, setting


class SendSettings(NodeSettings):
    """When a control tick sends."""

    only_changes = setting[BOOL](
        False,
        label="Only send changes",
        category="Sending",
        description=(
            "Off: every control tick sends the message. On: a tick sends to a gate only when the "
            "message differs from the last one that gate took; the first tick of a run always "
            "sends, and a gate that missed a message gets it on the next tick. Skipped ticks are "
            "counted as 'unchanged' in status."
        ),
        promotable=Promotable.CONFIG,
    )
