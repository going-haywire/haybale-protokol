"""Monitor taps: a bounded view of what a Line receives and sends.

A tap is a Line user whose subscribers only append to a bounded buffer, so the Monitor never
slows a Line: when the buffer is full the oldest message drops and is counted.
"""

from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass
from typing import Literal

from haybale_protokol.drivers import Message
from haybale_protokol.states.protokol_state import LineUse

#: Messages a tap keeps; older ones drop.
MONITOR_BUFFER = 2000

Direction = Literal["in", "out"]


@dataclass(frozen=True, slots=True)
class TapEntry:
    """One message a tap saw, and which way it went."""

    message: Message
    direction: Direction


class Tap:
    """A Monitor's hold on one Line. Close it to give the Line back."""

    def __init__(self, buffer: int = MONITOR_BUFFER) -> None:
        self._entries: deque[TapEntry] = deque(maxlen=buffer)
        self._lock = threading.Lock()
        self.received = 0
        """Messages seen since the tap opened or was cleared, kept or not."""
        self.dropped = 0
        """Messages pushed out of the full buffer."""
        self.paused = False
        """While paused, messages are counted but not kept."""
        self.use: LineUse
        self._closed = False

    def messages(self) -> list[TapEntry]:
        """What the tap holds, oldest first."""
        with self._lock:
            return list(self._entries)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
            self.received = 0
            self.dropped = 0

    def close(self) -> None:
        """Give the Line back; a second call does nothing."""
        if not self._closed:
            self._closed = True
            self.use.release()

    def on_in(self, message: Message) -> None:
        self._add(TapEntry(message, "in"))

    def on_out(self, message: Message) -> None:
        self._add(TapEntry(message, "out"))

    def _add(self, entry: TapEntry) -> None:
        with self._lock:
            self.received += 1
            if self.paused:
                return
            if len(self._entries) == self._entries.maxlen:
                self.dropped += 1
            self._entries.append(entry)
