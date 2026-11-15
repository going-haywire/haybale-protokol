# haybale-protokol — design

Settled with the owner in a design session on 2026-11-13. Terms in **bold** are defined in
[reference/glossary.md](reference/glossary.md). This file records *what* was decided and
*why*; the implementation plan says how and in what order.

## 1. Goal

Make control protocols first-class in Haywire, in both directions equally: graphs receive and
send OSC, MIDI and gamepad input. A **Monitor** shows what is on the wire, so a user learns
what to listen for and where to send. Hexler's [Protokol](https://hexler.net/protokol) is the
precedent for the Monitor: MIDI, OSC, Art-Net and game controllers, filtered and logged.

## 2. Packaging

One repository, several haybales, released together by `haywire share`:

| Haybale | Holds | Native dependency |
|---|---|---|
| `haybale-protokol` | `ProtokolState`, **Lines**, the **Gate file**, the **Device list**, the three editors, shared node plumbing | none |
| `haybale-protokol-osc` | OSC **Protocol driver** and nodes (UDP, TCP) | none (`python-osc`) |
| `haybale-protokol-midi` | MIDI driver and nodes | `python-rtmidi` (+ `mido`, pure Python, for parsing) |
| `haybale-protokol-gamepad` | gamepad driver and nodes | `pysdl2` + `pysdl2-dll` (SDL2) |
| `haybale-protokol-artnet` | Art-Net driver for the Monitor, `ArtPoll` | none |

Why split: each native dependency stays with its protocol, so an OSC user never installs SDL
or rtmidi — the reasoning that kept OSC out of `haybale-stream`. Why one repo: the shared base
and the drivers change together and release together.

The name `protokol` is deliberate German spelling. Every component folder is plural,
`states/` included.

## 3. Gates, Lines and Devices

### 3.1 Gate

A **Gate** is a named connection point a graph refers to by name only, like a volume key. It
is an **Input gate**, an **Output gate**, or — only where the protocol has one shared channel
(an OSC TCP connection, a gamepad) — a **Two-way gate**. UDP and MIDI gates are always one-way.

A gate whose protocol has no driver shows "protocol not installed"; a gate whose **Device** is
not on this machine is an **Unbound gate**. Either is a status on the node, never a crash.

### 3.2 Where things are stored — the colleague test

> If a colleague opened this project on their own laptop, with the same kind of hardware
> plugged in, would the value still be correct? Yes → project. No → machine.

- **Gate file** — `<project>/.haywire/protokol.toml`, committed: every gate, its protocol,
  direction, ports, hosts, TCP framing, bind address, OSCQuery advertising flag.
- **Device list** — `~/.haywire/protokol-devices.toml`: device names chosen by the user,
  mapped to OS identifiers (MIDI port names, SDL GUIDs). Shared by every project on the
  machine. Holds nothing about network peers. A driver may match an OS identifier that
  changed a little (MIDI on Linux and Windows appends a number that changes with plug order):
  the exact name first, else the one name equal without that number, never a guess between two.

A MIDI or gamepad gate names a **Device**; network gates name none. A network interface is
never stored: a gate stores a subnet, and the interface follows from it.

### 3.3 Line

A **Line** is the one open port or device connection, per protocol and port or per device.
Gates and the Monitor share it; nothing else opens a port, so nothing fights over one. The
Monitor may open a line no gate uses yet, and promote it to a gate ("Save as gate…").

- **Lifetime: counted by users.** Users are Receive/Send nodes in a running graph (taken in
  `on_startup`, given back in `on_shutdown`) and Monitor taps. The line opens with its first
  user and closes after the last one leaves, plus a **grace period** (a setting on
  `haybale-protokol`, about 2 s) so a graph restart does not drop a TCP peer.
- **Threading:** each line runs on its own daemon thread and hands each message to its
  subscribers. This is how Haywire already feeds the executor (`haybale-audio`'s `BlockPump`
  calls `context.emit_callback` from its thread). Editors learn of changes through the signal
  bridge only.
- **Line cache:** the last message per address, channel or axis — what a Receive node with
  **Start value** fires once when its run starts.
