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


from pathlib import Path  # noqa: E402

from haybale_protokol.devices import Device, device_list_path, save_devices  # noqa: E402
from haybale_protokol.gates import Gate, gate_file_path, save_gates  # noqa: E402
from haybale_protokol.states.protokol_state import ProtokolState  # noqa: E402
from haybale_protokol.widgets.gate_select_widget import (  # noqa: E402
    chip_template,
    gate_tone,
    select_options,
)
from tests.fakes import FakeDriver  # noqa: E402


def _state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ProtokolState:
    monkeypatch.setenv("HOME", str(tmp_path))
    state = ProtokolState()
    state.project_root = tmp_path
    state.register_driver(FakeDriver())
    save_gates(
        gate_file_path(tmp_path),
        [
            Gate("ok", "fake", "in"),
            Gate("both", "fake", "two-way"),
            Gate("out", "fake", "out"),
            Gate("other", "midi", "in"),
            Gate("pad", "fake", "in", device="nowhere"),
            Gate("desk", "fake", "in", device="desk"),
        ],
    )
    save_devices(device_list_path(), [Device("desk", "fake", "IAC 1")])
    return state


@pytest.mark.parametrize(
    ("name", "tone"),
    [
        ("ok", "success"),
        ("both", "success"),
        ("desk", "success"),
        ("pad", "warning"),
        ("out", "danger"),
        ("other", "danger"),
        ("nope", "danger"),
    ],
)
def test_gate_tone(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str, tone: str) -> None:
    assert gate_tone(_state(tmp_path, monkeypatch), name, "fake", "in") == tone


def test_protocol_not_installed_is_a_warning(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    state = _state(tmp_path, monkeypatch)
    state.unregister_driver("fake")
    assert gate_tone(state, "ok", "fake", "in") == "warning"


def test_chip_template_reads_the_option_label() -> None:
    """NiceGUI hands Quasar options as {value, label}: the name is props.opt.label, never props.opt."""
    template = chip_template({"ok": "success"})
    assert "props.opt.label" in template
    assert "{{ props.opt }}" not in template
    assert "[props.opt]" not in template


def test_chip_is_quiet_with_a_status_dot_in_theme_tokens() -> None:
    template = chip_template({"ok": "success", 'we"ird': "danger"})
    assert "hw-text-success" in template
    assert "hw-text-danger" in template
    assert "var(--hw-bg-elevated)" in template
    assert "var(--hw-text-body)" in template
    assert "currentColor" in template, "the dot takes its tone's colour"
    assert '"we\\"ird"' in template, "names are JSON-escaped"
    assert "#" not in template, "no hard-coded colours"


@pytest.mark.parametrize(
    ("properties", "multiple", "typed"),
    [({}, True, True), ({"multiple": False}, False, True), ({"typed": False}, True, False)],
)
def test_properties_drive_the_select(properties: dict[str, object], multiple: bool, typed: bool) -> None:
    kwargs = select_options(properties)
    assert kwargs["multiple"] is multiple
    assert ("new_value_mode" in kwargs) is typed


def test_single_gate_converter() -> None:
    converter = GateListConverter(multiple=False)
    assert converter.to_view("a, b") == "a"
    assert converter.to_view("") is None
    assert converter.to_model("a") == "a"
    assert converter.to_model(None) == ""
