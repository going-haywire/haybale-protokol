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

## Status texts

Receive and Send nodes report problems on their `status` outlet; nothing crashes the graph:

| Status | Meaning |
|---|---|
| `no gate named 'x'` | The Gate file has no such gate |
| `gate file: ...` | The Gate file cannot be read |
| `protocol not installed` | No enabled haybale provides the gate's protocol |
| `unbound gate: no device 'x' on this machine` | The Device list does not know the gate's device |
| `'x' is an input gate` / `an output gate` | The node uses the gate in the wrong direction |
| `cannot open: ...` | The port or device could not be opened (for example, already in use) |
| `gate 'x': ...` | The gate's options are incomplete or wrong, or disagree with another gate on the same Line |