- **Bind address:** per gate, default all interfaces. Lines do not follow the studio's
  `security.json` exposure: control protocols are unauthenticated show-network protocols, and
  forcing studio exposure to receive OSC would be worse security.

### 3.4 TCP

Both framings: OSC 1.0 (length prefix) and 1.1 (SLIP), a setting per gate (`python-osc` 1.10.2
supports both in its plain, threaded and asyncio TCP classes). A client gate reconnects with
backoff (0.5 s, 1 s, 2 s … capped near 5 s) while its line has users; its status shows
"reconnecting (n)". Sends while disconnected are dropped and counted, never queued: stale
control state is worse than none. A server gate accepts many peers; a send goes to all.

## 4. Service and extension

- **`ProtokolState`** — an `AppState` in `haybale-protokol`, one per app, shared by every
  session, the library form of the Observable store: it owns plain stores whose listeners
  only schedule onto the loop, then send a payload-free signal (pattern: `ModelsState`).
  Execution works whether or not an editor is open.
- **Protocol drivers** — each protocol haybale's own `AppState` registers its driver with
  `ProtokolState` in `on_enable` and removes it in `on_disable` (the `ensure_volume` shape).
  Each protocol haybale lists `linked_libraries = ["haybale_protokol"]`.
- `haybale-protokol` will import the open-graph registry (`GraphAppState`, in
  `haybale_graph_editor.states…` after the haywire-repo rename) for OSCQuery and possibly for
  reaching running interpreters, and list `haybale_graph_editor` in `linked_libraries`.
- No change to `haywire-core`. Gaps found go to the owner as proposals.

## 5. Editors and access

| Editor | Slot | Shows |
|---|---|---|
| **Gates editor** | ACTION | the project's gates, each with its line and status; binds unbound gates |
| **Monitor** | EDIT tab | live traffic on lines, filtered; test sends; export |
| **Device editor** | CONTEXT | the device or line in the **Protokol selection** |

The **Protokol selection** is a small per-session `SessionState`: selecting a gate or line,
or pressing its device button, drives the Device editor.

Access tiers: viewing everything and watching open lines is VIEW. Editing gates and opening
Monitor lines is EDIT (gates are project content, like graphs). Editing the Device list is
ADMIN (it changes the machine).

### 5.1 Monitor

- A bounded in-memory buffer per tap (last N messages or seconds), drawn at a capped rate.
  The tap drops when full; **the Monitor never slows a line**.
- "Export…" writes the current filtered buffer as JSONL or CSV.
- A test-send row per output gate or line: one message, typed or picked from a form.
- Art-Net appears here (universes and channels) though it has no gates or nodes yet.

### 5.2 Discovery

- Local devices: MIDI ports and gamepads, from the OS.
- Art-Net `ArtPoll`: the Art-Net nodes on the network.
- OSCQuery browsing: services found over mDNS and their address trees.
- OSCQuery advertising: opt-in per OSC input gate. The tree lists the address patterns of
  Receive nodes using the gate in open graphs; it is announced while the line is open and
  withdrawn when it closes. Served read-only on its own port, bound where its gate binds.

## 6. Nodes

The family rule: **one Receive and one Send node per protocol. A filter is the node's
address; the ports follow the filter.** Changing the filter rebuilds the ports.

### 6.1 Receive nodes

- EVENT nodes. Their data outlets double as the latest value for other flows: assembly stops
  at nodes with control pins and reads their stored outlet value
  (`DataFlowBuilder`, `data_flow_builder.py:131`). No separate Value node. Reads of several
  outlets across flows can tear; grouped tokens (`vf3`) arrive as one value and cannot.
- **Start value** flag: on by default for states (MIDI CC, pitch bend, aftertouch, gamepad
  axes, OSC), off for events (notes, program change, buttons, `raw`).
- Queue mode per node, as in `AudioEventNode`'s dispatch settings: Block by default for event
  kinds, Drop with size 1 for stream kinds. A Block-mode node forwards through its own thread,
  so a slow flow never stalls its Line (§8.1).
- **Route: `CallbackEvent`** (decided after check 1, §8.1). The node subscribes
  `CallbackEvent(event_name=<node id>)`, takes its `context` in `on_startup`, subscribes to its
  gate's line there, and the line's thread calls `context.emit_callback`. The line is the
  emitter and the node only names its gate. No core change and no cross-haybale import.

