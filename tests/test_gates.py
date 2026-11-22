"""The Gate file: reading, writing, and refusing a malformed one."""

import dataclasses
from pathlib import Path

import pytest

from haybale_protokol.gates import (
    Gate,
    GateFileError,
    gate_file_path,
    load_gates,
    remove_gate,
    save_gates,
    write_gate,
)


def test_gate_file_path(tmp_path: Path) -> None:
    assert gate_file_path(tmp_path) == tmp_path / ".haywire" / "protokol.toml"


def test_missing_file_is_empty(tmp_path: Path) -> None:
    assert load_gates(tmp_path / "nope.toml") == {}


def test_round_trip_keeps_options(tmp_path: Path) -> None:
    path = gate_file_path(tmp_path)
    gate = Gate("touchosc-in", "osc", "in", options={"transport": "udp", "port": 8000, "bind": "0.0.0.0"})
    pad = Gate("pad", "gamepad", "two-way", device="my pad")
    save_gates(path, [gate, pad])
    assert load_gates(path) == {"touchosc-in": gate, "pad": pad}


def test_save_keeps_comments(tmp_path: Path) -> None:
    path = tmp_path / "protokol.toml"
    path.write_text(
        '# gates of this show\n[gates.a]\n# the desk\nprotocol = "osc"\ndirection = "in"\nport = 1\n',
        encoding="utf-8",
    )
    save_gates(path, [Gate("a", "osc", "in", options={"port": 2}), Gate("b", "osc", "out")])
    text = path.read_text(encoding="utf-8")
    assert "# gates of this show" in text
    assert "# the desk" in text
    assert load_gates(path)["a"].options == {"port": 2}
    assert "b" in load_gates(path)


def test_save_removes_dropped_gates(tmp_path: Path) -> None:
    path = tmp_path / "protokol.toml"
    save_gates(path, [Gate("a", "osc", "in"), Gate("b", "osc", "out")])
    save_gates(path, [Gate("b", "osc", "out")])
    assert list(load_gates(path)) == ["b"]


@pytest.mark.parametrize(
    "text",
    [
        "[gates.a\nprotocol = 'osc'",
        "[gates.a]\nprotocol = 'osc'\ndirection = 'sideways'\n",
        "[gates.a]\ndirection = 'in'\n",
        "[gates.a]\nprotocol = 'osc'\ndirection = 'in'\ndevice = 3\n",
        "gates = 'x'\n",
    ],
)
def test_malformed_file_raises_gate_file_error(tmp_path: Path, text: str) -> None:
    path = tmp_path / "protokol.toml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(GateFileError, match="protokol.toml"):
        load_gates(path)


# -- comments survive a rename or delete --------------------------------------------

COMMENTED = """# Gates for the show

# The lighting desk, front of house
[gates.desk]
protocol = "osc"
direction = "out" # sends cues

# Phones in the audience
[gates.phones]
protocol = "osc"
direction = "in"

# Last one
[gates.tail]
protocol = "osc"
direction = "in"
"""


def _commented(tmp_path: Path) -> Path:
    path = tmp_path / "gates.toml"
    path.write_text(COMMENTED, encoding="utf-8")
    return path


def test_rename_keeps_place_and_comments(tmp_path: Path) -> None:
    path = _commented(tmp_path)
    desk = load_gates(path)["desk"]
    write_gate(path, dataclasses.replace(desk, name="console"), replaces="desk")
    assert path.read_text(encoding="utf-8") == COMMENTED.replace("[gates.desk]", "[gates.console]")


def test_rename_to_a_name_that_needs_quotes(tmp_path: Path) -> None:
    path = _commented(tmp_path)
    desk = load_gates(path)["desk"]
    write_gate(path, dataclasses.replace(desk, name="desk 2"), replaces="desk")
    assert '[gates."desk 2"]' in path.read_text(encoding="utf-8")
    assert list(load_gates(path)) == ["desk 2", "phones", "tail"]


def test_rename_with_changed_options_keeps_comments(tmp_path: Path) -> None:
    path = _commented(tmp_path)
    desk = load_gates(path)["desk"]
    write_gate(path, dataclasses.replace(desk, name="console", direction="in"), replaces="desk")
    text = path.read_text(encoding="utf-8")
    assert "# The lighting desk, front of house\n[gates.console]" in text
    assert "# Phones in the audience\n[gates.phones]" in text
    assert load_gates(path)["console"].direction == "in"


def test_delete_keeps_the_next_gates_comment(tmp_path: Path) -> None:
    path = _commented(tmp_path)
    remove_gate(path, "desk")
    assert path.read_text(encoding="utf-8") == (
        "# Gates for the show\n\n"
        '# Phones in the audience\n[gates.phones]\nprotocol = "osc"\ndirection = "in"\n\n'
        '# Last one\n[gates.tail]\nprotocol = "osc"\ndirection = "in"\n'
    )


def test_delete_the_last_gate_keeps_the_rest(tmp_path: Path) -> None:
    path = _commented(tmp_path)
    remove_gate(path, "tail")
    text = path.read_text(encoding="utf-8")
    assert "# Last one" not in text
    assert text.endswith('[gates.phones]\nprotocol = "osc"\ndirection = "in"\n')
    assert list(load_gates(path)) == ["desk", "phones"]


def test_delete_a_quoted_name(tmp_path: Path) -> None:
    path = tmp_path / "gates.toml"
    path.write_text('[gates."a b"]\nprotocol = "osc"\ndirection = "in"\n', encoding="utf-8")
    remove_gate(path, "a b")
    assert load_gates(path) == {}


def test_delete_keeps_a_comment_ending_the_file(tmp_path: Path) -> None:
    path = _commented(tmp_path)
    path.write_text(COMMENTED + "\n# end of show gates\n", encoding="utf-8")
    remove_gate(path, "tail")
    assert path.read_text(encoding="utf-8").endswith('direction = "in"\n\n# end of show gates\n')
