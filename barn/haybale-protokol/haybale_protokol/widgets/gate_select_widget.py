"""GateSelectWidget — pick one or more gates as chips; the port keeps them as ``"a, b"`` text."""

from __future__ import annotations

from typing import Any

from haywire.ui.widget.base import BaseWidget
from haywire.ui.widget.converters import PrimitiveUnwrappingConverter
from haywire.ui.widget.decorator import widget
from nicegui import ui

from haybale_protokol.gate_names import gate_names, join_gate_names


class GateListConverter(PrimitiveUnwrappingConverter):
    """Text ``"a, b"`` in the port, a list of names in the select."""

    def to_view(self, model_value: Any) -> Any:
        value = super().to_view(model_value)
        return gate_names(value if isinstance(value, str) else None)

    def to_model(self, view_value: Any) -> Any:
        return join_gate_names(view_value or [])


def merged_options(options: list[str], selected: list[str]) -> list[str]:
    """``options`` plus the selected names they lack (a gate missing from the file stays visible)."""
    return [*options, *(name for name in selected if name not in options)]


@widget(description="Pick gates as chips from the gates that fit the node; typed names are kept")
class GateSelectWidget(BaseWidget):
    """A multiple select with chips, like the Models editor's library filter.

    Config (``GateSelectWidget.config(properties={...})``), plain values since a port saves it:

    - ``protocol``: which gates to offer, e.g. ``"osc"``.
    - ``direction``: ``"in"`` or ``"out"``; two-way gates are offered for both.

    The offered gates are read from the project each time the widget is drawn, so new gates appear.

    A name typed and confirmed with Enter is kept even when no such gate exists yet; the node's
    status then reports it.
    """

    def build(self) -> Any:
        properties = self._config.get("properties", {})
        self._options = _choices(str(properties.get("protocol", "")), properties.get("direction", "in"))
        select = (
            ui.select(options=list(self._options), value=[], multiple=True, new_value_mode="add-unique")
            .props("use-chips")
            .classes("w-full text-xs")
        )
        return self.bind(select, converter=GateListConverter())

    def on_model_changed(self, value: Any) -> None:
        element = self.ui_element
        if element is not None:
            selected = GateListConverter().to_view(value)
            options = merged_options(self._options, selected)
            if options != list(element.options):
                element.set_options(options)
        super().on_model_changed(value)


def _choices(protocol: str, direction: Any) -> list[str]:
    """The gates to offer; none while haybale-protokol is not enabled."""
    from haywire.core.di.context import get_library_state_container

    from haybale_protokol.states.protokol_state import ProtokolState

    try:
        state = get_library_state_container().get(ProtokolState)
    except RuntimeError:
        return []
    return state.gate_choices(protocol, "out" if direction == "out" else "in") if state is not None else []
