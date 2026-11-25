# Protokol Gamepad

# Protokol Gamepad

Gamepads for Haywire, on top of `haybale-protokol`: a Gamepad Event node and a Send Rumble
node, using gates from the project's `.haywire/protokol.toml` (see the Protokol notes for the
file). It uses SDL2's GameController API (through `pysdl2`, with the SDL2 library from
`pysdl2-dll`), so hundreds of pads share one layout: button 0 is the bottom face button (A on
an Xbox pad, cross on a PlayStation pad), axis 0 the left stick's x.

## Gates and Devices

A gamepad gate is `in`, or `two-way` to rumble the pad too, and names a **Device**:

```toml
[gates.pad]
protocol = "gamepad"
direction = "two-way"
device = "pad"
```

The Device list on this machine (`~/.haywire/protokol-devices.toml`, edited in the Gates
editor's Device pane) maps the name to a pad's SDL GUID, so a colleague's project works on
their machine once they map `pad` to their own pad. A GUID names a model, not a unit: two alike
pads share one. The first of them, in SDL's device order, is listed as the GUID, the next as
`<guid>#2`, then `#3`. That order follows plug order, so two alike pads may swap after a replug
or a reboot; map them again if they do.

A Gamepad Event node whose pad is unplugged waits for it and listens again when it is back,
without a graph restart. Send Rumble drops and counts rumbles to an unplugged pad until the
graph restarts. On a machine where SDL cannot start, every gamepad gate reports
`cannot open: no gamepad support on this machine (…)`.

## Kinds

Gamepad Event has a **Kind** and an **Index** (−1 for any). Its outlets follow them:

| Kind | Outlets | Values |
|---|---|---|
| axis | value | sticks −1…1 (left and up negative, as SDL reports them); triggers 0…1 |
| button | pressed | True while held |
| hat | hat | the d-pad as a `VEC2I`: x −1 left … 1 right, y −1 up … 1 down |
| all | control, index, value, pressed, hat | `control` says `axis`, `button` or `hat`; a button's `value` is 0 or 1 |

An `index` outlet appears when the Index is −1, and always for `all`.

| Index | Axes | Buttons |
|---|---|---|
| 0 | leftx | a |
| 1 | lefty | b |
| 2 | rightx | x |
| 3 | righty | y |
| 4 | lefttrigger | back |
| 5 | righttrigger | guide |
| 6 | | start |
| 7–8 | | leftstick, rightstick |
| 9–10 | | leftshoulder, rightshoulder |
| 11–14 | | dpup, dpdown, dpleft, dpright |
| 15–20 | | misc1, paddle1–4, touchpad |

The d-pad's buttons arrive both as buttons 11–14 and as the hat. When a gate opens, the pad
reports where its sticks, triggers and d-pad are; with **Start value** on (the default for axes
and the hat), the node fires with that once when the graph starts. When the flow runs behind, a
node listening to one axis (or the hat) on one gate keeps only the newest value; any axis, any
button and `all` queue every change.

## Rumble

Send Rumble starts a rumble on every listed gate's pad on each control tick: **Low** and
**High** (0…1) are the strengths of the low-frequency (heavy) and high-frequency (light)
motors, **Duration** how long, in milliseconds (up to a minute). A new rumble replaces one
still running; strengths of 0 stop it. A pad without motors drops the rumble, and status says
so. With **Only send changes** a tick rumbles a gate only when the rumble differs from the last
one that gate took.

## Monitor test messages

`rumble 0.5 1 300` (low, high, milliseconds; 200 if left out), `stop`.

## Platforms

SDL runs on one thread of its own for the whole process, which reads every pad's events and
makes every SDL call. Tested on Linux with an Xbox 360 pad. On macOS that thread is not the
main thread: SDL starts and polls there without error (design §8.1), but it is not yet
confirmed with a pad plugged in.

<!-- marketstall:share-url:start -->
*Subscribe URL not yet published — run `uv run --frozen haywire share --bump patch`.*
<!-- marketstall:share-url:end -->

Gamepads for haybale-protokol: Device gates, Gamepad Event and Send Rumble nodes

## Nodes
### Protokol
- **Gamepad Event** — Triggered for each change of a gamepad axis, button or d-pad that passes its filter
- **Send Rumble** — Rumbles the gamepads of its gates each time it runs

## States
- **Protokol Gamepad** — Registers the gamepad driver with Protokol
