# OSC Receive

`haybale-protokol-osc:node:OscReceiveNode` · kind: node

Triggered for each OSC message on an input gate that matches the address pattern

## Ports

| id | direction | type | description |
|---|---|---|---|
| `gate` | config | `haywire-core:type:STRING` | The name of an input (or two-way) gate in the project's Gate file, .haywire/protokol.toml; make gates in the Gates editor. The node opens the gate's Line when the graph starts and gives it back when it stops. If the gate is missing, belongs to another protocol or its port is busy, the status outlet says why and nothing fires. A change applies on the next start. |
| `address` | config | `haywire-core:type:STRING` | The OSC address pattern to listen to; empty takes every message on the gate. Wildcards: \* (any text within one /part), ? (one character), [0-9] or [!a] (one character from a set), {left,right} (one of the words). Each wildcard adds a capture outlet, match_1, match_2 … from left to right. A capture starts as an empty + pin and takes the type of the inlet you connect it to (text, int, float or bool); a part that does not convert is reported in status. Changing the pattern rebuilds the match_ outlets; an invalid pattern is put back. |
| `arg_shape` | config | `haywire-core:type:STRING` | The Arg shape: the arguments the node expects, as tokens separated by spaces. i or h: int; f or d: float; s: text; b: blob; T: bool; r: colour; vi2–vi4 and vf2–vf4: 2 to 4 ints or floats as one vector; m3, m4: 9 or 16 floats as a matrix; _ skips one argument, _3 skips three. The args outlet always carries every argument as a list; each token adds its own outlet, in order. The shape and the pins follow each other: connecting the + pin at the bottom adds a token for the connected type, deleting the edge that grew a pin removes the pin and its token, and dragging pins into another order reorders the tokens. A message that does not fit is skipped and counted in status; extra arguments are ignored. An invalid shape is put back. |
| `received` | outlet | `haywire-core:type:EXEC` | Signal for controlling execution flow between nodes |
| `address_out` | outlet | `haywire-core:type:STRING` | Text data |
| `args` | outlet | `haybale-core:type:LIST` | Every argument of the message, as a list |
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
connected to. `args` always carries every argument as a list. `Arg Shape` lists the
arguments (`f i vf3 s`, `_` to skip one), each token adding its own outlet. A message that
does not fit the shape is skipped and counted in `status`.

The outlets keep the latest values, so other flows can read them.

Outputs:
    received: Control flow for each matching message
    address: The address that matched
    args: Every argument, as a list
    arg_N: One argument (or a group, such as a vector) per Arg Shape token
    match_N: What each wildcard matched
    timetag: The OSC bundle's timetag, 0 for a message outside a bundle
    status: The gate's state and how many messages were skipped
