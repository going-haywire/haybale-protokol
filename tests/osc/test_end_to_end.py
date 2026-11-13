"""A graph forwards OSC from an input gate to an output gate."""

import socket
from pathlib import Path
from typing import Any

import pytest
from pythonosc.osc_message import OscMessage
from pythonosc.udp_client import SimpleUDPClient

from haybale_protokol.gates import Gate
from haybale_protokol_osc.nodes.osc_receive import OscReceiveNode
from haybale_protokol_osc.nodes.osc_send import OscSendNode
from haywire.core.graph.base import BaseGraph
from tests.helpers import make_edge, make_node
from tests.osc.graphs import protokol_project, running, wait_until

pytestmark = pytest.mark.integration


def _forwarder(graph: Any, send_shape: str) -> tuple[Any, Any]:
    receive = make_node(graph, OscReceiveNode.class_identity.registry_key)
    receive.node.ports["gate"].set_value("osc-in")
    receive.node.ports["address"].set_value("/in/*")
    receive.node.ports["arg_shape"].set_value("f")
    send = make_node(graph, OscSendNode.class_identity.registry_key, position=(400, 0))
    send.node.ports["gate"].set_value("osc-out")
    send.node.ports["address"].set_value("/out")
    send.node.ports["arg_shape"].set_value(send_shape)
    assert make_edge(graph, receive.node_id, "received", send.node_id, "exec").state.is_valid()
    assert make_edge(graph, receive.node_id, "arg_1", send.node_id, "arg_1").state.is_valid()
    return receive, send


def _gates(in_port: int, listener: socket.socket) -> tuple[Gate, Gate]:
    return (
        Gate("osc-in", "osc", "in", options={"port": in_port, "bind": "127.0.0.1"}),
        Gate("osc-out", "osc", "out", options={"port": listener.getsockname()[1], "host": "127.0.0.1"}),
    )


def _listening(receive: Any) -> None:
    assert wait_until(lambda: str(receive.node.value("status")).startswith("listening on"))


def test_receive_to_send_loopback(
    graph: BaseGraph, tmp_path: Path, udp_port: int, listener: socket.socket
) -> None:
    receive, _ = _forwarder(graph, "f")
    with protokol_project(tmp_path, *_gates(udp_port, listener)), running(graph):
        _listening(receive)
        SimpleUDPClient("127.0.0.1", udp_port).send_message("/in/a", 1.5)
        message = OscMessage(listener.recvfrom(4096)[0])
    assert message.address == "/out"
    assert message.params == [1.5]


def test_capture_takes_the_connected_type(
    graph: BaseGraph, tmp_path: Path, udp_port: int, listener: socket.socket
) -> None:
    receive, send = _forwarder(graph, "f s")
    assert make_edge(graph, receive.node_id, "match_1", send.node_id, "arg_2").state.is_valid()
    assert receive.node.ports["match_1"].type_cls.__name__ == "STRING"
    with protokol_project(tmp_path, *_gates(udp_port, listener)), running(graph):
        _listening(receive)
        SimpleUDPClient("127.0.0.1", udp_port).send_message("/in/left", 0.5)
        message = OscMessage(listener.recvfrom(4096)[0])
    assert message.params == [0.5, "left"]


def test_capture_that_does_not_convert_is_a_status(
    graph: BaseGraph, tmp_path: Path, udp_port: int, listener: socket.socket
) -> None:
    receive, send = _forwarder(graph, "f i")
    assert make_edge(graph, receive.node_id, "match_1", send.node_id, "arg_2").state.is_valid()
    assert receive.node.ports["match_1"].type_cls.__name__ == "INT"
    with protokol_project(tmp_path, *_gates(udp_port, listener)), running(graph):
        _listening(receive)
        SimpleUDPClient("127.0.0.1", udp_port).send_message("/in/x", 0.5)
        assert wait_until(lambda: "match_1: 'x' is not INT" in str(receive.node.value("status")))

