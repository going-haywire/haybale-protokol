# Send Rumble

`haybale-protokol-gamepad:node:SendRumbleNode` · kind: node

Rumbles the gamepads of its gates each time it runs

## Ports

| id | direction | type | description |
|---|---|---|---|
| `exec` | inlet | `haywire-core:type:EXEC` | Signal for controlling execution flow between nodes |
| `low` | inlet | `haywire-core:type:FLOAT` | The low-frequency (left, heavy) motor, 0…1 |
| `high` | inlet | `haywire-core:type:FLOAT` | The high-frequency (right, light) motor, 0…1 |
| `duration` | inlet | `haywire-core:type:INT` | How long the rumble lasts, 0…60000 ms |
| `gate` | config | `haywire-core:type:STRING` | One or more two-way gamepad gates from the project's Gate file; pick them from the list or type a name. Each rumble goes to every listed gate; a gate whose pad is unplugged, unknown or cannot rumble is reported in status and the others still get it. A rumble no gate could take counts as dropped, never queued. Applies on the next start. |
| `next` | outlet | `haywire-core:type:EXEC` | Signal for controlling execution flow between nodes |

## Settings

| name | bag | default | description |
|---|---|---|---|
| `only_changes` | sending | `False` | Off: every control tick sends the message. On: a tick sends to a gate only when the message differs from the last one that gate took; the first tick of a run always sends, and a gate that missed a message gets it on the next tick. Skipped ticks are counted as 'unchanged' in status. |
| `status` | report | `''` | Each gate's state, and what was sent or dropped. Never saved. |

## Notes

Starts a rumble on every listed gate's pad on each control tick.

Low and High are the strengths of the pad's low- and high-frequency motors, 0…1; Duration is
how long it lasts. A new rumble replaces one still running, and strengths of 0 stop it. A
value out of range drops the rumble and status names it. With Only send changes, a tick
rumbles a gate only when the rumble differs from the last one that gate took.

Outputs:
    next: Control flow after sending

Status (a setting, off the card until promoted to a row or an outlet) says what was sent,
skipped and dropped, and which gates cannot be used.
