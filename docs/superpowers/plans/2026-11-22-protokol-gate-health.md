# Gate health, reconnect and one editor — Implementation Plan (Plan 4b, before Plan 5)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every view says whether a gate works, and why not. A Receive node picks its device up again when it is plugged back in, without a graph restart. The Device editor becomes the lower pane of the Gates editor.

**Architecture:**
- **One source: `ProtokolState.health(gate)`.** It returns a `GateHealth` (state and reason) worked out from the drivers, the Device list, the open Lines and the last failed open. Every view reads it: editor rows, the editor's icon, node badges and gate chips. Nothing computes health on its own.
- **A device watch.** A daemon thread in `ProtokolState` checks, about once a second, which Devices of device-using drivers are present (`drivers.list_devices` + `drivers.find_device`). It reports only changes: it emits `ProtokolChanged` for the editors and calls health listeners for nodes and bindings. A **refresh** button in the Device pane forces a check at once.
- **Reconnect lives in `ReceiveBinding`.** A binding whose gate is `not plugged in`, at start or after an unplug, waits for a health change and then takes the Line again. `GateSender` (Send nodes) does not reconnect (design §10.6.2).
- **Node badges use core's `NodeWarning`**, through one helper shared by the four Receive and Send nodes, like the MIDI filter badge (`midi_pins.show_filter_problem`).
- **One editor.** `GatesEditor` draws a vertical `ui.splitter` with the gate list above and the Device pane below. The Device pane is the former `DeviceEditor` body, driven by the same `ProtokolSelection`. `DeviceEditor` is removed.

**Tech Stack:** haywire-core (`NodeWarning`, `StoreStrategy`, `BaseEditor.draw_tab`, NiceGUI `ui.splitter`), python-rtmidi (MIDI presence), pytest. No new dependencies.

**Spec:** [docs/design.md](../../design.md) §10, approved by the owner in #15; also §3.2, §3.3 and §5. Builds on #14 and #16.

## Global Constraints

- All earlier constraints hold:
  - No haywire-repo changes.
  - `uv run --frozen` always; no new dependencies, so no `uv lock`.
  - Glossary terms.
  - Statuses and badges, never a crash.
  - The design guide for all UI.
  - The hot-reload rules (test-enforced): helpers at the package root, never in component folders; imports by full module path.
- **Health names are fixed** (§10.2): `working`, `closed`, `unbound`, `not plugged in`, `error`. Network gates are never `not plugged in`.
- **Thread safety:**
  - The watch thread never touches the UI. It emits through `ProtokolState._changed()`, which already hops to the asyncio loop.
  - Health listeners run on the watch thread. A listener must not block; `ReceiveBinding` reconnects on its own thread.
  - `NodeWarning` updates go through `NodeWrapper.replace_warnings`, which core documents as safe from worker threads.
- **The watch must stay cheap.** At most one listing per device-using driver per second. It runs only while at least one gate names a Device, and it lists with a probe object the driver keeps open, never a new rtmidi client per check.
- Access is unchanged: editing the Device list is ADMIN (§5). Without it, the Device pane's port picker is read-only and says "needs an admin".
- Branch `plan-4b-gate-health` from `master`, one commit per task, and a PR to `master` at the end, which the owner merges.

## Health, by case

| Case | `state` | `reason` (shown to the user) |
|---|---|---|
| The gate's Line is open and has users | `working` | `{line status} · {n} users` |
| Usable, nothing holds it now | `closed` | `closed` |
| The gate names a Device this machine's Device list lacks | `unbound` | `no device 'Grid' on this machine` |
| The Device is mapped, but no port matches its OS name now | `not plugged in` | `'Grid' is not plugged in (port 'Grid:Grid MIDI 1 28:0')` |
| No driver for the gate's protocol | `error` | `protocol not installed` |
| The gate file or this gate's entry cannot be read | `error` | the gate-file message |
| The last open failed (port in use, bad options …) | `error` | the open error, kept until the next open succeeds or the gate changes |

`working` and `closed` count as healthy; the other three are **unhealthy** and turn every view red.

## Review Focus

