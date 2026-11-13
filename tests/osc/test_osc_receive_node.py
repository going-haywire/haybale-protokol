"""OSC Receive: messages on an input gate run the node's flow."""

from pathlib import Path
from typing import Any

import re

import pytest
from pythonosc.udp_client import SimpleUDPClient

from haybale_protokol.gates import Gate
from haybale_protokol_osc.nodes.osc_receive import OscReceiveNode, convert_capture
from haywire.core.graph.base import BaseGraph
from haywire.core.graph.scheduler import SyncScheduler
from tests.helpers import make_node
from tests.osc.graphs import protokol_project, record, running, wait_until

pytestmark = pytest.mark.integration

_PIN = re.compile(r"args|arg_\d+|match_\d+")


def _gate(port: int) -> Gate:
    return Gate("in", "osc", "in", options={"port": port, "bind": "127.0.0.1"})


def _receive(graph: Any, gate: str = "in", address: str = "", shape: str = "") -> Any:
    wrapper = make_node(graph, OscReceiveNode.class_identity.registry_key)
    wrapper.node.ports["gate"].set_value(gate)
    wrapper.node.ports["address"].set_value(address)
    wrapper.node.ports["arg_shape"].set_value(shape)
    return wrapper


def _send(port: int, address: str, *args: Any) -> None:
    SimpleUDPClient("127.0.0.1", port).send_message(address, list(args))


def _listening(wrapper: Any) -> None:
    assert wait_until(lambda: str(wrapper.node.value("status")).startswith("listening on"))


def _ports(wrapper: Any) -> list[str]:
    return [p for p in wrapper.node.ports if _PIN.fullmatch(p)]


def test_args_list_by_default(graph: BaseGraph) -> None:
    wrapper = _receive(graph)
    assert _ports(wrapper) == ["args", "arg_1"]
    assert wrapper.node.ports["arg_1"].type_cls.__name__ == "ADD"


def test_shape_builds_typed_outlets(graph: BaseGraph) -> None:
    wrapper = _receive(graph, shape="f _ vi2")
    assert _ports(wrapper) == ["arg_1", "arg_2", "arg_3"]
    assert wrapper.node.ports["arg_1"].type_cls.__name__ == "FLOAT"
    assert wrapper.node.ports["arg_2"].type_cls.__name__ == "VEC2I"
    assert wrapper.node.ports["arg_3"].type_cls.__name__ == "ADD"
    wrapper.node.ports["arg_shape"].set_value("")
    assert [p for p in _ports(wrapper) if wrapper.node.ports[p].type_cls.__name__ != "ADD"] == ["args"]


def test_pattern_builds_capture_outlets(graph: BaseGraph) -> None:
    wrapper = _receive(graph, address="/blob/*/{x,y}")
    assert _ports(wrapper) == ["args", "arg_1", "match_1", "match_2"]
    assert wrapper.node.ports["match_1"].type_cls.__name__ == "ADD"


def test_invalid_shape_keeps_ports(graph: BaseGraph) -> None:
    wrapper = _receive(graph, shape="f")
    wrapper.node.ports["arg_shape"].set_value("f q")
    assert _ports(wrapper) == ["arg_1", "arg_2"]
    assert "not applied" in str(wrapper.node.value("status"))


def test_receives_into_flow(graph: BaseGraph, tmp_path: Path, udp_port: int) -> None:
    wrapper = _receive(graph, address="/fader/1")
    runs = record(wrapper, "args", "address_out")
    with protokol_project(tmp_path, _gate(udp_port)), running(graph):
        _listening(wrapper)
        _send(udp_port, "/fader/2", 0.1)
        _send(udp_port, "/fader/1", 0.5)
        assert wait_until(lambda: len(runs) >= 1)
    assert runs[-1]["args"] == [0.5]
    assert runs[-1]["address_out"] == "/fader/1"
    assert len(runs) == 1


def test_typed_outlets_receive(graph: BaseGraph, tmp_path: Path, udp_port: int) -> None:
    wrapper = _receive(graph, shape="f i")
    runs = record(wrapper, "arg_1", "arg_2")
    with protokol_project(tmp_path, _gate(udp_port)), running(graph):
        _listening(wrapper)
        _send(udp_port, "/x", 0.5, 3)
        assert wait_until(lambda: len(runs) >= 1)
    assert (runs[-1]["arg_1"], runs[-1]["arg_2"]) == (0.5, 3)


