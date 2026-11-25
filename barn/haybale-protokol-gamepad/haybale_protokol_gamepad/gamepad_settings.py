"""Settings bags of the gamepad nodes: how sticks are shaped, and the status report."""

from __future__ import annotations

from typing import Any

from haywire.api import BOOL, FLOAT, STRING, LabelWidget, NodeSettings, Promotable, StoreStrategy, setting


class StickShaping(NodeSettings):
    """How a Gamepad Event node shapes its stick and d-pad values. Applies to the next change."""

    dead_zone = setting[FLOAT](
        0.2,
        min=0.0,
        max=0.9,
        label="Dead zone",
        category="Sticks",
        description=(
            "How far a stick must move from its centre before it counts, 0…0.9. Inside, it reads 0; "
            "outside, it is rescaled to still reach 1. Pads rest a little off centre (often 0.05–0.2). "
            "Applies to x and y together, so diagonals stay true; 0 gives the raw value."
        ),
        promotable=Promotable.INPUT,
    )
    y_up = setting[BOOL](
        True,
        label="Y up",
        category="Sticks",
        description=(
            "On: pushing a stick or the d-pad up gives a positive y, as in maths and most 3D. Off: down "
            "is positive, as SDL and screen coordinates count (y grows downward)."
        ),
        promotable=Promotable.INPUT,
    )


class NodeReport(NodeSettings):
    """What the node reports. Off the card by default: promote Status to a row or an outlet to show it."""

    status = setting[STRING](
        "",
        label="Status",
        category="Report",
        description="Each gate's state, and what was sent or dropped. Never saved.",
        widget=LabelWidget.config(),
        promotable=Promotable.OUTLET | Promotable.CONFIG,
        store=StoreStrategy.NEVER,
    )


def show_status(node: Any, text: str) -> None:
    """Write ``text`` to ``node.report.status`` from any thread.

    Promoted, the field is a port sharing its cell, written through ``post_value`` so the graph
    sees it on its own thread (ADR 0064). Not promoted, only the properties panel shows it, and
    the field is written directly. Core offers no ``post_value`` for a setting.
    """
    port_id = "report.status"  # a promoted port's id is the setting's storage key: <bag>.<field>
    if port_id in node.ports:
        node.post_value(port_id, text)
    else:
        node.report.status = text
