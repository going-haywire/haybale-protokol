# Protokol base + OSC over UDP — Implementation Plan (Plan 1 of 6)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run the six checks of design §8, then build the shared base (`ProtokolState`, **Lines**, **Gate file**, **Device list**, **Protocol driver** interface, Receive/Send plumbing) and `haybale-protokol-osc` with OSC Receive and Send nodes over UDP, so a graph receives and sends OSC through a **Gate** written by hand in `.haywire/protokol.toml`.

**Architecture:** `ProtokolState` (an `AppState` in `haybale-protokol`) owns the drivers, reads the Gate file, and hands out counted uses of **Lines**. A Line wraps one driver connection whose daemon thread delivers each message to the Line, which updates the **Line cache** and fans the message out to its subscribers. Receive nodes subscribe in `on_startup` and fire their flow by the route chosen in check 1; Send nodes hold a Line use and call `Line.send`.

**Tech Stack:** Python 3.12, haywire-core (`BaseNode`, `AppState`, `LibrarySettings`, `EventSource`), `haybale-core` (`BYTES`, `LIST`), `python-osc` 1.10.2, `tomlkit` via `haywire.core.tomlio`, pytest.

**Spec:** [docs/design.md](../../design.md), terms from [docs/reference/glossary.md](../../reference/glossary.md).

**Plan sequence:** 1 base + OSC UDP (this) · 2 OSC TCP · 3 editors (Gates editor, Monitor, Device editor) · 4 MIDI · 5 gamepad · 6 Art-Net, discovery, OSCQuery. Each later plan is written when the previous one lands.

## Global Constraints

- No change to `haywire-core` or any haywire-repo file; gaps go to the owner as proposals (design §4, §7.11).
- **Do not link anything into haywire-repo** (no symlink, no `.gitignore`/pyproject edits there): the owner is changing that setup. All work and tests run in this repo's workspace.
- Do not import `haybale_graph_editor.state…` / `GraphAppState` until the owner says the `state/` → `states/` rename landed. Plan 1 needs neither.
- `uv run --frozen` for every command. The only re-lock is Task 0 Step 2 and Task 12 Step 1 (`uv lock`, intentional: new dependencies); afterwards `git diff uv.lock` must show only those additions.
- No ADRs; reasoning and check findings go into `docs/design.md` (and terms into the glossary).
- Use glossary terms exactly in code names, docstrings and status text: Gate, Input gate, Output gate, Line, Line cache, Start value, Device, Device list, Gate file, Protocol driver, Arg shape, OSC bundle, Unbound gate.
- Component folders are plural, `states/` included. Every new haybale follows the scaffold layout of `barn/haybale-protokol`.
- Gate file: `<project>/.haywire/protokol.toml`. Device list: `~/.haywire/protokol-devices.toml`.
- Status text "protocol not installed" verbatim for a gate whose protocol has no driver.
- Grace period: library setting on `haybale-protokol`, default `2.0` s.
- Bind address default: all interfaces (`0.0.0.0`). Lines ignore the studio's `security.json`.
- Start value defaults: on for OSC Receive. Queue mode: Drop with size 1 for stream kinds (OSC), Block for event kinds.
- OSC Send default wire types `f` / `i`; `d` / `h` only when the Arg shape says so.
- Release only via `haywire share`, and not in this plan. Ask the owner before every commit until they say otherwise (`docs/` and `uv.lock` are still uncommitted).

## Review Focus

1. **A gate name that is not in the Gate file, or a malformed `protokol.toml`.** Expect a status on the node ("no gate named 'x'" / "gate file: <error>"), the graph still runs, other gates still work. → Task 7 `test_malformed_file_raises_gate_file_error`, Task 10 `test_missing_gate_is_status_not_error`.
2. **The UDP port is already taken (another app, or a second gate with a different bind on the same port).** Expect the Line status "cannot open: <OS error>", node status shows it, no thread left running. → Task 12 `test_port_in_use_is_status`.
3. **A message whose arguments do not fit the Arg shape** (too few, wrong type, `vf3` with two floats). Expect the node to skip that message and count it in its status, not raise in the line thread. → Task 14 `test_decode_short_message_returns_none`, Task 15 `test_mismatched_message_is_counted`.
4. **Graph stopped and started within the grace period.** Expect the same Line (no re-bind, cache kept), and no double delivery from a stale subscriber. → Task 9 `test_reacquire_within_grace_keeps_line`, `test_released_subscriber_gets_nothing`.
5. **A burst of messages faster than the flow runs.** Expect the line thread never blocks (Drop/size 1 keeps the newest), the Line cache holds the latest per address. → Task 11 `test_fire_never_blocks_line_thread`.

