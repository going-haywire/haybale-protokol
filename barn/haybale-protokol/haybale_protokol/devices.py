"""Devices and the machine's Device list, ``~/.haywire/protokol-devices.toml``.

A Device is hardware this machine knows, under a name the user chose, mapped to what the OS
calls it. Every project on the machine shares the list; it holds nothing about network peers::

    [devices.desk]
    protocol = "midi"
    os_id = "IAC Driver Bus 1"
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import toml
import tomlkit

from haywire.core.tomlio import plain, read_toml, write_toml


class DeviceListError(ValueError):
    """The Device list cannot be read; the message names the file and, where known, the device."""


@dataclass(frozen=True)
class Device:
    """A piece of hardware under the user's name for it."""

    name: str
    protocol: str
    os_id: str
    """The OS's identifier: a MIDI port name, an SDL GUID."""


def device_list_path() -> Path:
    """Return where this machine's Device list lives (read at call time, so HOME may change)."""
    return Path.home() / ".haywire" / "protokol-devices.toml"


def load_devices(path: Path) -> dict[str, Device]:
    """Read every device in ``path``, by name; a missing file has none.

    Raises:
        DeviceListError: The file is not valid TOML, or a device is malformed.
    """
    if not path.is_file():
        return {}
    try:
        data = plain(read_toml(path))
    except (toml.TomlDecodeError, OSError) as exc:
        raise DeviceListError(f"{path}: {exc}") from exc
    tables = data.get("devices", {})
    if not isinstance(tables, dict):
        raise DeviceListError(f"{path}: [devices] must be a table")
    devices: dict[str, Device] = {}
    for name, table in tables.items():
        if not isinstance(table, dict):
            raise DeviceListError(f"{path}: device '{name}' must be a table")
        protocol, os_id = table.get("protocol"), table.get("os_id")
        if not isinstance(protocol, str) or not protocol or not isinstance(os_id, str) or not os_id:
            raise DeviceListError(f"{path}: device '{name}' needs a protocol and an os_id")
        devices[name] = Device(name, protocol, os_id)
    return devices


def save_devices(path: Path, devices: Iterable[Device]) -> None:
    """Write ``devices`` to ``path`` as the whole Device list, keeping the file's comments."""
    document = read_toml(path) if path.is_file() else tomlkit.document()
    if "devices" not in document:
        document["devices"] = tomlkit.table(is_super_table=True)
    tables = document["devices"]
    wanted = {device.name: device for device in devices}
    for name in [name for name in tables if name not in wanted]:
        del tables[name]
    for name, device in wanted.items():
        if name not in tables:
            tables[name] = tomlkit.table()
        tables[name]["protocol"] = device.protocol
        tables[name]["os_id"] = device.os_id
    path.parent.mkdir(parents=True, exist_ok=True)
    write_toml(path, document)
