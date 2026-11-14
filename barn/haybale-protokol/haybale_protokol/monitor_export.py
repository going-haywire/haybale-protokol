"""Monitor export: the rows a Monitor shows, as JSONL or CSV."""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

COLUMNS = ("time", "source", "direction", "address", "args", "description")


@dataclass(frozen=True, slots=True)
class MonitorRow:
    """One message as the Monitor shows it."""

    time: float
    source: str
    direction: str
    address: str
    args: tuple[Any, ...]
    description: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "time": self.time,
            "source": self.source,
            "direction": self.direction,
            "address": self.address,
            "args": [_plain(arg) for arg in self.args],
            "description": self.description,
        }


def to_jsonl(rows: Iterable[MonitorRow]) -> str:
    """One JSON object per line; blobs as hex."""
    return "".join(json.dumps(row.as_dict()) + "\n" for row in rows)


def to_csv(rows: Iterable[MonitorRow]) -> str:
    """A header, then one line per row; ``args`` as a JSON list."""
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(COLUMNS)
    for row in rows:
        data = row.as_dict()
        writer.writerow(
            [
                data["time"],
                data["source"],
                data["direction"],
                data["address"],
                json.dumps(data["args"]),
                data["description"],
            ]
        )
    return out.getvalue()


def _plain(value: Any) -> Any:
    if isinstance(value, (bytes, bytearray)):
        return bytes(value).hex()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return str(value)
