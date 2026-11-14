"""The MIDI Protocol driver: one Line per Device and direction, through python-rtmidi.

A MIDI gate is ``in`` or ``out`` and names a Device; the Device's OS id is the rtmidi port name
(inputs and outputs are separate ports with their own names). rtmidi calls back on its own thread
for each message, which is the Line's thread.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable, Hashable, Mapping, Sequence
from typing import Any

import rtmidi  # type: ignore[import-untyped]

from haybale_protokol.devices import Device
from haybale_protokol.drivers import Connection, GateField, LineKey, Message
from haybale_protokol.gates import Gate
import haybale_protokol_midi.midi_messages as midi_messages

logger = logging.getLogger(__name__)

#: Seconds an input's reading thread waits when no message is queued.
POLL_S = 0.001
#: Messages rtmidi holds for an input while its thread is busy.
QUEUE_SIZE = 4096
#: Seconds between checks that a port still exists (an unplugged Device).
PORT_CHECK_S = 0.5


class MidiDriver:
    """``ProtocolDriver`` for ``protocol = "midi"``."""

    protocol = "midi"
    uses_devices = True

    def gate_fields(self) -> tuple[GateField, ...]:
        """MIDI gates have no options of their own: the Device says which port."""
        return ()

    def line_key(self, gate: Gate, device: Device | None) -> LineKey:
        if gate.direction == "two-way":
            raise ValueError("a MIDI gate is in or out, never two-way")
        if device is None:
            raise ValueError("a MIDI gate needs a device")
        return LineKey("midi", f"{gate.direction} {device.os_id}")

    def line_options(self, gate: Gate) -> Mapping[str, Any]:
        return {}

    def open(self, key: LineKey, gate: Gate, device: Device | None) -> Connection:
        direction, _, port = key.address.partition(" ")
        return MidiInConnection(port) if direction == "in" else MidiOutConnection(port)

    def cache_key(self, message: Message) -> Hashable:
        return message.address

    def describe(self, message: Message) -> str:
        return midi_messages.describe(message)

    def parse_test_message(self, text: str) -> Message:
        return midi_messages.parse_test_message(text)

    def list_devices(self) -> list[tuple[str, str]]:
        """Every MIDI port on this machine, as ``(port name, "input" | "output" | "input and output")``."""
        try:
            inputs, outputs = set(_port_names(rtmidi.MidiIn)), set(_port_names(rtmidi.MidiOut))
        except Exception:  # no MIDI backend on this machine (e.g. Linux without ALSA's sequencer)
            logger.debug("listing MIDI ports failed", exc_info=True)
            return []
        names = sorted(inputs | outputs)
        return [(name, _role(name in inputs, name in outputs)) for name in names]


class MidiInConnection:
    """Listens on one MIDI input port; its own daemon thread reads and delivers each message.

    It polls rtmidi rather than taking rtmidi's callback: closing a port while a callback runs on
    CoreMIDI's thread deadlocks the process (the close keeps the GIL the callback waits for). The
    port is closed by the reading thread itself, after it stopped reading.
    """

    def __init__(self, port: str) -> None:
        self.port = port
        self.bad = 0
        self.gone = False
        """True once the port disappeared (the Device was unplugged)."""
        self.thread: threading.Thread | None = None
        self._closing = threading.Event()

    @property
    def status(self) -> str:
        if self.gone:
            return f"port gone: MIDI '{self.port}' (reconnect it, then restart the graph)"
        text = f"listening on MIDI '{self.port}'"
        return f"{text} · {self.bad} bad" if self.bad else text

    def start(self, deliver: Callable[[Message], None]) -> None:
        midi = rtmidi.MidiIn(queue_size_limit=QUEUE_SIZE)
        index = _index_of(midi, self.port)
        midi.ignore_types(sysex=False, timing=False, active_sense=True)
        try:
            midi.open_port(index)
        except Exception as exc:  # rtmidi's own error types
            midi.delete()
            raise OSError(f"cannot open MIDI port '{self.port}': {exc}") from exc
        self.thread = threading.Thread(
            target=self._read, args=(midi, deliver), name=f"protokol-midi-in-{self.port}", daemon=True
        )
        self.thread.start()

    def send(self, message: Message) -> bool:
        return False

    def close(self) -> None:
        self._closing.set()
        if self.thread is not None and self.thread is not threading.current_thread():
            self.thread.join(timeout=2.0)

    def _read(self, midi: Any, deliver: Callable[[Message], None]) -> None:
        checked = time.monotonic()
        try:
            while not self._closing.is_set():
                event = midi.get_message()
                if time.monotonic() - checked > PORT_CHECK_S:
                    checked = time.monotonic()
                    self.gone = self.port not in midi.get_ports()
                if event is None:
                    self._closing.wait(POLL_S)
                    continue
                try:
                    message = midi_messages.decode(event[0], time.time())
                except Exception:
                    self.bad += 1
                    continue
                if message is not None:
                    deliver(message)
        finally:
            midi.close_port()
            midi.delete()


class MidiOutConnection:
    """Sends to one MIDI output port; a message is sent whole, never queued."""

    def __init__(self, port: str) -> None:
        self.port = port
        self.sent = 0
        self.dropped = 0
        self.gone = False
        """True once the port disappeared (the Device was unplugged); sends are then dropped."""
        self._checked = 0.0
        self._midi: Any = None

    @property
    def status(self) -> str:
        self._check_port()
        if self.gone:
            reconnect = "(reconnect it, then restart the graph)"
            return f"port gone: MIDI '{self.port}' · dropped {self.dropped} {reconnect}"
        return f"sending to MIDI '{self.port}' · sent {self.sent} · dropped {self.dropped}"

    def start(self, deliver: Callable[[Message], None]) -> None:
        midi = rtmidi.MidiOut()
        index = _index_of(midi, self.port)
        try:
            midi.open_port(index)
        except Exception as exc:
            midi.delete()
            raise OSError(f"cannot open MIDI port '{self.port}': {exc}") from exc
        self._midi = midi

    def send(self, message: Message) -> bool:
        data = message.extra.get("bytes")
        self._check_port()
        if self._midi is None or not data or self.gone:
            self.dropped += 1
            return False
        try:
            self._midi.send_message(list(data))
        except Exception as exc:
            self.dropped += 1
            logger.debug("MIDI send to %s dropped: %s", self.port, exc)
            return False
        self.sent += 1
        return True

    def close(self) -> None:
        midi, self._midi = self._midi, None
        if midi is not None:
            midi.close_port()
            midi.delete()

    def _check_port(self) -> None:
        """Note an unplugged port, at most every ``PORT_CHECK_S`` (listing ports costs a system call)."""
        if self._midi is None or time.monotonic() - self._checked < PORT_CHECK_S:
            return
        self._checked = time.monotonic()
        self.gone = self.port not in self._midi.get_ports()


def _index_of(midi: Any, port: str) -> int:
    """The index of ``port`` among ``midi``'s ports.

    Raises:
        OSError: No port has this exact name (the Device is unplugged or renamed).
    """
    ports: Sequence[str] = midi.get_ports()
    if port not in ports:
        midi.delete()
        raise OSError(f"no MIDI port '{port}'")
    return list(ports).index(port)


def _port_names(cls: Any) -> list[str]:
    midi = cls()
    try:
        return list(midi.get_ports())
    finally:
        midi.delete()


def _role(is_input: bool, is_output: bool) -> str:
    if is_input and is_output:
        return "input and output"
    return "input" if is_input else "output"