### 6.2 OSC

- **Address pattern**, OSC syntax (`*`, `?`, `[0-9]`, `{a,b}`), one pattern per node; empty
  means everything on the gate. An `address` outlet says what matched. The line keeps exact
  addresses as a lookup and runs patterns only when a node uses one.
- **Capture outlets**: one per wildcard, starting as bare `ADD` and typed by what they are
  connected to (`/tracker/blob/*/pos` → `match_1`). A capture that does not convert to that
  type is a status, not an error.
- **Arg shape**: the single source of truth for argument pins, a text field applied on blur.
  Tokens: OSC type tags, `vi2`–`vi4`, `vf2`–`vf4`, `m3`, `m4` (to `VEC*` / `MAT*`), and on
  Receive `_` / `_n` to skip arguments. By default the node has one `args` list outlet.
  Growing a pin through `ADD`, removing it (by unplugging a grown pin or from the pin menu), or
  reordering it rewrites the field; each change is one undo step. A pin's label is its token. `q` is not a token until core has a quaternion type; use `vf4`.
- **Send**: `ADD` inlets whose order is the argument order; a `VEC3F` goes out as three `f`.
  An unconnected inlet sends its own widget value — there is no `_` on Send. The node shows
  its resulting shape. Default wire types are `f`/`i`; `d`/`h` in the shape for 64-bit.
- **Blobs** arrive as `BYTES`; decoding them is a job for separate nodes.
- **OSC bundles** are split into their messages; each fires its Receive nodes with the
  bundle's timetag in the payload. (Never "bundle" alone: `BUNDLE` is Haywire's carrier type.)
- Later: a learn state that sets the shape from the first message.

### 6.3 MIDI

One Receive and one Send node with a filter of **kind** (note, CC, pitch bend, aftertouch,
program change, sysex, clock/transport, `raw`), **channel** (1–16 or any) and **number**
(or any). Outlets follow the kind; `channel` and `number` outlets appear when set to any.
`python-rtmidi` owns ports and threads; `mido.Message.from_bytes` parses.

### 6.4 Gamepad

Receive filters on `axis`, `button`, `hat` or `all`, index or any: axis → `value` (FLOAT
−1…1), button → `pressed` (BOOL), hat → `VEC2I`. Send is rumble (low and high strength,
duration) on the gamepad's two-way gate. SDL2's GameController API gives one layout for
hundreds of pads and stable GUIDs for the Device list.

### 6.5 Art-Net

No gates and no nodes in this version: they need their own design round and research into how
Art-Net is used. The driver serves the Monitor and `ArtPoll` only.

## 7. Out of scope

1. Art-Net gates and nodes.
2. DMX over USB interfaces, sACN / E1.31.
3. OSC over UDP multicast or broadcast.
4. MIDI 2.0 / UMP, MIDI Time Code, MIDI Show Control.
5. A continuous Monitor log file, traffic replay, and the Receive learn state (planned next).
6. OSCQuery trees declared on the gate.
7. A "keep open" pin for lines.
8. A network interface entry in the Device list.
9. Protocol-neutral generic Receive/Send nodes.
10. A `QUAT` type (proposed to core).
11. Any change to `haywire-core`.

## 8. Checks the plan does first