def test_pattern_filters_and_captures(graph: BaseGraph, tmp_path: Path, udp_port: int) -> None:
    wrapper = _receive(graph, address="/blob/*/pos")
    runs = record(wrapper, "args")
    with protokol_project(tmp_path, _gate(udp_port)), running(graph):
        _listening(wrapper)
        _send(udp_port, "/blob/7/size", 1)
        _send(udp_port, "/blob/3/pos", 2)
        assert wait_until(lambda: len(runs) >= 1)
    assert len(runs) == 1
    assert runs[0]["payload"]["captures"] == ("3",)


def test_mismatched_message_is_counted(graph: BaseGraph, tmp_path: Path, udp_port: int) -> None:
    wrapper = _receive(graph, shape="vf3")
    runs = record(wrapper, "arg_1", "status")
    with protokol_project(tmp_path, _gate(udp_port)), running(graph):
        _listening(wrapper)
        _send(udp_port, "/x", 1.0)
        _send(udp_port, "/x", 1.0, 2.0, 3.0)
        assert wait_until(lambda: len(runs) >= 1)
    assert runs[-1]["arg_1"] == [1.0, 2.0, 3.0]
    assert "1 skipped" in runs[-1]["status"]


def test_start_value_fires_cached_on_restart(graph: BaseGraph, tmp_path: Path, udp_port: int) -> None:
    wrapper = _receive(graph, address="/x")
    runs = record(wrapper, "args")
    with protokol_project(tmp_path, _gate(udp_port), grace=5.0):
        with running(graph):
            _listening(wrapper)
            _send(udp_port, "/x", 0.25)
            assert wait_until(lambda: len(runs) >= 1)
        with running(graph):
            assert wait_until(lambda: len(runs) >= 2)
    assert [run["args"] for run in runs] == [[0.25], [0.25]]


def test_missing_gate_status(graph: BaseGraph, tmp_path: Path) -> None:
    wrapper = _receive(graph, gate="nope")
    with protokol_project(tmp_path), running(graph):
        assert wait_until(lambda: wrapper.node.value("status") == "no gate named 'nope'")


def test_save_reload_keeps_ports(graph: BaseGraph) -> None:
    wrapper = _receive(graph, address="/a/*", shape="f i")
    loaded = BaseGraph(filestem="reload", validation_scheduler=SyncScheduler())
    assert loaded.load_from_dict(graph.to_dict())
    node = loaded.get_node_wrapper(wrapper.node_id).node
    assert node.value("arg_shape") == "f i"
    assert sorted(p for p in node.ports if _PIN.fullmatch(p)) == ["arg_1", "arg_2", "arg_3", "match_1"]


@pytest.mark.parametrize(
    ("text", "type_name", "expected"),
    [("3", "INT", 3), ("0.5", "FLOAT", 0.5), ("on", "BOOL", True), ("x", "STRING", "x")],
)
def test_convert_capture(text: str, type_name: str, expected: Any) -> None:
    assert convert_capture(text, type_name) == expected


def test_convert_capture_refuses() -> None:
    with pytest.raises(ValueError, match="INT"):
        convert_capture("3a", "INT")


def test_skips_show_even_when_nothing_fits(graph: BaseGraph, tmp_path: Path, udp_port: int) -> None:
    wrapper = _receive(graph, shape="vf3")
    with protokol_project(tmp_path, _gate(udp_port)), running(graph):
        _listening(wrapper)
        _send(udp_port, "/x", 1.0)
        assert wait_until(lambda: "1 skipped" in str(wrapper.node.value("status")))


def test_invalid_text_is_reverted(graph: BaseGraph) -> None:
    wrapper = _receive(graph, address="/a/*", shape="f")
    wrapper.node.ports["arg_shape"].set_value("f q")
    assert wrapper.node.value("arg_shape") == "f"
    wrapper.node.ports["address"].set_value("/a[z-a]")
    assert wrapper.node.value("address") == "/a/*"
    assert "not applied" in str(wrapper.node.value("status"))


def test_removed_pin_is_a_status_not_misaligned(graph: BaseGraph, tmp_path: Path, udp_port: int) -> None:
    from haywire.core.undo.actions.graph_actions import RemovePortAction

    wrapper = _receive(graph, shape="f i s")
    RemovePortAction(graph, wrapper.node_id, "arg_2").execute()
    runs = record(wrapper, "arg_3", "status")
    with protokol_project(tmp_path, _gate(udp_port)), running(graph):
        _listening(wrapper)
        _send(udp_port, "/x", 0.5, 7, "s")
        assert wait_until(lambda: "Arg shape" in str(wrapper.node.value("status")))
    assert all(run["arg_3"] != 7 for run in runs)
