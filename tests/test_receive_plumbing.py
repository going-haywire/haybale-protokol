"""Receive plumbing: bindings deliver accepted messages to a node's flow without stalling a Line."""

import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from haybale_protokol.dispatch import ReceiveDispatchSettings, event_source_for, resolve_dispatch
from haybale_protokol.drivers import Message
from haybale_protokol.gates import Gate, gate_file_path, save_gates
from haybale_protokol.receive import ReceiveBinding
from haybale_protokol.states.protokol_state import ProtokolState
from haywire.core.execution import QueueMode
from haywire.core.execution.event_source import CallbackEvent
from tests.fakes import FakeDriver


@pytest.fixture
def setup(tmp_path: Path) -> Iterator[tuple[ProtokolState, FakeDriver]]:
    state = ProtokolState()
    state.project_root = tmp_path
    state.grace_s = lambda: 0.0
    driver = FakeDriver()
    state.register_driver(driver)
    save_gates(gate_file_path(tmp_path), [Gate("in", "fake", "in")])
    yield state, driver
    state.on_disable()


def _accept_numbers(message: Message) -> dict[str, Any] | None:
    if message.address.startswith("/n"):
        return {"value": message.args[0]}
    return None


def _wait(predicate: Any, timeout: float = 1.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.005)
    return predicate()


@pytest.mark.parametrize("block", [False, True])
def test_binding_fires_accepted_messages_only(setup: tuple[ProtokolState, FakeDriver], block: bool) -> None:
    state, driver = setup
    fired: list[dict[str, Any]] = []
    binding = ReceiveBinding(state, "in", _accept_numbers, fired.append, start_value=False, block=block)
    assert binding.status == "listening on in"
    driver.connections[0].push("/n", 1)
    driver.connections[0].push("/other", 2)
    driver.connections[0].push("/n", 3)
    assert _wait(lambda: len(fired) == 2)
    assert fired == [{"value": 1}, {"value": 3}]
    binding.close()


def test_start_value_fires_cache_once(setup: tuple[ProtokolState, FakeDriver]) -> None:
    state, driver = setup
    keeper = ReceiveBinding(state, "in", _accept_numbers, lambda p: None, start_value=False, block=False)
    driver.connections[0].push("/n", 1)
    driver.connections[0].push("/n", 2)
    driver.connections[0].push("/other", 9)
    fired: list[dict[str, Any]] = []
    binding = ReceiveBinding(state, "in", _accept_numbers, fired.append, start_value=True, block=False)
    assert fired == [{"value": 2}]
    binding.close()
    keeper.close()


def test_start_value_off_fires_nothing_at_start(setup: tuple[ProtokolState, FakeDriver]) -> None:
    state, driver = setup
    keeper = ReceiveBinding(state, "in", _accept_numbers, lambda p: None, start_value=False, block=False)
    driver.connections[0].push("/n", 1)
    fired: list[dict[str, Any]] = []
    binding = ReceiveBinding(state, "in", _accept_numbers, fired.append, start_value=False, block=False)
    assert fired == []
    binding.close()
    keeper.close()


@pytest.mark.parametrize("block", [False, True])
def test_close_releases_line(setup: tuple[ProtokolState, FakeDriver], block: bool) -> None:
    state, driver = setup
    binding = ReceiveBinding(state, "in", _accept_numbers, lambda p: None, start_value=False, block=block)
    binding.close()
    binding.close()
    assert state.lines() == []
    assert driver.connections[0].closed


def test_unknown_gate_status(setup: tuple[ProtokolState, FakeDriver]) -> None:
    state, _ = setup
    binding = ReceiveBinding(state, "nope", _accept_numbers, lambda p: None, start_value=True, block=True)
    assert binding.status == "no gate named 'nope'"
    binding.close()


def test_fire_never_blocks_line_thread(setup: tuple[ProtokolState, FakeDriver]) -> None:
    state, driver = setup
    release = threading.Event()
    fired: list[dict[str, Any]] = []

    def slow_fire(payload: dict[str, Any]) -> None:
        release.wait(2.0)
        fired.append(payload)

    binding = ReceiveBinding(state, "in", _accept_numbers, slow_fire, start_value=False, block=True)
    started = time.monotonic()
    for i in range(1000):
        driver.connections[0].push("/n", i)
    assert time.monotonic() - started < 0.5, "the line thread waited on a slow flow"
    release.set()
    assert _wait(lambda: len(fired) == 1000, timeout=2.0)
    assert [p["value"] for p in fired] == list(range(1000))
    binding.close()


def test_block_overflow_is_counted(setup: tuple[ProtokolState, FakeDriver]) -> None:
    state, driver = setup
    release = threading.Event()
    binding = ReceiveBinding(
        state, "in", _accept_numbers, lambda p: release.wait(2.0), start_value=False, block=True, capacity=4
    )
    for i in range(20):
        driver.connections[0].push("/n", i)
    assert binding.dropped >= 15
    assert "dropped" in binding.status
    release.set()
    binding.close()


def test_resolve_dispatch_auto_follows_kind() -> None:
    settings = ReceiveDispatchSettings()
    assert resolve_dispatch(settings, stream=True) == (QueueMode.DROP, 1, True)
    assert resolve_dispatch(settings, stream=False) == (QueueMode.BLOCK, 100, False)


def test_event_source_for_node() -> None:
    source = event_source_for("node_1", QueueMode.DROP, 1)
    assert isinstance(source, CallbackEvent)
    assert source.event_name == "node_1"
    assert source.queue_mode is QueueMode.DROP
    assert source.max_queue_size == 1
