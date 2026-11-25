"""OutputsMenuWidget — pick a Gamepad Event node's outputs as chips; the port keeps ``"a, b"`` text."""

from __future__ import annotations

import json
from typing import Any

from haywire.api import BaseWidget, widget
from haywire.api.workbench import LevelMode, stamp_requires
from nicegui import ui

from haybale_protokol.chips import (
    CHIP_FIELD_MIN_WIDTH,
    CHIP_STYLE,
    NameListConverter,
    chip_field_root,
    wrap_chips,
)
from haybale_protokol_gamepad.gamepad_outputs import CHOICES, OUTPUTS


def chip_template() -> str:
    """The select's ``selected-item`` slot: each output as a removable chip.

    The chip shows the outlet name (``left_stick_vec``), as on the node; hovering it shows the
    output's label and outlet type (``Left stick (x, y) · VEC2F``). NiceGUI hands the browser
    each option as ``{value: <its index>, label}``, so both are looked up by that index, in
    ``OUTPUTS`` order (the order of ``CHOICES``).
    """
    names = json.dumps([output.name for output in OUTPUTS])
    tips = json.dumps([f"{output.label} · {output.type_name}" for output in OUTPUTS])
    index = "props.opt.value"
    return (
        f'<q-chip dense square removable :tabindex="props.tabindex" style="{CHIP_STYLE}" '
        f'@remove="props.removeAtIndex(props.index)">'
        f"{{{{ {names}[{index}] ?? props.opt.label }}}}"
        f"<q-tooltip>{{{{ {tips}[{index}] }}}}</q-tooltip>"
        "</q-chip>"
    )


@widget(
    description="Pick a gamepad node's outputs as chips; each becomes an outlet, in the order picked",
    min_width=CHIP_FIELD_MIN_WIDTH,
)
class OutputsMenuWidget(BaseWidget):
    """A multiple select of the outputs in ``gamepad_outputs.OUTPUTS``, saved as ``"a, b"``.

    The menu lists each output by its label (``Left stick (x, y)``); a chosen one shows as a chip
    with its outlet name (``left_stick_vec``), and hovering the chip shows the label and the
    outlet's type. The select takes input only in edit mode.
    """

    def build(self) -> Any:
        with chip_field_root() as root:  # the root core's size box reaches (see haybale_protokol.chips)
            select = ui.select(options=dict(CHOICES), value=[], multiple=True).classes("w-full text-xs")
            wrap_chips(select)
            select.add_slot("selected-item", chip_template())
            stamp_requires(select, LevelMode.EDIT)
            self.bind(select, converter=NameListConverter())
        return root
