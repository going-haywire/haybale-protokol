"""ReceiveBinding: a Receive node's hold on its gate's Line while its graph runs.

Created in the node's ``on_startup`` and closed in ``on_shutdown``. The Line's thread calls
``accept`` for each message; an accepted payload goes to ``fire`` (the node's
``context.emit_callback``). ``fire`` may wait when a Block-mode flow queue is full, so a
Block-mode binding hands payloads to its own thread and the Line thread never waits.

A binding whose gate's Device is not plugged in, at start or later, waits for it and takes the
Line again when it comes back (design §10.5), so the graph needs no restart.
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
        self._state = state
        self._bind_lock = threading.Lock()
        """Guards ``_use``, ``_waiting`` and ``_reconnect`` between the node, the watch and a retry."""
        self._waiting = False
        """True while the gate's Device is not plugged in: the next healthy report reconnects."""
        self._reconnect: threading.Thread | None = None
        self._attempt = threading.Lock()
        """Held for a whole reconnect attempt, so two attempts never both take the Line."""
        self._use: LineUse | None = None
        result = state.use(gate_name, "in", self._on_message)
        if isinstance(result, LineUse):
            self._use = result
            self._status = f"listening on {gate_name}"
        elif state.health(gate_name).state == "not plugged in":
            self._wait_for_device()
        else:
            self._status = str(result)
        self._unwatch = state.watch_health(self._on_health)
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
        """Give the Line back, stop waiting for its Device, stop the forwarding thread; safe twice."""
        self._unwatch()
        with self._bind_lock:
            use, self._use = self._use, None
            self._waiting = False
            reconnect = self._reconnect
        if use is not None:
            use.release()
        if reconnect is not None and reconnect is not threading.current_thread():
            reconnect.join(timeout=2.0)
        with self._wake:
            self._closing = True
            self._pending.clear()
            self._wake.notify()
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(timeout=1.0)

    # -- waiting for the Device ------------------------------------------------------

    def _wait_for_device(self) -> None:
        gate = self._state.gates().get(self.gate_name)
        device = gate.device if gate is not None else None
        self._waiting = True
        self._status = f"waiting for '{device}'"

    def _on_health(self) -> None:
        """On a health change (watch thread): drop an unplugged Line, or reconnect when it is back."""
        with self._bind_lock:
            if self._closing:
                return
            use = self._use
        if use is not None:
            unplugged = self._state.health(self.gate_name).state == "not plugged in"
            if use.line.is_closed or unplugged:
                with self._bind_lock:
                    if self._use is use:
                        self._use = None
                        self._wait_for_device()
                use.release()
                if unplugged:
                    # Close it, not just give it back: a port that went away never comes back to
                    # the same connection (ALSA drops it), so the replug must open a fresh Line.
                    use.line.close()
            return
        if not self._waiting or not self._state.health(self.gate_name).healthy:
            return
        with self._bind_lock:
            if self._closing or (self._reconnect is not None and self._reconnect.is_alive()):
                return
            self._reconnect = threading.Thread(
                target=self._try_reconnect, name=f"protokol-recv-reconnect-{self.gate_name}", daemon=True
            )
            self._reconnect.start()

    def _try_reconnect(self) -> None:
        with self._attempt:
            with self._bind_lock:
                if self._closing or not self._waiting or self._use is not None:
                    return  # closed, or an earlier attempt already took the Line
            result = self._state.use(self.gate_name, "in", self._on_message)
            if not isinstance(result, LineUse):
                return  # still not openable: the next health report tries again
            with self._bind_lock:
                keep = not self._closing and self._waiting and self._use is None
                if keep:
                    self._use, self._waiting = result, False
                    self._status = f"listening on {self.gate_name}"
            if not keep:
                result.release()

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
    from haywire.api.workbench import get_library_state_container

    state = get_library_state_container().get(ProtokolState)
    if state is None:
        raise RuntimeError("haybale-protokol is not enabled")
    return state
