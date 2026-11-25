# Gamepad Event

`haybale-protokol-gamepad:node:GamepadEventNode` · kind: node

Triggered for each change of a gamepad axis, button or d-pad that passes its filter

## Ports

| id | direction | type | description |
|---|---|---|---|
| `gate` | config | `haywire-core:type:STRING` | One or more gamepad gates from the project's Gate file; pick them from the list or type a name. A gamepad gate names a Device, which the Gates editor's Device pane maps to a pad on this machine. Changes from every gate run the same flow; From gate says which one. A gate whose pad is unplugged waits for it and listens again when it is back. Applies on the next start. |
| `kind` | config | `haywire-core:type:STRING` | What to listen for. axis: a stick (−1…1, left and up negative) or a trigger (0…1); button: pressed or released; hat: the d-pad as one vector (x −1 left … 1 right, y −1 up … 1 down); all: every control, with a control outlet saying which kind. The outlets change with the kind. |
| `filter_index` | config | `haywire-core:type:INT` | Which control, by SDL's GameController layout, or −1 for any (an index outlet then says which). Axes: 0 leftx, 1 lefty, 2 rightx, 3 righty, 4 lefttrigger, 5 righttrigger. Buttons: 0 a, 1 b, 2 x, 3 y, 4 back, 5 guide, 6 start, 7 leftstick, 8 rightstick, 9 leftshoulder, 10 rightshoulder, 11 dpup, 12 dpdown, 13 dpleft, 14 dpright, 15 misc1, 16 paddle1, 17 paddle2, 18 paddle3, 19 paddle4, 20 touchpad. Hat: 0, the d-pad. Not used by all, which passes every control. |
| `received` | outlet | `haywire-core:type:EXEC` | Signal for controlling execution flow between nodes |
| `from_gate` | outlet | `haywire-core:type:STRING` | The gate the change came in on |
| `value` | outlet | `haywire-core:type:FLOAT` | Decimal number |
| `status` | outlet | `haywire-core:type:STRING` | Text data |

## Settings

| name | bag | default | description |
|---|---|---|---|
| `queue_mode` | dispatch | `'Auto (by message kind)'` | Block runs the flow for every message; a slow flow then falls behind, never the Line. Drop keeps only the newest message. Auto uses Drop for values from one source (one fader, axis or exact OSC address on one gate) and Block for everything else. |
| `max_queue_size` | dispatch | `100` | How many messages Block holds while the flow runs behind. Drop always holds one. |
| `start_value` | dispatch | `'Auto (by message kind)'` | Fire once with the last message the Line saw when the graph starts. Auto: on for values, off for events. |

## Notes

Runs its flow for each change of a gamepad control of its kind (and index) on its gates.

Kind and Index are the node's filter, and its outlets follow it. Axes and the d-pad fire their
last value when the graph starts and keep only the newest change when the flow runs behind;
buttons queue every press and release.

Outputs:
    received: Control flow for each change that passes the filter
    from_gate: The gate the change came in on
    control: For all, which kind of control changed (axis, button or hat)
    index: The control's index, when the filter leaves it open
    value: An axis (−1…1, a trigger 0…1); for all, a button as 0 or 1
    pressed: Whether a button is down
    hat: The d-pad as (x, y)
    status: Each gate's state
