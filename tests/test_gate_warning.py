"""The gate badge: a node shows each of its gates that does not work, kept up to date (design §10.3)."""

import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from haybale_protokol.devices import Device, device_list_path, save_devices
from haybale_protokol.gate_warning import GATE_WARNING, GateBadge
from haybale_protokol.gates import Gate, gate_file_path, save_gates
from haybale_protokol.states.protokol_state import ProtokolState
from tests.fakes import FakeDeviceDriver

PORT = "Grid:Grid MIDI 1 28:0"


def _wait(predicate: Any, timeout: float = 2.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return bool(predicate())


class Wrapper:
    def __init__(self) -> None:
        self.warnings: dict[str, list[str]] = {}

    def replace_warnings(self, kind: str, warnings: Any) -> bool:
        self.warnings[kind] = [w.message for w in warnings]
        return True


class Node:
    def __init__(self, gate: str) -> None:
        self.gate = gate
        self.wrapper = Wrapper()

    def value(self, port: str) -> Any:
        assert port == "gate"
        return self.gate

    @property
    def badges(self) -> list[str]:
        return self.wrapper.warnings.get(GATE_WARNING, [])


@pytest.fixture
def state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[ProtokolState]:
    monkeypatch.setenv("HOME", str(tmp_path))
    protokol = ProtokolState()
    protokol.project_root = tmp_path
    protokol.grace_s = lambda: 0.0
    protokol.watch_s = lambda: 0.05
    yield protokol
    protokol.on_disable()


@pytest.fixture
def driver(state: ProtokolState, tmp_path: Path) -> FakeDeviceDriver:
    fake = FakeDeviceDriver(present=[PORT])
    save_devices(device_list_path(), [Device("Grid", "fakedev", PORT)])
    save_gates(
        gate_file_path(tmp_path),
        [Gate("grid-in", "fakedev", "in", device="Grid"), Gate("pads", "fakedev", "in", device="Pads")],
    )
    state.register_driver(fake)
    return fake


def test_no_badge_for_a_closed_gate(state: ProtokolState, driver: FakeDeviceDriver) -> None:
    node = Node("grid-in")
    GateBadge(node, lambda: state).start()
    assert node.badges == []


def test_badge_appears_when_unplugged_and_goes_on_replug(
    state: ProtokolState, driver: FakeDeviceDriver
) -> None:
    node = Node("grid-in")
    badge = GateBadge(node, lambda: state)
    badge.start()
    driver.present = []
    assert _wait(lambda: node.badges == ["grid-in: 'Grid' is not plugged in (port 'Grid:Grid MIDI 1 28:0')"])
    driver.present = [PORT]
    assert _wait(lambda: node.badges == [])
    badge.stop()


def test_badge_names_each_unhealthy_gate(state: ProtokolState, driver: FakeDeviceDriver) -> None:
    node = Node("grid-in, pads, nope")
    GateBadge(node, lambda: state).start()
    assert node.badges == [
        "pads: unbound gate: no device 'Pads' on this machine",
        "no gate named 'nope'",
    ]


def test_refresh_follows_the_gate_setting(state: ProtokolState, driver: FakeDeviceDriver) -> None:
    node = Node("grid-in")
    badge = GateBadge(node, lambda: state)
    badge.start()
    node.gate = "pads"
    badge.refresh()
    assert node.badges == ["pads: unbound gate: no device 'Pads' on this machine"]
    node.gate = ""
    badge.refresh()
    assert node.badges == []


def test_stop_ends_updates(state: ProtokolState, driver: FakeDeviceDriver) -> None:
    node = Node("grid-in")
    badge = GateBadge(node, lambda: state)
    badge.start()
    badge.stop()
    time.sleep(0.2)  # a notification already under way when stop() ran may still arrive once
    node.wrapper.warnings.clear()
    driver.present = []
    state.refresh_devices()
    time.sleep(0.2)
    assert node.badges == []


def test_without_protokol_it_does_nothing() -> None:
    def missing() -> ProtokolState:
        raise RuntimeError("haybale-protokol is not enabled")

    node = Node("grid-in")
    GateBadge(node, missing).start()
    assert node.badges == []
