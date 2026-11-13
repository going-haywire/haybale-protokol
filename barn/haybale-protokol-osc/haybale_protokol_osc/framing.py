"""OSC packets on a TCP stream: OSC 1.0 frames each packet with a 32-bit big-endian length,
OSC 1.1 with SLIP (an END byte, ``0xC0``, around each packet; END and ESC inside are escaped).
"""

from __future__ import annotations

import struct
from typing import Literal, get_args

from pythonosc import slip

Framing = Literal["1.0", "1.1"]

FRAMINGS: tuple[str, ...] = get_args(Framing)
#: Largest packet a reader accepts; a peer claiming more is out of sync or hostile.
MAX_FRAME = 1 << 20

_LENGTH = struct.Struct(">I")


class FrameError(ValueError):
    """The stream cannot be cut into packets; the connection must be dropped."""


def encode_frame(packet: bytes, framing: Framing) -> bytes:
    """``packet`` framed for the stream."""
    if framing == "1.0":
        return _LENGTH.pack(len(packet)) + packet
    return bytes(slip.encode(packet))


class FrameReader:
    """Cuts a byte stream into packets, whatever the read boundaries."""

    def __init__(self, framing: Framing, max_frame: int = MAX_FRAME) -> None:
        if framing not in FRAMINGS:
            raise ValueError(f"unknown framing {framing!r}; use one of {FRAMINGS}")
        self.framing = framing
        self.max_frame = max_frame
        self._buffer = bytearray()

    def feed(self, data: bytes) -> list[bytes]:
        """Add ``data``; return every packet now complete, in order.

        Raises:
            FrameError: A length over ``max_frame``, or a SLIP packet growing past it.
        """
        self._buffer.extend(data)
        return self._cut_length() if self.framing == "1.0" else self._cut_slip()

    def _cut_length(self) -> list[bytes]:
        packets: list[bytes] = []
        while len(self._buffer) >= _LENGTH.size:
            (size,) = _LENGTH.unpack_from(self._buffer)
            if size > self.max_frame:
                raise FrameError(f"frame length {size} over the limit of {self.max_frame}")
            end = _LENGTH.size + size
            if len(self._buffer) < end:
                break
            packets.append(bytes(self._buffer[_LENGTH.size : end]))
            del self._buffer[:end]
        return packets

    def _cut_slip(self) -> list[bytes]:
        packets: list[bytes] = []
        while True:
            end = self._buffer.find(slip.END)
            if end == -1:
                break
            raw = bytes(self._buffer[:end])
            del self._buffer[: end + 1]
            if raw:
                try:
                    packets.append(bytes(slip.decode(raw)))
                except slip.ProtocolError as exc:
                    raise FrameError(f"bad SLIP escape: {exc}") from None
        if len(self._buffer) > self.max_frame:
            raise FrameError(f"no SLIP END within {self.max_frame} bytes")
        return packets
