# Monitor

`haybale-protokol:editor:MonitorEditor` · kind: editor

Live traffic on Lines

## Details

- **default_slot**: `info`
- **opens**: `OpenBehavior.ON_CONTEXT`
- **order**: `100`

## Notes

Tick a gate or an open Line to watch it; the table shows the newest messages first.

The filter matches the message text, case-insensitively. "New line…" opens a Line no gate
uses yet, and "Save as gate…" turns it into a gate. A ticked output gate gets a test-send
row: type a message in the protocol's own form (for OSC: ``/address 0.5 3 word``).
Export writes every message the filter keeps, as JSONL or CSV.
