# Protokol editors — Implementation Plan (Plan 3 of 6)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the three editors of design §5 and the state they need, so a user sees and edits the project's gates, watches live traffic on Lines, test-sends, exports what they saw, and maps Devices on this machine, without hand-editing TOML.

**Architecture:**
- **`ProtokolState` gains three things:**
  - **Taps:** a Monitor's hold on a Line, with a bounded ring buffer that never blocks the Line.
  - **Gate-file editing:** validated through the driver, keeping comments.
  - **Ad-hoc Lines:** a Line opened from an unsaved Gate.
- **Each Protocol driver describes itself** for the protocol-neutral editors: `gate_fields()` for the gate form, `parse_test_message(text)` for test-send, and `list_devices()` for device pickers. All three are optional; the editors fall back when a driver lacks them.
- **`ProtokolSelection` (a `SessionState`)** is the session's Protokol selection: a gate, a Line, or a Device.
- **The three editors** are NiceGUI `BaseEditor`s in `haybale-protokol`:
  - the **Gates editor** (ACTION),
  - the **Monitor** (EDIT tab),
  - the **Device editor** (CONTEXT).
  They redraw on `ProtokolChanged` and on the selection fields. The Monitor alone polls its taps on a capped `ui.timer`, because messages are far too frequent for signals.

**Tech Stack:** haywire-core UI (`BaseEditor`, `@editor`, `@redraw_on`, `haywire.ui.elements as hui`, `SessionState`/`signal_field`, `AccessTier`), NiceGUI 3, `nicegui.testing.user_simulation` for tests.

**Spec:** [docs/design.md](../../design.md) §3.2–3.3, §5, §5.1; glossary terms. Builds on `master` (Plans 1–2). Canon: `../haywire-repo/docs/components/editors/editor-canon.md`, `…/states/state-canon.md`, `…/guides/signals.md`.

## Global Constraints

- All earlier constraints hold: no haywire-repo changes or links, `uv run --frozen`, glossary terms, no ADRs, statuses instead of errors.
- **Do not import `GraphAppState` / `haybale_graph_editor.state…`.** Plan 3 needs neither: OSCQuery comes in Plan 6.
- **Access tiers (design §5):**
  - Seeing everything and watching Lines that are already open is **VIEW**.
  - Editing gates, opening Monitor Lines, test-sends and "Save as gate…" are **EDIT**.
  - Editing the Device list is **ADMIN**.
  - Editors declare `requires=AccessTier.VIEW` and gate their own actions with `context.can_edit()` / `context.can_admin()`.
- **Slots:** the Gates editor is ACTION, `opens="required"`. The Monitor is EDIT, `opens="on_context"`, opened from the Gates editor by `Reveal`. The Device editor is CONTEXT, `opens="required"`.
- **The Monitor never slows a Line.** A tap's subscriber only appends to a bounded `deque`. When the deque is full the oldest message drops and is counted. Drawing is capped at `MONITOR_REFRESH_S = 0.2`.
- **Editors learn of changes only through signals:** `ProtokolChanged` and the `ProtokolSelection` fields. The Monitor's timer reads tap buffers only.
- **No NiceGUI from `on_enable`;** no UI calls from Line threads.
- **Branch `plan-3-editors`** from `master`, one commit per task. At the end, push the branch and open a PR to `master`; the owner merges it.

## Review Focus

1. **A burst of thousands of messages a second on a tapped Line.** Expect the UI to stay responsive (it draws at most every 0.2 s, at most `MONITOR_ROWS` rows), the Line not to slow down, and the drop count to show. → Task 1 `test_tap_never_blocks_and_counts_drops`; Task 5 `test_monitor_draws_a_bounded_window`.
2. **Editing a gate while graphs use it.** Expect the file to be written with its comments kept; running nodes keep their Line until their next start. The editor says so: "applies when its users restart". → Task 1 `test_save_gate_keeps_comments_and_signals`; Task 4 `test_edit_hint_when_line_in_use`.
3. **An invalid gate in the form** (missing port, bad host, framing clash). Expect the dialog to stay open showing the driver's message, and nothing written. → Task 1 `test_save_gate_validates_through_driver`; Task 4 `test_invalid_gate_keeps_dialog_open`.
4. **A VIEW-only session.** Expect it to see everything and tap open Lines. It gets no add/edit/delete, no test-send, no opening closed Lines, and no Device-list edits; the controls are hidden. The state methods do not check access themselves: the editors gate them. → Tasks 4–6 `test_view_only_*`.
5. **Closing the Monitor tab, or a session ending, while taps are open.** Expect every tap released, so Lines close after the grace period, and no timer left running. → Task 5 `test_closing_monitor_releases_taps`.

---

### Task 1: State for editors — taps, ad-hoc Lines, gate editing

