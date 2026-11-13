# OSC Receive

`haybale-protokol-osc:node:OscReceiveNode` · kind: node

Triggered for each OSC message on an input gate that matches the address pattern

## Ports

| id | direction | type | description |
|---|---|---|---|
| `gate` | config | `haywire-core:type:STRING` | Text data |
| `address` | config | `haywire-core:type:STRING` | Text data |
| `arg_shape` | config | `haywire-core:type:STRING` | Text data |
| `received` | outlet | `haywire-core:type:EXEC` | Signal for controlling execution flow between nodes |
| `address_out` | outlet | `haywire-core:type:STRING` | Text data |
| `args` | outlet | `haybale-core:type:LIST` | Every argument of the message |
| `arg_1` | outlet | `haywire-core:type:ADD` | Grows a new port from whatever connects to it |
| `timetag` | outlet | `haywire-core:type:FLOAT` | Decimal number |
| `status` | outlet | `haywire-core:type:STRING` | Text data |

## Settings

| name | bag | default | description |
|---|---|---|---|
| `queue_mode` | dispatch | `'Auto (by message kind)'` | Block runs the flow for every message; a slow flow then falls behind, never the Line. Drop keeps only the newest message. Auto uses Drop for values (faders, axes, OSC) and Block for events (notes, buttons). |
| `max_queue_size` | dispatch | `100` | How many messages Block holds while the flow runs behind. Drop always holds one. |
| `start_value` | dispatch | `'Auto (by message kind)'` | Fire once with the last message the Line saw when the graph starts. Auto: on for values, off for events. |

## Notes

Runs its flow for each OSC message on its gate that matches its address.

`Gate` names an input gate in the project's Gate file (`.haywire/protokol.toml`). `Address`
is an OSC address pattern (`*`, `?`, `[0-9]`, `{a,b}`); empty takes every message. Each
wildcard gets a capture outlet, `match_1`, `match_2`..., which takes the type of what it is
connected to. `Arg Shape` lists the arguments (`f i vf3 s`, `_` to skip one): empty gives
one `args` list, otherwise one outlet per token. A message that does not fit the shape is
skipped and counted in `status`.

The outlets keep the latest values, so other flows can read them.

Outputs:
    received: Control flow for each matching message
    address: The address that matched
    args / arg_N: The arguments
    match_N: What each wildcard matched
    timetag: The OSC bundle's timetag, 0 for a message outside a bundle
    status: The gate's state and how many messages were skipped
