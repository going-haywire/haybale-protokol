# Protokol MIDI

# Protokol MIDI

MIDI 1.0 for Haywire, on top of `haybale-protokol`: a MIDI Receive node and a MIDI Send node,
using gates from the project's `.haywire/protokol.toml` (see the Protokol notes for the file).

## Gates and Devices

A MIDI gate is `in` or `out` and names a **Device**:

```toml
[gates.keys]
protocol = "midi"
direction = "in"
device = "keys"
```

The Device list on this machine (`~/.haywire/protokol-devices.toml`, edited in the Device
editor) maps the name to a MIDI port, so a colleague's project works on their machine once they
map `keys` to their own keyboard. MIDI inputs and outputs are separate ports with their own
names. A gate whose port is not connected reports `cannot open: no MIDI port '…'` and the graph
runs on. A port unplugged while the graph runs reports `port gone`; sends to it are dropped.
Reconnect the device and restart the graph to open it again.

On Linux (ALSA) and Windows, the OS appends a number to every port name (` 20:0`, ` 1`) that can
change with plug order or after a reboot. When the exact name is missing, the port whose name
matches without that number is used, and the Device editor shows `now '…'`. Two alike devices
(two of the same controller) never match that way; map them again in the Device editor.

## Kinds

Both nodes have a **Kind**, a **Channel** (1–16, or 0 for any) and a **Number** (note or
controller, 0–127, or −1 for any). Their pins follow them:

| Kind | Pins | Notes |
|---|---|---|
| note | note, velocity, on | `on` is False for note off and for note on with velocity 0 |
| cc | controller, value | |
| pitchbend | value | −8192…8191 |
| aftertouch | value | channel pressure; polyphonic aftertouch comes through `raw` |
| program | program | |
| sysex | data | without the F0/F7 framing |
| transport | event, position | clock, start, continue, stop, songpos |
| raw | bytes | every message as it is |

A channel, note or controller pin appears when its filter is "any". On MIDI Receive, values (cc,
pitch bend, aftertouch) fire their last value when the graph starts. When the flow runs behind,
a node listening to one controller on one channel and one gate keeps only the newest value;
anything broader, and every event (notes, programs, transport), queues each message.
MIDI Send sends on each control tick, or with **Only send changes** only when the message
differs from the last one a gate took. An out-of-range value is dropped and named in status.

## Monitor test messages

`note 1 60 100`, `note 1 60 off`, `cc 1 7 64`, `pb 1 -200`, `at 1 64`, `pc 1 5`,
`sysex 7D 01 02`, `clock`, `start`, `continue`, `stop`, `raw 90 3C 64` (hex).

<!-- marketstall:share-url:start -->
Always the latest (tracks the current branch):

```sh
https://github.com/going-haywire/haybale-protokol/blob/master/marketstall.toml
```

Frozen to this version:

```sh
https://github.com/going-haywire/haybale-protokol/blob/v0.0.5/marketstall.toml
```
<!-- marketstall:share-url:end -->

MIDI for haybale-protokol: Device gates, MIDI Receive and Send nodes

## Nodes
### Protokol
- **MIDI Receive** — Triggered for each MIDI message on its gates that passes its kind, channel and number
- **MIDI Send** — Sends one MIDI message to its gates each time it runs

## States
- **Protokol MIDI** — Registers the MIDI driver with Protokol
