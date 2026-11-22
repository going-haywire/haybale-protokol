"""MIDI Event: a filter of kind, channel and number; outlets follow the kind."""

from pathlib import Path
from typing import Any

import pytest

from haybale_protokol.devices import Device, device_list_path, save_devices
from haybale_protokol.gates import Gate
from haybale_protokol_midi.nodes.midi_event import MidiEventNode
from haywire.core.graph.base import BaseGraph
from haywire.core.graph.scheduler import SyncScheduler
from tests.helpers import make_node
from tests.midi.conftest import Source, needs_backend, needs_virtual
from tests.osc.graphs import protokol_project, record, running, wait_until

pytestmark = pytest.mark.integration

KIND_OUTLETS = {
    "note": ["velocity", "on"],
    "cc": ["value"],
    "pitchbend": ["value"],
    "aftertouch": ["value"],
    "program": ["program"],
    "sysex": ["data"],
    "transport": ["event", "position"],
    "raw": ["bytes"],
}
FILTER_OUTLETS = {"channel", "note", "controller"}


def _receive(graph: Any, kind: str = "cc", channel: int = 1, number: int = -1, gate: str = "keys") -> Any:
    wrapper = make_node(graph, MidiEventNode.class_identity.registry_key)
    node = wrapper.node
    node.ports["gate"].set_value(gate)
    node.ports["kind"].set_value(kind)
    node.ports["filter_channel"].set_value(channel)
    node.ports["filter_number"].set_value(number)
    return wrapper


def _values(wrapper: Any) -> list[str]:
    known = {*FILTER_OUTLETS, *(o for outs in KIND_OUTLETS.values() for o in outs)}
    outlets = [p for p in wrapper.node.ports.values() if p.is_outlet() and p.id in known]
    return [p.id for p in sorted(outlets, key=lambda p: p.order)]


def _device(source: Source, name: str = "keys") -> None:
    save_devices(device_list_path(), [Device(name, "midi", source.name)])


@pytest.mark.parametrize("kind", list(KIND_OUTLETS))
def test_outlets_follow_the_kind(graph: BaseGraph, kind: str) -> None:
    wrapper = _receive(graph, kind=kind, channel=1, number=60)
    assert _values(wrapper) == KIND_OUTLETS[kind]


def test_channel_and_number_outlets_appear_for_any(graph: BaseGraph) -> None:
    wrapper = _receive(graph, kind="note", channel=0, number=-1)
    assert _values(wrapper) == ["channel", "note", "velocity", "on"]
    wrapper.node.ports["kind"].set_value("cc")
    assert _values(wrapper) == ["channel", "controller", "value"]
    wrapper.node.ports["kind"].set_value("sysex")
    assert _values(wrapper) == ["data"], "system kinds have no channel"


def test_start_value_follows_the_kind(graph: BaseGraph) -> None:
    from haywire.core.execution import QueueMode

    wrapper = _receive(graph, kind="cc", number=7)
    wrapper.node.on_assembly()
    assert wrapper.node.event_subscription.queue_mode is QueueMode.DROP
    wrapper.node.ports["kind"].set_value("note")
    wrapper.node.on_assembly()
    assert wrapper.node.event_subscription.queue_mode is QueueMode.BLOCK


@needs_virtual
def test_receives_note_on_and_off(graph: BaseGraph, tmp_path: Path, source: Source) -> None:
    _device(source)
    wrapper = _receive(graph, kind="note", channel=1, number=-1)
    runs = record(wrapper, "note", "velocity", "on", "from_gate")
    with protokol_project(tmp_path, Gate("keys", "midi", "in", device="keys")), running(graph):
        assert wait_until(lambda: str(wrapper.node.value("status")).startswith("listening on"))
        source.send(0x90, 60, 100)
        source.send(0x90, 60, 0)
        source.send(0x91, 61, 100)  # channel 2: filtered out
        assert wait_until(lambda: len(runs) >= 2)
    assert [(r["note"], r["velocity"], r["on"]) for r in runs] == [(60, 100, True), (60, 0, False)]
    assert runs[0]["from_gate"] == "keys"


@needs_virtual
def test_cc_filter_by_controller(graph: BaseGraph, tmp_path: Path, source: Source) -> None:
    _device(source)
    wrapper = _receive(graph, kind="cc", channel=0, number=7)
    runs = record(wrapper, "value", "channel")
    with protokol_project(tmp_path, Gate("keys", "midi", "in", device="keys")), running(graph):
        assert wait_until(lambda: str(wrapper.node.value("status")).startswith("listening on"))
        source.send(0xB0, 1, 10)
        source.send(0xB2, 7, 99)
        assert wait_until(lambda: len(runs) >= 1)
    assert (runs[-1]["value"], runs[-1]["channel"]) == (99, 3)


