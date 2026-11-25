# Gamepad Event

`haybale-protokol-gamepad:node:GamepadEventNode` · kind: node

Triggered when one of its chosen sticks, triggers, d-pad or buttons changes

## Ports

| id | direction | type | description |
|---|---|---|---|
| `gate` | config | `haywire-core:type:STRING` | One or more gamepad gates from the project's Gate file; pick them from the list or type a name. A gamepad gate names a Device, which the Gates editor's Device pane maps to a pad on this machine. Changes from every gate run the same flow; From gate says which one. A gate whose pad is unplugged waits for it and listens again when it is back. Applies on the next start. |
| `outputs` | config | `haywire-core:type:STRING` | What to read from the pad: each chosen output becomes an outlet, in the order chosen, and the flow runs when one of their values changes. Sticks as a vector (left_stick_vec, VEC2F) or one axis (left_stick_x, FLOAT), triggers 0…1, the d-pad as a vector (dpad_vec, VEC2I), and each button (BOOL). Face buttons go by position on every brand: a is the bottom one. All outlets are read from the same moment, so a stick's x and y always belong together. |
| `received` | outlet | `haywire-core:type:EXEC` | Signal for controlling execution flow between nodes |
| `from_gate` | outlet | `haywire-core:type:STRING` | The gate the change came in on |
| `changed` | outlet | `haywire-core:type:STRING` | Which chosen output changed |
| `left_stick_vec` | outlet | `haywire-core:type:VEC2F` | 2D float vector |

## Settings

| name | bag | default | description |
|---|---|---|---|
| `dead_zone` | shaping | `0.2` | How far a stick must move from its centre before it counts, 0…0.9. Inside, it reads 0; outside, it is rescaled to still reach 1. Pads rest a little off centre (often 0.05–0.2). Applies to x and y together, so diagonals stay true; 0 gives the raw value. |
| `y_up` | shaping | `True` | On: pushing a stick or the d-pad up gives a positive y, as in maths and most 3D. Off: down is positive, as SDL and screen coordinates count (y grows downward). |
| `queue_mode` | dispatch | `'Auto (by message kind)'` | Block runs the flow for every message; a slow flow then falls behind, never the Line. Drop keeps only the newest message. Auto uses Drop for values from one source (one fader, axis or exact OSC address on one gate) and Block for everything else. |
| `max_queue_size` | dispatch | `100` | How many messages Block holds while the flow runs behind. Drop always holds one. |
| `start_value` | dispatch | `'Auto (by message kind)'` | Fire once with the last message the Line saw when the graph starts. Auto: on for values, off for events. |
| `status` | report | `''` | Each gate's state, and what was sent or dropped. Never saved. |

## Notes

Runs its flow when one of its chosen outputs changes on its gates.

Outputs is the node's filter: each output chosen is one outlet, and the flow runs when the
value leaving one of them changes (after the dead zone: a stick moving inside it fires
nothing), with every outlet read from the pad's state at that moment. Sticks, triggers and
the d-pad fire their value when the graph starts, and keep only the newest change when the flow
runs behind; with a button among the outputs, every press and release is kept.

Outputs:
    received: Control flow for each change of a chosen output
    from_gate: The gate the change came in on
    changed: The first chosen output, in their order, whose outlet value changed
    (one outlet per chosen output): sticks VEC2F or FLOAT, triggers FLOAT 0…1, the d-pad VEC2I,
        buttons BOOL
