"""MIDI test fixtures: virtual ports, so no hardware is needed (skipped where unsupported)."""

from __future__ import annotations

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


class Source:
    """A virtual port that sends: other programs see it as a MIDI input."""

    def __init__(self, name: str | None = None) -> None:
        self.name = name or f"protokol-src-{uuid.uuid4().hex[:6]}"
        self._out = rtmidi.MidiOut()
        self._out.open_virtual_port(self.name)
        time.sleep(0.1)

    def send(self, *data: int) -> None:
        self._out.send_message(list(data))

    def close(self) -> None:
        self._out.close_port()


class Sink:
    """A virtual port that receives: other programs see it as a MIDI output."""

    def __init__(self) -> None:
        self.name = f"protokol-sink-{uuid.uuid4().hex[:6]}"
        self.received: list[list[int]] = []
        self._in = rtmidi.MidiIn()
        self._in.ignore_types(sysex=False, timing=False, active_sense=True)
        self._in.set_callback(lambda event, _data=None: self.received.append(list(event[0])))
        self._in.open_virtual_port(self.name)
        time.sleep(0.1)

    def close(self) -> None:
        self._in.cancel_callback()
        time.sleep(0.02)
        self._in.close_port()


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
