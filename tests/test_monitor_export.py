"""Monitor export: JSONL and CSV of the rows a Monitor shows."""

import csv
import io
import json

from haybale_protokol.monitor_export import MonitorRow, to_csv, to_jsonl

ROWS = [
    MonitorRow(1700000000.25, "in", "in", "/fader/1", (0.5, 3), "/fader/1 ,fi 0.5 3"),
    MonitorRow(1700000001.5, "~fake out 9", "out", "/x", ("a, b",), '/x ,s "a, b"'),
]


def test_export_jsonl_round_trip() -> None:
    lines = to_jsonl(ROWS).splitlines()
    assert [json.loads(line) for line in lines] == [
        {
            "time": 1700000000.25,
            "source": "in",
            "direction": "in",
            "address": "/fader/1",
            "args": [0.5, 3],
            "description": "/fader/1 ,fi 0.5 3",
        },
        {
            "time": 1700000001.5,
            "source": "~fake out 9",
            "direction": "out",
            "address": "/x",
            "args": ["a, b"],
            "description": '/x ,s "a, b"',
        },
    ]


def test_export_csv_round_trip() -> None:
    rows = list(csv.reader(io.StringIO(to_csv(ROWS))))
    assert rows[0] == ["time", "source", "direction", "address", "args", "description"]
    assert rows[2] == ["1700000001.5", "~fake out 9", "out", "/x", '["a, b"]', '/x ,s "a, b"']


def test_bytes_args_are_exported_as_hex() -> None:
    row = MonitorRow(0.0, "s", "in", "/b", (b"\x01\xff",), "")
    assert json.loads(to_jsonl([row]))["args"] == ["01ff"]
