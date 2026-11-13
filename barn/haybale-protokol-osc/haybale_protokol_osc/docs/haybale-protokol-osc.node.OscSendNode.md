# OSC Send

`haybale-protokol-osc:node:OscSendNode` · kind: node

Sends one OSC message to an output gate each time it runs

## Ports

| id | direction | type | description |
|---|---|---|---|
| `exec` | inlet | `haywire-core:type:EXEC` | Signal for controlling execution flow between nodes |
| `address` | inlet | `haywire-core:type:STRING` | Text data |
| `arg_1` | inlet | `haywire-core:type:ADD` | Grows a new port from whatever connects to it |
| `gate` | config | `haywire-core:type:STRING` | Text data |
| `arg_shape` | config | `haywire-core:type:STRING` | Text data |
| `next` | outlet | `haywire-core:type:EXEC` | Signal for controlling execution flow between nodes |
| `shape` | outlet | `haywire-core:type:STRING` | Text data |
| `status` | outlet | `haywire-core:type:STRING` | Text data |

## Notes

Sends `Address` with one argument per argument inlet, in inlet order, to its gate.

`Gate` names an output gate in the project's Gate file. Connect anything to the empty
inlet at the bottom to add an argument; `Arg Shape` lists the arguments (`f i vf3 s`) and
follows the inlets. A vector goes out as its components (`vf3` → three `f`); use `d` or `h`
in the shape for 64-bit numbers. An unconnected inlet sends its own value.

Outputs:
    next: Control flow after sending
    shape: The OSC type tags sent last
    status: What was sent and dropped, or why nothing can be sent
