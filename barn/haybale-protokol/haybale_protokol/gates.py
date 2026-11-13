"""Gates and the project's Gate file, ``<project>/.haywire/protokol.toml``.

A graph stores only a Gate's name; everything else about the Gate lives here, committed
with the project. Each gate is one table under ``[gates]``::

    [gates.touchosc-in]
    protocol = "osc"
    direction = "in"
    transport = "udp"
    port = 8000

``protocol``, ``direction`` and ``device`` are the Gate's own fields; every other key is
an option its Protocol driver reads.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, cast, get_args

import tomlkit

from haywire.core.tomlio import plain, read_toml, write_toml

Direction = Literal["in", "out", "two-way"]

_DIRECTIONS: tuple[str, ...] = get_args(Direction)
_OWN_KEYS = ("protocol", "direction", "device")


class GateFileError(ValueError):
    """The Gate file cannot be read; the message names the file and, where known, the gate."""


@dataclass(frozen=True)
class Gate:
    """A named connection point to one control protocol, referred to by graphs by name only."""

    name: str
    protocol: str
    direction: Direction
    device: str | None = None
    """The Device this gate uses (MIDI, gamepad); network gates name none."""
    options: Mapping[str, Any] = field(default_factory=dict)
    """Protocol-specific settings (``transport``, ``port``, ``host``, ``bind``, ...)."""


def gate_file_path(project_root: Path) -> Path:
    """Return where the project's Gate file lives."""
    return project_root / ".haywire" / "protokol.toml"


def load_gates(path: Path) -> dict[str, Gate]:
    """Read every gate in ``path``, by name; a missing file has none.

    Raises:
        GateFileError: The file is not valid TOML, or a gate is malformed.
    """
    gates, errors = load_gates_leniently(path)
    if errors:
        raise GateFileError(next(iter(errors.values())))
    return gates


def load_gates_leniently(path: Path) -> tuple[dict[str, Gate], dict[str, str]]:
    """Read the well-formed gates in ``path``, and why each malformed one was left out.

    One bad gate leaves the others usable; only a file that cannot be read fails as a whole.

    Raises:
        GateFileError: The file is not valid TOML, or ``[gates]`` is not a table.
    """
    if not path.is_file():
        return {}, {}
    try:
        data = plain(read_toml(path))
    except (ValueError, OSError) as exc:  # read_toml raises toml.TomlDecodeError, a ValueError
        raise GateFileError(f"{path}: {exc}") from exc
    tables = data.get("gates", {})
    if not isinstance(tables, dict):
        raise GateFileError(f"{path}: [gates] must be a table")
    gates: dict[str, Gate] = {}
    errors: dict[str, str] = {}
    for name, table in tables.items():
        try:
            gates[name] = _gate_from_table(path, name, table)
        except GateFileError as exc:
            errors[name] = str(exc)
    return gates, errors


def save_gates(path: Path, gates: Iterable[Gate]) -> None:
    """Write ``gates`` to ``path`` as its whole gate list, keeping the file's comments."""
    document = read_toml(path) if path.is_file() else tomlkit.document()
    if "gates" not in document:
        document["gates"] = tomlkit.table(is_super_table=True)
    tables = document["gates"]
    wanted = {gate.name: gate for gate in gates}
    for name in [name for name in tables if name not in wanted]:
        del tables[name]
    for name, gate in wanted.items():
        values = _table_from_gate(gate)
        if name not in tables:
            table = tomlkit.table()
            table.update(values)
            tables[name] = table
            continue
        table = tables[name]
        for key in [key for key in table if key not in values]:
            del table[key]
        for key, value in values.items():
            if key not in table or plain(table[key]) != value:
                table[key] = value
    path.parent.mkdir(parents=True, exist_ok=True)
    write_toml(path, document)


def _gate_from_table(path: Path, name: str, table: Any) -> Gate:
    if not isinstance(table, dict):
        raise GateFileError(f"{path}: gate '{name}' must be a table")
    protocol = table.get("protocol")
    if not isinstance(protocol, str) or not protocol:
        raise GateFileError(f"{path}: gate '{name}' has no protocol")
    direction = table.get("direction")
    if direction not in _DIRECTIONS:
        raise GateFileError(f"{path}: gate '{name}' has direction {direction!r}; use one of {_DIRECTIONS}")
    device = table.get("device")
    if device is not None and not isinstance(device, str):
        raise GateFileError(f"{path}: gate '{name}' device must be a name")
    options = {key: value for key, value in table.items() if key not in _OWN_KEYS}
    return Gate(name, protocol, cast(Direction, direction), device, options)


def _table_from_gate(gate: Gate) -> dict[str, Any]:
    values: dict[str, Any] = {"protocol": gate.protocol, "direction": gate.direction}
    if gate.device is not None:
        values["device"] = gate.device
    values.update(gate.options)
    return values