**Files:**
- Modify: `barn/haybale-protokol/haybale_protokol/states/protokol_state.py`, `drivers.py`, `gates.py`
- Create: `barn/haybale-protokol/haybale_protokol/taps.py`
- Test: `tests/test_taps.py`, `tests/test_gate_editing.py`

**Interfaces (produces):**
- `drivers.py`, optional driver features, all read with `getattr` so a driver may omit them:
  - `@dataclass(frozen=True) class GateField: key: str; label: str; kind: Literal["text", "int", "choice"]; default: Any = None; choices: tuple[str, ...] = (); applies: Mapping[str, tuple[Any, ...]] = field(default_factory=dict)`. A field applies only when, for each `applies` key, the gate's value for that key is in the tuple; for example `bind` applies to `{"direction": ("in", "two-way")}` or `{"role": ("server",)}`.
  - `ProtocolDriver.gate_fields() -> Sequence[GateField]`
  - `ProtocolDriver.parse_test_message(text: str) -> Message` (raises `ValueError` naming the problem)
  - `ProtocolDriver.list_devices() -> Sequence[tuple[str, str]]` (`(os_id, description)`)
  - `ProtocolDriver.uses_devices: bool` (default False)
- `taps.py`: `class Tap` with `messages() -> list[Message]` (a copy, oldest first), `dropped: int`, `received: int`, `clear()`, `close()` (idempotent; gives back its `LineUse`), `use: LineUse`, and `paused: bool` (while paused, messages are counted but not kept). `MONITOR_BUFFER = 2000`.
- `ProtokolState`:
  - `use_gate(gate: Gate, direction, subscriber=None) -> LineUse | str`. This is the body of today's `use()`, which keeps its signature and resolves the name first. Ad-hoc gates go through here.
  - `tap(gate: Gate, *, open_line: bool) -> Tap | str`. With `open_line=False`, it only taps a Line that is already open (VIEW), else returns `"line not open"`. It uses direction `"in"` for in/two-way gates and `"out"` for output gates, and records what this side sends (see below).
  - `line_of(gate: Gate) -> Line | None`: the open Line a gate resolves to, without opening it.
  - `save_gate(gate: Gate, *, replaces: str | None = None) -> str | None`: validates through `driver.line_key` (a `ValueError` becomes the returned message), plus name rules (`[A-Za-z0-9._-]+`, unique unless `replaces`). Writes through `save_gates`, keeping comments and the other gates. Returns `None` on success and calls `_changed()`. A gate whose protocol has no driver is saved unvalidated.
  - `delete_gate(name: str) -> None`.
- **Outgoing messages in taps.** `Line.send` also hands each message it sent to the Line's "outbound" subscribers, so a tap on an output gate shows what the graph sends. That means `Line.add_user(subscriber, *, outbound: bool = False)`. A tap subscribes with `outbound=True` on output Lines. Two-way taps get both directions, and messages carry `extra["direction"] = "in" | "out"`.

- [ ] Tests, `test_taps.py` (FakeDriver):
  - `test_tap_collects_and_keeps_order`
  - `test_tap_never_blocks_and_counts_drops`: 10 000 pushes in under 0.5 s; buffer length equals `MONITOR_BUFFER`; `dropped == 8000`.
  - `test_tap_view_mode_needs_open_line`
  - `test_tap_close_releases_line`
  - `test_paused_tap_counts_but_keeps_nothing`
  - `test_outbound_messages_reach_taps_marked_out`
  - `test_tap_on_ad_hoc_gate_opens_line`
- [ ] Tests, `test_gate_editing.py`:
  - `test_save_gate_validates_through_driver`
  - `test_save_gate_keeps_comments_and_signals`
  - `test_rename_replaces_old_entry`
  - `test_duplicate_name_refused`
  - `test_bad_name_refused`
  - `test_delete_gate`
  - `test_unknown_protocol_saved_unvalidated`
- [ ] FAIL → implement → PASS → commit.

### Task 2: OSC driver describes itself

**Files:** Modify `barn/haybale-protokol-osc/haybale_protokol_osc/driver.py`; Test `tests/osc/test_driver_describe.py`

**Interfaces:**
- `OscDriver.gate_fields()`:
  - `transport` choice `udp`/`tcp`
  - `role` choice `client`/`server`, applies to tcp
  - `host` text, applies to udp out and tcp client
  - `port` int
  - `bind` text, default `0.0.0.0`, applies to udp in and tcp server
  - `framing` choice `1.1`/`1.0`, applies to tcp
- `OscDriver.parse_test_message("/fader/1 0.5 3 hello T")`:
  - becomes `Message("/fader/1", (0.5, 3, "hello", True), now, {"types": "fisT"})`;
  - `"…"` quotes a string containing spaces;
  - a bad address raises `ValueError`.
