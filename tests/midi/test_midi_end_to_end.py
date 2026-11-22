"""A graph forwards MIDI from one device to another."""

from pathlib import Path

import pytest

from haybale_protokol.devices import Device, device_list_path, save_devices
from haybale_protokol.gates import Gate
from haybale_protokol_midi.nodes.midi_event import MidiEventNode
from haybale_protokol_midi.nodes.send_midi import SendMidiNode
from haywire.core.graph.base import BaseGraph
from tests.helpers import make_edge, make_node
from tests.midi.conftest import Sink, Source, needs_virtual, wait_for
from tests.osc.graphs import protokol_project, running, wait_until

pytestmark = [pytest.mark.integration, needs_virtual]


def test_receive_to_send_through_virtual_ports(
    graph: BaseGraph, tmp_path: Path, source: Source, sink: Sink
) -> None:
    save_devices(
        device_list_path(), [Device("keys", "midi", source.name), Device("synth", "midi", sink.name)]
    )
    receive = make_node(graph, MidiEventNode.class_identity.registry_key)
    for port, value in (("gate", "keys"), ("kind", "cc"), ("filter_channel", 1), ("filter_number", 7)):
        receive.node.ports[port].set_value(value)
    send = make_node(graph, SendMidiNode.class_identity.registry_key, position=(400, 0))
    for port, value in (("gate", "synth"), ("kind", "cc"), ("filter_channel", 2), ("filter_number", 10)):
        send.node.ports[port].set_value(value)
    assert make_edge(graph, receive.node_id, "received", send.node_id, "exec").state.is_valid()
    assert make_edge(graph, receive.node_id, "value", send.node_id, "value").state.is_valid()
    gates = (Gate("keys", "midi", "in", device="keys"), Gate("synth", "midi", "out", device="synth"))
    with protokol_project(tmp_path, *gates), running(graph):
        assert wait_until(lambda: str(receive.node.value("status")).startswith("listening on"))
        source.send(0xB0, 7, 99)
        assert wait_for(lambda: sink.received == [[0xB1, 10, 99]])
