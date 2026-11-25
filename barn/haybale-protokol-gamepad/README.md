# Protokol Gamepad

# Protokol Gamepad

Gamepads for Haywire, on top of `haybale-protokol`: a Gamepad Event node and a Send Rumble
node, using gates from the project's `.haywire/protokol.toml` (see the Protokol notes for the
file). It uses SDL2's GameController API (through `pysdl2`, with the SDL2 library from
`pysdl2-dll`), so hundreds of pads share one layout: `a` is the bottom face button on every
pad (A on Xbox, cross on PlayStation, B on Nintendo), whatever its label.

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

## Outputs

Gamepad Event has one **Outputs** field: pick what to read as chips, and each chip becomes an
outlet, in the order picked. The flow runs when the value leaving one of these outlets changes,
and every outlet is read from the pad's state at that same moment, so a stick's x and y always
belong together. A stick moving inside its dead zone changes no outlet, so it fires nothing.

| Outputs | Outlet | Values |
|---|---|---|
| left_stick_vec, right_stick_vec | VEC2F | the stick as (x, y), each −1…1 |
| left_stick_x, left_stick_y, right_stick_x, right_stick_y | FLOAT | one axis of a stick, −1…1 |
| left_trigger, right_trigger | FLOAT | 0…1 (on Switch pads, whose triggers are buttons: 0 or 1) |
| dpad_vec | VEC2I | the d-pad as (x, y), each −1, 0 or 1 |
| a, b, x, y | BOOL | the face buttons, by position on every brand: a bottom, b right, x left, y top |
| back, guide, start, misc1 | BOOL | misc1 is share (Xbox Series), mic (PS5), capture (Switch) |
| left_shoulder, right_shoulder, left_stick_press, right_stick_press | BOOL | |
| dpad_up, dpad_down, dpad_left, dpad_right | BOOL | the d-pad as four buttons |
| paddle1–paddle4, touchpad | BOOL | Elite and Edge paddles, the PlayStation touchpad press |

**From gate** says which gate a change came from, **Changed** the first chosen output (in the
order picked) whose outlet value changed.

Settings (in the properties, promotable):

- **Dead zone** (default 0.2): how far a stick must move from its centre before it counts.
  Inside, it reads 0; outside, it is rescaled to still reach 1, radially, so diagonals stay true.
  Pads rest a little off centre (an Xbox 360 pad here rested at x −0.18).
- **Y up** (default on): pushing a stick or the d-pad up gives a positive y. Off, down is
  positive, as SDL and screen coordinates count.
- **Status** (off the card): each gate's state. Promote it to a row or an outlet to show it.

When a gate opens, the pad reports where its sticks, triggers and d-pad are; with **Start
value** on (the default without buttons), the node fires with that once when the graph starts.
Without a button among the outputs the node keeps only the newest change when the flow runs
behind, which loses nothing, since each change carries the whole pad. With a button, every
press and release is kept.

## Rumble

Send Rumble starts a rumble on every listed gate's pad on each control tick: **Low** and
**High** (0…1) are the strengths of the low-frequency (heavy) and high-frequency (light)
motors, **Duration** how long, in milliseconds (up to a minute). A new rumble replaces one
still running; strengths of 0 stop it. A pad without motors drops the rumble, and its
**Status** (off the card, like Gamepad Event's) says so. With **Only send changes** a tick
rumbles a gate only when the rumble differs from the last one that gate took.

## Monitor test messages

`rumble 0.5 1 300` (low, high, milliseconds; 200 if left out), `stop`.

## Platforms

SDL runs on one thread of its own for the whole process, which reads every pad's events and
makes every SDL call. Tested on Linux with an Xbox 360 pad. On macOS that thread is not the
main thread: SDL starts and polls there without error (design §8.1), but it is not yet
confirmed with a pad plugged in.

<!-- marketstall:share-url:start -->
Always the latest (tracks the current branch):

```sh
https://github.com/going-haywire/haybale-protokol/blob/master/marketstall.toml
```

Frozen to this version:

```sh
https://github.com/going-haywire/haybale-protokol/blob/v0.0.9/marketstall.toml
```
<!-- marketstall:share-url:end -->

Gamepads for haybale-protokol: Device gates, Gamepad Event and Send Rumble nodes

## Nodes
### Protokol
- **Gamepad Event** — Triggered when one of its chosen sticks, triggers, d-pad or buttons changes
- **Send Rumble** — Rumbles the gamepads of its gates each time it runs

## Widgets
- **OutputsMenuWidget** — Pick a gamepad node's outputs as chips; each becomes an outlet, in the order picked

## States
- **Protokol Gamepad** — Registers the gamepad driver with Protokol
