"""Chip fields on node cards: what every chip select of this family shares.

A chip field is a multiple ``ui.select`` with ``use-chips`` whose port keeps the chosen names as
one text, ``"a, b"``. The Gate widget and the gamepad Outputs widget use it; each draws its own
chips.

Two workarounds live here, for gaps in haywire-core (to remove once core ships its fix; see this
repository's ``after-core-release`` issue):

- **Wrapping.** Node cards and the settings panel are ``compact-fields``, whose CSS fixes every
  field's control at ``var(--hw-compact-field-h)`` (26px), clipping a second row of chips.
  ``WRAP_CHIPS_STYLE`` sets that variable to ``auto`` on the select alone.
- **The size box.** A widget declaring ``@widget(min_width=CHIP_FIELD_MIN_WIDTH)`` gets
  ``contain: inline-size``, so a node sized by hand is not floored at all its chips in one row.
  Core stamps that declaration on the widget's root; on a ``ui.select`` it lands on an inner
  Quasar element, out of reach of core's rule. ``chip_field_root`` is a plain ``div`` to build
  the select in, and to return as the root.
"""

from __future__ import annotations

from typing import Any

from haywire.api import PrimitiveUnwrappingConverter
from nicegui import ui

from haybale_protokol.gate_names import gate_names, join_gate_names

#: Lets the chips wrap onto more lines, the field growing with them (see the module docstring).
WRAP_CHIPS_STYLE = "--hw-compact-field-h: auto"

#: The narrowest a chip field makes its node, for ``@widget(min_width=...)``.
CHIP_FIELD_MIN_WIDTH = 160

#: A quiet chip (design guide §1.3): surface background, body text.
CHIP_STYLE = "background-color: var(--hw-bg-elevated); color: var(--hw-text-body)"


def chip_field_root() -> ui.element:
    """A plain full-width ``div`` to build a chip select in and return from ``build()``."""
    return ui.element("div").classes("w-full")


def wrap_chips(select: ui.select) -> ui.select:
    """Show ``select``'s choices as chips that wrap onto more lines."""
    return select.props("use-chips").style(WRAP_CHIPS_STYLE)


class NameListConverter(PrimitiveUnwrappingConverter):
    """Text ``"a, b"`` in the port; a list of names in the select (one name when not ``multiple``).

    Blanks and repeats are dropped on the way in and out.
    """

    def __init__(self, *, multiple: bool = True) -> None:
        super().__init__()
        self.multiple = multiple

    def to_view(self, model_value: Any) -> Any:
        value = super().to_view(model_value)
        names = gate_names(value if isinstance(value, str) else None)
        if self.multiple:
            return names
        return names[0] if names else None

    def to_model(self, view_value: Any) -> Any:
        if isinstance(view_value, str):
            view_value = [view_value]
        return join_gate_names(view_value or [])
