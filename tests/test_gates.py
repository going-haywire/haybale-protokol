"""The Gate file: reading, writing, and refusing a malformed one."""

from pathlib import Path

import pytest

from haybale_protokol.gates import Gate, GateFileError, gate_file_path, load_gates, save_gates


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
