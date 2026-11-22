"""The gate badge: a Receive or Send node shows each of its gates that does not work (design §10.3).

One ``NodeWarning`` per unhealthy gate, with the gate's health reason, kept up to date while the
node exists: when its gate setting changes, when its graph assembles or starts, and on every
health change (a device unplugged or plugged back in). Shared by the OSC and MIDI nodes.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from haywire.api import NodeWarning

from haybale_protokol.gate_names import gate_names, named_status
from haybale_protokol.states.protokol_state import ProtokolState

logger = logging.getLogger(__name__)

#: The ``NodeWarning.kind`` of the gate badge.
GATE_WARNING = "protokol-gate"


def gate_problems(state: ProtokolState, names: list[str]) -> list[str]:
    """The health reason of each gate in ``names`` that does not work, named by gate."""
    problems = []
    for name in names:
        health = state.health(name)
        if not health.healthy:
            problems.append(named_status(name, health.reason))
    return problems


class GateBadge:
    """Keeps a node's gate badge in step with its gates' health; the node owns one.

    The node calls ``start()`` in ``post_init``, ``refresh()`` when its gate setting changes or its
    graph assembles or starts, and ``stop()`` in ``on_teardown``. The state holds ``refresh`` weakly,
    so a node that is gone without ``stop()`` is not kept alive by it.
    """

    def __init__(self, node: Any, state: Callable[[], ProtokolState] | None = None) -> None:
        self._node = node
        self._get_state = state or _protokol_state
        self._unwatch: Callable[[], None] | None = None

    def start(self) -> None:
        state = self._state()
        if state is not None and self._unwatch is None:
            self._unwatch = state.watch_health(self.refresh)
        self.refresh()

    def stop(self) -> None:
        if self._unwatch is not None:
            self._unwatch()
            self._unwatch = None

    def refresh(self) -> None:
        """Set the node's gate warnings from its gates' health now; does nothing without a wrapper."""
        wrapper = getattr(self._node, "wrapper", None)
        state = self._state()
        if wrapper is None or state is None:
            return
        try:
            names = gate_names(str(self._node.value("gate") or ""))
            problems = gate_problems(state, names)
        except Exception:  # a node half torn down, or a gate file mid-write: try again next change
            logger.debug("gate badge refresh failed", exc_info=True)
            return
        wrapper.replace_warnings(GATE_WARNING, [NodeWarning(p, None, kind=GATE_WARNING) for p in problems])

    def _state(self) -> ProtokolState | None:
        try:
            return self._get_state()
        except RuntimeError:  # haybale-protokol not enabled (yet)
            return None


def _protokol_state() -> ProtokolState:
    from haybale_protokol.receive import get_protokol_state

    return get_protokol_state()
