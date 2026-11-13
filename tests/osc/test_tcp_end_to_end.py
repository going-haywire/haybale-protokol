"""OSC Receive and Send over TCP gates, in a running graph."""

import socket
from pathlib import Path
from typing import Any

import pytest
from pythonosc.osc_message import OscMessage

from haybale_protokol.gates import Gate
from haybale_protokol_osc.driver import build_message
from haybale_protokol_osc.framing import FrameReader, encode_frame
from haybale_protokol_osc.nodes.osc_receive import OscReceiveNode
from haybale_protokol_osc.nodes.osc_send import OscSendNode
from haywire.core.graph.base import BaseGraph
from tests.helpers import make_edge, make_node
from tests.osc.conftest import TestPeer
from tests.osc.graphs import protokol_project, running, wait_until

pytestmark = pytest.mark.integration


def _forwarder(graph: Any, gate: str) -> tuple[Any, Any]:
    receive = make_node(graph, OscReceiveNode.class_identity.registry_key)
    receive.node.ports["gate"].set_value(gate)
    receive.node.ports["address"].set_value("/in")
    receive.node.ports["arg_shape"].set_value("f")
    send = make_node(graph, OscSendNode.class_identity.registry_key, position=(400, 0))
    send.node.ports["gate"].set_value(gate)
    send.node.ports["address"].set_value("/out")
    send.node.ports["arg_shape"].set_value("f")
    assert make_edge(graph, receive.node_id, "received", send.node_id, "exec").state.is_valid()
    assert make_edge(graph, receive.node_id, "arg_1", send.node_id, "arg_1").state.is_valid()
    return receive, send


def _client_gate(port: int, framing: str) -> Gate:
    options = {"transport": "tcp", "host": "127.0.0.1", "port": port, "framing": framing}
    return Gate("desk", "osc", "two-way", options=options)


def _listening(receive: Any) -> None:
    assert wait_until(lambda: str(receive.node.value("status")).startswith("listening on"))


def test_receive_and_send_over_two_way_client_gate(graph: BaseGraph, tmp_path: Path, peer: TestPeer) -> None:
    receive, _ = _forwarder(graph, "desk")
    with protokol_project(tmp_path, _client_gate(peer.port, peer.framing)), running(graph):
        _listening(receive)
        assert wait_until(lambda: peer.accepts == 1 and len(peer.clients) == 1)
        assert wait_until(_connected)
        peer.send("/in", 1.5)
        assert wait_until(lambda: ("/out", [1.5]) in peer.messages())


def _connected() -> bool:
    from haybale_protokol.states.protokol_state import ProtokolState
    from haywire.core.di.context import get_library_state_container

    state = get_library_state_container().get(ProtokolState)
    assert state is not None
    return any(line.status.startswith("connected") for line in state.lines())


def test_server_gate_forwards_to_peers(graph: BaseGraph, tmp_path: Path) -> None:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = int(probe.getsockname()[1])
    options = {"transport": "tcp", "role": "server", "port": port, "bind": "127.0.0.1"}
    gate = Gate("tablets", "osc", "two-way", options=options)
    receive, _ = _forwarder(graph, "tablets")
    with protokol_project(tmp_path, gate), running(graph):
        _listening(receive)
        a = socket.create_connection(("127.0.0.1", port), timeout=2.0)
        b = socket.create_connection(("127.0.0.1", port), timeout=2.0)
        try:
            assert wait_until(lambda: "2 peers" in _line_status(port))
            a.sendall(encode_frame(build_message("/in", (0.25,), "f"), "1.1"))
            for sock in (a, b):
                message = _recv(sock)
                assert (message.address, message.params) == ("/out", [0.25])
        finally:
            a.close()
            b.close()


def _line_status(port: int) -> str:
    from haybale_protokol.states.protokol_state import ProtokolState
    from haywire.core.di.context import get_library_state_container

    state = get_library_state_container().get(ProtokolState)
    assert state is not None
    return " | ".join(line.status for line in state.lines() if str(port) in line.key.address)


def _recv(sock: socket.socket) -> OscMessage:
    reader = FrameReader("1.1")
    while True:
        packets = reader.feed(sock.recv(4096))
        if packets:
            return OscMessage(packets[0])


def test_restart_within_grace_keeps_peer(graph: BaseGraph, tmp_path: Path) -> None:
    peer = TestPeer("1.1")
    try:
        receive, _ = _forwarder(graph, "desk")
        with protokol_project(tmp_path, _client_gate(peer.port, "1.1"), grace=5.0):
            with running(graph):
                _listening(receive)
                assert wait_until(lambda: peer.accepts == 1)
            with running(graph):
                _listening(receive)
                assert wait_until(lambda: len(peer.clients) == 1)
                peer.send("/in", 2.0)
                assert wait_until(lambda: ("/out", [2.0]) in peer.messages())
        assert peer.accepts == 1
    finally:
        peer.stop()


def test_missing_peer_does_not_block_start(graph: BaseGraph, tmp_path: Path) -> None:
    from haybale_core.nodes.events.begin_play import BeginPlayNode

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = int(probe.getsockname()[1])
    send = make_node(graph, OscSendNode.class_identity.registry_key, position=(400, 0))
    send.node.ports["gate"].set_value("desk")
    begin = make_node(graph, BeginPlayNode.class_identity.registry_key)
    assert make_edge(graph, begin.node_id, "exec", send.node_id, "exec").state.is_valid()
    with protokol_project(tmp_path, _client_gate(port, "1.1")), running(graph):
        assert wait_until(lambda: "dropped 1" in str(send.node.value("status")))
    assert "connecting" in str(send.node.value("status"))
