"""OutputsMenuWidget — pick a Gamepad Event node's outputs as chips; the port keeps ``"a, b"`` text."""

from __future__ import annotations

from typing import Any

from haywire.api import BaseWidget, PrimitiveUnwrappingConverter, widget
from haywire.api.workbench import LevelMode, stamp_requires
from nicegui import ui

from haybale_protokol_gamepad.gamepad_outputs import CHOICES, names, join_names

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
    """The select's ``selected-item`` slot: each output as a removable chip, by its outlet name."""
    name = "(props.opt.value ?? props.opt)"
    return (
        f'<q-chip dense square removable :tabindex="props.tabindex" style="{_CHIP_STYLE}" '
        f'@remove="props.removeAtIndex(props.index)">{{{{ {name} }}}}</q-chip>'
    )


@widget(description="Pick a gamepad node's outputs as chips; each becomes an outlet, in the order picked")
class OutputsMenuWidget(BaseWidget):
    """A multiple select of the outputs in ``gamepad_outputs.OUTPUTS``, saved as ``"a, b"``.

    The menu lists each output by its label (``Left stick (x, y)``); a chosen one shows as a chip
    with its outlet name (``left_stick_vec``). The select takes input only in edit mode.
    """

    def build(self) -> Any:
        select = ui.select(options=dict(CHOICES), value=[], multiple=True).classes("w-full text-xs")
        select.props("use-chips")
        select.add_slot("selected-item", chip_template())
        stamp_requires(select, LevelMode.EDIT)
        return self.bind(select, converter=OutputListConverter())
