"""The device watch: present Devices checked about once a second, changes reported (design §10.6.1)."""

import gc
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

from haybale_protokol.devices import Device, device_list_path, save_devices
from haybale_protokol.gates import Gate, gate_file_path, save_gates
from haybale_protokol.states.protokol_state import ProtokolState
from tests.fakes import FakeDeviceDriver, FakeDriver

PORT = "Grid:Grid MIDI 1 28:0"


def _wait(predicate: object, timeout: float = 2.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():  # type: ignore[operator]
            return True
        time.sleep(0.01)
    return bool(predicate())  # type: ignore[operator]


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
    save_gates(gate_file_path(tmp_path), [Gate("grid-in", "fakedev", "in", device="Grid")])
    state.register_driver(fake)
    return fake


class Counter:
    def __init__(self) -> None:
        self.calls = 0
        self.threads: set[str] = set()

    def __call__(self) -> None:
        self.calls += 1
        self.threads.add(threading.current_thread().name)

    def method(self) -> None:
        self()


def test_watch_reports_a_device_going_and_coming_back(
    state: ProtokolState, driver: FakeDeviceDriver
) -> None:
    assert state.health("grid-in").state == "closed"
    seen = Counter()
    state.watch_health(seen)
    driver.present = []
    assert _wait(lambda: state.health("grid-in").state == "not plugged in")
    assert _wait(lambda: seen.calls >= 1)
    calls = seen.calls
    driver.present = [PORT]
    assert _wait(lambda: state.health("grid-in").state == "closed")
    assert _wait(lambda: seen.calls > calls)


def test_listeners_run_on_the_watch_thread(state: ProtokolState, driver: FakeDeviceDriver) -> None:
    seen = Counter()
    state.watch_health(seen)
    driver.present = []
    assert _wait(lambda: seen.calls >= 1)
    assert seen.threads == {"protokol-device-watch"}


def test_no_change_no_call(state: ProtokolState, driver: FakeDeviceDriver) -> None:
    state.health("grid-in")
    time.sleep(0.15)
    seen = Counter()
    state.watch_health(seen)
    listings = driver.listings
    time.sleep(0.3)
    assert driver.listings > listings, "the watch keeps checking"
    assert seen.calls == 0


def test_refresh_checks_at_once(state: ProtokolState, driver: FakeDeviceDriver) -> None:
    state.watch_s = lambda: 30.0
    state.health("grid-in")
    driver.present = []
    state.refresh_devices()
    assert state.health("grid-in").state == "not plugged in"


def test_unwatch_stops_calls(state: ProtokolState, driver: FakeDeviceDriver) -> None:
    seen = Counter()
    unwatch = state.watch_health(seen)
    unwatch()
    driver.present = []
    state.refresh_devices()
    time.sleep(0.2)
    assert seen.calls == 0


def test_a_dead_bound_listener_is_dropped(state: ProtokolState, driver: FakeDeviceDriver) -> None:
    """A node's listener must not keep the node alive after it is deleted."""
    seen = Counter()
    state.watch_health(seen.method)
    del seen
    gc.collect()
    driver.present = []
    state.refresh_devices()
    time.sleep(0.2)  # nothing to assert but that no call crashes the watch
    assert state.health("grid-in").state == "not plugged in"


def test_other_changes_are_reported_too(
    state: ProtokolState, driver: FakeDeviceDriver, tmp_path: Path
) -> None:
    """A gate saved or a Line opened changes health too; listeners hear of it, off the caller's thread."""
    seen = Counter()
    state.watch_health(seen)
    assert state.save_gate(Gate("grid-out", "fakedev", "out", device="Grid")) is None
    assert _wait(lambda: seen.calls >= 1)
    assert seen.threads == {"protokol-device-watch"}


def test_watch_lists_nothing_without_device_gates(state: ProtokolState, tmp_path: Path) -> None:
    fake = FakeDeviceDriver(present=[PORT])
    state.register_driver(fake)
    state.register_driver(FakeDriver())
    save_gates(gate_file_path(tmp_path), [Gate("desk", "fake", "in", options={"port": 9000})])
    time.sleep(0.3)
    assert fake.listings == 0


def test_on_disable_stops_the_watch(state: ProtokolState, driver: FakeDeviceDriver) -> None:
    state.watch_health(Counter())
    thread = state._watch
    assert thread is not None
    assert thread.is_alive()
    state.on_disable()
    assert not thread.is_alive()


def test_unregister_closes_the_drivers_probes(state: ProtokolState, driver: FakeDeviceDriver) -> None:
    closed: list[bool] = []
    driver.close = lambda: closed.append(True)  # type: ignore[attr-defined]
    state.unregister_driver("fakedev")
    assert closed == [True]
