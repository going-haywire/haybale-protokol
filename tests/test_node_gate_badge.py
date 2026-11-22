"""The four Receive and Send nodes: a gate badge, and a status outlet never saved (Plan 4b, task 4)."""

from pathlib import Path
from typing import Any

import pytest

from haybale_protokol.gate_warning import GATE_WARNING
from haybale_protokol.gates import Gate
from haybale_protokol_midi.midi_pins import FILTER_WARNING
from haybale_protokol_midi.nodes.midi_event import MidiEventNode
from haybale_protokol_midi.nodes.send_midi import SendMidiNode
from haybale_protokol_osc.nodes.osc_event import OscEventNode
from haybale_protokol_osc.nodes.send_osc import SendOscNode
from haywire.core.graph.base import BaseGraph
from haywire.core.graph.scheduler import SyncScheduler
from tests.helpers import make_node
from tests.osc.graphs import protokol_project

pytestmark = pytest.mark.integration

NODES = {
    "osc-event": OscEventNode,
    "send-osc": SendOscNode,
    "midi-event": MidiEventNode,
    "send-midi": SendMidiNode,
}


def _badges(wrapper: Any, kind: str = GATE_WARNING) -> list[str]:
    return [w.message for w in wrapper.state.warnings if w.kind == kind]


@pytest.mark.parametrize("name", list(NODES))
def test_a_missing_gate_shows_a_badge_at_once(graph: BaseGraph, tmp_path: Path, name: str) -> None:
    with protokol_project(tmp_path):
        wrapper = make_node(graph, NODES[name].class_identity.registry_key)
        assert _badges(wrapper) == []
        wrapper.node.ports["gate"].set_value("nope")
        assert _badges(wrapper) == ["no gate named 'nope'"]
        wrapper.node.ports["gate"].set_value("")
        assert _badges(wrapper) == []


@pytest.mark.parametrize("name", ["midi-event", "send-midi"])
def test_an_unbound_device_gate_shows_a_badge(graph: BaseGraph, tmp_path: Path, name: str) -> None:
    direction = "in" if name == "midi-event" else "out"
    with protokol_project(tmp_path, Gate("pads", "midi", direction, device="nowhere")):
        wrapper = make_node(graph, NODES[name].class_identity.registry_key)
        wrapper.node.ports["gate"].set_value("pads")
        assert _badges(wrapper) == ["pads: unbound gate: no device 'nowhere' on this machine"]


def test_gate_badge_and_filter_badge_coexist(graph: BaseGraph, tmp_path: Path) -> None:
    with protokol_project(tmp_path):
        wrapper = make_node(graph, MidiEventNode.class_identity.registry_key)
        wrapper.node.ports["gate"].set_value("nope")
        wrapper.node.ports["filter_channel"].set_value(17)
        assert _badges(wrapper) == ["no gate named 'nope'"]
        assert _badges(wrapper, FILTER_WARNING) == ["Channel must be 0 (any) or 1–16, not 17"]
        wrapper.node.ports["gate"].set_value("")
        assert _badges(wrapper) == []
        assert _badges(wrapper, FILTER_WARNING) == ["Channel must be 0 (any) or 1–16, not 17"]


@pytest.mark.parametrize("name", list(NODES))
def test_status_is_not_saved(graph: BaseGraph, name: str) -> None:
    """A reopened graph never shows the last session's status (design §10.1)."""
    wrapper = make_node(graph, NODES[name].class_identity.registry_key)
    wrapper.node.post_value("status", "listening on Grid")
    assert wrapper.node.value("status") == "listening on Grid"
    loaded = BaseGraph(filestem="reload", validation_scheduler=SyncScheduler())
    assert loaded.load_from_dict(graph.to_dict())
    assert loaded.get_node_wrapper(wrapper.node_id).node.value("status") == ""
