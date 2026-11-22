"""MIDI presence for the device watch: probes kept open, and live port lists (Plan 4b, task 2)."""

from typing import Any

import pytest

from haybale_protokol_midi.driver import MidiDriver
from tests.midi.conftest import Source, needs_backend, needs_virtual


@needs_virtual
def test_virtual_port_presence_follows_open_and_delete() -> None:
    driver = MidiDriver()
    try:
        source = Source()
        assert source.name in dict(driver.list_devices())
        source.close()
        assert source.name not in dict(driver.list_devices())
    finally:
        driver.close()


@needs_backend
def test_listing_reuses_one_probe_pair_per_process(monkeypatch: pytest.MonkeyPatch) -> None:
    import haybale_protokol_midi.driver as driver_module

    made: list[str] = []
    real_in, real_out = driver_module.rtmidi.MidiIn, driver_module.rtmidi.MidiOut

    def counting(cls: Any, label: str) -> Any:
        def make(*args: Any, **kwargs: Any) -> Any:
            made.append(label)
            return cls(*args, **kwargs)

        return make

    monkeypatch.setattr(driver_module.rtmidi, "MidiIn", counting(real_in, "in"))
    monkeypatch.setattr(driver_module.rtmidi, "MidiOut", counting(real_out, "out"))
    MidiDriver().close()  # start without probes
    made.clear()
    drivers = [MidiDriver() for _ in range(3)]
    try:
        for _ in range(5):
            for driver in drivers:
                driver.list_devices()
        assert sorted(made) == ["in", "out"], "one probe pair for the whole process"
    finally:
        drivers[0].close()


@needs_backend
def test_close_is_safe_twice_and_lists_again() -> None:
    driver = MidiDriver()
    driver.list_devices()
    driver.close()
    driver.close()
    assert isinstance(driver.list_devices(), list)
    driver.close()
