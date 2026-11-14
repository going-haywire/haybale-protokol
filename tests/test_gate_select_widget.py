"""The gate picker: chips for several gates, kept as one comma-separated text value."""

import pytest

from haybale_protokol.gate_names import gate_names, join_gate_names
from haybale_protokol.widgets.gate_select_widget import GateListConverter, merged_options


@pytest.mark.parametrize(
    ("text", "names"),
    [("", []), ("a", ["a"]), (" a , b,,a ", ["a", "b"]), (None, [])],
)
def test_gate_names(text: str | None, names: list[str]) -> None:
    assert gate_names(text) == names


def test_join_gate_names() -> None:
    assert join_gate_names(["a", " b ", "", "a"]) == "a, b"


def test_converter_round_trip() -> None:
    converter = GateListConverter()
    assert converter.to_view("a, b") == ["a", "b"]
    assert converter.to_view(None) == []
    assert converter.to_model(["b", "a"]) == "b, a"
    assert converter.to_model(None) == ""


def test_selected_names_missing_from_options_are_kept() -> None:
    assert merged_options(["in", "both"], ["gone", "in"]) == ["in", "both", "gone"]


@pytest.mark.integration
def test_widget_is_registered(library_system: object) -> None:
    from haybale_protokol.widgets.gate_select_widget import GateSelectWidget

    assert GateSelectWidget.class_identity.registry_key == "haybale-protokol:widget:GateSelectWidget"
