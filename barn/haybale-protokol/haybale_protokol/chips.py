"""Chip fields on node cards: what every chip select of this family shares.

A chip field is a multiple ``ui.select`` with ``use-chips`` whose port keeps the chosen names as
one text, ``"a, b"``. The Gate widget and the gamepad Outputs widget use it; each draws its own
chips.
"""

from __future__ import annotations

from typing import Any

from haywire.api import PrimitiveUnwrappingConverter

from haybale_protokol.gate_names import gate_names, join_gate_names

#: The narrowest a chip field makes its node, for ``@widget(min_width=...)``.
CHIP_FIELD_MIN_WIDTH = 160

#: A quiet chip (design guide §1.3): surface background, body text.
CHIP_STYLE = "background-color: var(--hw-bg-elevated); color: var(--hw-text-body)"


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
