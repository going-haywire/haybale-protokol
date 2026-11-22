# Send MIDI

`haybale-protokol-midi:node:SendMidiNode` · kind: node

Sends one MIDI message to its gates each time it runs

## Ports

| id | direction | type | description |
|---|---|---|---|
| `exec` | inlet | `haywire-core:type:EXEC` | Signal for controlling execution flow between nodes |
| `controller` | inlet | `haywire-core:type:INT` | Whole number |
| `value` | inlet | `haywire-core:type:INT` | Whole number |
| `gate` | config | `haywire-core:type:STRING` | One or more MIDI output gates from the project's Gate file; pick them from the list or type a name. A MIDI gate names a Device, which the Device editor maps to a port on this machine. Each message goes to every listed gate; a gate whose device is unplugged or unknown is reported in status and the others still get it. A message no gate could take counts as dropped, never queued. Applies on the next start. |
| `kind` | config | `haywire-core:type:STRING` | What to send. note: note on or off (the on inlet); cc: a controller; pitchbend: −8192…8191; aftertouch: channel pressure; program: program change; sysex: the data without F0/F7; transport: clock, start, continue, stop or songpos (with position); raw: bytes as they are. The inlets change with the kind. |
| `filter_channel` | config | `haywire-core:type:INT` | The MIDI channel, 1–16, or 0 to take it from a channel inlet. Not used by sysex, transport and raw. |
| `filter_number` | config | `haywire-core:type:INT` | For note and cc: the note or controller number, 0–127, or −1 to take it from an inlet. |
| `next` | outlet | `haywire-core:type:EXEC` | Signal for controlling execution flow between nodes |
| `status` | outlet | `haywire-core:type:STRING` | Text data |

## Settings

| name | bag | default | description |
|---|---|---|---|
| `only_changes` | sending | `False` | Off: every control tick sends the message. On: a tick sends to a gate only when the message differs from the last one that gate took; the first tick of a run always sends, and a gate that missed a message gets it on the next tick. Skipped ticks are counted as 'unchanged' in status. |

## Notes

Sends one message of its kind to every listed gate on each control tick.

Kind, Channel and Number say what to send; the inlets follow them, and a channel or number left
open comes from its own inlet. A value out of range drops the message and status names it.
With Only send changes, a tick sends to a gate only when the message differs from the last one
that gate took.

Outputs:
    next: Control flow after sending
    status: What was sent, skipped and dropped, and which gates cannot be used
