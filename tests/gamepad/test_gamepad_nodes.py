"""Gamepad Event and Send Rumble, on a fake SDL through the app's ProtokolState."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from haybale_protokol.devices import Device, device_list_path, save_devices
from haybale_protokol.gates import Gate
from haybale_protokol_gamepad.nodes.gamepad_event import OUTPUTS_WARNING, GamepadEventNode
from haybale_protokol_gamepad.nodes.send_rumble import SendRumbleNode
from haywire.core.graph.base import BaseGraph
from haywire.core.types.enums import PortType
from tests.gamepad.fake_sdl import XBOX, FakeBackend, FakePad
from tests.helpers import make_node
from tests.osc.graphs import protokol_project, record, running, wait_until

pytestmark = pytest.mark.integration

PAD_GATE = Gate("pad", "gamepad", "two-way", device="pad")
FIXED = {"received", "from_gate", "changed"}


def _receive(graph: Any, outputs: str = "left_stick_vec", gate: str = "pad") -> Any:
    wrapper = make_node(graph, GamepadEventNode.class_identity.registry_key)
    node = wrapper.node
    node.ports["gate"].set_value(gate)
    node.ports["outputs"].set_value(outputs)
    node.shaping.dead_zone = 0.0
    node.shaping.y_up = False
    return wrapper


def _outlets(wrapper: Any) -> list[str]:
    outlets = [p for p in wrapper.node.ports.values() if p.is_outlet() and p.id not in FIXED]
    return [p.id for p in sorted(outlets, key=lambda p: p.order)]


def _refreshed(state: Any) -> bool:
    """Re-check which Devices are present (as the refresh button does); always true, for wait_until."""
    state.refresh_devices()
    return True


def _plug(sdl: FakeBackend, state: Any, pad: FakePad | None = None) -> FakePad:
    pad = pad or FakePad()
    sdl.plug(pad)
    save_devices(device_list_path(), [Device("pad", "gamepad", XBOX)])
    assert wait_until(lambda: _refreshed(state) and state.health("pad").state == "closed")
    return pad


def _listening(wrapper: Any) -> bool:
    return str(wrapper.node.report.status).startswith("listening on")


def test_outlets_follow_the_outputs_in_their_order(graph: BaseGraph) -> None:
    wrapper = _receive(graph, "a, left_stick_vec, left_stick_x")
    assert _outlets(wrapper) == ["a", "left_stick_vec", "left_stick_x"]
    types = {p.id: p.registry_id for p in wrapper.node.ports.values() if p.id in ("a", "left_stick_vec")}
    assert types == {"a": "BOOL", "left_stick_vec": "VEC2F"}
    wrapper.node.ports["outputs"].set_value("dpad_vec, right_trigger")
    assert _outlets(wrapper) == ["dpad_vec", "right_trigger"]


def test_status_is_off_the_card_by_default(graph: BaseGraph) -> None:
    wrapper = _receive(graph)
    assert "report.status" not in wrapper.node.ports
    assert hasattr(wrapper.node.report, "status")


def test_unknown_outputs_show_a_warning_badge(graph: BaseGraph) -> None:
    wrapper = _receive(graph, "a, nope")
    assert _outlets(wrapper) == ["a"]
    warnings = [w.message for w in wrapper.state.warnings if w.kind == OUTPUTS_WARNING]
    assert warnings == ["Unknown outputs: nope"]
    wrapper.node.ports["outputs"].set_value("a")
    assert not [w for w in wrapper.state.warnings if w.kind == OUTPUTS_WARNING]


def test_queue_mode_follows_the_outputs(graph: BaseGraph) -> None:
    from haywire.core.execution import QueueMode

    wrapper = _receive(graph, "left_stick_vec, right_trigger, dpad_vec")
    wrapper.node.on_assembly()
    assert wrapper.node.event_subscription.queue_mode is QueueMode.DROP, "values: the newest state is enough"
    wrapper.node.ports["outputs"].set_value("left_stick_vec, a")
    wrapper.node.on_assembly()
    assert wrapper.node.event_subscription.queue_mode is QueueMode.BLOCK, "a button: every press counts"


def test_a_stick_arrives_whole(graph: BaseGraph, tmp_path: Path, sdl: FakeBackend) -> None:
    wrapper = _receive(graph, "left_stick_vec, left_stick_x, left_stick_y")
    runs = record(wrapper, "left_stick_vec", "left_stick_x", "left_stick_y", "changed", "from_gate")
    pad = FakePad()
    pad.axes[0] = 16384  # held right when the graph starts
    with protokol_project(tmp_path, PAD_GATE) as state:
        _plug(sdl, state, pad)
        with running(graph):
            assert wait_until(lambda: len(runs) >= 1)
            assert list(runs[-1]["left_stick_vec"]) == pytest.approx([0.5, 0.0], abs=1e-4), "start value"
            sdl.move(pad, 2, 32767)  # the right stick: not chosen
            sdl.move(pad, 1, 32767)
            assert wait_until(lambda: runs[-1]["left_stick_y"] == pytest.approx(1.0))
    last = runs[-1]
    assert list(last["left_stick_vec"]) == pytest.approx([0.5, 1.0], abs=1e-4), "x kept from before"
    assert last["left_stick_x"] == pytest.approx(0.5, abs=1e-4)
    assert (last["changed"], last["from_gate"]) == ("left_stick_vec", "pad")


def test_y_up_and_dead_zone_apply(graph: BaseGraph, tmp_path: Path, sdl: FakeBackend) -> None:
    wrapper = _receive(graph, "left_stick_vec")
    wrapper.node.shaping.y_up = True
    wrapper.node.shaping.dead_zone = 0.2
    runs = record(wrapper, "left_stick_vec")
    with protokol_project(tmp_path, PAD_GATE) as state:
        pad = _plug(sdl, state)
        with running(graph):
            assert wait_until(lambda: _listening(wrapper))
            sdl.move(pad, 0, 3000)  # inside the dead zone
            sdl.move(pad, 1, -32767)  # pushed fully up
            assert wait_until(lambda: bool(runs) and list(runs[-1]["left_stick_vec"])[1] > 0.9)
    x, y = runs[-1]["left_stick_vec"]
    assert x == pytest.approx(0.091, abs=0.01)
    assert y == pytest.approx(0.996, abs=0.01)


def test_receives_every_button_press(graph: BaseGraph, tmp_path: Path, sdl: FakeBackend) -> None:
    wrapper = _receive(graph, "a, y")
    runs = record(wrapper, "a", "y", "changed")
    with protokol_project(tmp_path, PAD_GATE) as state:
        pad = _plug(sdl, state)
        with running(graph):
            assert wait_until(lambda: _listening(wrapper))
            sdl.press(pad, 0)
            sdl.press(pad, 1)  # b: not chosen
            sdl.press(pad, 0, False)
            sdl.press(pad, 3)
            assert wait_until(lambda: len(runs) >= 3)
    assert [(r["changed"], r["a"], r["y"]) for r in runs] == [
        ("a", True, False),
        ("a", False, False),
        ("y", False, True),
    ]


def test_dpad_vec_fires_once_per_press(graph: BaseGraph, tmp_path: Path, sdl: FakeBackend) -> None:
    wrapper = _receive(graph, "dpad_vec")
    wrapper.node.dispatch.start_value = "Off"
    wrapper.node.dispatch.queue_mode = "Block (every message)"
    runs = record(wrapper, "dpad_vec")
    with protokol_project(tmp_path, PAD_GATE) as state:
        pad = _plug(sdl, state)
        with running(graph):
            assert wait_until(lambda: _listening(wrapper))
            sdl.press(pad, 11)
            sdl.press(pad, 14)
            assert wait_until(lambda: len(runs) >= 2)
    assert [list(r["dpad_vec"]) for r in runs] == [[0, -1], [1, -1]]


def test_start_value_off_ignores_the_state_at_open(
    graph: BaseGraph, tmp_path: Path, sdl: FakeBackend
) -> None:
    wrapper = _receive(graph, "left_stick_y")
    wrapper.node.dispatch.start_value = "Off"
    runs = record(wrapper, "left_stick_y")
    pad = FakePad()
    pad.axes[1] = -32768
    with protokol_project(tmp_path, PAD_GATE) as state:
        _plug(sdl, state, pad)
        with running(graph):
            assert wait_until(lambda: _listening(wrapper))
            sdl.move(pad, 1, 0)
            assert wait_until(lambda: len(runs) >= 1)
    assert [r["left_stick_y"] for r in runs] == [0.0]


def test_waits_for_an_unplugged_pad(graph: BaseGraph, tmp_path: Path, sdl: FakeBackend) -> None:
    save_devices(device_list_path(), [Device("pad", "gamepad", XBOX)])
    wrapper = _receive(graph, "a")
    runs = record(wrapper, "a")
    with protokol_project(tmp_path, PAD_GATE) as state, running(graph):
        state.refresh_devices()
        assert wait_until(lambda: str(wrapper.node.report.status) == "waiting for 'pad'")
        pad = FakePad()
        sdl.plug(pad)
        assert wait_until(lambda: _refreshed(state) and _listening(wrapper))
        sdl.press(pad, 0)
        assert wait_until(lambda: len(runs) >= 1)


def test_promoted_status_is_written_through_its_port(
    graph: BaseGraph, tmp_path: Path, sdl: FakeBackend
) -> None:
    from haywire.core.node.promotion import promote_setting

    wrapper = _receive(graph, "a")
    promote_setting(wrapper.node, "report", "status", PortType.OUTLET)
    assert "report.status" in wrapper.node.ports
    with protokol_project(tmp_path, PAD_GATE) as state:
        _plug(sdl, state)
        with running(graph):
            assert wait_until(lambda: str(wrapper.node.value("report.status")).startswith("listening on"))
    assert wrapper.node.report.status == wrapper.node.value("report.status"), "one value"


def _rumble(graph: Any, gate: str = "pad") -> Any:
    node = make_node(graph, SendRumbleNode.class_identity.registry_key).node
    node.ports["gate"].set_value(gate)
    return node


def test_send_rumble(graph: BaseGraph, tmp_path: Path, sdl: FakeBackend) -> None:
    node = _rumble(graph)
    assert "report.status" not in node.ports, "off the card by default"
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
        status = str(node.report.status)
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
        status = str(node.report.status)
        node.on_shutdown(context)
    assert "'pad' is an input gate" in status
