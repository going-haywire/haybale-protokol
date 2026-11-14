"""Editing the Device list through ProtokolState."""

from pathlib import Path

import pytest

from haybale_protokol.devices import Device, device_list_path, load_devices
from haybale_protokol.states.protokol_state import ProtokolState


@pytest.fixture
def state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ProtokolState:
    monkeypatch.setenv("HOME", str(tmp_path))
    protokol = ProtokolState()
    protokol.project_root = tmp_path
    return protokol


def test_save_device_and_rename(state: ProtokolState) -> None:
    assert state.save_device(Device("desk", "midi", "IAC Bus 1")) is None
    assert state.save_device(Device("mixer", "midi", "IAC Bus 1"), replaces="desk") is None
    assert set(load_devices(device_list_path())) == {"mixer"}
    assert state.devices()["mixer"].os_id == "IAC Bus 1"


def test_duplicate_device_refused(state: ProtokolState) -> None:
    state.save_device(Device("desk", "midi", "a"))
    assert state.save_device(Device("desk", "midi", "b")) == "a device named 'desk' already exists"


@pytest.mark.parametrize(
    ("device", "text"),
    [
        (Device("", "midi", "a"), "name"),
        (Device("x", "", "a"), "protocol"),
        (Device("x", "midi", " "), "OS"),
    ],
)
def test_incomplete_device_refused(state: ProtokolState, device: Device, text: str) -> None:
    result = state.save_device(device)
    assert result is not None
    assert text in result


def test_delete_device(state: ProtokolState) -> None:
    state.save_device(Device("desk", "midi", "a"))
    state.save_device(Device("pad", "gamepad", "b"))
    state.delete_device("desk")
    assert set(state.devices()) == {"pad"}


def test_unreadable_device_list_is_reported(state: ProtokolState) -> None:
    path = device_list_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("[devices.x\n", encoding="utf-8")
    assert state.devices() == {}
    assert state.device_list_error is not None
    assert (state.save_device(Device("y", "midi", "a")) or "").startswith("device list: ")
