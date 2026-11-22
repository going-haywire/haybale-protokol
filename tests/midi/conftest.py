"""MIDI test fixtures: virtual ports, so no hardware is needed (skipped where unsupported)."""

from __future__ import annotations

import re
import time
import uuid
from collections.abc import Callable, Iterator
from typing import Any

import pytest

rtmidi = pytest.importorskip("rtmidi")


def _virtual_supported() -> bool:
    try:
        probe = rtmidi.MidiOut()
        probe.open_virtual_port(f"protokol-probe-{uuid.uuid4().hex[:6]}")
        probe.close_port()
        return True
    except Exception:
        return False


VIRTUAL = _virtual_supported()
needs_virtual = pytest.mark.skipif(not VIRTUAL, reason="MIDI virtual ports are not available here")


def _backend_present() -> bool:
    try:
        rtmidi.MidiIn().delete()
        return True
    except Exception:
        return False


BACKEND = _backend_present()
needs_backend = pytest.mark.skipif(not BACKEND, reason="this machine has no MIDI system")


def _listed(port: str, kind: Any) -> str:
    """The name other programs see for a virtual port opened as ``port``.

    CoreMIDI lists it as opened; ALSA lists it as ``RtMidi… Client:<port> <client>:<port>``.
    """
    alsa = re.compile(rf":{re.escape(port)} \d+:\d+$")
    deadline = time.monotonic() + 1.0
    while True:
        names = kind().get_ports()
        found = [name for name in names if name == port or alsa.search(name)]
        if found or time.monotonic() > deadline:
            break
        time.sleep(0.02)
    assert len(found) == 1, f"virtual port {port!r} listed as {found} among {names}"
    return found[0]


class Source:
    """A virtual port that sends: other programs see it as a MIDI input.

    ``port`` is the name it was opened with; ``name`` is the name the system lists for it.
    """

    def __init__(self, port: str | None = None) -> None:
        self.port = port or f"protokol-src-{uuid.uuid4().hex[:6]}"
        self._out: Any = rtmidi.MidiOut()
        self._out.open_virtual_port(self.port)
        self.name = _listed(self.port, rtmidi.MidiIn)

    def send(self, *data: int) -> None:
        self._out.send_message(list(data))

    def close(self) -> None:
        """Remove the port, like unplugging it (on ALSA ``close_port`` alone leaves it listed).

        Safe to call twice: a test may unplug the port before the fixture's own close.
        """
        if self._out is None:
            return
        out, self._out = self._out, None
        out.close_port()
        out.delete()


class Sink:
    """A virtual port that receives: other programs see it as a MIDI output."""

    def __init__(self) -> None:
        self.port = f"protokol-sink-{uuid.uuid4().hex[:6]}"
        self.received: list[list[int]] = []
        self._in: Any = rtmidi.MidiIn()
        self._in.ignore_types(sysex=False, timing=False, active_sense=True)
        self._in.set_callback(lambda event, _data=None: self.received.append(list(event[0])))
        self._in.open_virtual_port(self.port)
        self.name = _listed(self.port, rtmidi.MidiOut)

    def close(self) -> None:
        """Remove the port, like unplugging it; safe to call twice."""
        if self._in is None:
            return
        midi, self._in = self._in, None
        midi.cancel_callback()
        time.sleep(0.02)
        midi.close_port()
        midi.delete()


@pytest.fixture
def source() -> Iterator[Source]:
    port = Source()
    yield port
    port.close()


@pytest.fixture
def sink() -> Iterator[Sink]:
    port = Sink()
    yield port
    port.close()


def wait_for(predicate: Callable[[], Any], timeout: float = 2.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return bool(predicate())
