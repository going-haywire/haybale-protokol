"""The Device list: per machine, under the user's home."""

from pathlib import Path

import pytest

from haybale_protokol.devices import Device, DeviceListError, device_list_path, load_devices, save_devices


def test_device_list_under_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    assert device_list_path() == tmp_path / ".haywire" / "protokol-devices.toml"


def test_missing_file_is_empty(tmp_path: Path) -> None:
    assert load_devices(tmp_path / "nope.toml") == {}


def test_round_trip(tmp_path: Path) -> None:
    path = tmp_path / ".haywire" / "protokol-devices.toml"
    devices = [Device("desk", "midi", "IAC Driver Bus 1"), Device("pad", "gamepad", "030000005e04")]
    save_devices(path, devices)
    assert load_devices(path) == {d.name: d for d in devices}
    save_devices(path, devices[1:])
    assert list(load_devices(path)) == ["pad"]


@pytest.mark.parametrize(
    "text",
    ["[devices.a\n", "[devices.a]\nprotocol = 'midi'\n", "[devices.a]\nos_id = 'x'\n", "devices = 1\n"],
)
def test_malformed_raises(tmp_path: Path, text: str) -> None:
    path = tmp_path / "protokol-devices.toml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(DeviceListError, match="protokol-devices.toml"):
        load_devices(path)
