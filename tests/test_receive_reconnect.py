"""Receive reconnect: a binding waits for its Device and takes its Line again (design §10.5)."""

import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

from haybale_protokol.devices import Device, device_list_path, save_devices
from haybale_protokol.drivers import Message
from haybale_protokol.gates import Gate, gate_file_path, save_gates
from haybale_protokol.receive import ReceiveBinding
from haybale_protokol.states.protokol_state import ProtokolState
from tests.fakes import FakeDeviceDriver

PORT = "Grid:Grid MIDI 1 28:0"


def _wait(predicate: object, timeout: float = 3.0) -> bool:
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
    protokol.grace_s = lambda: 5.0  # long: a replug must never reuse the unplugged Line
    protokol.watch_s = lambda: 0.05
    yield protokol
    protokol.on_disable()


@pytest.fixture
def driver(state: ProtokolState, tmp_path: Path) -> FakeDeviceDriver:
    fake = FakeDeviceDriver(present=[PORT])
    save_devices(device_list_path(), [Device("Grid", "fakedev", PORT)])
    save_gates(
        gate_file_path(tmp_path),
        [Gate("grid-in", "fakedev", "in", device="Grid"), Gate("desk", "fakedev", "in", device="Desk")],
    )
    state.register_driver(fake)
    return fake


def _binding(state: ProtokolState, got: list[Message], gate: str = "grid-in") -> ReceiveBinding:
    return ReceiveBinding(
        state, gate, lambda m: {"m": m}, lambda p: got.append(p["m"]), start_value=False, block=False
    )


def _live(driver: FakeDeviceDriver) -> object:
    """The newest connection that started (the Line the binding listens on now)."""
    started = [c for c in driver.connections if c.starts and not c.closed]
    return started[-1] if started else None


def test_binding_waits_then_listens_when_device_appears(
    state: ProtokolState, driver: FakeDeviceDriver
) -> None:
    driver.present = []
    state.refresh_devices()
    got: list[Message] = []
    binding = _binding(state, got)
    try:
        assert not binding.is_bound
        assert binding.status == "waiting for 'Grid'"
        driver.present = [PORT]
        assert _wait(lambda: binding.is_bound)
        assert binding.status == "listening on grid-in"
        _live(driver).push("/cc", 1)  # type: ignore[attr-defined]
        assert _wait(lambda: len(got) == 1)
    finally:
        binding.close()


def test_unplug_mid_run_reconnects_on_a_fresh_line(state: ProtokolState, driver: FakeDeviceDriver) -> None:
    got: list[Message] = []
    binding = _binding(state, got)
    try:
        assert binding.is_bound
        first = _live(driver)
        driver.present = []
        assert _wait(lambda: binding.status == "waiting for 'Grid'")
        assert first.closed, "the unplugged Line is closed, not kept for its grace period"  # type: ignore[attr-defined]
        driver.present = [PORT]
        assert _wait(lambda: binding.is_bound)
        second = _live(driver)
        assert second is not first
        second.push("/cc", 2)  # type: ignore[attr-defined]
        assert _wait(lambda: [m.args for m in got] == [(2,)])
    finally:
        binding.close()


def test_close_while_waiting_leaves_no_user_or_thread(
    state: ProtokolState, driver: FakeDeviceDriver
) -> None:
    driver.present = []
    state.refresh_devices()
    binding = _binding(state, [])
    binding.close()
    driver.present = [PORT]
    state.refresh_devices()
    time.sleep(0.3)
    assert not binding.is_bound
    assert all(line.users == 0 for line in state.lines())
    assert not [t for t in threading.enumerate() if t.name.startswith("protokol-recv-reconnect")]


def test_close_during_a_reconnect_gives_the_line_back(
    state: ProtokolState, driver: FakeDeviceDriver
) -> None:
    """The reconnect thread may finish its use() after close(): it must release, not keep it."""
    driver.present = []
    state.refresh_devices()
    binding = _binding(state, [])
    opened = threading.Event()
    release = threading.Event()
    real_open = driver.open

    def slow_open(*args: object) -> object:
        opened.set()
        release.wait(2.0)
        return real_open(*args)  # type: ignore[arg-type]

    driver.open = slow_open  # type: ignore[method-assign]
    driver.present = [PORT]
    assert opened.wait(2.0)
    binding.close()
    release.set()
    assert _wait(
        lambda: not [t for t in threading.enumerate() if t.name.startswith("protokol-recv-reconnect")]
    )
    assert all(line.users == 0 for line in state.lines())


def test_two_bindings_on_one_gate_share_the_new_line(state: ProtokolState, driver: FakeDeviceDriver) -> None:
    driver.present = []
    state.refresh_devices()
    a, b = _binding(state, []), _binding(state, [])
    try:
        driver.present = [PORT]
        assert _wait(lambda: a.is_bound and b.is_bound)
        assert len({id(line) for line in state.lines() if line.users}) == 1
        assert next(line for line in state.lines() if line.users).users == 2
    finally:
        a.close()
        b.close()


def test_unbound_does_not_retry(state: ProtokolState, driver: FakeDeviceDriver) -> None:
    binding = _binding(state, [], gate="desk")
    try:
        assert binding.status == "unbound gate: no device 'Desk' on this machine"
        save_devices(device_list_path(), [Device("Grid", "fakedev", PORT), Device("Desk", "fakedev", PORT)])
        state.refresh_devices()
        time.sleep(0.3)
        assert not binding.is_bound
    finally:
        binding.close()


def test_on_status_is_called_when_the_binding_waits_and_listens_again(
    state: ProtokolState, driver: FakeDeviceDriver
) -> None:
    """A waiting node never fires, so its status must be pushed when the binding's changes."""
    seen: list[str] = []
    holder: dict[str, ReceiveBinding] = {}
    binding = ReceiveBinding(
        state,
        "grid-in",
        lambda m: {"m": m},
        lambda p: None,
        start_value=False,
        block=False,
        on_status=lambda: seen.append(holder["b"].status),
    )
    holder["b"] = binding
    try:
        driver.present = []
        assert _wait(lambda: seen[-1:] == ["waiting for 'Grid'"])
        driver.present = [PORT]
        assert _wait(lambda: seen[-1:] == ["listening on grid-in"])
    finally:
        binding.close()
