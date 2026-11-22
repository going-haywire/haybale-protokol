"""Send MIDI: inlets follow the kind; one message to every listed gate per tick."""

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from haybale_protokol.devices import Device, device_list_path, save_devices
from haybale_protokol.gates import Gate
from haybale_protokol_midi.midi_pins import FILTER_WARNING
from haybale_protokol_midi.nodes.send_midi import SendMidiNode
from haywire.core.graph.base import BaseGraph
from tests.helpers import make_node
from tests.midi.conftest import Sink, needs_virtual, wait_for
from tests.osc.graphs import protokol_project

pytestmark = pytest.mark.integration

KIND_INLETS = {
    "note": ["velocity", "on"],
    "cc": ["value"],
    "pitchbend": ["value"],
    "aftertouch": ["value"],
    "program": ["program"],
    "sysex": ["data"],
    "transport": ["event", "position"],
    "raw": ["bytes"],
}
KNOWN = {"channel", "note", "controller", *(i for inlets in KIND_INLETS.values() for i in inlets)}


def _send(graph: Any, kind: str = "cc", channel: int = 1, number: int = -1, gate: str = "synth") -> Any:
    node = make_node(graph, SendMidiNode.class_identity.registry_key).node
    node.ports["gate"].set_value(gate)
    node.ports["kind"].set_value(kind)
    node.ports["filter_channel"].set_value(channel)
    node.ports["filter_number"].set_value(number)
    return node


def _inlets(node: Any) -> list[str]:
    inlets = [p for p in node.ports.values() if p.is_inlet() and p.id in KNOWN]
    return [p.id for p in sorted(inlets, key=lambda p: p.order)]


def _run(node: Any, tmp_path: Path, *gates: Gate, ticks: int = 1) -> str:
    context = MagicMock()
    with protokol_project(tmp_path, *gates):
        node.on_startup(context)
        for _ in range(ticks):
            node.worker(context)
        status = str(node.value("status"))
        node.on_shutdown(context)
    return status


@pytest.mark.parametrize("kind", list(KIND_INLETS))
def test_inlets_follow_the_kind(graph: BaseGraph, kind: str) -> None:
    assert _inlets(_send(graph, kind=kind, channel=1, number=60)) == KIND_INLETS[kind]


def test_channel_and_number_inlets_for_any(graph: BaseGraph) -> None:
    node = _send(graph, kind="note", channel=0, number=-1)
    assert _inlets(node) == ["channel", "note", "velocity", "on"]


def test_an_impossible_fixed_channel_shows_a_warning_badge(graph: BaseGraph) -> None:
    node = _send(graph, kind="note", channel=1, number=60)
    node.ports["filter_channel"].set_value(17)
    warnings = [w.message for w in node.wrapper.state.warnings if w.kind == FILTER_WARNING]
    assert warnings == ["Channel must be 0 (from an inlet) or 1–16, not 17"]
    node.ports["filter_channel"].set_value(0)
    assert not node.wrapper.state.has_warning()


@needs_virtual
def test_sends_note_to_virtual_port(graph: BaseGraph, tmp_path: Path, sink: Sink) -> None:
    save_devices(device_list_path(), [Device("synth", "midi", sink.name)])
    node = _send(graph, kind="note", channel=2, number=64)
    node.ports["velocity"].set_value(90)
    node.ports["on"].set_value(True)
    status = _run(node, tmp_path, Gate("synth", "midi", "out", device="synth"))
    assert wait_for(lambda: sink.received == [[0x91, 64, 90]])
    assert "sent 1" in status


@needs_virtual
def test_sends_cc_with_any_controller_inlet(graph: BaseGraph, tmp_path: Path, sink: Sink) -> None:
    save_devices(device_list_path(), [Device("synth", "midi", sink.name)])
    node = _send(graph, kind="cc", channel=1, number=-1)
    node.ports["controller"].set_value(74)
    node.ports["value"].set_value(12)
    _run(node, tmp_path, Gate("synth", "midi", "out", device="synth"))
    assert wait_for(lambda: sink.received == [[0xB0, 74, 12]])


@needs_virtual
def test_out_of_range_dropped_and_named(graph: BaseGraph, tmp_path: Path, sink: Sink) -> None:
    save_devices(device_list_path(), [Device("synth", "midi", sink.name)])
    node = _send(graph, kind="cc", channel=1, number=7)
    node.ports["value"].set_value(300)
    status = _run(node, tmp_path, Gate("synth", "midi", "out", device="synth"))
    assert "dropped 1" in status
    assert "value" in status
    assert sink.received == []


@needs_virtual
def test_only_send_changes(graph: BaseGraph, tmp_path: Path, sink: Sink) -> None:
    save_devices(device_list_path(), [Device("synth", "midi", sink.name)])
    node = _send(graph, kind="cc", channel=1, number=7)
    node.sending.only_changes = True
    node.ports["value"].set_value(5)
    status = _run(node, tmp_path, Gate("synth", "midi", "out", device="synth"), ticks=3)
    assert wait_for(lambda: len(sink.received) == 1)
    assert "unchanged 2" in status


@needs_virtual
def test_two_gates(graph: BaseGraph, tmp_path: Path) -> None:
    a, b = Sink(), Sink()
    try:
        save_devices(device_list_path(), [Device("a", "midi", a.name), Device("b", "midi", b.name)])
        node = _send(graph, kind="program", channel=1, gate="a, b")
        node.ports["program"].set_value(3)
        gates = (Gate("a", "midi", "out", device="a"), Gate("b", "midi", "out", device="b"))
        _run(node, tmp_path, *gates)
        assert wait_for(lambda: a.received == [[0xC0, 3]] and b.received == [[0xC0, 3]])
    finally:
        a.close()
        b.close()
