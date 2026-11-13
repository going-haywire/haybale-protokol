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
from collections.abc import Callable, Hashable, Iterator, Mapping
from typing import Any

from pythonosc.osc_bundle import OscBundle
from pythonosc.osc_message import OscMessage
from pythonosc.osc_message_builder import OscMessageBuilder

from haybale_protokol.devices import Device
from haybale_protokol.drivers import Connection, LineKey, Message
from haybale_protokol.gates import Gate
from haybale_protokol_osc.framing import FRAMINGS, FrameError, FrameReader, Framing, encode_frame

logger = logging.getLogger(__name__)

#: How often a receiving thread checks whether it was closed.
POLL_S = 0.2
#: Largest datagram read; bigger ones are truncated by the OS and fail to parse.
MAX_DATAGRAM = 65536
#: Seconds a TCP client waits between connection attempts; the last step repeats.
BACKOFF_S = (0.5, 1.0, 2.0, 4.0, 5.0)
#: Longest a TCP connection attempt may take, so ``close()`` stays quick.
CONNECT_TIMEOUT_S = 0.5


class OscDriver:
    """``ProtocolDriver`` for ``protocol = "osc"``."""

    protocol = "osc"

    def line_key(self, gate: Gate, device: Device | None) -> LineKey:
        transport = gate.options.get("transport", "udp")
        port = gate.options.get("port")
        if port is None:
            raise ValueError("OSC gate needs a port")
        if not isinstance(port, int) or isinstance(port, bool) or not 0 < port < 65536:
            raise ValueError(f"OSC port must be a number from 1 to 65535, not {port!r}")
        if transport == "tcp":
            return self._tcp_line_key(gate, port)
        if transport != "udp":
            raise ValueError(f"OSC transport {transport!r} is unknown; use udp or tcp")
        if gate.direction == "two-way":
            raise ValueError("an OSC UDP gate is in or out, never two-way")
        if gate.direction == "in":
            return LineKey("osc", f"udp-in {_text_option(gate, 'bind', '0.0.0.0')}:{port}")
        return LineKey("osc", f"udp-out {_text_option(gate, 'host')}:{port}")

    def _tcp_line_key(self, gate: Gate, port: int) -> LineKey:
        role = gate.options.get("role", "client")
        if role not in ("client", "server"):
            raise ValueError(f"OSC TCP role {role!r} is unknown; use client or server")
        framing = gate.options.get("framing", "1.1")
        if framing not in FRAMINGS:
            raise ValueError(f"OSC TCP framing {framing!r} is unknown; use one of {FRAMINGS}")
        if role == "server":
            return LineKey("osc", f"tcp-server {_text_option(gate, 'bind', '0.0.0.0')}:{port}")
        return LineKey("osc", f"tcp-client {_text_option(gate, 'host')}:{port}")

    def line_options(self, gate: Gate) -> Mapping[str, Any]:
        """Options every gate on one Line must agree on: the framing of a TCP Line."""
        if gate.options.get("transport", "udp") == "tcp":
            return {"framing": gate.options.get("framing", "1.1")}
        return {}

    def open(self, key: LineKey, gate: Gate, device: Device | None) -> Connection:
        kind, _, where = key.address.partition(" ")
        host, _, port = where.rpartition(":")
        if kind == "udp-in":
            return UdpInConnection(host, int(port))
        if kind == "udp-out":
            return UdpOutConnection(host, int(port))
        framing = gate.options.get("framing", "1.1")
        if kind == "tcp-client":
            return TcpClientConnection(host, int(port), framing)
        raise ValueError("an OSC TCP server is not available yet")

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