---

## Phase A — tooling and the six checks

### Task 0: Test tooling

**Files:**
- Modify: `pyproject.toml` (root)
- Create: `tests/__init__.py`, `tests/conftest.py`, `tests/test_library.py`

**Interfaces:**
- Produces: fixtures `project_root`, `_isolated_home` (autouse, session), `library_system` (session), `graph` (function: an empty `BaseGraph` bound to the library system), helpers `make_node(graph, registry_key, position=(0, 0))` and `make_edge(graph, src_id, src_port, dst_id, dst_port)` in `tests/helpers.py`.

- [ ] **Step 1:** Add to root `pyproject.toml`: `[dependency-groups] dev = ["pytest>=8", "pytest-timeout", "ruff==0.12.12", "mypy==2.1.0"]`, `[tool.ruff]` / `[tool.ruff.lint]` exactly as in `../haybale-spandrel/pyproject.toml`, `[tool.pytest.ini_options] testpaths = ["tests"]`, `timeout = 30`, `markers = ["integration"]`.
- [ ] **Step 2:** `uv lock && uv sync`; check `git diff uv.lock` shows only the dev group.
- [ ] **Step 3:** Write `tests/conftest.py` mirroring `../haybale-spandrel/tests/conftest.py` (`_isolated_home`, `library_system` via `create_test_library_system(workspace_root=…, library_paths=[project_root/"barn"], load_libraries=True, enable_file_watching=False)`). Port `make_node` / `make_edge` and the `graph_with_library_system` fixture from `../haywire-repo/tests/conftest.py` into `tests/helpers.py` / `conftest.py` (copy, do not import haywire-repo tests).
- [ ] **Step 4:** `tests/test_library.py::test_protokol_library_loads` — asserts `"haybale-protokol"` is among the loaded library names of `library_system`.
- [ ] **Step 5:** Run `uv run --frozen pytest -q` → 1 passed. `uv run --frozen ruff check .` → clean.
- [ ] **Step 6:** Ask the owner whether to commit `docs/`, `uv.lock` and this task; commit only on yes.

### Tasks 1–6: The checks of design §8

Each check is a spike: throwaway code under the scratchpad, never in `barn/`. Each ends with a short finding appended to `docs/design.md` §8 under the check (“**Finding (2026-11-…):** … — consequence: …”). A finding that contradicts a design decision is **not** written as a decision: note it as “open — put to owner”.

#### Task 1: Event route (decides Task 11)

Questions, answered from source and a spike run against haywire-core:
- [ ] **Step 1 — CallbackEvent:** an EVENT node subscribing `CallbackEvent(event_name=self.node_id)` in `post_init`, and calling `context.emit_callback(self.node_id, payload)` from a foreign thread with the `context` it got in `on_startup`. Does `on_startup` run for an EVENT node whose flow has not yet triggered (i.e. is the group started at `start_execution`, or lazily on first trigger)? Read `interpreter.py` `start_execution` / `ExecutionGroup.start`, then confirm with a spike: graph with one such node + a recording node; thread emits 3 payloads; assert 3 worker runs.
- [ ] **Step 2 — ExternalEvent:** `event_subscription = ExternalEvent(category="protokol", name=<line/gate key>)` + `GraphInterpreter.dispatch_external_event`. How can `ProtokolState` reach every running interpreter (search the VM / execution service for a registry of running interpreters; `GraphAppState` is off-limits until the rename)? Note per-node vs per-gate keying: one key per gate means every Receive node on the gate is woken and must filter in its worker.
- [ ] **Step 3:** Is `emit_callback` safe to call from a non-executor thread (check `CallbackManager.emit_callback` locking, and `haybale_audio.emitter.BlockPump`, which does it)? Does `enqueue_trigger` block under `QueueMode.BLOCK` (it must not block a Line thread → we would always use DROP or a non-blocking path)?
- [ ] **Step 4:** Write the finding and the chosen route. Expected outcome to confirm or refute: CallbackEvent works without any core hook because the node owns its `context`; ExternalEvent needs a way to find interpreters that only `GraphAppState` provides → if CallbackEvent works, recommend it to the owner despite the design's lean, because it is the only route that needs no off-limits import.

#### Task 2: macOS gamepads off the main thread

