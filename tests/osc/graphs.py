"""Helpers for OSC node tests: a gate file on the shared ProtokolState, running a graph, recording runs."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from haybale_protokol.gates import Gate, gate_file_path, save_gates
from haybale_protokol.states.protokol_state import ProtokolState
from haywire.core.execution.interpreter import Interpreter


@contextmanager
def protokol_project(root: Path, *gates: Gate, grace: float = 0.0) -> Iterator[ProtokolState]:
    """Point the library system's ProtokolState at ``root`` with ``gates`` for one test."""
    from haywire.core.di.context import get_library_state_container

    state = get_library_state_container().get(ProtokolState)
    assert state is not None
    saved = (state.project_root, state.grace_s)
    save_gates(gate_file_path(root), gates)
    state.project_root = root
    state.grace_s = lambda: grace
    try:
        yield state
    finally:
        for line in state.lines():
            line.close()
        state.project_root, state.grace_s = saved


@contextmanager
def running(graph: Any) -> Iterator[Interpreter]:
    """Load and start ``graph``; stop it on exit."""
    interpreter = Interpreter()
    interpreter.load_graph(graph)
    interpreter.start_execution()
    try:
        yield interpreter
    finally:
        interpreter.shutdown()


def record(wrapper: Any, *port_ids: str) -> list[dict[str, Any]]:
    """Record the values of ``port_ids`` (and the trigger payload) after each worker run."""
    runs: list[dict[str, Any]] = []
    base = type(wrapper.node)

    class Recording(base):  # type: ignore[valid-type, misc]
        def worker(self, context: Any) -> Any:
            result = super().worker(context)
            entry = {port_id: self.value(port_id) for port_id in port_ids}
            entry["payload"] = context.trigger.payload if context.trigger else None
            runs.append(entry)
            return result

    wrapper.node.__class__ = Recording
    wrapper.node._executor = None
    return runs


def wait_until(predicate: Callable[[], bool], timeout: float = 2.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()
