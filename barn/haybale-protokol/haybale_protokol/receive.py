"""ReceiveBinding: a Receive node's hold on its gate's Line while its graph runs.

Created in the node's ``on_startup`` and closed in ``on_shutdown``. The Line's thread calls
``accept`` for each message; an accepted payload goes to ``fire`` (the node's
``context.emit_callback``). ``fire`` may wait when a Block-mode flow queue is full, so a
Block-mode binding hands payloads to its own thread and the Line thread never waits.
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from collections.abc import Callable
from typing import Any

from haybale_protokol.drivers import Message
from haybale_protokol.line_use import LineUse
from haybale_protokol.states.protokol_state import ProtokolState

logger = logging.getLogger(__name__)

Payload = dict[str, Any]

#: Payloads a Block-mode binding holds while its flow runs behind.
DEFAULT_CAPACITY = 1024


class ReceiveBinding:
    """Subscribes ``accept``/``fire`` to the Line of ``gate_name``; ``status`` says how it went."""

    def __init__(
        self,
        state: ProtokolState,
        gate_name: str,
        accept: Callable[[Message], Payload | None],
        fire: Callable[[Payload], None],
        *,
        start_value: bool,
        block: bool,
        capacity: int = DEFAULT_CAPACITY,
    ) -> None:
        self.gate_name = gate_name
        self.dropped = 0
        """Payloads lost because a Block-mode binding's own queue was full (the oldest go first)."""
        self._accept = accept
        self._fire = fire
        self._pending: deque[Payload] = deque()
        self._capacity = capacity
        self._wake = threading.Condition()
        self._closing = False
        self._thread: threading.Thread | None = None
        if block:
            name = f"protokol-recv-{gate_name}"
            self._thread = threading.Thread(target=self._forward, name=name, daemon=True)
            self._thread.start()
        result = state.use(gate_name, "in", self._on_message)
        self._use: LineUse | None = result if isinstance(result, LineUse) else None
        self._status = f"listening on {gate_name}" if self._use is not None else str(result)
        if self._use is not None and start_value:
            for message in self._use.line.cached():
                self._on_message(message)

    @property
    def status(self) -> str:
        if self.dropped:
            return f"{self._status} · dropped {self.dropped}"
        return self._status

    @property
    def is_bound(self) -> bool:
        return self._use is not None

    def close(self) -> None:
        """Give the Line back and stop the forwarding thread; safe to call twice."""
        if self._use is not None:
            self._use.release()
        with self._wake:
            self._closing = True
            self._pending.clear()
            self._wake.notify()
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(timeout=1.0)

    def _on_message(self, message: Message) -> None:
        payload = self._accept(message)
        if payload is None:
            return
        if self._thread is None:
            self._fire(payload)
            return
        with self._wake:
            if self._closing:
                return
            if len(self._pending) >= self._capacity:
                self._pending.popleft()  # keep the newest: a stop behind a backlog of clocks still arrives
                self.dropped += 1
            self._pending.append(payload)
            self._wake.notify()

    def _forward(self) -> None:
        while True:
            with self._wake:
                while not self._pending and not self._closing:
                    self._wake.wait()
                if self._closing:
                    return
                payload = self._pending.popleft()
            try:
                self._fire(payload)
            except Exception:
                logger.exception("Receive on gate %s failed to fire", self.gate_name)


def get_protokol_state() -> ProtokolState:
    """The app's ProtokolState.

    Raises:
        RuntimeError: haybale-protokol is not enabled.
    """
    from haywire.core.di.context import get_library_state_container

    state = get_library_state_container().get(ProtokolState)
    if state is None:
        raise RuntimeError("haybale-protokol is not enabled")
    return state
