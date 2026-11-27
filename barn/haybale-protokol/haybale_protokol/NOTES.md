# Protokol

Control protocols for Haywire graphs: OSC now, then MIDI and gamepads, each added by its own
protocol haybale (`haybale-protokol-osc`, ...). This haybale is the shared base. It has no
nodes of its own.

## Gates

A graph refers to a **Gate** by name only. The project's Gate file,
`.haywire/protokol.toml`, is committed with the project and defines each gate:

```toml
[gates.touchosc-in]
protocol = "osc"
direction = "in"        # in, out, or two-way where the protocol has one shared channel
transport = "udp"
port = 8000
bind = "0.0.0.0"        # default: all interfaces

[gates.lights-out]
protocol = "osc"
direction = "out"
port = 9000
host = "10.0.0.2"

[gates.desk]            # OSC over TCP: we connect to the peer
protocol = "osc"
direction = "two-way"   # TCP has one shared channel, so a gate may go both ways
transport = "tcp"
role = "client"         # or "server": peers connect to us (on bind, default all interfaces)
host = "10.0.0.5"
port = 3032
framing = "1.1"         # "1.0" length prefix, or "1.1" SLIP (default)
```

MIDI and gamepad gates name a **Device** (`device = "desk"`). The machine's Device list,
`~/.haywire/protokol-devices.toml`, maps that name to what the OS calls the hardware.

## Lines

Gates that resolve to the same connection (the same protocol, transport, address and port)
share one **Line**, the only thing that opens a port. Two gates on one port with different
bind addresses are two Lines, and the second cannot open (`cannot open: ...`). A Line opens
with its first user and closes once the last one has left and the grace period has passed
(setting **Line grace period**, default 2 s), so a graph restart keeps its peers. Lines run on
their own threads; a slow flow never holds a Line up.

## Editors

| Editor | Slot | What it does | Who may change things |
|---|---|---|---|
| **Gates** | left icon bar | Two panes with a divider that moves (and never collapses). Above, the project's gates, each with its health: a green or red dot and, for a gate that does not work, why. Add, edit, delete; "Bind…" for a gate whose device this machine does not know; open the Monitor on a gate that works. Below, the **Device pane**: it follows the selection (a gate: its options, Device mapping, health, Line and last values; a device; a Line), and with nothing selected lists the machine's Device list. Its refresh button checks which devices are plugged in now. A red dot on the editor's icon means some gate does not work. | Gates: edit access. The Device list (add, edit, map, delete): admin access |
| **Monitor** | bottom tab | Click a line's eye to watch it; the eye then hides or shows its messages in the output without losing them. Each watched line has its own Clear, Export (JSONL or CSV) and Stop watching; the toolbar's act on all shown lines. Filter by text, pause. Test-send to output gates. "New line…" watches a Line no gate uses yet, and "Save as gate…" keeps it. | Watching open Lines: view access. Opening Lines, test-send, saving gates: edit access |

The Monitor never slows a Line: each watched source keeps the last 2000 messages (older ones
drop and are counted), and the output redraws at most five times a second, showing the newest
300 messages: newest first, or oldest first like a log (the toolbar toggles it; a log follows the
newest message unless you scroll up to read). Export writes everything the filter keeps.

A gate edited while graphs use it applies when those graphs next start.

## Gate health

Every gate has one health, shown alike in the Gates editor, on the gate chips of nodes (green or
red) and as a warning badge on Receive and Send nodes:

| Health | Meaning |
|---|---|
| `working` | Its Line is open and in use |
| `closed` | It works; nothing uses it now |
| `unbound` | It names a device this machine's Device list does not have |
| `not plugged in` | Its device is mapped, but not connected now |
| `error` | It cannot be used: protocol not installed, a bad gate entry, or the port could not be opened |

Which devices are plugged in is checked about once a second (setting **Device check interval**),
only while some gate names a device; the Device pane's refresh button checks at once.

A Receive node whose device is not plugged in, when its graph starts or later, says
`waiting for '<device>'` and picks the device up again when it is plugged back in: no restart.
Send nodes drop and count messages until their graph restarts. A node's status is not saved
with the graph, so a reopened graph never shows the last session's status.

## Status texts

Receive and Send nodes report problems on their `status` outlet; nothing crashes the graph:

| Status | Meaning |
|---|---|
| `no gate named 'x'` | The Gate file has no such gate |
| `gate file: ...` | The Gate file cannot be read |
| `protocol not installed` | No enabled haybale provides the gate's protocol |
| `unbound gate: no device 'x' on this machine` | The Device list does not know the gate's device |
| `'x' is an input gate` / `an output gate` | The node uses the gate in the wrong direction |
| `waiting for 'x'` | A Receive node's device is not plugged in; it reconnects when it is |
| `cannot open: ...` | The port or device could not be opened (for example, already in use) |
| `gate 'x': ...` | The gate's options are incomplete or wrong, or disagree with another gate on the same Line |
