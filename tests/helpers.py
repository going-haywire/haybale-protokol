"""Graph-building helpers, copied from the haywire monorepo's test conftest."""

from __future__ import annotations

from typing import Any


def make_node(graph: Any, registry_key: str, **kwargs: Any) -> Any:
    """``graph.create_node_wrapper`` that fails loudly instead of returning None."""
    wrapper = graph.create_node_wrapper(registry_key, **kwargs)
    assert wrapper is not None, f"node creation failed for {registry_key!r}"
    return wrapper


def make_edge(graph: Any, source_id: str, outlet_id: str, sink_id: str, inlet_id: str, **kwargs: Any) -> Any:
    """``graph.create_edge_wrapper`` that fails loudly instead of returning None."""
    edge = graph.create_edge_wrapper(source_id, outlet_id, sink_id, inlet_id, **kwargs)
    assert edge is not None, f"edge creation failed: {outlet_id} -> {inlet_id}"
    return edge
