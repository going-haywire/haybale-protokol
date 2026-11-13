# Handoff: OSC library for Haywire

> **Superseded (2026-11-13).** A design session with the owner widened this to the
> `haybale-protokol` family (OSC, MIDI, gamepads, Art-Net, plus a Monitor) and settled the
> open questions below, sometimes differently: the "endpoint" is now a **Gate**, sockets are
> shared **Lines**, and setup is split between a project **Gate file** and a per-machine
> **Device list**. The circular import under "Development setup" is fixed in haywire
> (`c7f5661b2`). Read `docs/reference/glossary.md` and the design spec instead; this file is
> kept only as history.

This summarizes a design conversation held in the main haywire repo
(`/Volumes/Ddrive/06_open_tracking_tool/haywire/haywire-repo`, called `haywire-repo` below).
Nothing is built yet: this repo holds only the `haywire init` scaffold. The decisions
below were agreed with the owner. Open questions are still open: settle them with the owner
(a `/design` pass) before implementing. Haywire's rule: do not make architectural decisions
about class hierarchies, DI wiring, ownership or registration without the owner's confirmation.

## Goal

Add OSC (Open Sound Control) to Haywire: receive and send OSC messages from graphs.

## Decided

1. **Wrapped library: `python-osc`** (PyPI `python-osc`, import `pythonosc`).
   - Pure Python, so no native dependency (good for `pip install` on every platform).
     Most widely used and maintained; Unlicense.
   - Has an asyncio UDP server (`AsyncIOOSCUDPServer`), threaded servers, `Dispatcher`
     for address-pattern matching, bundles and timetags, and TCP.
   - Rejected: `pyliblo3` (needs the native liblo, patchy wheels, LGPL), `oscpy` (stale
     since about 2020, threads only), `osc4py3` (small user base, awkward API), `aiosc`
     (unmaintained).
   - Not yet checked against the current release: the latest version, and that its TCP
     client and server support both OSC 1.0 (length prefix) and OSC 1.1 (SLIP) framing.
     Check both before relying on them.
   - Not yet added to `barn/haybale-osc/pyproject.toml` `dependencies`.

2. **Its own external library in its own repo (this one)**, symlinked into
   `haywire-repo/barn/haybale-osc` for local development, like `haybale-stream`,
   `haybale-spandrel`, `haybale-visiongraph` and `haybale-comfyui`.
   - Why: in `haywire-repo/barn/`, the in-repo folders are framework packages and the
     libraries that define basic data types. Integrations with outside
     protocols, tools and ecosystems are external repos. OSC is an outside protocol.
   - Rejected: putting it in `haybale-core` (every user gets network code and a protocol
     dependency), or in `haybale-stream` (OSC users would have to install NDI, Syphon and numpy).
   - Accepted cost: haywire-repo's CI does not catch a `haywire-core` API change that
     breaks this library.

3. **An OSC editor in the studio's action slot**, set up like the Models editor
   (`haywire-repo/barn/haybale-models/haybale_models/editors/models_editor.py`, the
   `@editor(..., default_slot=SlotName.ACTION, requires=...)` decorator at about line 176).
   - In the editor the user defines named **endpoints**: receivers and senders, each with its
     protocol (UDP or TCP), port, and for a sender the target host.
   - Nodes refer to an endpoint by name. Only the endpoint opens a socket, so two nodes can
     never fight over the same port.
   - The "configure centrally, graph stores only a name/key" model follows named volumes:
     `haywire-repo/docs/adr/0065-named-volumes-instead-of-absolute-paths.md` (missing entry →
     status shown on the node, not a crash).

## Open questions: recommendations are proposals, not yet confirmed

1. **Where endpoint setup is stored**
   - (a) Per machine, like `~/.haywire/volumes.toml`. Hosts and IPs vary by machine and venue.
   - **(b) recommended:** in the project. The graph stores only the endpoint name; the setup
     travels with the project, and a sender's IP is edited per venue.
   - (c) In the graph. Rejected: two graphs couldn't share a receiver.

2. **When sockets are open**
   - (a) Always, while the studio runs.
   - **(b) recommended:** counted by users. A socket opens when the first running node or the
     editor's live monitor needs it, and closes when the last one lets go.
   - (c) Only while a graph runs. Rejected: the editor could never show traffic.

3. **The endpoints must not depend on the editor.** The list of endpoints and the sockets
   should be an app-level service in the library. The editor is only a view of it, and nodes
   talk to the service. Execution then works whether or not the editor is open, and every
   session sees the same endpoints. Candidate pattern: the "Observable Store" in haywire-core
   (ambient accessor, listener, app bridge, signal with no payload). Find it in haywire-repo
   and confirm the fit with the owner.

4. **Access tier.** Opening a port exposes the machine to the network, so editing endpoints
   should need ADMIN, as the Volumes editor does. Viewing them and the live monitor could be VIEW.

5. **Nodes**
   - **OSC Receive:** an event node that takes an endpoint and an address pattern. Messages
     arrive as the trigger payload: see how
     `haywire-repo/barn/haybale-audio/haybale_audio/nodes/audio_event.py` reads
     `context.trigger.payload`. It needs a choice between queuing every message and dropping
     all but the newest (`queue_mode=DROP, max_queue_size=1`, see `EventSource` and `CallbackEvent` in
     `haywire-repo/packages/haywire-core/src/haywire/core/execution/event_source.py`).
   - **OSC Send:** takes an endpoint, an address and arguments.
   - A node whose endpoint is missing or down shows that as its status rather than raising.
   - Still to decide: how OSC value types (int32, float32, string, blob, bool, nil, timetag)
     map to Haywire types; whether arguments come through as one list or as dynamic ports;
     whether to use python-osc's pattern matching or match exact addresses only.

6. **TCP details:** each TCP endpoint needs a setting for its framing (OSC 1.0 length prefix
   or OSC 1.1 SLIP), and a TCP sender needs a rule for reconnecting after the connection drops.

7. **Threading:** if python-osc's asyncio server runs on the NiceGUI event loop, no
   thread-to-loop handoff is needed. If the executor runs elsewhere, use the threaded server.
   Check how other event sources hand values to the executor before choosing.

**Suggested extra:** a live traffic log in the editor (address, arguments, source, rate). It's
the first thing anyone needs when debugging OSC.

## Development setup

- `haywire-repo/barn/haybale-osc` is a symlink to this repo's `barn/haybale-osc`. It's
  gitignored there and excluded from haywire-repo's uv workspace, so it's installed into
  haywire-repo's venv with `uv pip install -e barn/haybale-osc`.
- This repo's root `pyproject.toml` already points to haywire-repo's packages as editable
  path sources.
- Release only with `haywire share` (see `CLAUDE.md`). Never change versions by hand.
- Known trap: `python -c "import haybale_osc"` on its own fails with a circular import in
  haywire-core (`macro.registry` → `node` → `node.factory` → `macro.registry`), set off by
  the scaffold's `__init__.py` importing `haywire.core.macro.registry` early. It imports fine
  once `haywire.core.node` is loaded, as it is in the app. Tests that import the library
  first will hit this. The scaffold template is in
  `haywire-repo/packages/haywire-studio/src/haywire_studio/init.py`. Report it to the owner;
  don't fix it in this repo.

## Suggested next step

Run a `/design` pass with the owner on the open questions above, then write a plan.
