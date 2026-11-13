"""OSC Send: inlets become the arguments of one OSC message per run."""

import re
import socket
from pathlib import Path
from typing import Any

import pytest
from pythonosc.osc_message import OscMessage

from haybale_protokol.gates import Gate
from haybale_protokol_osc.nodes.osc_send import OscSendNode
from haywire.core.graph.base import BaseGraph
from tests.helpers import make_edge, make_node
from tests.osc.graphs import protokol_project, running, wait_until

pytestmark = pytest.mark.integration

_ARG = re.compile(r"arg_\d+")


def _send_node(graph: Any, address: str = "/x", shape: str = "", gate: str = "out") -> Any:
    wrapper = make_node(graph, OscSendNode.class_identity.registry_key, position=(400, 0))
    wrapper.node.ports["gate"].set_value(gate)
    wrapper.node.ports["address"].set_value(address)
    if shape:
        wrapper.node.ports["arg_shape"].set_value(shape)
    return wrapper


def _begin_play(graph: Any, send: Any) -> Any:
    from haybale_core.nodes.events.begin_play import BeginPlayNode

    begin = make_node(graph, BeginPlayNode.class_identity.registry_key)
    assert make_edge(graph, begin.node_id, "exec", send.node_id, "exec").state.is_valid()
    return begin


def _number(graph: Any, kind: str, value: Any, y: int) -> Any:
    from haybale_core.nodes.widgets.number import FloatNumberNode, IntNumberNode

    cls = FloatNumberNode if kind == "float" else IntNumberNode
    wrapper = make_node(graph, cls.class_identity.registry_key, position=(0, y))
    wrapper.node.ports["value"].set_value(value)
    return wrapper


def _args(wrapper: Any) -> list[tuple[str, str]]:
    ports = sorted((p for p in wrapper.node.ports.values() if _ARG.fullmatch(p.id)), key=lambda p: p.order)
    return [(p.id, p.type_cls.__name__) for p in ports]


def _out_gate(listener: socket.socket) -> Gate:
    return Gate("out", "osc", "out", options={"port": listener.getsockname()[1], "host": "127.0.0.1"})


def _receive(listener: socket.socket) -> tuple[OscMessage, bytes]:
    data, _ = listener.recvfrom(4096)
    return OscMessage(data), data


def test_starts_with_one_add_slot(graph: BaseGraph) -> None:
    assert _args(_send_node(graph)) == [("arg_1", "ADD")]


def test_shape_builds_inlets_and_slot(graph: BaseGraph) -> None:
    wrapper = _send_node(graph, shape="f vf3")
    assert _args(wrapper) == [("arg_1", "FLOAT"), ("arg_2", "VEC3F"), ("arg_3", "ADD")]


def test_connecting_slot_grows_inlet_and_shape(graph: BaseGraph) -> None:
    wrapper = _send_node(graph)
    number = _number(graph, "int", 3, 0)
    assert make_edge(graph, number.node_id, "value", wrapper.node_id, "arg_1").state.is_valid()
    assert _args(wrapper) == [("arg_1", "INT"), ("arg_2", "ADD")]
    assert wrapper.node.value("arg_shape") == "i"


def test_send_reaches_udp_socket(graph: BaseGraph, tmp_path: Path, listener: socket.socket) -> None:
    send = _send_node(graph, address="/x")
    _begin_play(graph, send)
    for y, (kind, value) in enumerate((("float", 0.5), ("int", 3))):
        number = _number(graph, kind, value, 100 * y)
        slot = _args(send)[-1][0]
        assert make_edge(graph, number.node_id, "value", send.node_id, slot).state.is_valid()
    with protokol_project(tmp_path, _out_gate(listener)), running(graph):
        message, data = _receive(listener)
    assert message.address == "/x"
    assert message.params == [0.5, 3]
    assert data[4:8] == b",fi\x00"
    assert wait_until(lambda: str(send.node.value("status")).startswith("sent 1"))
    assert send.node.value("shape") == "fi"


def test_vec3_goes_out_as_three_floats(graph: BaseGraph, tmp_path: Path, listener: socket.socket) -> None:
    send = _send_node(graph, shape="vf3")
    send.node.ports["arg_1"].set_value([1.0, 2.0, 3.0])
    _begin_play(graph, send)
    with protokol_project(tmp_path, _out_gate(listener)), running(graph):
        message, data = _receive(listener)
    assert message.params == [1.0, 2.0, 3.0]
    assert data[4:8] == b",fff"
    assert wait_until(lambda: send.node.value("shape") == "fff")


def test_unconnected_inlet_sends_widget_value(
    graph: BaseGraph, tmp_path: Path, listener: socket.socket
) -> None:
    send = _send_node(graph, shape="s")
    send.node.ports["arg_1"].set_value("hello")
    _begin_play(graph, send)
    with protokol_project(tmp_path, _out_gate(listener)), running(graph):
        message, _ = _receive(listener)
    assert message.params == ["hello"]


def test_64bit_from_shape(graph: BaseGraph, tmp_path: Path, listener: socket.socket) -> None:
    send = _send_node(graph, shape="d h")
    send.node.ports["arg_1"].set_value(0.1)
    send.node.ports["arg_2"].set_value(2**40)
    _begin_play(graph, send)
    with protokol_project(tmp_path, _out_gate(listener)), running(graph):
        message, data = _receive(listener)
    assert data[4:8] == b",dh\x00"
    assert message.params == [0.1, 2**40]


def test_out_of_range_int_is_dropped_and_named(
    graph: BaseGraph, tmp_path: Path, listener: socket.socket
) -> None:
    send = _send_node(graph, shape="f i")
    send.node.ports["arg_2"].set_value(3_000_000_000)
    _begin_play(graph, send)
    with protokol_project(tmp_path, _out_gate(listener)), running(graph):
        assert wait_until(lambda: "dropped 1" in str(send.node.value("status")))
    assert "arg 2: 3000000000 does not fit i (use h)" in str(send.node.value("status"))


def test_skip_token_rejected(graph: BaseGraph) -> None:
    send = _send_node(graph, shape="f")
    send.node.ports["arg_shape"].set_value("_ f")
    assert _args(send) == [("arg_1", "FLOAT"), ("arg_2", "ADD")]
    assert "not applied" in str(send.node.value("status"))


def test_missing_gate_status(graph: BaseGraph, tmp_path: Path) -> None:
    send = _send_node(graph, gate="nope")
    _begin_play(graph, send)
    with protokol_project(tmp_path), running(graph):
        assert wait_until(lambda: str(send.node.value("status")) == "no gate named 'nope'")