1. **Unplug and replug while a graph runs.** Expect:
   - The gate turns `not plugged in` within about a second.
   - The node badge appears, and its gate chip turns red.
   - On replug, the Receive node fires again with no restart; the badge and the red chip go.
   - Send MIDI drops and counts messages until its graph restarts.
2. **Start with the device unplugged** (the owner's live check, design §10.1). Expect every view to say `not plugged in`, and the node to fire once it's plugged in.
3. **Races.** Close a binding while it's reconnecting, unplug again during a reconnect, and have two Receive nodes on one gate. Expect no stray Line users, no thread left behind after `on_shutdown`, and no double subscription.
4. **Cost.** With MIDI gates and the studio idle, expect one listing per second, and no ALSA client created per check (`aconnect -l` shows a stable client list).
5. **Editor.** Expect:
   - The divider moves and never collapses.
   - Its position survives the list redrawing, but not a page reload.
   - The red dot shows while any gate is unhealthy and goes when none is.
   - A saved workspace that still names the removed Device editor opens without error.

---

### Task 1: `GateHealth` in `ProtokolState`

**Files:** Create `haybale_protokol/gate_health.py` (package root: a helper). Modify `states/protokol_state.py`, and `gate_status.py`, which gets replaced by health. Test `tests/test_gate_health.py`.

**Interfaces:**
- `@dataclass(frozen=True) class GateHealth: state: Literal["working", "closed", "unbound", "not plugged in", "error"]; reason: str`, with the property `healthy -> bool` (`working` or `closed`).
- `ProtokolState.health(gate: Gate | str) -> GateHealth`, following the table above. A `str` names a gate; an unknown name is `error` (`no gate named 'x'`).
- `ProtokolState` records the last failed open per gate, inside `use_gate`, where `cannot open: …` and `gate 'x': …` are already returned. The record is cleared when an open succeeds, the gate is saved or the driver is re-registered.
- Device presence comes from Task 2. Until then, `health` calls `drivers.list_devices` / `find_device` directly.
- `gate_status(state, gate)` becomes `state.health(gate).reason`. Keep the function, so its callers change in Tasks 5 and 6, not here.

- [ ] Tests, using `tests/fakes.FakeDriver`, given a `uses_devices` flag and a settable list of present devices:
  - each row of the table
  - `test_open_failure_is_remembered_until_a_good_open`
  - `test_closed_and_working_are_healthy`
  - `test_network_gate_is_never_not_plugged_in`
- [ ] FAIL → implement → PASS → commit.

### Task 2: The device watch, refresh and health listeners

**Files:** Modify `states/protokol_state.py` and `drivers.py` (optional hook doc). Modify `barn/haybale-protokol-midi/haybale_protokol_midi/driver.py` to list ports through probe objects it keeps. Test `tests/test_device_watch.py` (fake driver), and `tests/midi/test_midi_presence.py` (virtual ports, `needs_virtual`).

**Interfaces:**
- `ProtokolState.present_devices(protocol) -> frozenset[str] | None`: the last checked set of present Device names, or `None` if never checked.
- `ProtokolState.refresh_devices() -> None`: check now, on the calling thread, and report changes. This is the Device pane's refresh button.
- `ProtokolState.watch_health(callback: Callable[[], None]) -> Callable[[], None]`. It returns an `unwatch`. Listeners are held weakly when they are bound methods, so a deleted node can't keep a listener alive. A listener is called on the watch thread after any health change: presence, a gate saved or deleted, a Device saved or deleted, or a Line opened, closed or gone.
- **The watch thread**, `protokol-device-watch`, a daemon:
  - It starts when the first gate naming a Device is loaded or saved, and stops when none is left or in `on_disable`.
  - Its interval is a new setting `device_watch_s` in `settings/protokol_settings.py`, next to `grace_period_s`, default `1.0`.
  - It only emits when something changed.
- **The MIDI driver** keeps one `rtmidi.MidiIn` and one `rtmidi.MidiOut` probe for `list_devices`, made lazily and closed in a new optional driver hook, `close()`, which `unregister_driver` calls. It never creates a client per check.

- [ ] Tests:
  - `test_watch_reports_a_device_appearing_and_going`
  - `test_no_change_no_signal`
  - `test_refresh_checks_at_once`
  - `test_watch_stops_with_no_device_gates`
  - `test_dead_listener_is_dropped`
  - MIDI: `test_virtual_port_presence_follows_open_and_delete`, which uses `Source`/`Sink` from `tests/midi/conftest.py`, whose `close()` deletes the port
  - `test_listing_reuses_probe_clients`: patch `rtmidi.MidiIn`, then count constructions across 5 listings
- [ ] FAIL → implement → PASS → commit.

### Task 3: Receive reconnect

**Files:** Modify `receive.py` (`ReceiveBinding`). Test `tests/test_receive_reconnect.py` (fake driver), and `tests/midi/test_midi_reconnect.py` (virtual ports).

**Interfaces:**
- When `state.use` fails and `state.health(gate).state == "not plugged in"`, the binding keeps a status of `waiting for '{device}'`, registers `watch_health`, and on each call retries `state.use` on its own short-lived thread, `protokol-recv-reconnect-{gate}`, one at a time.
- When its Line's connection reports `gone` (an unplug mid-run), the binding releases that use and waits as above. The old Line is closed on the next `use`, as `use_gate` already does.
- On success the status returns to `listening on {gate}`. `start_value` is not replayed: a fresh Line has an empty cache.
- `close()` unregisters the listener, cancels any pending retry, and is safe during a retry.
- Other failures (`unbound`, `error`) don't retry. They wait for a graph restart, as today.

- [ ] Tests:
  - `test_binding_waits_then_listens_when_device_appears`
  - `test_unplug_mid_run_reconnects`
  - `test_close_during_reconnect_leaves_no_user_or_thread`
  - `test_two_bindings_on_one_gate_share_the_new_line`
  - `test_unbound_does_not_retry`
  - MIDI end to end: a MIDI Event node in a running graph, `Source` deleted and reopened under the same name, with the node firing again
- [ ] FAIL → implement → PASS → commit.

### Task 4: Node badges, and the status outlet not saved

**Files:** Create `haybale_protokol/gate_warning.py` (package root). Modify the four nodes: `haybale-protokol-osc` `nodes/osc_event.py` and `nodes/send_osc.py`, and `haybale-protokol-midi` `nodes/midi_event.py` and `nodes/send_midi.py`. Test `tests/test_gate_warning.py`, plus a test per node in its existing test file.

**Interfaces:**
- `GATE_WARNING = "protokol-gate"`, the `NodeWarning.kind`.
- `show_gate_health(node, state, gate_names) -> None`: one `NodeWarning` per unhealthy gate, named as in `named_status` (`Grid: 'Grid' is not plugged in …`), or none. It goes through `wrapper.replace_warnings(GATE_WARNING, …)` and does nothing without a wrapper.
- Each node calls it:
  - in `post_init`, `on_assembly` and `on_startup`
  - when its `gate` value changes
  - from a `watch_health` listener the node registers in `post_init` and drops in its removal hook. If core has no removal hook, the weak listener from Task 2 covers it.
- Each node's `status` outlet is declared with `store_strategy=StoreStrategy.NEVER` (`haywire.api`), so a reopened graph shows no stale status (design §10.1).

- [ ] Tests:
  - `test_badge_appears_when_device_is_unplugged_and_goes_on_replug` (fake driver)
  - `test_badge_names_each_unhealthy_gate`
  - `test_no_badge_for_closed_gate`
  - per node, `test_status_is_not_saved`: save the graph, reload, and expect `status` to be `""`
  - the MIDI filter badge (`protokol-midi-filter`) and the gate badge coexist without replacing each other
- [ ] FAIL → implement → PASS → commit.

### Task 5: Gate chips from health

**Files:** Modify `widgets/gate_menu_widget.py` (`gate_tone`). Test `tests/test_gate_menu_widget.py`.

**Interfaces:**
- `gate_tone` keeps `danger` for a missing gate or the wrong protocol or direction.
- Otherwise it maps health: healthy → `success`, unhealthy → `danger`. The design asks for red, and the owner noted the chip was green.
- The widget redraws its chips on `ProtokolChanged`. The widget already reacts to it; check that it does.

- [ ] Tests:
  - `test_not_plugged_in_is_danger`
  - `test_unbound_is_danger`
  - `test_closed_is_success`
- [ ] FAIL → implement → PASS → commit.

### Task 6: Gates editor rows, the Monitor button, and the red dot

**Files:** Modify `editors/gates_editor.py`. Test `tests/editors/test_gates_editor.py`.

**Interfaces:**
- Each row shows a health dot and, when unhealthy, the reason, in the danger tone (design guide §1.3).
- The row's Monitor button is disabled for an unhealthy gate, with the reason as its tooltip.
- `GatesEditor.draw_tab(context, orientation=...)` draws the icon with a plain red dot while any gate is unhealthy. Check how `ErrorsEditor` gets its tab redrawn and follow the same path on `ProtokolChanged`.

- [ ] Tests:
  - `test_row_shows_not_plugged_in`
  - `test_monitor_button_disabled_when_unhealthy`
  - `test_icon_dot_follows_health`
- [ ] FAIL → implement → PASS → commit.

### Task 7: The Device pane in the Gates editor; remove the Device editor

**Files:**
- Modify `editors/gates_editor.py`.
- Move the body of `editors/device_editor.py` into a package-root helper `device_pane.py`, which draws into a given container.
- Delete `editors/device_editor.py`.
- Tests: move `tests/editors/test_device_editor.py` to `tests/editors/test_device_pane.py`, and update the `DeviceEditor` uses in `tests/editors/test_redraws.py` and `tests/midi/test_midi_editors.py`.

**Interfaces:**
- `GatesEditor.draw`: `ui.splitter(horizontal=True, value=60, limits=(20, 80))`.
  - **Top pane:** the "Gates" header with its **+**, and the gate list.
  - **Bottom pane:** the "Device" header with its **+** and a **refresh** button (`ProtokolState.refresh_devices`), then the Device pane.
  - Redraws are targeted (`@react_on`), so the divider keeps its position. It isn't remembered across reloads (§10.6.3).
- **The Device pane** follows `ProtokolSelection` exactly as `DeviceEditor` did:
  - a gate: its options, Device mapping, health and Line
  - a Line: as before
  - nothing: this machine's Device list
- For an unbound gate the pane offers a port picker (ADMIN), which creates or updates the Device entry. That's the "map a gate's device name" path the Device editor has today.
- The gate row's device button (`gates_editor.py:134`) selects the device in the pane.
- A saved workspace naming the removed editor: check core's behaviour for an editor id that no longer exists. If it raises, that's a core issue to report; ask the owner before working around it here.

- [ ] Tests, moved and extended:
  - `test_selecting_a_gate_fills_the_device_pane`
  - `test_map_unbound_gate_from_the_pane` (ADMIN)
  - `test_port_picker_read_only_without_admin`
  - `test_refresh_button_checks_devices`
  - `test_device_editor_is_gone`, which checks the registry has no `DeviceEditor`
- [ ] FAIL → implement → PASS → commit.

### Task 8: Docs, live check, PR

- [ ] Update:
  - `haybale_protokol/NOTES.md`: the status table gains the health states, `waiting for '…'` and reconnect.
  - the glossary: **Gate health**, **not plugged in**
  - design §5's editor table, now superseded by §10.4
- [ ] Regenerate docs (`haywire docs`). Run the full suite, ruff and mypy.
- [ ] Live check with the owner, through a Farmhand questionnaire: the four cases of design §10.1 again, plus replug while running (Review Focus 1 and 2), the divider, and the red dot.
- [ ] Push and open a PR to `master` that links #15, this plan and the live-check findings.

## Deferred

- **System notifications instead of polling**: ALSA's announce port, CoreMIDI's notifications. To do if polling proves costly; WinMM has none (§10.6.1).
- **Send reconnect.** The owner chose dropping (§10.6.2).
- **Gamepads (Plan 5)** get health and reconnect for free through `uses_devices`, `list_devices` and `match_device`. The SDL GUID is their OS id.
- **Network gates' reachability** (a TCP client's peer) stays in the Line status; it isn't a health state.
- **Core issues seen on the way, to report to core, not fix here:**
  - a detached edge after a kind change is logged as a "Port type validation error"
  - hot reload doesn't reload package-root helpers, and raised a `KeyError` reloading node modules (2026-11-22)
