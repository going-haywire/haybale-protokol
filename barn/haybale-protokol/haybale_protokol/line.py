"""The Line: the one open port or device connection that Gates and the Monitor share.

A Line opens with its first user and closes after the last one leaves, plus the grace
period, so a graph restart does not drop a peer. Its Connection's thread delivers each
message here; the Line updates the Line cache and hands the message to every subscriber on
that same thread, so subscribers must return quickly. A closed Line is finished:
``ProtokolState`` makes a new one for the next user.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Hashable

from haybale_protokol.drivers import Connection, LineKey, Message

logger = logging.getLogger(__name__)

Subscriber = Callable[[Message], None]


class LineOpenError(RuntimeError):
    """The Line's Connection could not be opened; ``Line.status`` says why."""


class Line:
    """One shared connection, counted by its users."""

    def __init__(
        self,
        key: LineKey,
        connection: Connection,
        cache_key: Callable[[Message], Hashable],
        grace_s: Callable[[], float],
    ) -> None:
        self.key = key
        self.connection = connection
        self._cache_key = cache_key
        self._grace_s = grace_s
        self._lock = threading.Lock()
        self._users: dict[int, Subscriber | None] = {}
        self._subscribers: tuple[Subscriber, ...] = ()
        self._next_token = 0
        self._cache: dict[Hashable, Message] = {}
        self._timer: threading.Timer | None = None
        self._open = False
        self._closed = False
        self._error: str | None = None
        self._failed_subscribers: set[int] = set()
        self.on_closed: Callable[[Line], None] | None = None
        """Called once, after the Line closed."""
        self.on_changed: Callable[[Line], None] | None = None
        """Called when the Line opens, closes, or its users change."""

    @property
    def is_open(self) -> bool:
        return self._open

    @property
    def users(self) -> int:
        return len(self._users)

    @property
    def status(self) -> str:
        if self._error is not None:
            return f"cannot open: {self._error}"
        if self._closed:
            return "closed"
        if not self._open:
            return "not open"
        return self.connection.status

    def add_user(self, subscriber: Subscriber | None = None) -> int:
        """Count a user, opening the Line if it is the first; returns the token to give back.

        Raises:
            LineOpenError: The Connection could not be opened, or the Line already closed.
        """
        with self._lock:
            if self._closed:
                raise LineOpenError("line closed")
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            if not self._open:
                try:
                    self.connection.start(self._deliver)
                except OSError as exc:
                    self._error = exc.strerror or str(exc)
                    raise LineOpenError(self.status) from exc
                self._error = None
                self._open = True
            token = self._next_token
            self._next_token += 1
            self._users[token] = subscriber
            self._subscribers = tuple(s for s in self._users.values() if s is not None)
        self._notify_changed()
        return token

    def remove_user(self, token: int) -> None:
        """Give back a user's token; the last one starts the grace period. Unknown tokens are ignored."""
        close_now = False
        with self._lock:
            if token not in self._users:
                return
            del self._users[token]
            self._subscribers = tuple(s for s in self._users.values() if s is not None)
            if not self._users and self._open:
                grace = max(0.0, float(self._grace_s()))
                if grace == 0:
                    close_now = True
                else:
                    self._timer = threading.Timer(grace, self._close_if_unused)
                    self._timer.daemon = True
                    self._timer.start()
        if close_now:
            self._close_if_unused()
        else:
            self._notify_changed()

    def close(self) -> None:
        """Close at once, whatever the users (driver removed, library disabled)."""
        with self._lock:
            self._users.clear()
            self._subscribers = ()
        self._close_if_unused()

    def send(self, message: Message) -> bool:
        """Send through the Connection; ``False`` while the Line is not open."""
        if not self._open:
            return False
        return self.connection.send(message)

    def cached(self) -> list[Message]:
        """The last message per cache key, oldest first."""
        with self._lock:
            return list(self._cache.values())

    def _deliver(self, message: Message) -> None:
        key = self._cache_key(message)
        with self._lock:
            self._cache.pop(key, None)
            self._cache[key] = message
            subscribers = self._subscribers
        for subscriber in subscribers:
            try:
                subscriber(message)
            except Exception:
                if id(subscriber) not in self._failed_subscribers:
                    self._failed_subscribers.add(id(subscriber))
                    logger.exception("Subscriber of line %s failed; later failures are not logged", self.key)

    def _close_if_unused(self) -> None:
        with self._lock:
            if self._users or self._closed:
                return
            self._timer = None
            was_open = self._open
            self._open = False
            self._closed = True
        if was_open:
            try:
                self.connection.close()
            except Exception:
                logger.exception("Closing line %s failed", self.key)
        if self.on_closed is not None:
            self.on_closed(self)
        self._notify_changed()

    def _notify_changed(self) -> None:
        if self.on_changed is not None:
            self.on_changed(self)
