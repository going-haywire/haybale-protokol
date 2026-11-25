"""OutputsMenuWidget — pick a Gamepad Event node's outputs as chips; the port keeps ``"a, b"`` text."""

from __future__ import annotations

import json
from typing import Any

from haywire.api import BaseWidget, PrimitiveUnwrappingConverter, widget
from haywire.api.workbench import LevelMode, stamp_requires
from nicegui import ui

from haybale_protokol_gamepad.gamepad_outputs import CHOICES, OUTPUTS, join_names, names

#: Lets the chips wrap onto more lines, the field growing with them. Node cards and the settings
#: panel are ``compact-fields``, whose CSS fixes every field's control at
#: ``var(--hw-compact-field-h)`` (26px), so a second row of chips was clipped. The variable is
#: set on this select alone, so only its own field grows.
WRAP_CHIPS_STYLE = "--hw-compact-field-h: auto"

#: A quiet chip, like the gate chips (design guide §1.3).
_CHIP_STYLE = "background-color: var(--hw-bg-elevated); color: var(--hw-text-body)"


class OutputListConverter(PrimitiveUnwrappingConverter):
    """Text ``"a, b"`` in the port; a list of output names in the select."""

    def to_view(self, model_value: Any) -> Any:
        value = super().to_view(model_value)
        return names(value if isinstance(value, str) else None)

    def to_model(self, view_value: Any) -> Any:
        return join_names(view_value or [])


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
        f'<q-chip dense square removable :tabindex="props.tabindex" style="{_CHIP_STYLE}" '
        f'@remove="props.removeAtIndex(props.index)">'
        f"{{{{ {names}[{index}] ?? props.opt.label }}}}"
        f"<q-tooltip>{{{{ {tips}[{index}] }}}}</q-tooltip>"
        "</q-chip>"
    )


#: The narrowest the field makes its node, as for the gate field: declared, its width stops coming
#: from its content (``contain: inline-size``), so a manually sized node can be narrower than all its
#: chips in one row; its height still follows the chips as they wrap.
MIN_WIDTH = 160


@widget(
    description="Pick a gamepad node's outputs as chips; each becomes an outlet, in the order picked",
    min_width=MIN_WIDTH,
)
class OutputsMenuWidget(BaseWidget):
    """A multiple select of the outputs in ``gamepad_outputs.OUTPUTS``, saved as ``"a, b"``.

    The menu lists each output by its label (``Left stick (x, y)``); a chosen one shows as a chip
    with its outlet name (``left_stick_vec``), and hovering the chip shows the label and the
    outlet's type. The select takes input only in edit mode.
    """

    def build(self) -> Any:
        select = ui.select(options=dict(CHOICES), value=[], multiple=True).classes("w-full text-xs")
        select.props("use-chips").style(WRAP_CHIPS_STYLE)
        select.add_slot("selected-item", chip_template())
        stamp_requires(select, LevelMode.EDIT)
        return self.bind(select, converter=OutputListConverter())
