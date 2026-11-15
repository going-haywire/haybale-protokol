"""Matching a Device's port name when the OS appends a number that changes between boots."""

from haybale_protokol.drivers import find_device
from haybale_protokol_midi.driver import ALSA_SUFFIX, WINMM_SUFFIX, MidiDriver, match_port


def test_exact_name_wins() -> None:
    ports = ["nanoKONTROL2 20:0", "nanoKONTROL2 24:0"]
    assert match_port("nanoKONTROL2 24:0", ports, ALSA_SUFFIX) == "nanoKONTROL2 24:0"


def test_alsa_client_number_may_change() -> None:
    ports = ["Midi Through:Midi Through Port-0 14:0", "nanoKONTROL2:nanoKONTROL2 MIDI 1 24:0"]
    found = match_port("nanoKONTROL2:nanoKONTROL2 MIDI 1 20:0", ports, ALSA_SUFFIX)
    assert found == "nanoKONTROL2:nanoKONTROL2 MIDI 1 24:0"


def test_windows_index_may_change() -> None:
    ports = ["Microsoft GS Wavetable Synth 0", "Launchpad Mini 2"]
    assert match_port("Launchpad Mini 1", ports, WINMM_SUFFIX) == "Launchpad Mini 2"


def test_two_alike_devices_never_guess() -> None:
    ports = ["nanoKONTROL2 0", "nanoKONTROL2 1"]
    assert match_port("nanoKONTROL2 5", ports, WINMM_SUFFIX) is None


def test_a_number_of_the_name_itself_is_kept() -> None:
    """Only the appended suffix goes: Bus 1 never matches Bus 2."""
    assert match_port("IAC Driver Bus 1 0", ["IAC Driver Bus 2 1"], WINMM_SUFFIX) is None
    assert match_port("Synth 1 20:0", ["Synth 2 24:0"], ALSA_SUFFIX) is None


def test_without_a_suffix_rule_only_the_exact_name_matches() -> None:
    """macOS (CoreMIDI) names carry no appended number."""
    assert match_port("IAC Driver Bus 1", ["IAC Driver Bus 2"], None) is None
    assert match_port("IAC Driver Bus 1", ["IAC Driver Bus 1"], None) == "IAC Driver Bus 1"


def test_find_device_uses_the_drivers_rule(monkeypatch) -> None:
    import haybale_protokol_midi.driver as driver_module

    monkeypatch.setattr(driver_module, "PORT_SUFFIX", ALSA_SUFFIX)
    seen = [("Synth 24:0", "input")]
    assert find_device(MidiDriver(), "Synth 20:0", seen) == "Synth 24:0"
    assert find_device(MidiDriver(), "Other 20:0", seen) is None


def test_find_device_without_a_rule_is_exact() -> None:
    class Plain:
        pass

    seen = [("IAC 1", "IAC Driver Bus 1")]
    assert find_device(Plain(), "IAC 1", seen) == "IAC 1"
    assert find_device(Plain(), "IAC 2", seen) is None