@needs_virtual
def test_two_gates(graph: BaseGraph, tmp_path: Path) -> None:
    a, b = Source(), Source()
    try:
        save_devices(device_list_path(), [Device("a", "midi", a.name), Device("b", "midi", b.name)])
        wrapper = _receive(graph, kind="cc", channel=1, number=-1, gate="a, b")
        runs = record(wrapper, "from_gate", "value")
        gates = (Gate("a", "midi", "in", device="a"), Gate("b", "midi", "in", device="b"))
        with protokol_project(tmp_path, *gates), running(graph):
            assert wait_until(lambda: str(wrapper.node.value("status")).count("listening on") == 2)
            a.send(0xB0, 7, 1)
            assert wait_until(lambda: len(runs) >= 1)  # cc keeps only the newest: one at a time
            b.send(0xB0, 7, 2)
            assert wait_until(lambda: len(runs) >= 2)
        assert sorted((r["from_gate"], r["value"]) for r in runs) == [("a", 1), ("b", 2)]
    finally:
        a.close()
        b.close()


@pytest.mark.parametrize(
    ("kind", "channel", "number", "problem"),
    [
        ("cc", 17, -1, "Channel must be 0 (any) or 1–16, not 17"),
        ("note", -2, -1, "Channel must be 0 (any) or 1–16, not -2"),
        ("cc", 1, 128, "Number must be −1 (any) or 0–127, not 128"),
        ("note", 1, -5, "Number must be −1 (any) or 0–127, not -5"),
    ],
)
def test_an_impossible_filter_is_named_in_status(
    graph: BaseGraph, tmp_path: Path, kind: str, channel: int, number: int, problem: str
) -> None:
    """A filter no message can pass would never fire; the status says why instead."""
    wrapper = _receive(graph, kind=kind, channel=channel, number=number)
    with protokol_project(tmp_path, Gate("keys", "midi", "in", device="keys")), running(graph):
        assert wait_until(lambda: str(wrapper.node.value("status")).startswith(problem))


def test_filters_a_kind_ignores_are_not_checked(graph: BaseGraph, tmp_path: Path) -> None:
    wrapper = _receive(graph, kind="sysex", channel=99, number=999)
    with protokol_project(tmp_path, Gate("keys", "midi", "in", device="keys")), running(graph):
        assert wait_until(lambda: "unbound gate" in str(wrapper.node.value("status")))
        assert "must be" not in str(wrapper.node.value("status"))


@needs_backend
def test_missing_device_status(graph: BaseGraph, tmp_path: Path) -> None:
    save_devices(device_list_path(), [Device("keys", "midi", "no such port")])
    wrapper = _receive(graph)
    with protokol_project(tmp_path, Gate("keys", "midi", "in", device="keys")), running(graph):
        assert wait_until(
            lambda: "keys: cannot open: no MIDI port 'no such port'" in str(wrapper.node.value("status"))
        )


def test_save_reload_keeps_ports(graph: BaseGraph) -> None:
    wrapper = _receive(graph, kind="note", channel=0, number=-1)
    loaded = BaseGraph(filestem="reload", validation_scheduler=SyncScheduler())
    assert loaded.load_from_dict(graph.to_dict())
    node = loaded.get_node_wrapper(wrapper.node_id)
    assert node.node.value("kind") == "note"
    assert _values(node) == ["channel", "note", "velocity", "on"]


def test_auto_drops_only_for_one_controller_on_one_gate(graph: BaseGraph) -> None:
    from haywire.core.execution import QueueMode

    node = _receive(graph, kind="cc", channel=1, number=7).node
    node.on_assembly()
    assert node.event_subscription.queue_mode is QueueMode.DROP
    for port, value in (("filter_number", -1), ("filter_channel", 0)):
        node.ports["filter_number"].set_value(7)
        node.ports["filter_channel"].set_value(1)
        node.ports[port].set_value(value)
        node.on_assembly()
        assert node.event_subscription.queue_mode is QueueMode.BLOCK, port
    node.ports["filter_number"].set_value(7)
    node.ports["filter_channel"].set_value(1)
    node.ports["gate"].set_value("a, b")
    node.on_assembly()
    assert node.event_subscription.queue_mode is QueueMode.BLOCK
