"""Editing gates through ProtokolState: validated by the driver, comments kept."""

from pathlib import Path
from typing import Any

import pytest

from haybale_protokol.gates import Gate, gate_file_path, load_gates
from haybale_protokol.states.protokol_state import ProtokolState
from tests.fakes import FakeDriver


class StrictDriver(FakeDriver):
    def line_key(self, gate: Gate, device: Any) -> Any:
        if "port" not in gate.options:
            raise ValueError("needs a port")
        return super().line_key(gate, device)


@pytest.fixture
def state(tmp_path: Path) -> ProtokolState:
    protokol = ProtokolState()
    protokol.project_root = tmp_path
    protokol.register_driver(StrictDriver())
    return protokol


def _file(tmp_path: Path) -> Path:
    return gate_file_path(tmp_path)


def test_save_gate_validates_through_driver(state: ProtokolState, tmp_path: Path) -> None:
    assert state.save_gate(Gate("a", "fake", "in")) == "needs a port"
    assert not _file(tmp_path).exists()


def test_save_gate_keeps_comments_and_signals(state: ProtokolState, tmp_path: Path) -> None:
    path = _file(tmp_path)
    path.parent.mkdir(parents=True)
    text = '# show gates\n[gates.keep]\nprotocol = "fake"\ndirection = "in"\nport = 1\n'
    path.write_text(text, encoding="utf-8")
    calls: list[int] = []
    state._changed = lambda: calls.append(1)  # type: ignore[method-assign]
    assert state.save_gate(Gate("new", "fake", "out", options={"port": 2})) is None
    assert "# show gates" in path.read_text(encoding="utf-8")
    assert set(load_gates(path)) == {"keep", "new"}
    assert calls
    assert state.gates()["new"].options == {"port": 2}


def test_rename_replaces_old_entry(state: ProtokolState, tmp_path: Path) -> None:
    state.save_gate(Gate("a", "fake", "in", options={"port": 1}))
    assert state.save_gate(Gate("b", "fake", "in", options={"port": 1}), replaces="a") is None
    assert set(load_gates(_file(tmp_path))) == {"b"}


def test_duplicate_name_refused(state: ProtokolState) -> None:
    state.save_gate(Gate("a", "fake", "in", options={"port": 1}))
    assert state.save_gate(Gate("a", "fake", "in", options={"port": 2})) == "a gate named 'a' already exists"
    assert state.save_gate(Gate("a", "fake", "in", options={"port": 2}), replaces="a") is None


@pytest.mark.parametrize("name", ["", "with space", "a/b", "~x"])
def test_bad_name_refused(state: ProtokolState, name: str) -> None:
    result = state.save_gate(Gate(name, "fake", "in", options={"port": 1}))
    assert result is not None
    assert "name" in result


def test_delete_gate(state: ProtokolState, tmp_path: Path) -> None:
    state.save_gate(Gate("a", "fake", "in", options={"port": 1}))
    state.save_gate(Gate("b", "fake", "in", options={"port": 2}))
    state.delete_gate("a")
    assert set(load_gates(_file(tmp_path))) == {"b"}


def test_unknown_protocol_saved_unvalidated(state: ProtokolState, tmp_path: Path) -> None:
    assert state.save_gate(Gate("m", "midi", "in", device="desk")) is None
    assert load_gates(_file(tmp_path))["m"].device == "desk"


def test_malformed_gate_survives_an_edit(state: ProtokolState, tmp_path: Path) -> None:
    path = _file(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text('[gates.bad]\nprotocol = "fake"\ndirection = "sideways"\n', encoding="utf-8")
    assert state.save_gate(Gate("ok", "fake", "in", options={"port": 1})) is None
    assert "[gates.bad]" in path.read_text(encoding="utf-8")
