# MIDI — Implementation Plan (Plan 4 of 6)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `haybale-protokol-midi`: a MIDI Protocol driver and one MIDI Receive node and one MIDI Send node, so that a graph receives and sends MIDI through gates bound to **Devices** on this machine. The Gates, Monitor and Device editors from Plan 3 work with it unchanged.

**Architecture:**
- **One Line per Device and direction.** A MIDI Line is one `python-rtmidi` port. `MidiInConnection` opens the input port named by the Device's OS id and delivers each message from rtmidi's callback thread. `MidiOutConnection` sends raw bytes.
- **`midi_messages.py`** maps bytes to a protokol `Message` (whose address carries kind, channel and number, which is also the Line cache key) and back, using `mido` for parsing and building.
- **The nodes follow the OSC nodes' shape.** A filter of kind, channel and number is the node's address; the ports follow the filter; one node can use several gates through the gate picker (`protocol="midi"`).

**Tech Stack:** `python-rtmidi==1.5.8` (prebuilt wheels; the newest version fails to build on macOS), `mido==1.3.3`, haywire-core, pytest. Tests use rtmidi **virtual ports**, so no hardware is needed. They're skipped where virtual ports are unavailable (Windows).

**Spec:** [docs/design.md](../../design.md) §3.1–3.3, §6.1, §6.3; the glossary. Builds on Plan 3 (`plan-3-editors`, PR #2).

## Global Constraints

- All earlier constraints hold: no haywire-repo changes or links, `uv run --frozen` except the one intentional `uv lock`, glossary terms, statuses instead of errors, the design guide for all UI.
- Hot-reload rules (test-enforced): helpers at the package root, never in component folders; imports by full module path.
- MIDI gates are always one-way (`in` or `out`) and always name a **Device**. A Device's OS id is the rtmidi port name.
- The Device list maps names to port names; MIDI inputs and outputs are separate ports with separate names.
- A gate whose Device isn't connected is "cannot open: no MIDI port 'X'" at start, never a crash.
- MIDI 1.0 only. MIDI 2.0/UMP, MTC and MSC are out of scope (design §7).
- **Start value** under the "Auto" default: on for stream kinds (CC, pitch bend, aftertouch), off for event kinds (note, program, sysex, transport, raw). The queue mode follows the same split.
- Branch `plan-4-midi`, stacked on `plan-3-editors` and rebased onto `master` once PR #2 is merged. One commit per task; a PR to `master` at the end, which the owner merges.

## Kinds and their pins

| Kind | Filter | Receive outlets (beside `received`, `from_gate`, `status`) | Send inlets |
|---|---|---|---|
| `note` | channel, note | `note` (when note is any), `velocity` INT, `on` BOOL; note-off and note-on with velocity 0 give `on = False` | `note`, `velocity`, `on` |
| `cc` | channel, controller | `controller` (when any), `value` INT 0–127 | `controller`, `value` |
| `pitchbend` | channel | `value` INT −8192…8191 | `value` |
| `aftertouch` | channel | `value` INT 0–127 (channel pressure; polyphonic aftertouch comes through `raw`) | `value` |
| `program` | channel | `program` INT | `program` |
| `sysex` | — | `data` BYTES (without the F0/F7 framing) | `data` |
| `transport` | — | `event` STRING (`clock`, `start`, `continue`, `stop`, `songpos`), `position` INT | `event`, `position` |
| `raw` | — | `bytes` BYTES (the whole message) | `bytes` |

A `channel` outlet appears when the channel filter is "any" for channel kinds. A `channel` or number inlet on Send appears when its filter is "any". Channels are 1–16, as musicians count them.

## Review Focus

1. **A Device unplugged while its Line is open.** Expect no crash. The Device editor shows "not connected", and the Line reopens when the graph restarts with the Device plugged in again.
2. **A burst (a fader sweep, clock at 24 ppqn).** Expect the rtmidi callback never to block: CC and pitch bend use Drop with a queue of 1 by default, and clock events are counted, not queued without bound.
3. **Running status, note-off as note-on with velocity 0, and sysex split across callbacks.** Expect each to decode to the right kind and values.
4. **A filter change while the graph runs.** Expect the ports to rebuild, with edges kept where the ids survive, and the new filter to apply on the next start.
5. **Two gates on the same Device in the same direction.** Expect them to share one Line, as gates do.

---

### Task 1: Haybale scaffold, driver registration, dependency lock

**Files:**
- Create: `barn/haybale-protokol-midi/` mirroring `barn/haybale-protokol-osc/`: `pyproject.toml` with `python-rtmidi==1.5.8`, `mido==1.3.3`, `haybale-protokol` and `haywire-core`; `haybale.toml` with `linked_libraries = ["haybale_protokol"]`; the registry scans; `states/midi_state.py`.
- Modify: the root `pyproject.toml` (dependency plus workspace source).

- [ ] `uv lock && uv sync`; `git diff uv.lock` shows only the two new packages and the haybale.
- [ ] `MidiState.on_enable` registers `MidiDriver()`; `on_disable` unregisters it. Test `test_midi_state_registers_driver` (integration).
- [ ] FAIL → implement → PASS → commit.

### Task 2: Messages: bytes ↔ `Message`

**Files:** Create `haybale_protokol_midi/midi_messages.py`; Test `tests/midi/test_midi_messages.py`

**Interfaces:**
- `decode(data: Sequence[int], time: float) -> Message | None`:
  - The address is `"note 1 60"`, `"cc 1 7"`, `"pitchbend 1"`, `"aftertouch 1"`, `"program 1"`, `"sysex"`, `"transport"`, or `"raw"` for anything else, including poly aftertouch.
  - `args` are the values in the table's order.
  - `extra` holds `{"kind", "channel", "number", "bytes"}`.
  - Running status is resolved by rtmidi, which always hands complete messages.
- `encode(kind: str, channel: int, number: int | None, values: Mapping[str, Any]) -> bytes`. Range errors raise `ValueError` naming the field.
- `parse_test_message(text) -> Message`:
  - `note 1 60 100`, `note 1 60 off`;
  - `cc 1 7 64`, `pb 1 -200`, `at 1 64`, `pc 1 5`;
  - `sysex 7D 01 02`, `clock`, `start`, `stop`, `continue`;
  - `raw 90 3C 64` (hex).

  `extra["bytes"]` holds the wire bytes.
- `describe(message) -> str`, e.g. `note on ch1 60 vel 100`, `cc ch1 7 = 64`.
- [ ] Tests: one per kind both ways; note-on with velocity 0 is `on = False`; channel 16 becomes status `0x9F`; pitch bend range ends; sysex framing; unknown bytes become `raw`; `test_parse_test_message_forms`; `test_encode_out_of_range_names_field`. FAIL → implement → PASS → commit.

### Task 3: The MIDI driver

**Files:** Create `haybale_protokol_midi/driver.py`; Test `tests/midi/test_midi_driver.py` (rtmidi virtual ports; module-level skip when `open_virtual_port` fails).

**Interfaces:**
- `MidiDriver`:
  - `protocol = "midi"`, `uses_devices = True`, `gate_fields() -> ()`.
  - `line_key(gate, device)` gives `LineKey("midi", f"{direction} {device.os_id}")`. It raises `ValueError` for a two-way gate ("a MIDI gate is in or out") or a missing device.
  - `open(...)` gives `MidiInConnection(port_name)` or `MidiOutConnection(port_name)`.
  - `cache_key = message.address`, `describe` and `parse_test_message` from Task 2.
  - `list_devices() -> [(port_name, "input" | "output" | "input and output")]`.
- `MidiInConnection`:
  - `start(deliver)` finds the port by exact name. A missing port raises `OSError(f"no MIDI port '{name}'")`.
  - It sets `ignore_types(sysex=False, timing=False, active_sense=True)` and a callback that decodes and delivers each message.
  - `status` reads `listening on MIDI 'name' · n bad`; `close()` closes the port.
- `MidiOutConnection`: `send(message)` sends `message.extra["bytes"]`, counting sends and drops; a missing port raises at start.
- [ ] Tests:
  - `test_receives_from_virtual_port`
  - `test_sends_to_virtual_port`
  - `test_missing_port_is_cannot_open`
  - `test_two_gates_on_one_device_share_a_line`
  - `test_list_devices_sees_virtual_ports`
  - `test_two_way_gate_rejected`

  FAIL → implement → PASS → commit.

### Task 4: MIDI Receive node

**Files:** Create `haybale_protokol_midi/nodes/midi_receive.py`; Test `tests/midi/test_midi_receive_node.py`

**Interfaces:** `@node(label="MIDI Receive", menu="protokol/midi", node_type=NodeType.EVENT)`.
- Configs:
  - `gate`: `GateSelectWidget` with `protocol="midi"`, `direction="in"`;
  - `kind`: CHOICES from the table;
  - `channel`: INT, 0 means any, 1–16;
  - `number`: INT, −1 means any.

  Each config has a full description, as on the OSC nodes. A change to kind, channel or number rebuilds the outlets with stable ids.
- Dispatch: the `ReceiveDispatchSettings` bag with `stream = kind in {cc, pitchbend, aftertouch}`. The event subscription is recomputed in `on_assembly`.
- Runtime: one `ReceiveBinding` per gate (as in OSC). `accept` matches kind, channel and number; the worker writes the kind's outlets plus `channel` and `from_gate`. Statuses name the gate.
- [ ] Tests:
  - `test_outlets_follow_the_kind` (one per kind)
  - `test_channel_and_number_outlets_appear_for_any`
  - `test_receives_note_on_and_off`
  - `test_cc_filter_by_controller`
  - `test_start_value_on_for_cc_off_for_note`
  - `test_two_gates`
  - `test_missing_device_status`
  - `test_save_reload_keeps_ports`

  FAIL → implement → PASS → commit.

### Task 5: MIDI Send node

**Files:** Create `haybale_protokol_midi/nodes/midi_send.py`; Test `tests/midi/test_midi_send_node.py`

**Interfaces:** `@node(label="MIDI Send", menu="protokol/midi", node_type=NodeType.CONTROL)`.
- Configs: the same filter as Receive, with `direction="out"` on the gate picker.
- Ports: inlets per the table; a `channel` or number inlet appears when its filter is "any". Outlets: `next`, `status`.
- Settings: "Only send changes" per gate, as on OSC Send. An out-of-range value is dropped, and the status names the field.
- [ ] Tests:
  - `test_inlets_follow_the_kind`
  - `test_sends_note_to_virtual_port`
  - `test_sends_cc_with_any_controller_inlet`
  - `test_out_of_range_dropped_and_named`
  - `test_only_send_changes_per_gate`
  - `test_two_gates`

  FAIL → implement → PASS → commit.

### Task 6: Editors with MIDI, end to end, docs, PR

- [ ] Tests:
  - `test_device_editor_maps_a_midi_port`: the device picker lists virtual ports, and an unbound gate binds and opens.
  - `test_gate_form_offers_devices_for_midi`
  - `test_monitor_test_send_midi` (with `parse_test_message`)
  - `test_receive_to_send_through_virtual_ports`, end to end: graph Receive (cc) → Send (cc), with the gates bound to two virtual ports.
- [ ] NOTES for the MIDI haybale: Devices, kinds, test-message forms. Regenerate docs; full suite, ruff, mypy.
- [ ] Rebase onto `master` if PR #2 is merged; push; open a PR to `master`.
- [ ] Note for the owner: the umbrella's `pyproject.toml` lists the protokol haybales for `bin/haywire-studio`. `haybale-protokol-midi` must be added there to load in the studio, and that's the owner's file.

## Deferred

- Hot-plug notification (a Device appearing or vanishing while running): the Device editor polls `list_devices` when drawn; there is no live watch.
- MIDI clock generation (a clock source node), MPE, and NRPN/RPN as a kind.
- Plan 3's deferred minors stay in the cleanup slice.
