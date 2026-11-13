"""ProtokolState: drivers, the Gate file, and counted uses of Lines."""

import os
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from haybale_protokol.devices import Device, device_list_path, save_devices
from haybale_protokol.drivers import Message
from haybale_protokol.gates import Gate, gate_file_path, save_gates
from haybale_protokol.states.protokol_state import LineUse, ProtokolState
from tests.fakes import FakeDriver


@pytest.fixture
def state(tmp_path: Path) -> Iterator[ProtokolState]:
    protokol = ProtokolState()
    protokol.project_root = tmp_path
    protokol.grace_s = lambda: 0.0
    yield protokol
    protokol.on_disable()


def _gates(root: Path, *gates: Gate) -> None:
    save_gates(gate_file_path(root), gates)


def test_missing_gate_is_status_not_error(state: ProtokolState) -> None:
    assert state.use("nope", "in") == "no gate named 'nope'"


def test_gate_file_error_is_status(state: ProtokolState, tmp_path: Path) -> None:
    path = gate_file_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text("[gates.a\n", encoding="utf-8")
    result = state.use("a", "in")
    assert isinstance(result, str)
    assert result.startswith("gate file: ")
    assert state.gate_file_error is not None


def test_protocol_not_installed(state: ProtokolState, tmp_path: Path) -> None:
    _gates(tmp_path, Gate("a", "fake", "in"))
    assert state.use("a", "in") == "protocol not installed"


def test_direction_mismatch_is_status(state: ProtokolState, tmp_path: Path) -> None:
    state.register_driver(FakeDriver())
    _gates(tmp_path, Gate("a", "fake", "in"), Gate("b", "fake", "out"), Gate("c", "fake", "two-way"))
    assert state.use("a", "out") == "'a' is an input gate"
    assert state.use("b", "in") == "'b' is an output gate"
    assert isinstance(state.use("c", "in"), LineUse)


def test_unbound_gate(state: ProtokolState, tmp_path: Path) -> None:
    state.register_driver(FakeDriver())
    _gates(tmp_path, Gate("a", "fake", "in", device="desk"))
    assert state.use("a", "in") == "unbound gate: no device 'desk' on this machine"
    save_devices(device_list_path(), [Device("desk", "fake", "IAC 1")])
    assert isinstance(state.use("a", "in"), LineUse)


def test_two_uses_share_one_line(state: ProtokolState, tmp_path: Path) -> None:
    driver = FakeDriver()
    state.register_driver(driver)
    port = {"port": 1}
    _gates(tmp_path, Gate("a", "fake", "in", options=port), Gate("b", "fake", "in", options=port))
    seen: list[str] = []
    first = state.use("a", "in", lambda m: seen.append("a"))
    second = state.use("b", "in", lambda m: seen.append("b"))
    assert isinstance(first, LineUse)
    assert isinstance(second, LineUse)
    assert first.line is second.line
    assert len(driver.connections) == 1
    driver.connections[0].push("/x")
    assert sorted(seen) == ["a", "b"]
    first.release()
    first.release()
    assert first.line.users == 1
    second.release()
    assert state.lines() == []


def test_line_reopens_after_close(state: ProtokolState, tmp_path: Path) -> None:
    driver = FakeDriver()
    state.register_driver(driver)
    _gates(tmp_path, Gate("a", "fake", "in"))
    use = state.use("a", "in")
    assert isinstance(use, LineUse)
    use.release()
    again = state.use("a", "in")
    assert isinstance(again, LineUse)
    assert again.line.is_open
    assert len(driver.connections) == 2


def test_open_failure_is_status(state: ProtokolState, tmp_path: Path) -> None:
    state.register_driver(FakeDriver(fail="Address already in use"))
    _gates(tmp_path, Gate("a", "fake", "in"))
    assert state.use("a", "in") == "cannot open: Address already in use"
    assert state.lines() == []


def test_unregister_driver_closes_lines(state: ProtokolState, tmp_path: Path) -> None:
    driver = FakeDriver()
    state.register_driver(driver)
    _gates(tmp_path, Gate("a", "fake", "in"))
    use = state.use("a", "in")
    assert isinstance(use, LineUse)
    state.unregister_driver("fake")
    assert driver.connections[0].closed
    assert state.lines() == []
    assert state.use("a", "in") == "protocol not installed"


def test_gate_file_edit_is_picked_up(state: ProtokolState, tmp_path: Path) -> None:
    state.register_driver(FakeDriver())
    _gates(tmp_path, Gate("a", "fake", "in", options={"port": 1}))
    assert state.gates()["a"].options["port"] == 1
    _gates(tmp_path, Gate("a", "fake", "in", options={"port": 2}))
    path = gate_file_path(tmp_path)
    later = time.time() + 5
    os.utime(path, (later, later))
    assert state.gates()["a"].options["port"] == 2


def test_send_through_use(state: ProtokolState, tmp_path: Path) -> None:
    driver = FakeDriver()
    state.register_driver(driver)
    _gates(tmp_path, Gate("o", "fake", "out"))
    use = state.use("o", "out")
    assert isinstance(use, LineUse)
    assert use.line.send(Message("/x", (1,), 0.0))
    assert [m.address for m in driver.connections[0].sent] == ["/x"]


@pytest.mark.integration
def test_grace_comes_from_settings(library_system: Any) -> None:
    from haywire.core.di.context import get_library_state_container

    state = get_library_state_container().get(ProtokolState)
    assert state is not None
    from haybale_protokol.settings.protokol_settings import ProtokolSettings

    assert float(ProtokolSettings().grace_period_s) == 2.0, "read from the setting, not the fallback"
    assert state.grace_s() == 2.0