- `OscDriver.uses_devices = False`; it has no `list_devices`.
- [ ] Tests: `test_gate_fields_cover_every_option` (each field key is accepted by `line_key`), `test_fields_apply_by_transport_and_role`, `test_parse_test_message_types`, `test_parse_quoted_string`, `test_parse_rejects_bad_address`. FAIL → implement → PASS → commit.

### Task 3: Protokol selection

**Files:** Create `barn/haybale-protokol/haybale_protokol/states/protokol_selection.py`; Test `tests/test_selection.py`

**Interfaces:** `@state(label="Protokol selection") class ProtokolSelection(SessionState)`:
- signal fields: `gate: str | None`, `line: LineKey | None`, `device: str | None`;
- methods `select_gate(name)`, `select_line(key)` and `select_device(name)`, each clearing the other two;
- `clear()`.
- [ ] Tests: `test_selecting_one_clears_others`, `test_selection_is_registered_per_session` (library_system: `LibraryStateRegistry` knows the class as a session state). FAIL → implement → PASS → commit.

### Task 4: Gates editor (ACTION)

**Files:** Create `barn/haybale-protokol/haybale_protokol/editors/gates_editor.py`, `barn/haybale-protokol/haybale_protokol/editors/gate_form.py` (the dialog, built from `gate_fields`); Test `tests/editors/test_gates_editor.py`

**Interfaces:** `@editor(label="Gates", icon="cable", default_slot=SlotName.ACTION, requires=AccessTier.VIEW, description="The project's gates and their Lines")`.

- **Rows.** One row per gate: name, protocol and direction tags, and a status line taken from:
  - `gate_errors`,
  - "protocol not installed",
  - "unbound gate: …",
  - the open Line's `status` with `· n users`,
  - or "closed".

  A gate-file error shows once, at the top.
