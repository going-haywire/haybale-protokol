"""Gamepad Event and Send Rumble, on a fake SDL through the app's ProtokolState."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from haybale_protokol.devices import Device, device_list_path, save_devices
from haybale_protokol.gates import Gate
from haybale_protokol_gamepad.gamepad_pins import FILTER_WARNING
from haybale_protokol_gamepad.nodes.gamepad_event import GamepadEventNode
from haybale_protokol_gamepad.nodes.send_rumble import SendRumbleNode
from haywire.core.graph.base import BaseGraph
from tests.gamepad.fake_sdl import XBOX, FakeBackend, FakePad
from tests.helpers import make_node
from tests.osc.graphs import protokol_project, record, running, wait_until

pytestmark = pytest.mark.integration

KIND_OUTLETS = {
    "axis": ["value"],
    "button": ["pressed"],
    "hat": ["hat"],
    "all": ["control", "index", "value", "pressed", "hat"],
}
KNOWN = {"index", *(o for outs in KIND_OUTLETS.values() for o in outs)}
PAD_GATE = Gate("pad", "gamepad", "two-way", device="pad")


def _receive(graph: Any, kind: str = "axis", index: int = 0, gate: str = "pad") -> Any:
    wrapper = make_node(graph, GamepadEventNode.class_identity.registry_key)
    node = wrapper.node
    node.ports["gate"].set_value(gate)
    node.ports["kind"].set_value(kind)
    node.ports["filter_index"].set_value(index)
    return wrapper


def _outlets(wrapper: Any) -> list[str]:
    outlets = [p for p in wrapper.node.ports.values() if p.is_outlet() and p.id in KNOWN]
    return [p.id for p in sorted(outlets, key=lambda p: p.order)]


def _plug(sdl: FakeBackend, state: Any, pad: FakePad | None = None) -> FakePad:
    pad = pad or FakePad()
    sdl.plug(pad)
    save_devices(device_list_path(), [Device("pad", "gamepad", XBOX)])
    assert wait_until(lambda: _refreshed(state) and state.health("pad").state == "closed")
    return pad


def _refreshed(state: Any) -> bool:
    """Re-check which Devices are present (as the refresh button does); always true, for wait_until."""
    state.refresh_devices()
    return True


@pytest.mark.parametrize("kind", list(KIND_OUTLETS))
def test_outlets_follow_the_kind(graph: BaseGraph, kind: str) -> None:
    assert _outlets(_receive(graph, kind=kind, index=0)) == KIND_OUTLETS[kind]


def test_index_outlet_for_any(graph: BaseGraph) -> None:
    wrapper = _receive(graph, kind="button", index=-1)
    assert _outlets(wrapper) == ["index", "pressed"]
    wrapper.node.ports["filter_index"].set_value(3)
    assert _outlets(wrapper) == ["pressed"]


def test_queue_mode_follows_the_kind(graph: BaseGraph) -> None:
    from haywire.core.execution import QueueMode

    wrapper = _receive(graph, kind="axis", index=1)
    wrapper.node.on_assembly()
    assert wrapper.node.event_subscription.queue_mode is QueueMode.DROP
    wrapper.node.ports["filter_index"].set_value(-1)
    wrapper.node.on_assembly()
    assert wrapper.node.event_subscription.queue_mode is QueueMode.BLOCK, "any axis: several sources"
    wrapper.node.ports["kind"].set_value("button")
    wrapper.node.ports["filter_index"].set_value(0)
    wrapper.node.on_assembly()
    assert wrapper.node.event_subscription.queue_mode is QueueMode.BLOCK


def test_an_index_no_control_has_shows_a_warning_badge(graph: BaseGraph) -> None:
    wrapper = _receive(graph, kind="axis", index=6)
    warnings = [w.message for w in wrapper.state.warnings if w.kind == FILTER_WARNING]
    assert warnings == ["Index must be −1 (any) or 0–5 for axis, not 6"]
    wrapper.node.ports["kind"].set_value("button")
    assert not wrapper.state.has_warning()


def test_receives_an_axis_with_its_start_value(graph: BaseGraph, tmp_path: Path, sdl: FakeBackend) -> None:
    wrapper = _receive(graph, kind="axis", index=1)
    runs = record(wrapper, "value", "from_gate")
    pad = FakePad()
    pad.axes[1] = -32768  # held up when the graph starts
    with protokol_project(tmp_path, PAD_GATE) as state:
        _plug(sdl, state, pad)
        with running(graph):
            assert wait_until(lambda: len(runs) >= 1)
            assert runs[0]["value"] == -1.0, "the state the pad reported when its Line opened"
            sdl.move(pad, 0, 32767)  # another axis: filtered out
            sdl.move(pad, 1, 16384)
            assert wait_until(lambda: runs[-1]["value"] == pytest.approx(0.5, abs=1e-4))
    assert {r["from_gate"] for r in runs} == {"pad"}
    assert all(r["value"] in (-1.0, pytest.approx(0.5, abs=1e-4)) for r in runs), "never axis 0"


def test_start_value_off_ignores_the_state_at_open(
    graph: BaseGraph, tmp_path: Path, sdl: FakeBackend
) -> None:
    wrapper = _receive(graph, kind="axis", index=1)
    wrapper.node.dispatch.start_value = "Off"
    runs = record(wrapper, "value")
    pad = FakePad()
    pad.axes[1] = -32768
    with protokol_project(tmp_path, PAD_GATE) as state:
        _plug(sdl, state, pad)
        with running(graph):
            assert wait_until(lambda: str(wrapper.node.value("status")).startswith("listening on"))
            sdl.move(pad, 1, 0)
            assert wait_until(lambda: len(runs) >= 1)
    assert [r["value"] for r in runs] == [0.0]


def test_receives_every_button_press(graph: BaseGraph, tmp_path: Path, sdl: FakeBackend) -> None:
    wrapper = _receive(graph, kind="button", index=-1)
    runs = record(wrapper, "index", "pressed")
    with protokol_project(tmp_path, PAD_GATE) as state:
        pad = _plug(sdl, state)
        with running(graph):
            assert wait_until(lambda: str(wrapper.node.value("status")).startswith("listening on"))
            sdl.press(pad, 0)
            sdl.press(pad, 0, False)
            sdl.press(pad, 3)
            assert wait_until(lambda: len(runs) >= 3)
    assert [(r["index"], r["pressed"]) for r in runs] == [(0, True), (0, False), (3, True)]


def test_all_says_which_kind(graph: BaseGraph, tmp_path: Path, sdl: FakeBackend) -> None:
    wrapper = _receive(graph, kind="all", index=0)
    runs = record(wrapper, "control", "index", "value", "pressed", "hat")
    wrapper.node.dispatch.start_value = "Off"
    with protokol_project(tmp_path, PAD_GATE) as state:
        pad = _plug(sdl, state)
        with running(graph):
            assert wait_until(lambda: str(wrapper.node.value("status")).startswith("listening on"))
            sdl.press(pad, 12)
            assert wait_until(lambda: len(runs) >= 2)
    assert [(r["control"], r["index"]) for r in runs[:2]] == [("button", 12), ("hat", 0)]
    assert (runs[0]["pressed"], runs[0]["value"]) == (True, 1.0)
    assert list(runs[1]["hat"]) == [0, 1]


def test_waits_for_an_unplugged_pad(graph: BaseGraph, tmp_path: Path, sdl: FakeBackend) -> None:
    save_devices(device_list_path(), [Device("pad", "gamepad", XBOX)])
    wrapper = _receive(graph, kind="button", index=0)
    runs = record(wrapper, "pressed")
    with protokol_project(tmp_path, PAD_GATE) as state, running(graph):
        state.refresh_devices()
        assert wait_until(lambda: str(wrapper.node.value("status")) == "waiting for 'pad'")
        pad = FakePad()
        sdl.plug(pad)
        assert wait_until(lambda: _refreshed(state) and "listening on" in str(wrapper.node.value("status")))
        sdl.press(pad, 0)
        assert wait_until(lambda: len(runs) >= 1)


def _rumble(graph: Any, gate: str = "pad") -> Any:
    node = make_node(graph, SendRumbleNode.class_identity.registry_key).node
    node.ports["gate"].set_value(gate)
    return node


def test_send_rumble(graph: BaseGraph, tmp_path: Path, sdl: FakeBackend) -> None:
    node = _rumble(graph)
    node.ports["low"].set_value(1.0)
    node.ports["high"].set_value(0.0)
    node.ports["duration"].set_value(300)
    context = MagicMock()
    with protokol_project(tmp_path, PAD_GATE) as state:
        pad = _plug(sdl, state)
        node.on_startup(context)
        node.worker(context)
        node.ports["high"].set_value(2.0)
        node.worker(context)
        status = str(node.value("status"))
        node.on_shutdown(context)
    assert pad.rumbles == [(0xFFFF, 0, 300)]
    assert status.startswith("sent 1 · dropped 1")
    assert "high must be 0…1, not 2.0" in status


def test_send_rumble_needs_a_two_way_gate(graph: BaseGraph, tmp_path: Path, sdl: FakeBackend) -> None:
    node = _rumble(graph)
    context = MagicMock()
    with protokol_project(tmp_path, Gate("pad", "gamepad", "in", device="pad")) as state:
        _plug(sdl, state)
        node.on_startup(context)
        node.worker(context)
        status = str(node.value("status"))
        node.on_shutdown(context)
    assert "'pad' is an input gate" in status