class TcpClientConnection:
    """Connects to one TCP peer and keeps reconnecting, with backoff, while the Line is open.

    Sends while disconnected are dropped and counted, never queued.
    """

    def __init__(self, host: str, port: int, framing: Framing) -> None:
        self.host = host
        self.port = port
        self.framing = framing
        self.sent = 0
        self.dropped = 0
        self.bad = 0
        self.attempts = 0
        """Failed or lost connections since the last good one."""
        self.thread: threading.Thread | None = None
        self._sock: socket.socket | None = None
        self._send_lock = threading.Lock()
        self._closing = threading.Event()

    @property
    def connected(self) -> bool:
        return self._sock is not None

    @property
    def status(self) -> str:
        if self.connected:
            state = f"connected to tcp {self.host}:{self.port}"
        elif self.attempts:
            state = f"reconnecting ({self.attempts}) to tcp {self.host}:{self.port}"
        else:
            state = f"connecting to tcp {self.host}:{self.port}"
        text = f"{state} · sent {self.sent} · dropped {self.dropped}"
        return f"{text} · {self.bad} bad" if self.bad else text

    def start(self, deliver: Callable[[Message], None]) -> None:
        self.thread = threading.Thread(
            target=self._run, args=(deliver,), name=f"protokol-osc-tcp-client-{self.port}", daemon=True
        )
        self.thread.start()

    def send(self, message: Message) -> bool:
        with self._send_lock:
            sock = self._sock
            if sock is None:
                self.dropped += 1
                return False
            try:
                packet = build_message(message.address, message.args, message.extra.get("types"))
                sock.sendall(encode_frame(packet, self.framing))
            except OSError:
                self.dropped += 1
                _shutdown(sock)
                return False
            except Exception as exc:
                self.dropped += 1
                logger.debug("OSC send to %s:%s dropped: %s", self.host, self.port, exc)
                return False
            self.sent += 1
            return True

    def close(self) -> None:
        self._closing.set()
        with self._send_lock:
            if self._sock is not None:
                _shutdown(self._sock)
        if self.thread is not None and self.thread is not threading.current_thread():
            self.thread.join(timeout=CONNECT_TIMEOUT_S + 2 * POLL_S + 1.0)

    def _run(self, deliver: Callable[[Message], None]) -> None:
        while not self._closing.is_set():
            try:
                sock = socket.create_connection((self.host, self.port), timeout=CONNECT_TIMEOUT_S)
            except OSError:
                self._back_off()
                continue
            sock.settimeout(POLL_S)
            with self._send_lock:
                self._sock = sock
                self.attempts = 0
            try:
                self.bad += read_stream(sock, self.framing, deliver, self._closing)
            finally:
                with self._send_lock:
                    self._sock = None
                sock.close()
            self._back_off()

    def _back_off(self) -> None:
        if self._closing.is_set():
            return
        self.attempts += 1
        self._closing.wait(BACKOFF_S[min(self.attempts, len(BACKOFF_S)) - 1])


def read_stream(
    sock: socket.socket, framing: Framing, deliver: Callable[[Message], None], closing: threading.Event
) -> int:
    """Deliver every message on ``sock`` until the peer leaves, the stream breaks, or ``closing`` is set.

    Returns:
        How many bad packets were seen; a broken frame counts one and ends the stream.
    """
    reader = FrameReader(framing)
    bad = 0
    while not closing.is_set():
        try:
            data = sock.recv(MAX_DATAGRAM)
        except TimeoutError:
            continue
        except OSError:
            return bad
        if not data:
            return bad
        try:
            packets = reader.feed(data)
        except FrameError:
            return bad + 1
        now = time.time()
        for packet in packets:
            try:
                messages = list(_split(packet, None))
            except Exception:
                bad += 1
                continue
            for message, timetag in messages:
                extra = {"timetag": timetag} if timetag is not None else {}
                deliver(Message(message.address, tuple(message.params), now, extra))
    return bad


def _shutdown(sock: socket.socket) -> None:
    try:
        sock.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass


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


def _text_option(gate: Gate, key: str, default: str | None = None) -> str:
    """The text option ``key`` of ``gate``.

    Raises:
        ValueError: It is missing (with no default), empty, or not text.
    """
    value = gate.options.get(key, default)
    if value is None:
        raise ValueError(f"OSC gate needs a {key}")
    if not isinstance(value, str) or not value:
        raise ValueError(f"OSC gate {key} must be text, not {value!r}")
    return value


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
