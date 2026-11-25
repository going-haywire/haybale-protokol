"""GateMenuWidget — pick gates as chips; the port keeps them as ``"a, b"`` text."""

from __future__ import annotations

import json
from typing import Any, Literal

from haywire.api.workbench import LevelMode, get_library_state_container, stamp_requires
from haywire.api import BaseWidget, PrimitiveUnwrappingConverter, widget
from nicegui import ui

from haybale_protokol.gate_names import gate_names, join_gate_names
from haybale_protokol.states.protokol_state import ProtokolState

Tone = Literal["success", "warning", "danger"]

#: Theme classes for each tone (design guide §1.2: colours only through --hw-* tokens).
_TONE_CLASS: dict[str, str] = {
    "success": "hw-text-success",
    "warning": "hw-text-warning",
    "danger": "hw-text-danger",
}


class GateListConverter(PrimitiveUnwrappingConverter):
    """Text ``"a, b"`` in the port; a list of names in the select (one name when not ``multiple``)."""

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


def merged_options(options: list[str], selected: list[str]) -> list[str]:
    """``options`` plus the selected names they lack (a gate missing from the file stays visible)."""
    return [*options, *(name for name in selected if name not in options)]


def select_options(properties: dict[str, Any]) -> dict[str, Any]:
    """The ``ui.select`` arguments the widget's properties ask for."""
    kwargs: dict[str, Any] = {"multiple": bool(properties.get("multiple", True))}
    if properties.get("typed", True):
        kwargs["new_value_mode"] = "add-unique"
    return kwargs


def gate_tone(state: ProtokolState, name: str, protocol: str, direction: str) -> Tone:
    """How usable ``name`` is for a node of ``protocol`` that wants ``direction``.

    ``success``: it works now (its health is ``working`` or ``closed``). ``danger``: no such gate,
    one of another protocol or direction, or a gate that does not work now: unbound, its device not
    plugged in, its protocol not installed, a failed open (``ProtokolState.health``).
    """
    gate = state.gates().get(name)
    if gate is None or gate.protocol != protocol or gate.direction not in (direction, "two-way"):
        return "danger"
    return "success" if state.health(gate).healthy else "danger"


#: The gate name of a select option: NiceGUI hands Quasar ``{value, label}`` objects; a typed value
#: may arrive bare.
_NAME = "(props.opt.label ?? props.opt)"

#: Lets the chips wrap onto more lines, the field growing with them. Node cards and the settings
#: panel are ``compact-fields``, whose CSS fixes every field's control at
#: ``var(--hw-compact-field-h)`` (26px), so a second row of chips was clipped. The variable is
#: set on this select alone, so only its own field grows.
WRAP_CHIPS_STYLE = "--hw-compact-field-h: auto"

#: A quiet chip (design guide §1.3): surface background, body text; the state is a dot.
_CHIP_STYLE = "background-color: var(--hw-bg-elevated); color: var(--hw-text-body)"
_DOT_STYLE = (
    "display: inline-block; width: 6px; height: 6px; border-radius: 50%; "
    "background: currentColor; margin-right: 4px; flex-shrink: 0"
)


def chip_template(tones: dict[str, Tone], *, removable: bool = True) -> str:
    """The select's ``selected-item`` slot: each chosen gate with a dot in its state's theme colour."""
    classes = {name: _TONE_CLASS[tone] for name, tone in tones.items()}
    lookup = json.dumps(classes).replace("'", "\\u0027")  # inside a single-quoted attribute
    dot = f'<span :class=\'({lookup})[{_NAME}] || "{_TONE_CLASS["danger"]}"\' style="{_DOT_STYLE}"></span>'
    label = f"<span>{{{{ {_NAME} }}}}</span>"
    if not removable:
        return f'<span class="row items-center no-wrap">{dot}{label}</span>'
    return (
        f'<q-chip dense square removable :tabindex="props.tabindex" style="{_CHIP_STYLE}" '
        f'@remove="props.removeAtIndex(props.index)">{dot}{label}</q-chip>'
    )


@widget(description="Pick gates as chips from the gates that fit the node, each coloured by its state")
class GateMenuWidget(BaseWidget):
    """A select of gates; its behaviour is set by plain properties, as the port saves them.

    Each chosen gate shows as a chip coloured by its state: success when it works now, danger when
    it does not (``gate_tone``): no such gate, another protocol or direction, or its health is
    unbound, not plugged in or error. The select takes input only in edit mode.

    Properties (``GateMenuWidget.config(properties={...})``):

    - ``protocol``: the gates to offer and check, e.g. ``"osc"``.
    - ``direction``: ``"in"`` or ``"out"``; two-way gates fit both.
    - ``multiple`` (default ``True``): several gates, stored as ``"a, b"``; ``False`` for exactly one.
    - ``typed`` (default ``True``): a name typed and confirmed with Enter is kept even when no such
      gate exists yet.

    The offered gates are read from the project each time the widget is drawn, so new gates appear.
    """

    def build(self) -> Any:
        properties = self._config.get("properties", {})
        self._protocol = str(properties.get("protocol", ""))
        self._direction: Literal["in", "out"] = "out" if properties.get("direction") == "out" else "in"
        self._multiple = bool(properties.get("multiple", True))
        state = _state()
        self._options = state.gate_choices(self._protocol, self._direction) if state is not None else []
        select = ui.select(
            options=list(self._options), value=[] if self._multiple else None, **select_options(properties)
        ).classes("w-full text-xs")
        if self._multiple:
            select.props("use-chips").style(WRAP_CHIPS_STYLE)
        stamp_requires(select, LevelMode.EDIT)
        return self.bind(select, converter=GateListConverter(multiple=self._multiple))

    def on_model_changed(self, value: Any) -> None:
        element = self.ui_element
        if element is not None:
            selected = gate_names(PrimitiveUnwrappingConverter().to_view(value) or "")
            options = merged_options(self._options, selected)
            if options != list(element.options):
                element.set_options(options)
            state = _state()
            tones: dict[str, Tone] = (
                {name: gate_tone(state, name, self._protocol, self._direction) for name in selected}
                if state is not None
                else {}
            )
            element.add_slot("selected-item", chip_template(tones, removable=self._multiple))
            element.update()
        super().on_model_changed(value)


def _state() -> ProtokolState | None:
    """The app's ProtokolState; ``None`` while haybale-protokol is not enabled."""

    try:
        return get_library_state_container().get(ProtokolState)
    except RuntimeError:
        return None
