"""Gate health: one live state and reason per gate, the source every view reads (design §10.2)."""

from collections.abc import Iterator
from pathlib import Path

import pytest

from haybale_protokol.devices import Device, device_list_path, save_devices
from haybale_protokol.gate_health import GateHealth
from haybale_protokol.gates import Gate, gate_file_path, save_gates
from haybale_protokol.line_use import LineUse
from haybale_protokol.states.protokol_state import ProtokolState
from tests.fakes import FakeDeviceDriver, FakeDriver


@pytest.fixture
def state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[ProtokolState]:
    monkeypatch.setenv("HOME", str(tmp_path))
    protokol = ProtokolState()
    protokol.project_root = tmp_path
    protokol.grace_s = lambda: 0.0
    yield protokol
    protokol.on_disable()


@pytest.fixture
def midiish(state: ProtokolState, tmp_path: Path) -> FakeDeviceDriver:
    """A device driver whose Grid is plugged in, a Device for it, and an input gate on it."""
    driver = FakeDeviceDriver(present=["Grid:Grid MIDI 1 28:0"])
    state.register_driver(driver)
    save_devices(device_list_path(), [Device("Grid", "fakedev", "Grid:Grid MIDI 1 28:0")])
    save_gates(gate_file_path(tmp_path), [Gate("grid-in", "fakedev", "in", device="Grid")])
    return driver


def test_healthy_states() -> None:
    assert GateHealth("working", "").healthy
    assert GateHealth("closed", "closed").healthy
    for name in ("unbound", "not plugged in", "error"):
        assert not GateHealth(name, "x").healthy  # type: ignore[arg-type]


def test_closed_when_nothing_uses_it(state: ProtokolState, midiish: FakeDeviceDriver) -> None:
    assert state.health("grid-in") == GateHealth("closed", "closed")


def test_working_while_used(state: ProtokolState, midiish: FakeDeviceDriver) -> None:
    use = state.use("grid-in", "in")
    assert isinstance(use, LineUse)
    health = state.health("grid-in")
    assert health.state == "working"
    assert health.reason == "open · 1 users"
    use.release()
    assert state.health("grid-in").state == "closed"


def test_not_plugged_in(state: ProtokolState, midiish: FakeDeviceDriver) -> None:
    midiish.present = []
    assert state.health("grid-in") == GateHealth(
        "not plugged in", "'Grid' is not plugged in (port 'Grid:Grid MIDI 1 28:0')"
    )


def test_a_changed_os_suffix_still_counts_as_plugged_in(
    state: ProtokolState, midiish: FakeDeviceDriver
) -> None:
    """The driver's match_device decides, as when opening (ALSA renumbers ports on replug)."""
    midiish.present = ["Grid:Grid MIDI 1 32:0"]
    midiish.match_device = lambda os_id, names: names[0] if names else None  # type: ignore[attr-defined]
    assert state.health("grid-in").state == "closed"


def test_unbound(state: ProtokolState, midiish: FakeDeviceDriver) -> None:
    save_devices(device_list_path(), [])
    assert state.health("grid-in") == GateHealth("unbound", "unbound gate: no device 'Grid' on this machine")


def test_protocol_not_installed(state: ProtokolState, midiish: FakeDeviceDriver) -> None:
    state.unregister_driver("fakedev")
    assert state.health("grid-in") == GateHealth("error", "protocol not installed")


def test_unknown_gate(state: ProtokolState) -> None:
    assert state.health("nope") == GateHealth("error", "no gate named 'nope'")


def test_gate_file_error(state: ProtokolState, tmp_path: Path) -> None:
    path = gate_file_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("[gates.a\n", encoding="utf-8")
    health = state.health("a")
    assert health.state == "error"
    assert health.reason.startswith("gate file: ")


def test_open_failure_is_remembered_until_a_good_open(state: ProtokolState, tmp_path: Path) -> None:
    driver = FakeDriver(fail="port in use")
    state.register_driver(driver)
    save_gates(gate_file_path(tmp_path), [Gate("desk", "fake", "in", options={"port": 9000})])
    assert state.health("desk").state == "closed"
    assert state.use("desk", "in") == "cannot open: port in use"
    assert state.health("desk") == GateHealth("error", "cannot open: port in use")
    driver.fail = None
    use = state.use("desk", "in")
    assert isinstance(use, LineUse)
    assert state.health("desk").state == "working"
    use.release()
    assert state.health("desk").state == "closed"


def test_saving_the_gate_clears_its_open_failure(state: ProtokolState, tmp_path: Path) -> None:
    state.register_driver(FakeDriver(fail="port in use"))
    save_gates(gate_file_path(tmp_path), [Gate("desk", "fake", "in", options={"port": 9000})])
    state.use("desk", "in")
    assert state.health("desk").state == "error"
    assert state.save_gate(Gate("desk", "fake", "in", options={"port": 9001}), replaces="desk") is None
    assert state.health("desk").state == "closed"


def test_not_plugged_in_wins_over_the_open_failure_it_caused(
    state: ProtokolState, midiish: FakeDeviceDriver
) -> None:
    """Opening an absent port fails; health says why in the user's terms, and recovers on replug."""
    midiish.present = []
    assert isinstance(state.use("grid-in", "in"), str)
    assert state.health("grid-in").state == "not plugged in"
    midiish.present = ["Grid:Grid MIDI 1 28:0"]
    assert state.health("grid-in").state == "closed"


def test_network_gate_is_never_not_plugged_in(state: ProtokolState, tmp_path: Path) -> None:
    state.register_driver(FakeDriver())
    save_gates(gate_file_path(tmp_path), [Gate("desk", "fake", "out", options={"port": 9000})])
    assert state.health("desk").state == "closed"


def test_health_takes_a_gate_or_a_name(state: ProtokolState, midiish: FakeDeviceDriver) -> None:
    gate = state.gates()["grid-in"]
    assert state.health(gate) == state.health("grid-in")
