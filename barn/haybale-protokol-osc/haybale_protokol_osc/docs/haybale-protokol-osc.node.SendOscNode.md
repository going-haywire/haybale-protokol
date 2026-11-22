# Send OSC

`haybale-protokol-osc:node:SendOscNode` · kind: node

Sends one OSC message to an output gate each time it runs

## Ports

| id | direction | type | description |
|---|---|---|---|
| `exec` | inlet | `haywire-core:type:EXEC` | Signal for controlling execution flow between nodes |
| `address` | inlet | `haywire-core:type:STRING` | Text data |
| `arg_1` | inlet | `haywire-core:type:ADD` | Grows a new port from whatever connects to it |
| `gate` | config | `haywire-core:type:STRING` | One or more output (or two-way) gates from the project's Gate file, .haywire/protokol.toml; pick them from the list, which offers this project's OSC gates that can send, or type a name and press Enter. Make gates in the Gates editor. Each send goes to every listed gate. The node opens each gate's Line when the graph starts and gives it back when it stops. A gate that is missing, of another protocol or cannot reach its peer is reported in status and the others still get the message; a message no gate could take counts as dropped, never queued. A change applies on the next start. |
| `arg_shape` | config | `haywire-core:type:STRING` | The Arg shape: one token per argument inlet, in inlet order. i: int; f: float; s: text; b: blob; T: bool; r: colour (#rgb, #rgba, #rrggbb or #rrggbbaa); vi2–vi4 and vf2–vf4: a vector, sent as its components; m3, m4: a matrix, sent as 9 or 16 floats. Use d or h instead of f or i for 64-bit numbers. There is no _: every inlet is sent, and an unconnected inlet sends its own value. Typing the shape rebuilds the inlets; connecting the + pin at the bottom adds a token for the connected type, deleting the edge that grew a pin removes the pin and its token, and dragging pins into another order reorders the tokens. An int too large for i is dropped and named in status; an invalid shape is put back. |
| `next` | outlet | `haywire-core:type:EXEC` | Signal for controlling execution flow between nodes |
| `shape` | outlet | `haywire-core:type:STRING` | Text data |
| `status` | outlet | `haywire-core:type:STRING` | Text data |

## Settings

| name | bag | default | description |
|---|---|---|---|
| `only_changes` | sending | `False` | Off: every control tick sends the message. On: a tick sends to a gate only when the message differs from the last one that gate took; the first tick of a run always sends, and a gate that missed a message gets it on the next tick. Skipped ticks are counted as 'unchanged' in status. |

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
