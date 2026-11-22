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

import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, cast, get_args

import tomlkit

from haywire.api import read_toml, to_builtin, write_toml

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
        data = to_builtin(read_toml(path))
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
    for gate in wanted.values():
        _put_table(tables, gate)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_toml(path, document)


def write_gate(path: Path, gate: Gate, *, replaces: str | None = None) -> None:
    """Add or update one gate in ``path``, leaving every other table and comment as it is.

    ``replaces`` names a gate this one takes the place of (a rename); it is removed.
    """
    document = read_toml(path) if path.is_file() else tomlkit.document()
    if "gates" not in document:
        document["gates"] = tomlkit.table(is_super_table=True)
    tables = document["gates"]
    if replaces is not None and replaces != gate.name and replaces in tables:
        renamed = _renamed_in_text(path, document, replaces, gate.name)
        if renamed is not None:
            document, tables = renamed, renamed["gates"]
        else:
            del tables[replaces]
    _put_table(tables, gate)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_toml(path, document)


def remove_gate(path: Path, name: str) -> None:
    """Remove one gate from ``path``; a missing gate or file changes nothing."""
    if not path.is_file():
        return
    document = read_toml(path)
    tables = document.get("gates")
    if tables is not None and name in tables:
        removed = _removed_in_text(path, document, name)
        if removed is None:
            del tables[name]
            removed = document
        write_toml(path, removed)


# -- comment-keeping text edits -------------------------------------------------------
#
# tomlkit stores a comment written above a table as the tail of the table before it, so
# deleting a table through tomlkit drops the next gate's comment, and a rename (delete and
# add) loses the gate's comments and moves it to the end. These edit the text instead, with
# one rule: the comment lines directly above a gate's header belong to that gate. The result
# is parsed back and checked; anything unexpected falls back to the tomlkit edit.

_ANY_HEADER = re.compile(r"^\s*\[")
_GATE_HEADER = re.compile(
    r"""^(?P<lead>\s*\[\s*gates\s*\.\s*)(?P<key>[A-Za-z0-9_-]+|"(?:[^"\\]|\\.)*"|'[^']*')(?P<rest>\s*\].*)$"""
)
_COMMENT = re.compile(r"^\s*#")
_BARE_KEY = re.compile(r"[A-Za-z0-9_-]+")


def _header_name(key: str) -> str:
    if key.startswith('"'):
        return str(json.loads(key))
    return key[1:-1] if key.startswith("'") else key


def _toml_key(name: str) -> str:
    return name if _BARE_KEY.fullmatch(name) else json.dumps(name, ensure_ascii=False)


def _header_line(lines: list[str], name: str) -> int | None:
    found = [
        i
        for i, line in enumerate(lines)
        if (m := _GATE_HEADER.match(line)) and _header_name(m["key"]) == name
    ]
    return found[0] if len(found) == 1 else None


def _checked(text: str, before: Any, expected: dict[str, Any]) -> Any | None:
    """``text`` parsed, if its gates are exactly ``expected`` and the rest of ``before`` is unchanged."""
    try:
        after = tomlkit.parse(text)
    except Exception:
        return None
    rest = {key: value for key, value in to_builtin(before).items() if key != "gates"}
    if {key: value for key, value in to_builtin(after).items() if key != "gates"} != rest:
        return None
    return after if to_builtin(after.get("gates", {})) == expected else None


def _renamed_in_text(path: Path, document: Any, old: str, new: str) -> Any | None:
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    index = _header_line(lines, old)
    if index is None:
        return None
    match = _GATE_HEADER.match(lines[index].rstrip("\r\n"))
    assert match is not None
    ending = lines[index][len(lines[index].rstrip("\r\n")) :]
    lines[index] = f"{match['lead']}{_toml_key(new)}{match['rest']}{ending}"
    gates = to_builtin(document["gates"])
    expected = {(new if key == old else key): value for key, value in gates.items()}
    return _checked("".join(lines), document, expected)


def _removed_in_text(path: Path, document: Any, name: str) -> Any | None:
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    start = _header_line(lines, name)
    if start is None:
        return None
    end = next((i for i in range(start + 1, len(lines)) if _ANY_HEADER.match(lines[i])), len(lines))
    # The comment and blank lines ending the block belong to the next table (or end the file).
    while end - 1 > start and (_COMMENT.match(lines[end - 1]) or not lines[end - 1].strip()):
        end -= 1
    while start > 0 and _COMMENT.match(lines[start - 1]):  # the gate's own comment goes with it
        start -= 1
    kept = lines[:start] + lines[end:]
    if start > 0 and start < len(kept) and not kept[start - 1].strip() and not kept[start].strip():
        del kept[start]  # one blank line between neighbours, not two
    while kept and not kept[-1].strip():  # no blank lines left at the end of the file
        kept.pop()
    expected = {key: value for key, value in to_builtin(document["gates"]).items() if key != name}
    return _checked("".join(kept), document, expected)


def _put_table(tables: Any, gate: Gate) -> None:
    values = _table_from_gate(gate)
    if gate.name not in tables:
        table = tomlkit.table()
        table.update(values)
        tables[gate.name] = table
        return
    table = tables[gate.name]
    for key in [key for key in table if key not in values]:
        del table[key]
    for key, value in values.items():
        if key not in table or to_builtin(table[key]) != value:
            table[key] = value


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
