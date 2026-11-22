# SDD ledger — plan: docs/superpowers/plans/2026-11-15-protokol-midi.md

Owner approved Plan 4 (2026-11-15); PR #2 merged by request. Branch plan-4-midi from master cf43686.
Pre-flight: T2 decode/encode/parse_test_message/describe consumed by T3 driver and T4/T5 nodes: consistent. T3 MidiDriver consumed by T4-T6 via ProtokolState.use: consistent. Gate picker (protocol midi) and ReceiveBinding/dispatch from Plans 1-3 reused.
Task 1: Ruling: python-rtmidi==1.5.8 / mido==1.3.3 pinned — newer python-rtmidi builds from source and fails on macOS (sem_timedwait in its JACK backend) — cost if wrong: missing newer fixes.
Task 1: complete (commits ..527fed2, tests: uv run --frozen pytest -q → 423 passed; ruff, mypy clean)
Task 1: note: first commit went in with a failing test (chained command only checked the last stage); fixed and amended before any push. Checks now run as separate steps.
Task 2: complete (commits ..05ea29e, tests: uv run --frozen pytest -q → 479 passed; ruff, mypy clean)
Task 3: complete (commits ..0a8c5f7, tests: uv run --frozen pytest -q → 485 passed; ruff, mypy clean). Tests use rtmidi virtual ports (skipped where unsupported).
Task 4: Ruling: haybale-protokol-midi depends on haybale-core (BYTES for sysex/raw outlets), as OSC does — plan gap — cost if wrong: none.
Task 4: Ruling: filter configs are filter_channel / filter_number (labels Channel / Number) — outlets channel/note/controller share the node's port id namespace — cost if wrong: config ids in files.
Task 4: complete (commits ..eff9b94, tests: uv run --frozen pytest -q → 502 passed; ruff, mypy clean)
Owner decision: pin-removal hook (haywire-core ec268a49c, #103) as its own slice after Plan 4 (A).
Task 5: Ruling: SendSettings (Only send changes) moves to haybale_protokol/sending.py, shared by OSC and MIDI Send; bag name and field unchanged so saved values load — cost if wrong: none.
Task 5: Ruling: GateSender (haybale_protokol/gate_sender.py) holds a Send node's gate uses, per-gate only-changes, counters and status; OSC Send moves onto it — one implementation for every protocol's Send — cost if wrong: refactor risk on OSC Send (its tests guard it).
Task 5: Ruling: shared MIDI pin tables -> midi_pins.py; LineUse -> line_use.py; import guard tightened to require component classes from component modules (it let uppercase helpers through) — cost if wrong: none.
Task 5: complete (commits ..a7ae3f4, tests: uv run --frozen pytest -q → 522 passed; ruff, mypy clean)
Task 6: note: editor/end-to-end tests passed on first run (no new code; they verify Tasks 1-5 through the editors and a graph).
Task 6: complete (commits ..c90c942, tests: uv run --frozen pytest -q → 526 passed; ruff, mypy clean)
Final review: opus reviewer, verdict "no" -> 1 Critical (#1 close deadlock), Important #2 (unplugged device looks healthy), #3 (Auto Drop shares one slot across controllers/addresses/gates), #4 (Block overflow drops newest, e.g. stop behind clocks); #5 (Linux/Windows port names) -> owner; list_devices unguarded re-graded Minor->Important (Device editor fails without a MIDI backend).
Final: fixed #1 close deadlock (polling thread; port closed by its reader) — test_open_close_under_a_stream_never_hangs RED (process hung) -> GREEN x4, suite 534/534
Final: fixed #2 unplugged device — test_an_unplugged_input_says_so_and_a_new_use_reopens, test_an_unplugged_output_drops_and_says_so RED->GREEN, suite 534/534
Final: fixed #3 Auto Drop only for a single source (MIDI and OSC) — test_resolve_dispatch_drops_only_for_a_single_source, test_auto_drops_only_for_one_controller_on_one_gate, test_auto_drops_only_for_one_exact_address_on_one_gate RED->GREEN; formerly flaky OSC two-gates test 3/3 green
Final: fixed #4 Block overflow drops the oldest — test_block_overflow_keeps_the_newest RED->GREEN
Final: fixed list_devices without a backend — test_listing_devices_without_a_midi_backend_is_empty RED->GREEN
Final: Ruling: inputs poll rtmidi every 1 ms on their own thread instead of rtmidi's callback — the callback design deadlocks on close (reviewer probe, our test) — cost if wrong: up to 1 ms extra latency, ~1000 wakeups/s per open input.
Final: minor (deferred): the filter applies at once mid-run while queue mode/Start value stay from start
Final: minor (deferred): Channel/Number have no range check on Receive (silently never fires); Send truncates 3.7 to 3 and type errors lack the field name
Final: minor (deferred): no split-sysex test (Windows WinMM splits long sysex into raw pieces)
Final: minor (deferred): rebuilds reset user port order; Send rebuild does not mark_layout_changed
Final: minor (deferred): import guard blind spots (ast.Import of component modules, deeper nesting, missing skin/theme/panel/type bases)
Final: owner chose A for #5 Linux (ALSA appends ' client:port') and Windows (WinMM appends ' index') port names change between boots/plug order, so exact-name Devices break there
Final: fixed #5 (owner chose A) — exact port name first, else the one port equal without the OS-appended suffix (ALSA " client:port", WinMM " index"; none on macOS); two alike devices never match; Device editor shows "now '…'" — tests/midi/test_midi_port_match.py, test_a_changed_alsa_suffix_still_opens_the_port, test_device_seen_under_a_new_name RED→GREEN, suite 544/544
Final: Ruling: the suffix rule is per platform (sys.platform), never a strip of any trailing number — on macOS "IAC Driver Bus 1" would otherwise silently open "IAC Driver Bus 2" — cost if wrong: a Linux/Windows name form other than rtmidi's appended suffix still needs re-mapping
Follow-up (2026-11-22): fixed Channel/Number range (MIDI Event names an impossible filter in status; Send never truncates 3.7 and names the field). Virtual-port tests now run on Linux (ALSA).