1. **Event route:** `CallbackEvent` (subscriber with the context taken in `on_startup`; does
   an event flow's group start before its first trigger?) against `ExternalEvent` +
   `GraphInterpreter.dispatch_external_event` (exists, unused; how does `ProtokolState` reach
   the running interpreters?). Leaning `ExternalEvent`.
2. **macOS gamepads:** can SDL gamepad events be pumped from a background thread? If not, a
   main-thread pump for that driver.
3. Does a grown `ADD` pin turn back into `ADD` when its last edge is removed?
4. Is a node told when the user reorders its ports (`ReorderPortsAction`), or must it read
   `DataPort.order`?
5. Switching from the `args` list to typed pins on a saved, connected node across reload and
   undo.
6. 32-bit versus 64-bit numbers on the OSC wire.

### 8.1 Findings (2026-11-13)

Spikes ran against haywire-core in haywire-repo's venv; nothing in haywire-repo was changed.

1. **Event route.** `Interpreter.load_graph` starts every execution group, and a group's
   runner calls `on_startup` on all its nodes, the event node included, before its first
   trigger. A spike node that kept its `context` from `on_startup` and called
   `context.emit_callback(node_id, payload)` from a foreign thread fired its flow every time,
   before and after `BEGIN_PLAY`. `ExternalEvent` would need the running interpreters, which
   only haybale-haystack's `GraphEntry` holds, and nothing in core dispatches it.
   Two consequences: a **Start value** fires when the graph loads, not at `BEGIN_PLAY`. And
   `FlowQueue.enqueue_trigger` in **Block** mode waits up to 5 s for room when called from a
   foreign thread, so a Line thread calling it directly could stall every other user of the
   Line. — Route decided by the owner: `CallbackEvent`. Block-mode stall, decided by the owner: a Block-mode Receive node gets its own forwarding thread; the Line thread only puts the message on that node's queue, so only that node waits. Drop-mode nodes need none.
2. **macOS gamepads.** `SDL_Init(GAMECONTROLLER)` and an `SDL_PollEvent` loop on a
   background thread run without error (pysdl2-dll 2.32.10), with and without
   `SDL_HINT_JOYSTICK_THREAD`. Not yet tested with a pad connected; finish in Plan 5.
3. **`ADD` pins.** Core never turns a grown pin back into `ADD`. The node does it: user edge
   deletion (`RemoveElementsAction`, `release_pins=True`) calls `BaseNode.release_pins`, its
   undo calls `restore_pins`, and both are part of the same undo step. Ports also offer
   `on_disconnect`. No core gap.
4. **Port reorder.** `ReorderPortsAction` calls `node.reorder_ports(ids)` (also on undo with
   the previous order), which sets `DataPort.order` and `mark_layout_changed()`. There is no
   hook. A node can override `reorder_ports`, call `super()`, then rewrite its Arg shape;
   undo stays one step. A public hook would be cleaner (proposal for core, not needed).
5. **`args` → typed pins.** Ports rebuilt in an `on_change` handler with `rejig` behave as
   needed: an edge on a removed port is detached, not deleted, and relinks when a port with
   the same id returns, so undoing the shape change restores `args` and its edge. A saved
   node reloads with the ports it was saved with. Stable port ids (`args`, `arg_1`…) are what
   make this work.
6. **32/64-bit.** python-osc 1.10.2 infers `f` for every Python `float` (32-bit) and `i` for
   an `int`, switching to `h` above 32 bits. With an explicit tag, an out-of-range `i`
   raises `BuildError`. `d` and `h` decode to Python `float` / `int`. The Send node therefore
   always passes explicit tags from its Arg shape. An int beyond 32 bits under `i` (decided by the
   owner): the message is dropped and counted in the node's status, naming the argument and
   suggesting `h`; never clamped, never promoted.

## 9. Outside this repo

- **haywire-repo:** rename `state/` → `states/` in all haybales (a breaking change the owner
  will make), fix `haybale-canon.md` (`states/`, and add `MacroRegistry` and
  `CatalogRegistry` to the registry table). Tell this repo when the rename lands.
- **Docs to add to haywire-repo:** the library form of the Observable store; reading an event
  or control node's outlet from another flow; `set_node_type` in the node canon. (`ExternalEvent` dropped: check 1 chose
  `CallbackEvent`, which needs no new doc.)
- **Proposed for core:** a `QUAT` type.
- **Landed in core (haywire-core 0.5, ADR 0082):** the pin-menu removal hooks
  `on_pin_removed(port_id, spec) -> memento`, called by `RemovePortAction` after the port is
  gone (and again on redo), and `on_pin_restored(port_id, memento)` on undo, after the port
  and its edges are back. The OSC nodes remove or reinsert the token and return
  `[index, position, token, was_grown]` as the memento. They write the Arg shape with their
  own rebuild suppressed (a hook must not change ports), and OSC Receive refreshes its decode
  tokens under its lock. Argument pin labels are the bare token, since positions shift.
