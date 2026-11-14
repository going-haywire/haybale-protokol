"""Monitor taps: a bounded, never-blocking view of a Line, in both directions."""

import time
from collections.abc import Iterator
from pathlib import Path

import pytest

from haybale_protokol.drivers import Message
from haybale_protokol.gates import Gate, gate_file_path, save_gates
from haybale_protokol.states.protokol_state import LineUse, ProtokolState
from haybale_protokol.taps import MONITOR_BUFFER, Tap
from tests.fakes import FakeDriver


@pytest.fixture
def setup(tmp_path: Path) -> Iterator[tuple[ProtokolState, FakeDriver]]:
    state = ProtokolState()
    state.project_root = tmp_path
    state.grace_s = lambda: 0.0
    driver = FakeDriver()
    state.register_driver(driver)
    save_gates(
        gate_file_path(tmp_path),
        [Gate("in", "fake", "in"), Gate("out", "fake", "out", options={"port": 2}),
         Gate("both", "fake", "two-way", options={"port": 3})],
    )
    yield state, driver
    state.on_disable()


def _tap(state: ProtokolState, name: str, *, open_line: bool = True) -> Tap:
    tap = state.tap(state.gates()[name], open_line=open_line)
    assert isinstance(tap, Tap), tap
    return tap


def test_tap_collects_and_keeps_order(setup: tuple[ProtokolState, FakeDriver]) -> None:
    state, driver = setup
    tap = _tap(state, "in")
    for i in range(3):
        driver.connections[0].push("/a", i)
    seen = [(e.message.args, e.direction) for e in tap.messages()]
    assert seen == [((0,), "in"), ((1,), "in"), ((2,), "in")]
    assert tap.received == 3
    tap.close()


def test_tap_never_blocks_and_counts_drops(setup: tuple[ProtokolState, FakeDriver]) -> None:
    state, driver = setup
    tap = _tap(state, "in")
    started = time.monotonic()
    for i in range(10_000):
        driver.connections[0].push("/a", i)
    assert time.monotonic() - started < 0.5
    assert len(tap.messages()) == MONITOR_BUFFER
    assert tap.dropped == 10_000 - MONITOR_BUFFER
    assert tap.messages()[-1].message.args == (9999,)
    tap.close()


def test_tap_view_mode_needs_open_line(setup: tuple[ProtokolState, FakeDriver]) -> None:
    state, _ = setup
    assert state.tap(state.gates()["in"], open_line=False) == "line not open"
    keeper = state.use("in", "in")
    assert isinstance(keeper, LineUse)
    tap = _tap(state, "in", open_line=False)
    assert tap.use.line is keeper.line
    tap.close()
    keeper.release()


def test_tap_close_releases_line(setup: tuple[ProtokolState, FakeDriver]) -> None:
    state, driver = setup
    tap = _tap(state, "in")
    tap.close()
    tap.close()
    assert state.lines() == []
    assert driver.connections[0].closed


def test_paused_tap_counts_but_keeps_nothing(setup: tuple[ProtokolState, FakeDriver]) -> None:
    state, driver = setup
    tap = _tap(state, "in")
    tap.paused = True
    driver.connections[0].push("/a", 1)
    assert tap.received == 1
    assert tap.messages() == []
    tap.clear()
    tap.close()


def test_outbound_messages_reach_taps_marked_out(setup: tuple[ProtokolState, FakeDriver]) -> None:
    state, driver = setup
    out_tap = _tap(state, "out")
    sender = state.use("out", "out")
    assert isinstance(sender, LineUse)
    assert sender.line.send(Message("/x", (1,), 0.0))
    assert [(e.message.address, e.direction) for e in out_tap.messages()] == [("/x", "out")]
    both_tap = _tap(state, "both")
    both_sender = state.use("both", "out")
    assert isinstance(both_sender, LineUse)
    both_sender.line.send(Message("/y", (), 0.0))
    both_sender.line.connection.push("/z")  # type: ignore[attr-defined]
    assert [(e.message.address, e.direction) for e in both_tap.messages()] == [("/y", "out"), ("/z", "in")]
    for closable in (out_tap, both_tap):
        closable.close()
    sender.release()
    both_sender.release()


def test_tap_on_ad_hoc_gate_opens_line(setup: tuple[ProtokolState, FakeDriver]) -> None:
    state, driver = setup
    ad_hoc = Gate("~fake in 9", "fake", "in", options={"port": 9})
    tap = state.tap(ad_hoc, open_line=True)
    assert isinstance(tap, Tap)
    assert tap.use.line.is_open
    assert state.line_of(ad_hoc) is tap.use.line
    tap.close()
    assert state.line_of(ad_hoc) is None