- **Clicking a row** sets `ProtokolSelection.select_gate(name)`.
- **EDIT actions:**
  - **Add** (header button) and **Edit** (row button): the form dialog (name, protocol select from the registered drivers, direction, device select when `uses_devices`, then the driver's `gate_fields` filtered by `applies`). Save calls `save_gate`; an error shows in the dialog and keeps it open. When the gate's Line is in use, the hint reads "applies when its users restart".
  - **Delete**, with a confirm step.
  - **Monitor** (row button): `select_gate`, then `Reveal(editor=MonitorEditor)`.
- **Unbound gates** get a "Bind…" button that selects the device (`select_device(gate.device)`), so the Device editor can map it.
- **Redraws** on `ProtokolChanged`, `ProtokolSelection.gate`, `ProtokolSelection.line` and `ProtokolSelection.device`.
- [ ] Tests (user_simulation, a real `ProtokolState` with `FakeDriver`, a context stub whose `app_data`/`data` return them):
  - `test_requires_view`
  - `test_rows_show_status_kinds` (installed/not installed/unbound/open/closed/file error)
  - `test_row_click_selects_gate`
  - `test_add_gate_writes_file`
  - `test_invalid_gate_keeps_dialog_open`
  - `test_edit_hint_when_line_in_use`
  - `test_delete_gate_after_confirm`
  - `test_view_only_has_no_edit_controls`
  - `test_bind_selects_device`
- [ ] FAIL → implement → PASS → commit.

### Task 5: Monitor (EDIT tab)

**Files:** Create `barn/haybale-protokol/haybale_protokol/editors/monitor_editor.py`, `barn/haybale-protokol/haybale_protokol/monitor_export.py`; Test `tests/editors/test_monitor_editor.py`, `tests/test_monitor_export.py`

**Interfaces:** `@editor(label="Monitor", icon="monitor_heart", default_slot=SlotName.EDIT, opens="on_context", requires=AccessTier.VIEW, description="Live traffic on Lines")`.

- **Taps.** One per selected source, held in the editor instance (`_taps: dict[str, Tap]`, keyed by gate name or `~<line key>`).
- **Sources.**
  - The toolbar lists the project's gates and the open Lines; ticking one opens a tap. An unticked source that would need its Line opened is only offered with EDIT. A VIEW session sees "open" sources only.
  - **"New line…"** (EDIT) builds an ad-hoc gate with the same form as the Gates editor, minus the name. It is tapped under `~<line key>`. The tap's header shows **"Save as gate…"**, which opens the gate form prefilled.
  - **Selection drives it.** On `ProtokolSelection.gate`/`.line`, the editor ticks that source.
- **Filter.** A text field matched against `driver.describe(message)` (substring, case-insensitive), and per-source toggles.
- **View.**
  - A table of the newest `MONITOR_ROWS = 300` filtered messages across ticked taps, newest first.
  - Columns: time (`HH:MM:SS.mmm`), source, direction, description.
  - Per-tap counters (received, dropped).
  - Pause and Clear.
- **Refresh.** A `ui.timer(MONITOR_REFRESH_S)` redraws only the table and the counters, and only when something changed (a received-count check).
- **Export… (VIEW):** `monitor_export.to_jsonl(rows)` and `to_csv(rows)`, with columns `time, source, direction, address, args, description`. Delivered through `ui.download` as `protokol-monitor-<timestamp>.<ext>`.
- **Test-send row (EDIT).** One per ticked output or two-way source: a text field parsed by `driver.parse_test_message`, and a Send button. Errors show inline. It sends through a `use_gate(gate, "out")`, held while the row exists. Without `parse_test_message`, the row says "test-send not available for <protocol>".
- **Releasing taps.** `cleanup()` and `handle_close_request()` close every tap and stop the timer, as does unticking a source.
- [ ] Tests:
  - `test_requires_view`
  - `test_monitor_draws_a_bounded_window` (5000 messages → 300 rows)
  - `test_filter_matches_description`
  - `test_view_only_cannot_open_closed_lines`
  - `test_view_only_taps_open_line`
  - `test_test_send_reaches_fake_connection`
  - `test_test_send_error_inline`
  - `test_new_line_and_save_as_gate`
  - `test_selection_ticks_source`
  - `test_closing_monitor_releases_taps`
  - `test_export_jsonl_and_csv_round_trip` (unit, in `test_monitor_export.py`)
- [ ] FAIL → implement → PASS → commit.

### Task 6: Device editor (CONTEXT)

**Files:** Create `barn/haybale-protokol/haybale_protokol/editors/device_editor.py`; Modify `barn/haybale-protokol/haybale_protokol/states/protokol_state.py` (`devices()`, `save_device(device, replaces=None) -> str | None`, `delete_device(name)`, all through the Device list with `_changed()`); Test `tests/editors/test_device_editor.py`, `tests/test_device_editing.py`

**Interfaces:** `@editor(label="Device", icon="usb", default_slot=SlotName.CONTEXT, requires=AccessTier.VIEW, description="The device or Line in the Protokol selection")`.

- **Nothing selected:** the Device list, one row per Device: name, protocol, OS id, and "not connected" when the protocol's `list_devices()` doesn't contain its OS id.
- **`device` selected:**
  - its details;
  - **ADMIN:** edit the name and OS id (a select from `list_devices()` plus free text), or delete;
  - for a gate's missing device name: **"Map device…"** (ADMIN), creating the entry.
- **`gate` selected:** the gate's options (read-only here; editing belongs to the Gates editor), its Line's status and users, and the Line cache (the last message per key, described by the driver).
- **`line` selected:** the Line's key, status, users and cache.
- **Redraws** on the selection fields and `ProtokolChanged`.
- **State tests:** `test_save_device_and_rename`, `test_duplicate_device_refused`, `test_delete_device`.
- **Editor tests:**
  - `test_requires_view`
  - `test_shows_device_list_by_default`
  - `test_gate_selection_shows_line_and_cache`
  - `test_map_unbound_device_admin_only`
  - `test_view_only_cannot_edit_devices`
  - `test_device_not_connected_hint` (FakeDriver with `list_devices`)
- [ ] FAIL → implement → PASS → commit.

### Task 7: In the studio, docs, PR

- [ ] Start the studio from this checkout. Use the umbrella's `bin/haywire-studio` if it works from here; otherwise `uv run --frozen haywire-studio`, checking `--help` first. Then:
  - check that the Gates editor appears in ACTION, the Device editor in CONTEXT, and that the Monitor opens from a gate;
  - add a UDP gate in the form;
  - tap it and send it OSC from a terminal (`python -c` with `SimpleUDPClient`);
  - test-send to an output gate;
  - export.

  Report what was seen, with screenshots if the browser tools are available. Anything broken becomes a fix with a test.
- [ ] Update both NOTES.md files: the editors, the access tiers, Monitor limits. Regenerate docs. Full suite, `ruff`, `mypy`.
- [ ] Push `plan-3-editors` and open a PR to `master` with a summary and the test plan. Do not merge.

## Deferred

- Discovery (MIDI ports and gamepads come with their drivers in Plans 4–5; ArtPoll, OSCQuery browsing and advertising in Plan 6), Art-Net in the Monitor (Plan 6).
- A continuous Monitor log file and replay (design §7.5).
- Gate stores a subnet, interface follows (design §3.2). The gate form takes a literal `bind`; subnet resolution needs the interface list, so it is planned in the same slice as discovery (Plan 6).
- Plan 1/2 deferred minors stay in the cleanup slice.
