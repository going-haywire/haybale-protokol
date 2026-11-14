"""OSC nodes on several gates at once."""

import socket
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from pythonosc.osc_message import OscMessage
from pythonosc.udp_client import SimpleUDPClient

from haybale_protokol.gates import Gate
from haybale_protokol_osc.nodes.osc_receive import OscReceiveNode
from haybale_protokol_osc.nodes.osc_send import OscSendNode
from haywire.core.graph.base import BaseGraph
from tests.helpers import make_node
from tests.osc.conftest import free_udp_port
from tests.osc.graphs import protokol_project, record, running, wait_until

pytestmark = pytest.mark.integration


def _in(name: str, port: int) -> Gate:
    return Gate(name, "osc", "in", options={"port": port, "bind": "127.0.0.1"})


def _out(name: str, sock: socket.socket) -> Gate:
    return Gate(name, "osc", "out", options={"port": sock.getsockname()[1], "host": "127.0.0.1"})


def test_choices_follow_protocol_and_direction(library_system: Any, tmp_path: Path) -> None:
    gates = (
        _in("in", 1),
        Gate("out", "osc", "out", options={"port": 2, "host": "h"}),
        Gate("both", "osc", "two-way", options={"transport": "tcp", "port": 3, "host": "h"}),
        Gate("midi", "midi", "in", device="desk"),
    )
    with protokol_project(tmp_path, *gates) as state:
        assert state.gate_choices("osc", "in") == ["both", "in"]
        assert state.gate_choices("osc", "out") == ["both", "out"]


def test_receive_from_two_gates(graph: BaseGraph, tmp_path: Path) -> None:
    port_a, port_b = free_udp_port(), free_udp_port()
    receive = make_node(graph, OscReceiveNode.class_identity.registry_key)
    receive.node.ports["gate"].set_value("a, b")
    runs = record(receive, "from_gate", "args")
    with protokol_project(tmp_path, _in("a", port_a), _in("b", port_b)), running(graph):
        assert wait_until(lambda: str(receive.node.value("status")).count("listening on") == 2)
        SimpleUDPClient("127.0.0.1", port_a).send_message("/x", 1)
        SimpleUDPClient("127.0.0.1", port_b).send_message("/x", 2)
        assert wait_until(lambda: len(runs) >= 2)
    assert sorted((run["from_gate"], run["args"][0]) for run in runs) == [("a", 1), ("b", 2)]


def test_receive_reports_a_missing_gate_and_uses_the_rest(graph: BaseGraph, tmp_path: Path) -> None:
    port = free_udp_port()
    receive = make_node(graph, OscReceiveNode.class_identity.registry_key)
    receive.node.ports["gate"].set_value("a, nope")
    runs = record(receive, "from_gate")
    with protokol_project(tmp_path, _in("a", port)), running(graph):
        assert wait_until(lambda: "no gate named 'nope'" in str(receive.node.value("status")))
        assert "listening on a" in str(receive.node.value("status"))
        SimpleUDPClient("127.0.0.1", port).send_message("/x", 1)
        assert wait_until(lambda: len(runs) >= 1)


def _drain(sock: socket.socket) -> list[OscMessage]:
    sock.settimeout(0.3)
    messages = []
    try:
        while True:
            messages.append(OscMessage(sock.recvfrom(4096)[0]))
    except TimeoutError:
        return messages


def test_send_to_two_gates_and_skip_a_missing_one(graph: BaseGraph, tmp_path: Path) -> None:
    a = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    b = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    for sock in (a, b):
        sock.bind(("127.0.0.1", 0))
    node = make_node(graph, OscSendNode.class_identity.registry_key).node
    node.ports["gate"].set_value("a, b, nope")
    node.ports["address"].set_value("/x")
    context = MagicMock()
    try:
        with protokol_project(tmp_path, _out("a", a), _out("b", b)):
            node.on_startup(context)
            node.worker(context)
            status = str(node.value("status"))
            node.on_shutdown(context)
        assert [m.address for m in _drain(a)] == ["/x"]
        assert [m.address for m in _drain(b)] == ["/x"]
        assert "sent 1" in status
        assert "no gate named 'nope'" in status
    finally:
        a.close()
        b.close()