- [ ] **Step 1:** In the scratchpad: `uv run --with pysdl2 --with pysdl2-dll python spike_sdl.py`. Spike: `SDL_Init(SDL_INIT_GAMECONTROLLER)` and an `SDL_PollEvent` loop on a `threading.Thread`; report devices added and axis events with a pad plugged in (ask the owner to plug one in and move a stick; without a pad, report init/poll errors only).
- [ ] **Step 2:** Same with `SDL_SetHint(SDL_HINT_JOYSTICK_THREAD, "1")`. Finding: background pump works / needs main thread → consequence for Plan 5.

#### Task 3: Does a grown `ADD` pin revert to `ADD` when its last edge goes?

- [ ] **Step 1:** Read how `ADD` resolves on connect (`haywire/barn/builtin/types/add.py`, `loop_array.py:101-123`) and whether anything retypes on disconnect (`release_pins`, the edge-delete action in `undo/actions/graph_actions.py`).
- [ ] **Step 2:** Spike test in scratchpad: node with one `ADD` outlet, connect to a `FLOAT` inlet, delete the edge (through the undo action, as the UI does), print the port type; undo, print again. Finding → if it stays `FLOAT`, Task 15 calls `release_pins` to turn a capture/arg pin back into `ADD`; proposal to owner if core should do it.

#### Task 4: Is a node told about port reorder?

- [ ] **Step 1:** Read `ReorderPortsAction` (`graph_actions.py:1568`): what it changes (`DataPort.order`?) and whether it calls any node hook or emits a signal. Finding → either Task 16 hooks it, or the Arg shape is derived from `DataPort.order` when the node next assembles (`on_assembly`), plus proposal for a notification.

#### Task 5: `args` list → typed pins on a saved, connected node

