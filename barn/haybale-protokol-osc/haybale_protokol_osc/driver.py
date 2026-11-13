"""The OSC Protocol driver, over UDP.

Gate options read here::

    transport = "udp"      # the only transport until TCP lands
    port = 8000            # required
    bind = "0.0.0.0"       # input gates: the address to listen on (default all interfaces)
    host = "10.0.0.2"      # output gates: where to send (required)

UDP gates are always one-way. An input Line splits each OSC bundle into its messages, each
carrying the bundle's ``timetag`` in ``Message.extra``.
"""

from __future__ import annotations

import logging
import socket
import threading
import time
from collections.abc import Callable, Hashable, Iterator
from typing import Any

from pythonosc.osc_bundle import OscBundle
from pythonosc.osc_message import OscMessage
from pythonosc.osc_message_builder import OscMessageBuilder

from haybale_protokol.devices import Device
from haybale_protokol.drivers import Connection, LineKey, Message
from haybale_protokol.gates import Gate

logger = logging.getLogger(__name__)

#: How often a receiving thread checks whether it was closed.
POLL_S = 0.2
#: Largest datagram read; bigger ones are truncated by the OS and fail to parse.
MAX_DATAGRAM = 65536


class OscDriver:
    """``ProtocolDriver`` for ``protocol = "osc"``."""

    protocol = "osc"

    def line_key(self, gate: Gate, device: Device | None) -> LineKey:
        transport = gate.options.get("transport", "udp")
        if transport != "udp":
            raise ValueError(f"OSC transport {transport!r} is not supported yet; use udp")
        if gate.direction == "two-way":
            raise ValueError("an OSC UDP gate is in or out, never two-way")
        port = gate.options.get("port")
        if port is None:
            raise ValueError("OSC gate needs a port")
        if not isinstance(port, int) or isinstance(port, bool) or not 0 < port < 65536:
            raise ValueError(f"OSC port must be a number from 1 to 65535, not {port!r}")
        if gate.direction == "in":
            return LineKey("osc", f"udp-in {gate.options.get('bind', '0.0.0.0')}:{port}")
        host = gate.options.get("host")
        if not isinstance(host, str) or not host:
            raise ValueError("OSC output gate needs a host")
        return LineKey("osc", f"udp-out {host}:{port}")

    def open(self, key: LineKey, gate: Gate, device: Device | None) -> Connection:
        kind, _, where = key.address.partition(" ")
        host, _, port = where.rpartition(":")
        if kind == "udp-in":
            return UdpInConnection(host, int(port))
        return UdpOutConnection(host, int(port))

    def cache_key(self, message: Message) -> Hashable:
        return message.address

    def describe(self, message: Message) -> str:
        types = message.extra.get("types") or "".join(_type_tag(arg) for arg in message.args)
        values = " ".join(repr(arg) if isinstance(arg, str) else str(arg) for arg in message.args)
        return f"{message.address} ,{types} {values}".rstrip()


class UdpInConnection:
    """Listens on one UDP port; its daemon thread delivers every message it parses."""

    def __init__(self, bind: str, port: int) -> None:
        self.bind = bind
        self.port = port
        self.bad_packets = 0
        self.thread: threading.Thread | None = None
        self._sock: socket.socket | None = None
        self._closing = threading.Event()

    @property
    def status(self) -> str:
        text = f"listening on udp {self.bind}:{self.port}"
        return f"{text} · {self.bad_packets} bad" if self.bad_packets else text

    def start(self, deliver: Callable[[Message], None]) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.bind((self.bind, self.port))
        except OSError:
            sock.close()
            raise
        sock.settimeout(POLL_S)
        self._sock = sock
        self.thread = threading.Thread(
            target=self._run, args=(sock, deliver), name=f"protokol-osc-udp-in-{self.port}", daemon=True
        )
        self.thread.start()

    def send(self, message: Message) -> bool:
        return False

    def close(self) -> None:
        self._closing.set()
        if self.thread is not None and self.thread is not threading.current_thread():
            self.thread.join(timeout=2 * POLL_S + 1.0)
        if self._sock is not None:
            self._sock.close()
            self._sock = None

    def _run(self, sock: socket.socket, deliver: Callable[[Message], None]) -> None:
        while not self._closing.is_set():
            try:
                data, _peer = sock.recvfrom(MAX_DATAGRAM)
            except TimeoutError:
                continue
            except OSError:
                if not self._closing.is_set():
                    logger.exception("OSC line on udp %s:%s stopped", self.bind, self.port)
                return
            now = time.time()
            try:
                messages = list(_split(data, None))
            except Exception:
                self.bad_packets += 1
                continue
            for message, timetag in messages:
                extra = {"timetag": timetag} if timetag is not None else {}
                deliver(Message(message.address, tuple(message.params), now, extra))


class UdpOutConnection:
    """Sends to one host and port; unbuildable messages are dropped, never queued."""

    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port
        self.sent = 0
        self.dropped = 0
        self._sock: socket.socket | None = None

    @property
    def status(self) -> str:
        return f"sending to udp {self.host}:{self.port} · sent {self.sent} · dropped {self.dropped}"

    def start(self, deliver: Callable[[Message], None]) -> None:
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def send(self, message: Message) -> bool:
        if self._sock is None:
            return False
        try:
            dgram = build_message(message.address, message.args, message.extra.get("types"))
            self._sock.sendto(dgram, (self.host, self.port))
        except Exception as exc:
            self.dropped += 1
            logger.debug("OSC send to %s:%s dropped: %s", self.host, self.port, exc)
            return False
        self.sent += 1
        return True

    def close(self) -> None:
        if self._sock is not None:
            self._sock.close()
            self._sock = None


def build_message(address: str, args: tuple[Any, ...], types: str | None) -> bytes:
    """Encode one OSC message; with ``types`` each argument takes its tag, else python-osc infers.

    Raises:
        ValueError: ``types`` and ``args`` differ in length.
        pythonosc.osc_message_builder.BuildError: A value does not fit its tag.
    """
    builder = OscMessageBuilder(address)
    if types is None:
        for arg in args:
            builder.add_arg(arg)
    else:
        if len(types) != len(args):
            raise ValueError(f"{len(types)} type tags for {len(args)} arguments")
        for arg, tag in zip(args, types, strict=True):
            builder.add_arg(arg, tag)
    return bytes(builder.build().dgram)


def _split(data: bytes, timetag: float | None) -> Iterator[tuple[OscMessage, float | None]]:
    if OscBundle.dgram_is_bundle(data):
        bundle = OscBundle(data)
        for content in bundle:
            if isinstance(content, OscBundle):
                yield from _split(content.dgram, content.timestamp)
            else:
                yield content, bundle.timestamp
    else:
        yield OscMessage(data), timetag


def _type_tag(arg: Any) -> str:
    if isinstance(arg, bool):
        return "T" if arg else "F"
    if isinstance(arg, int):
        return "i"
    if isinstance(arg, float):
        return "f"
    if isinstance(arg, bytes):
        return "b"
    if arg is None:
        return "N"
    return "s"
