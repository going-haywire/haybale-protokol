"""Pin edits rewrite the Arg shape, each as one undo step."""

from typing import Any

import pytest

from haybale_protokol_osc.nodes.osc_receive import OscReceiveNode
from haybale_protokol_osc.nodes.osc_send import OscSendNode
from haywire.core.graph.base import BaseGraph
from haywire.core.undo.actions.graph_actions import AddEdgeAction, RemoveElementsAction, ReorderPortsAction
from tests.helpers import make_node

pytestmark = pytest.mark.integration


def _node(graph: Any, cls: Any, shape: str = "", x: int = 0) -> Any:
    wrapper = make_node(graph, cls.class_identity.registry_key, position=(x, 0))
    if shape:
        wrapper.node.ports["arg_shape"].set_value(shape)
    return wrapper


def _number(graph: Any) -> Any:
    from haybale_core.nodes.widgets.number import FloatNumberNode

    return make_node(graph, FloatNumberNode.class_identity.registry_key, position=(-300, 0))


def _shape(wrapper: Any) -> str:
    return str(wrapper.node.value("arg_shape"))


def _slot(wrapper: Any) -> str:
    return str(wrapper.node.store.arg_slot)


def _typed(wrapper: Any) -> list[tuple[str, str]]:
    ports = wrapper.node._arg_ports()
    return [(port.id, port.type_cls.__name__) for port in ports]


def _connect(graph: Any, src: Any, outlet: str, dst: Any, inlet: str) -> AddEdgeAction:
    action = AddEdgeAction(graph, src.node_id, outlet, dst.node_id, inlet)
    action.execute()
    return action


def test_grown_add_pin_appends_token(graph: BaseGraph) -> None:
    receive = _node(graph, OscReceiveNode, shape="i")
    send = _node(graph, OscSendNode, shape="vf3", x=400)
    _connect(graph, receive, _slot(receive), send, "arg_1")
    assert _shape(receive) == "i vf3"
    assert [t for _, t in _typed(receive)] == ["INT", "VEC3F"]
    assert "args" in receive.node.ports, "args always carries every argument"


def test_growth_undo_is_one_step(graph: BaseGraph) -> None:
    send = _node(graph, OscSendNode, shape="i", x=400)
    number = _number(graph)
    grown = _slot(send)
    action = _connect(graph, number, "value", send, grown)
    assert _shape(send) == "i f"
    action.undo()
    assert _shape(send) == "i"
    assert grown not in send.node.ports
    action.execute()
    assert _shape(send) == "i f"
    assert send.node.ports[grown].is_linked()


def test_deleting_the_growing_edge_drops_pin_and_token(graph: BaseGraph) -> None:
    send = _node(graph, OscSendNode, shape="i", x=400)
    number = _number(graph)
    grown = _slot(send)
    edge_id = _connect(graph, number, "value", send, grown).wrapper.edge_id
    remove = RemoveElementsAction(graph, [], [edge_id], release_pins=True)
    remove.execute()
    assert _shape(send) == "i"
    assert grown not in send.node.ports
    remove.undo()
    assert _shape(send) == "i f"
    assert send.node.ports[grown].is_linked()


def test_typed_pin_stays_after_edge_delete(graph: BaseGraph) -> None:
    send = _node(graph, OscSendNode, shape="f", x=400)
    number = _number(graph)
    edge_id = _connect(graph, number, "value", send, "arg_1").wrapper.edge_id
    RemoveElementsAction(graph, [], [edge_id], release_pins=True).execute()
    assert _shape(send) == "f"
    assert "arg_1" in send.node.ports


def test_reorder_rewrites_shape(graph: BaseGraph) -> None:
    send = _node(graph, OscSendNode, shape="f i s", x=400)
    a, b, c = (port_id for port_id, _ in _typed(send))
    action = ReorderPortsAction(graph, send.node_id, [c, a, b, _slot(send)])
    action.execute()
    assert _shape(send) == "s f i"
    assert [t for _, t in _typed(send)] == ["STRING", "FLOAT", "INT"]
    action.undo()
    assert _shape(send) == "f i s"


def test_reorder_keeps_skips_in_place(graph: BaseGraph) -> None:
    receive = _node(graph, OscReceiveNode, shape="f _ i")
    a, b = (port_id for port_id, _ in _typed(receive))
    ReorderPortsAction(graph, receive.node_id, [b, a, _slot(receive)]).execute()
    assert _shape(receive) == "i _ f"


def test_deleting_grown_edge_after_invalid_typing(graph: BaseGraph) -> None:
    send = _node(graph, OscSendNode, shape="i", x=400)
    grown = _slot(send)
    edge_id = _connect(graph, _number(graph), "value", send, grown).wrapper.edge_id
    send.node.ports["arg_shape"].set_value("i f q")
    RemoveElementsAction(graph, [], [edge_id], release_pins=True).execute()
    assert _shape(send) == "i"


def _outlet_order(wrapper: Any) -> list[str]:
    outlets = [p for p in wrapper.node.ports.values() if p.is_outlet()]
    return [p.id for p in sorted(outlets, key=lambda p: p.order)]


@pytest.mark.parametrize("shape", ["", "f i", "f _ vf3"])
def test_receive_slot_is_the_last_outlet(graph: BaseGraph, shape: str) -> None:
    receive = _node(graph, OscReceiveNode)
    receive.node.ports["address"].set_value("/blob/*")
    receive.node.ports["arg_shape"].set_value(shape)
    assert _outlet_order(receive)[-1] == _slot(receive)


def test_receive_slot_stays_last_after_growing(graph: BaseGraph) -> None:
    receive = _node(graph, OscReceiveNode, shape="i")
    send = _node(graph, OscSendNode, shape="vf3", x=400)
    _connect(graph, receive, _slot(receive), send, "arg_1")
    assert _outlet_order(receive)[-1] == _slot(receive)


@pytest.mark.parametrize("cls", [OscReceiveNode, OscSendNode])
def test_configs_explain_themselves(graph: BaseGraph, cls: Any) -> None:
    ports = _node(graph, cls).node.ports
    assert "Gate file" in ports["gate"].description
    assert "Arg shape" in ports["arg_shape"].description or "token" in ports["arg_shape"].description
    assert "pin" in ports["arg_shape"].description
    if cls is OscReceiveNode:
        assert "match_" in ports["address"].description