- [ ] **Step 1:** Spike: node with an Arg shape setting whose change removes `args` and adds typed outlets; connect `args`, change the shape, save to dict, reload, undo, redo. Record: are edges to removed ports dropped cleanly, do added ports survive reload (canon: ports added outside `init()` are kept as saved), does undo restore `args` and its edge?
- [ ] **Step 2:** Finding → the mechanism Task 15 uses (rebuild ports in the setting's change hook vs in `init()` from the saved setting). If `init()` can read the saved setting, prefer it (canon: saved nodes follow `init()`).

#### Task 6: 32- vs 64-bit on the OSC wire

- [ ] **Step 1:** `uv run --with python-osc==1.10.2 python spike_osc.py`: what `OscMessageBuilder.add_arg` infers for Python `float` / `int` with no type, and with `ARG_TYPE_DOUBLE` / `ARG_TYPE_INT64`; what `OscMessage` decodes `d` / `h` to; out-of-range int → `i`? Finding → the encode table of Task 14 (`f`, `i` by default; ints beyond 32 bit with `i` in the shape: clamp, or error status?). Put the out-of-range behaviour to the owner with a recommendation (status, message dropped).

#### STOP — report the checks

- [ ] Report all six findings to the owner, one decision question at a time where a finding needs one. Phase B starts only after the owner confirms. Adjust Tasks 11, 15, 16 here if a finding changes them.

---

## Phase B — the base haybale (`barn/haybale-protokol`)

### Task 7: Gate and Gate file

**Files:**
- Create: `barn/haybale-protokol/haybale_protokol/gates.py`
- Test: `tests/test_gates.py`

**Interfaces:**
- Produces:
  - `Direction = Literal["in", "out", "two-way"]`
  - `@dataclass(frozen=True) class Gate: name: str; protocol: str; direction: Direction; device: str | None = None; options: Mapping[str, Any] = field(default_factory=dict)` — `options` holds everything protocol-specific (`transport`, `port`, `host`, `bind`, …), read by the driver.
  - `gate_file_path(project_root: Path) -> Path` → `project_root / ".haywire" / "protokol.toml"`
  - `load_gates(path: Path) -> dict[str, Gate]` — missing file → `{}`.
  - `save_gates(path: Path, gates: Iterable[Gate]) -> None` — through `haywire.core.tomlio.edit_toml`, so a hand-written file keeps its comments.
  - `class GateFileError(ValueError)` — message names the file and the gate.

File format:

```toml
[gates.touchosc-in]
protocol = "osc"
direction = "in"
transport = "udp"
port = 8000
bind = "0.0.0.0"
```

- [ ] **Step 1: tests** — `test_missing_file_is_empty`, `test_round_trip_keeps_options` (Gate with `options={"transport": "udp", "port": 8000}` saved and loaded equal), `test_save_keeps_comments` (file with a `# note` comment keeps it), `test_malformed_file_raises_gate_file_error` (bad TOML; `direction = "sideways"`; missing `protocol` — each raises, message contains the path), `test_two_way_only_for_tcp_or_device` is **not** checked here (driver concern, Plan 2).
- [ ] **Step 2:** run → FAIL. **Step 3:** implement. **Step 4:** run → PASS.

### Task 8: Device and Device list

**Files:**
- Create: `barn/haybale-protokol/haybale_protokol/devices.py`
- Test: `tests/test_devices.py`

**Interfaces:**
- Produces: `@dataclass(frozen=True) class Device: name: str; protocol: str; os_id: str`; `device_list_path() -> Path` (`Path.home() / ".haywire" / "protokol-devices.toml"`, read at call time so the test HOME applies); `load_devices(path: Path) -> dict[str, Device]`; `save_devices(path: Path, devices: Iterable[Device]) -> None`; `DeviceListError(ValueError)`.

Format: `[devices.<name>] protocol = "midi"`, `os_id = "IAC Driver Bus 1"`.

- [ ] Tests `test_device_list_under_home`, `test_round_trip`, `test_malformed_raises`; FAIL → implement → PASS. (Used by MIDI/gamepad plans; OSC gates name no device.)

### Task 9: Protocol driver interface and Line

**Files:**
- Create: `barn/haybale-protokol/haybale_protokol/drivers.py`, `barn/haybale-protokol/haybale_protokol/line.py`
- Test: `tests/test_line.py` (with a `FakeDriver` / `FakeConnection` in `tests/fakes.py`)

**Interfaces:**
- Produces, in `drivers.py`:
  - `@dataclass(frozen=True) class LineKey: protocol: str; address: str` — address is driver-defined, e.g. `"udp-in 0.0.0.0:8000"`.
  - `@dataclass(frozen=True, slots=True) class Message: address: str; args: tuple[Any, ...]; time: float; extra: Mapping[str, Any] = field(default_factory=dict)` — `extra["timetag"]` for an OSC bundle member.
  - `class Connection(Protocol)`: `def start(self, deliver: Callable[[Message], None]) -> None` (starts its daemon thread, or raises `OSError`), `def send(self, message: Message) -> bool`, `def close(self) -> None`, `status: str`.
  - `class ProtocolDriver(Protocol)`: `protocol: str`; `def line_key(self, gate: Gate, device: Device | None) -> LineKey`; `def open(self, key: LineKey, gate: Gate, device: Device | None) -> Connection`; `def cache_key(self, message: Message) -> Hashable`; `def describe(self, message: Message) -> str` (one line, for the Monitor).
- Produces, in `line.py`:
  - `class Line: __init__(self, key: LineKey, connection: Connection, cache_key: Callable[[Message], Hashable], grace_s: Callable[[], float])`
  - `add_user(self, subscriber: Callable[[Message], None] | None = None) -> int` (token; first user starts the connection; a pending grace close is cancelled)
  - `remove_user(self, token: int) -> None` (last user leaves → `threading.Timer(grace_s())` closes; `grace_s() == 0` closes at once)
  - `send(self, message: Message) -> bool`; `cached(self) -> list[Message]`; `users: int`; `is_open: bool`; `status: str`; `on_closed: Callable[[Line], None] | None` (set by `ProtokolState` to drop the Line from its table).
  - Delivery runs on the connection's thread: update cache under a lock, then call each subscriber; a subscriber that raises is logged once and does not stop the others.

- [ ] **Step 1: tests** — `test_first_user_opens_last_closes_after_grace` (grace 0.05 s; closed after ~0.1 s), `test_reacquire_within_grace_keeps_line` (same connection object, not restarted, cache kept), `test_released_subscriber_gets_nothing`, `test_cache_keeps_last_per_key`, `test_raising_subscriber_does_not_stop_others`, `test_open_error_sets_status_and_no_user_kept` (`start` raises `OSError("in use")` → `add_user` raises `LineOpenError`, `status == "cannot open: in use"`, `users == 0`).
- [ ] **Step 2:** FAIL → **Step 3:** implement (`class LineOpenError(RuntimeError)` in `line.py`) → **Step 4:** PASS.

### Task 10: ProtokolState and ProtokolSettings

**Files:**
- Create: `barn/haybale-protokol/haybale_protokol/states/protokol_state.py`, `barn/haybale-protokol/haybale_protokol/settings/protokol_settings.py`, `barn/haybale-protokol/haybale_protokol/signals.py`
- Modify: `barn/haybale-protokol/haybale_protokol/haybale.toml` (label "Protokol", description, tags `["osc", "midi", "gamepad", "control", "protocol"]`, keep `name`/`version`)
- Test: `tests/test_protokol_state.py`

**Interfaces:**
- Consumes: Tasks 7–9.
- Produces:
  - `@settings class ProtokolSettings(LibrarySettings)`: `grace_period_s = setting[FLOAT](2.0, min=0.0, max=30.0, label="Line grace period (s)", description="How long a Line stays open after its last user leaves, so a graph restart keeps TCP peers.")`
  - `class ProtokolChanged(Signal)` — payload-free.
  - `@state(label="Protokol", …) class ProtokolState(AppState)`:
    - `register_driver(self, driver: ProtocolDriver) -> None`; `unregister_driver(self, protocol: str) -> None` (closes that protocol's Lines at once)
    - `project_root: Path | None` — `None` → `get_workspace_root()` at first use; tests set it.
    - `gates(self) -> dict[str, Gate]` — reads the Gate file on each call when its mtime changed; a `GateFileError` is kept in `gate_file_error: str | None` and yields `{}`.
    - `use(self, gate_name: str, direction: Literal["in", "out"], subscriber: Callable[[Message], None] | None = None) -> LineUse | str` — returns a status string instead of a use: `"no gate named '<n>'"`, `"gate file: <error>"`, `"protocol not installed"`, `"unbound gate: no device '<d>' on this machine"`, `"'<n>' is an output gate"` / `"… an input gate"`, `"cannot open: <os error>"`.
    - `@dataclass class LineUse: line: Line; token: int; gate: Gate` with `release(self) -> None` (idempotent).
    - `lines(self) -> list[Line]`.
    - `_changed(self)` — `loop.call_soon_threadsafe(self._signal_emit, ProtokolChanged())`, dropped when no loop runs (copy the `ModelsState._on_models_changed` shape); called on line open/close/status change and driver (un)register.
    - `on_disable` closes every Line.
- [ ] **Step 1: tests** (with `FakeDriver`, `project_root=tmp_path`): `test_missing_gate_is_status_not_error`, `test_protocol_not_installed`, `test_direction_mismatch_is_status`, `test_two_uses_share_one_line`, `test_unregister_driver_closes_lines`, `test_gate_file_edit_is_picked_up` (rewrite file, next `use` sees new port), `test_grace_comes_from_settings`.
- [ ] **Step 2:** FAIL → **Step 3:** implement; `Library.register_components` already scans `states/` before `editors/` → **Step 4:** PASS, plus `tests/test_library.py::test_protokol_state_registered` (container `get(ProtokolState)` is not None in `library_system`).

### Task 11: Receive/Send node plumbing

**Files:**
- Create: `barn/haybale-protokol/haybale_protokol/receive.py`, `barn/haybale-protokol/haybale_protokol/dispatch.py`
- Test: `tests/test_receive_plumbing.py`

**Interfaces** (route per Task 1; written for CallbackEvent, adjust at the STOP if Task 1 chose ExternalEvent):
- Produces:
  - `dispatch.py`: `class ReceiveDispatchSettings(NodeSettings)` — `queue_mode` (CHOICES `"Block (every message)"` / `"Drop (newest only)"`), `max_queue_size` (INT, 1…1024), `start_value` (BOOL) — each `promotable=Promotable.CONFIG`, shaped like `AudioEventNode.DispatchSettings`. Defaults are per node class via `ReceiveDispatchSettings.defaults(stream: bool)` or subclass constants: stream → Drop / 1 / start on; event → Block / 100 / off.
  - `event_source_for(node_id: str, dispatch: ReceiveDispatchSettings) -> EventSource`
  - `receive.py`: `class ReceiveBinding` — created in a Receive node's `on_startup(context)`:
    `ReceiveBinding(state: ProtokolState, gate_name: str, accept: Callable[[Message], dict | None], fire: Callable[[dict], None], start_value: bool)`;
    `.status: str` (`"listening on <gate>"` or the status from `ProtokolState.use`); `.close()` in `on_shutdown`. `accept` turns a Message into a trigger payload or `None` (filtered out). With `start_value`, after subscribing, every cached Message that `accept`s fires once.
  - `fire` for CallbackEvent: `lambda payload: context.emit_callback(event_name=node_id, payload=payload)`.
  - `get_protokol_state() -> ProtokolState` (via `get_library_state_container().get(ProtokolState)`, raising a clear error when the library is disabled).
- [ ] **Step 1: tests** (FakeDriver): `test_binding_fires_accepted_messages_only`, `test_start_value_fires_cache_once`, `test_start_value_off_fires_nothing_at_start`, `test_close_releases_line`, `test_unknown_gate_status`, `test_fire_never_blocks_line_thread` (a `fire` backed by a DROP queue of size 1; 1000 messages delivered in < 0.5 s; newest is kept).
- [ ] **Step 2:** FAIL → **Step 3:** implement → **Step 4:** PASS.

---

## Phase C — `barn/haybale-protokol-osc`

### Task 12: Haybale scaffold and UDP driver

**Files:**
- Create: `barn/haybale-protokol-osc/` mirroring `barn/haybale-protokol/` (pyproject, README, `haybale_protokol_osc/__init__.py` with the same registry scans, `haybale.toml` with `name = "haybale-protokol-osc"`, `version = "0.0.1"`, `linked_libraries = ["haybale_protokol", "haybale_core"]`, every component folder incl. `states/`)
- Create: `haybale_protokol_osc/driver.py`, `haybale_protokol_osc/states/osc_state.py`
- Modify: root `pyproject.toml` (`haybale-protokol-osc` in dependencies + `[tool.uv.sources.haybale-protokol-osc] workspace = true`)
- Test: `tests/osc/test_udp_driver.py`

**Interfaces:**
- Consumes: Tasks 9–10.
- Produces:
  - `class OscDriver` implementing `ProtocolDriver`, `protocol = "osc"`. Gate options: `transport = "udp"` (Plan 2 adds `"tcp"`), `port: int`, `bind: str = "0.0.0.0"` (in), `host: str` (out). `line_key`: in → `LineKey("osc", f"udp-in {bind}:{port}")`, out → `LineKey("osc", f"udp-out {host}:{port}")`. `cache_key(m) = m.address`. `describe(m)` → `"/a/b ,fi 0.5 3"`.
  - `UdpInConnection` — own socket + daemon thread `protokol-osc-udp-in-<port>`; parses each datagram with `pythonosc.osc_packet.OscPacket`; an OSC bundle is split, each member delivered with `extra={"timetag": <float>}`; a datagram that fails to parse increments `bad_packets` and is skipped. `close()` unblocks the thread (socket timeout 0.2 s or `shutdown`).
  - `UdpOutConnection` — `send` builds with `OscMessageBuilder` from `Message.extra["types"]` (type tag string from Task 14) and `args`.
  - `@state class OscState(AppState)`: `on_enable` → `get_library_state_container().get(ProtokolState).register_driver(OscDriver())`; `on_disable` → `unregister_driver("osc")` (the `ensure_volume` shape).
- [ ] **Step 1:** pyproject dependency `python-osc==1.10.2`, `haybale-protokol`, `haybale-core`; `uv lock && uv sync`; check `git diff uv.lock`.
- [ ] **Step 2: tests** — `test_receives_message_on_loopback` (send with `SimpleUDPClient` to `127.0.0.1:<free port>`), `test_bundle_is_split_with_timetag`, `test_bad_datagram_is_counted`, `test_close_stops_thread` (thread not alive after `close()`), `test_port_in_use_is_status` (two connections on one port → second raises `OSError`; via `ProtokolState.use` → `"cannot open: …"`), `test_send_reaches_socket`, `test_osc_state_registers_driver` (library_system: `ProtokolState` has driver `"osc"`).
- [ ] **Step 3:** FAIL → implement → PASS.

### Task 13: Address patterns

**Files:** Create `haybale_protokol_osc/pattern.py`; Test `tests/osc/test_pattern.py`

**Interfaces:**
- Produces: `@dataclass(frozen=True) class AddressPattern: text: str; captures: int` with `compile_pattern(text: str) -> AddressPattern` and `AddressPattern.match(address: str) -> tuple[str, ...] | None` (the captured strings, `()` for an exact or empty pattern; empty pattern matches everything). `AddressPattern.is_exact: bool`.
- Translation (one capture group per wildcard, never across `/`): `*` → `([^/]*)`, `?` → `([^/])`, `[0-9]` / `[!a-c]` → `([0-9])` / `([^a-c])`, `{a,b}` → `(a|b)`; everything else `re.escape`d; anchored. Invalid pattern → `ValueError` naming the position.
- [ ] Tests: `test_star_captures`(`/tracker/blob/*/pos` vs `/tracker/blob/3/pos` → `("3",)`), `test_star_does_not_cross_slash`, `test_question_and_range`, `test_negated_range`, `test_alternatives`, `test_exact_is_exact`, `test_empty_matches_all`, `test_unclosed_bracket_raises`. FAIL → implement → PASS.

### Task 14: Arg shape

**Files:** Create `haybale_protokol_osc/shape.py`; Test `tests/osc/test_shape.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) class Token: text: str; width: int; haywire_type: str | None` (`None` for a skip).
  - `parse_shape(text: str, *, receive: bool) -> list[Token]` — whitespace-separated; `ShapeError(ValueError)` for an unknown token, and for `_` / `_n` when `receive=False`.
  - `decode(tokens: list[Token], args: tuple) -> list[Any] | None` — one value per non-skip token; `None` when the args are too few or a type does not fit. Extra trailing args are ignored.
  - `encode(tokens: list[Token], values: list[Any]) -> tuple[str, tuple]` — `(type_tags, flat_args)`; a `VEC3F` value for `vf3` becomes three `f`.
  - `infer_shape(values: list[Any]) -> str` — for Send pins with no shape token: `float` → `f`, `int` → `i`, `bool` → `T`/`F`, `str` → `s`, `bytes` → `b`, vector types → `vf2…vi4`, matrices → `m3`/`m4`.
- Token table: `i`,`h` → `INT`; `f`,`d` → `FLOAT`; `s`,`S`,`c` → `STRING`; `b` → `BYTES`; `T`/`F` (shape token `T` means "a bool") → `BOOL`; `r` → `COLOR`; `vi2`–`vi4` → `VEC2I`–`VEC4I`; `vf2`–`vf4` → `VEC2F`–`VEC4F`; `m3`/`m4` → `MAT3`/`MAT4` (9 / 16 floats, row-major); `_` skip 1, `_n` skip n. Out-of-range `i`: as decided at the Task 6 STOP.
- [ ] Tests: `test_parse_known_tokens`, `test_skip_only_on_receive`, `test_unknown_token_raises`, `test_decode_groups_vectors`(`vf3 i` + `(1.,2.,3.,7)`), `test_decode_short_message_returns_none`, `test_decode_wrong_type_returns_none`, `test_encode_vector_flattens`, `test_encode_64bit_tags` (`d h` → `"dh"`), `test_infer_shape`. FAIL → implement → PASS.

### Task 15: OSC Receive node

**Files:** Create `haybale_protokol_osc/nodes/osc_receive.py`; Test `tests/osc/test_osc_receive_node.py`

**Interfaces:**
- Consumes: Tasks 11, 13, 14; Task 1/3/5 findings.
- Produces: `@node(label="OSC Receive", menu="protokol/osc", node_type=NodeType.EVENT, search_tags=["osc", "receive", "control", "network"]) class OscReceiveNode(BaseNode)`:
  - Settings: `gate: STRING` (gate name), `address: STRING` (pattern, empty = all), `arg_shape: STRING` (empty = one `args` outlet), dispatch bag `ReceiveDispatchSettings` with stream defaults.
  - Outlets: `received` (EXEC), `address` (STRING), then either `args` (`LIST`) or one typed outlet per non-skip token (`arg_1`, `arg_2`, … labelled by token), then capture outlets `match_1…match_n` as bare `ADD`, `timetag` (FLOAT, 0 outside an OSC bundle), `status` (STRING).
  - Ports are rebuilt when `address` or `arg_shape` changes (mechanism per Task 5); an invalid pattern or shape leaves the ports as they were and sets `status`.
  - `on_startup`: `ReceiveBinding(get_protokol_state(), gate, accept, fire, start_value)`; `accept` does pattern match → decode → payload `{"address", "values", "captures", "timetag"}`; a decode miss increments `skipped` shown in status (`"listening on touchosc-in · 3 skipped"`). `on_shutdown`: `close()`.
  - `worker`: writes outlets from the payload; a capture that does not convert to its connected type sets status `"match_1: '3a' is not INT"` and leaves the outlet unchanged; returns `"received"`.
- [ ] **Step 1: tests** (integration, with library_system, OSC driver, gate file in `tmp_path`, `ProtokolState.project_root` set): `test_receives_into_flow` (Receive → recording node; send `/fader/1 0.5`; record sees 0.5), `test_pattern_filters_and_captures`, `test_args_list_by_default`, `test_shape_builds_typed_outlets`, `test_mismatched_message_is_counted`, `test_start_value_fires_cached_on_restart` (stop + start within grace → recording sees last value once), `test_missing_gate_status`, `test_save_reload_keeps_ports_and_edges` (per Task 5).
- [ ] **Step 2:** FAIL → **Step 3:** implement → **Step 4:** PASS.

### Task 16: Pin edits rewrite the Arg shape

**Files:** Modify `haybale_protokol_osc/nodes/osc_receive.py`; Test `tests/osc/test_shape_pins.py`

**Interfaces:** `shape_from_ports(node) -> str` in `haybale_protokol_osc/shape.py`, used by Receive and Send.

Exact hooks depend on Tasks 3 and 4 findings; behaviour is fixed by the design:
- [ ] Tests: `test_grown_add_pin_appends_token` (connect a `VEC3F` inlet to a trailing `ADD` arg pin → shape gains `vf3`), `test_removing_pin_drops_token`, `test_reorder_rewrites_shape`, `test_each_change_is_one_undo_step` (undo restores the previous shape text and ports in one step). FAIL → implement → PASS. Any hook that does not exist in core → stop, proposal to the owner, keep the test as `xfail(reason=…)` only with the owner's OK.

### Task 17: OSC Send node

**Files:** Create `haybale_protokol_osc/nodes/osc_send.py`; Test `tests/osc/test_osc_send_node.py`

**Interfaces:**
- Produces: `@node(label="OSC Send", menu="protokol/osc", search_tags=["osc", "send", "control", "network"]) class OscSendNode(BaseNode)`:
  - Inlets: `exec` (EXEC), `address` (STRING), arg inlets as `ADD` that grow one per edge (order = argument order), plus `arg_shape: STRING` setting that overrides types (`d`, `h`) for 64-bit; no `_` (ShapeError on Send). Outlets: `next` (EXEC), `shape` (STRING: the resulting type tags, shown on the node), `status` (STRING: `"sent 12 · dropped 0"`).
  - `on_startup`: `get_protokol_state().use(gate, "out")`; status on failure. `on_shutdown`: release.
  - `worker`: values of every arg inlet (an unconnected one sends its widget value) → `encode` → `Line.send(Message(address, args, time, extra={"types": tags}))`; returns `"next"`.
- [ ] Tests: `test_send_reaches_udp_socket` (bind a test socket; trigger node; assert parsed message `/x ,fi 0.5 3`), `test_vec3_goes_out_as_three_floats`, `test_unconnected_inlet_sends_widget_value`, `test_64bit_from_shape`, `test_skip_token_rejected`, `test_missing_gate_status`. FAIL → implement → PASS.

### Task 18: End-to-end and docs

**Files:** Create `tests/osc/test_end_to_end.py`, `barn/haybale-protokol/haybale_protokol/NOTES.md`, `barn/haybale-protokol-osc/haybale_protokol_osc/NOTES.md`; Modify `docs/design.md` (only to record findings already accepted by the owner).

- [ ] `test_receive_to_send_loopback` — gate file with `osc-in` (UDP 127.0.0.1, free port) and `osc-out` pointing at a test socket; graph Receive(`/in/*`) → Send(`/out`) forwarding `arg_1`; send `/in/a 1.5`; test socket gets `/out 1.5`.
- [ ] `uv run --frozen pytest -q` all green; `uv run --frozen ruff check .`; `uv run --frozen mypy barn` clean (or pre-existing errors listed to the owner).
- [ ] NOTES.md per haybale: what it is, the Gate file format with one example, status texts. Then `uv run --frozen haywire docs barn/haybale-protokol` and `… barn/haybale-protokol-osc`.
- [ ] Report to the owner; ask before committing. No `haywire share`.

## Deferred to later plans (named so nothing is lost)

- TCP, framings, reconnect, server fan-out, Two-way gates → Plan 2.
- Gate stores a subnet and the interface follows from it (needs interface enumeration, shared with the Gates editor) → Plan 3. Plan 1 binds the literal `bind` address.
- Gates editor, Monitor and taps, Device editor, Protokol selection, access tiers, "Save as gate…" → Plan 3.
- MIDI, gamepad (incl. Task 2 finding), Art-Net, discovery, OSCQuery → Plans 4–6.
- Docs for haywire-repo (design §9) → proposals to the owner after Task 1.
