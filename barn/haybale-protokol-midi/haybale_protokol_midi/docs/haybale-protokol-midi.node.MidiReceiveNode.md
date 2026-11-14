# MIDI Receive

`haybale-protokol-midi:node:MidiReceiveNode` · kind: node

Triggered for each MIDI message on its gates that passes its kind, channel and number

## Ports

| id | direction | type | description |
|---|---|---|---|
| `gate` | config | `haywire-core:type:STRING` | One or more MIDI input gates from the project's Gate file; pick them from the list or type a name. A MIDI gate names a Device, which the Device editor maps to a port on this machine. Messages from every gate run the same flow; From gate says which one. A gate whose device is unplugged or unknown is reported in status; the others still work. Applies on the next start. |
| `kind` | config | `haywire-core:type:STRING` | What to listen for. note: note on and off (on is False for note off and velocity 0); cc: a controller; pitchbend: −8192…8191; aftertouch: channel pressure; program: program change; sysex: the data without F0/F7; transport: clock, start, continue, stop and song position; raw: every message as bytes, including polyphonic aftertouch. The outlets change with the kind. |
| `filter_channel` | config | `haywire-core:type:INT` | The MIDI channel, 1–16, or 0 for any; with any, a channel outlet says which. Not used by sysex, transport and raw. |
| `filter_number` | config | `haywire-core:type:INT` | For note and cc: the note or controller number, 0–127, or −1 for any; with any, an outlet says which. |
| `received` | outlet | `haywire-core:type:EXEC` | Signal for controlling execution flow between nodes |
| `from_gate` | outlet | `haywire-core:type:STRING` | The gate the message came in on |
| `controller` | outlet | `haywire-core:type:INT` | Whole number |
| `value` | outlet | `haywire-core:type:INT` | Whole number |
| `status` | outlet | `haywire-core:type:STRING` | Text data |

## Settings

| name | bag | default | description |
|---|---|---|---|
| `queue_mode` | dispatch | `'Auto (by message kind)'` | Block runs the flow for every message; a slow flow then falls behind, never the Line. Drop keeps only the newest message. Auto uses Drop for values (faders, axes, OSC) and Block for events (notes, buttons). |
| `max_queue_size` | dispatch | `100` | How many messages Block holds while the flow runs behind. Drop always holds one. |
| `start_value` | dispatch | `'Auto (by message kind)'` | Fire once with the last message the Line saw when the graph starts. Auto: on for values, off for events. |

## Notes

Runs its flow for each MIDI message of its kind (and channel and number) on its gates.

Kind, Channel and Number are the node's filter, and its outlets follow it. Values (cc, pitch
bend, aftertouch) fire their last value when the graph starts and keep only the newest message
when the flow runs behind; events (notes, programs, transport) queue every message.

Outputs:
    received: Control flow for each message that passes the filter
    from_gate: The gate the message came in on
    channel / note / controller: What the filter leaves open
    velocity, on, value, program, data, event, position, bytes: The message, by kind
    status: Each gate's state
