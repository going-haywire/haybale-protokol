"""The Outputs chips: each shows its outlet name and, on hover, its label and type."""

import json
import re

import haywire.core.node  # noqa: F401  (import order: the library modules need the node package first)
from haybale_protokol_gamepad.gamepad_outputs import CHOICES, OUTPUTS
from haybale_protokol_gamepad.widgets.outputs_menu_widget import OutputListConverter, chip_template


def _lists(template: str) -> list[list[str]]:
    return [json.loads(found) for found in re.findall(r"\{\{ (\[.*?\])\[props\.opt\.value\]", template)]


def test_chip_looks_up_by_the_option_index() -> None:
    names, tips = _lists(chip_template())
    assert names == list(CHOICES), "NiceGUI numbers the options in CHOICES order"
    assert names[0] == "left_stick_vec"
    assert tips[0] == "Left stick (x, y) · VEC2F"
    assert tips[names.index("a")] == "A (bottom) · BOOL"
    assert len(tips) == len(OUTPUTS)
    assert "<q-tooltip>" in chip_template()


def test_converter_keeps_text_in_the_port() -> None:
    converter = OutputListConverter()
    assert converter.to_view("a, left_stick_vec, a") == ["a", "left_stick_vec"]
    assert converter.to_model(["dpad_vec", "b"]) == "dpad_vec, b"
    assert converter.to_model(None) == ""
