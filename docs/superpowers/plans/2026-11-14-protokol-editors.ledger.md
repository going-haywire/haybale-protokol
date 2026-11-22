# SDD ledger — plan: docs/superpowers/plans/2026-11-14-protokol-editors.md

Owner approved Plan 3 incl. subnet resolution moved to Plan 6 (2026-11-14). Branch plan-3-editors from master a7ec406.
Pre-flight: T1 GateField/gate_fields/parse_test_message/list_devices/uses_devices consumed by T2 (OSC implements), T4 (form), T5 (test-send), T6 (device picker): consistent. T1 Tap/tap/use_gate/line_of/save_gate consumed by T4-T6. T3 ProtokolSelection consumed by T4-T6. T6 adds save_device/delete_device/devices to ProtokolState (own task).
Task 1: Ruling: a tap stores TapEntry(message, direction) instead of extra["direction"] on a copied Message — no per-message copy, Line messages stay untouched — cost if wrong: none.
Task 1: Ruling: Line.add_user(subscriber, *, outbound=None) — one token holds both the inbound and outbound subscriber of a two-way tap — cost if wrong: none.
Task 1: Ruling: gate editing writes one table at a time (write_gate/remove_gate) instead of save_gates of the lenient list, so malformed gates in the file are never dropped by an edit — cost if wrong: none.
Task 1: complete (commits 676f48f..4afd2a3, tests: uv run --frozen pytest -q → 223 passed)
Task 2: Ruling: GateField.applies is a tuple of alternative condition maps (any one matching shows the field) — host/bind each need an OR (udp out | tcp client) — cost if wrong: none (only OSC uses it so far).
Task 2: Ruling: test messages tokenized with a regex: "quoted" is always a string, bare tokens become i/f/T/F/s by form — shlex loses the quoting, so "3" could not stay a string — cost if wrong: none.
Task 2: complete (commits ..2ecd648, tests: uv run --frozen pytest -q → 234 passed)
Task 3: complete (commits ..dc33876, tests: uv run --frozen pytest -q tests/test_selection.py → 2 passed)
Task 4: Ruling: the row's Monitor button lands with the Monitor in Task 5 (the Reveal needs MonitorEditor) — keeps Task 4 green — cost if wrong: none.
Task 4: Ruling: ProtokolState._changed drops the signal when the state is not bound to an app (standalone instances in editor tests) — in the app it is always bound — cost if wrong: none.
Task 4: Ruling: ProtokolState.protocols() lists the registered protocols for the form's protocol select.
Task 4: complete (commits ..20d7aa1, tests: uv run --frozen pytest -q → 248 passed)
Task 5: Ruling: the table's direction column shows in/out as words (not arrows) — readable and exportable alike — cost if wrong: none.
Task 5: Ruling: Export writes every message the filter keeps (all taps' buffers), not only the 300 rows shown — design 5.1: the current filtered buffer — cost if wrong: none.
Task 5: complete (commits ..ae7f536, tests: uv run --frozen pytest -q → 263 passed)
Task 6: Ruling: drivers.list_devices(driver) returns None when the driver cannot list devices (vs () when none are connected), so "not connected" is only claimed by a driver that can tell — cost if wrong: none.
Task 6: complete (commits ..9197e58, tests: uv run --frozen pytest -q → 279 passed)
Task 7: studio started (bin/haywire-studio): all three editors registered, no errors in the log; visual check not done — Chrome extension not connected and the studio requires a login. Left to the owner.
Task 7: complete (commits ..16120a7, tests: uv run --frozen pytest -q → 279 passed)
Task 8 (owner feedback, studio check): Monitor table unreadable (raw ui.table, light default). Design-guide pass: no raw ui.table (html rows with hw-text tokens), hui.editor_toolbar, list rows with hw-list-item-hover/active, 4px scrollbars (design guide 9.4), hui.icon where AppIcon has the meaning.
Task 8: Ruling: protocol-domain icons absent from AppIcon (gates, monitor, device, send, bind, back) live in haybale_protokol/icons.py as one local registry — AppIcon is core (no core changes); propose adding them to AppIcon later — cost if wrong: a later rename.
Task 8: complete (commits ..5c23d14, tests: uv run --frozen pytest -q → 282 passed)
Task 8 fix: owner reported opening Gates breaks every editor. Cause: thumb-style/bar-style strings (design guide 9.4 example) into QScrollArea Object props -> browser exception stops Vue. Fixed in c40dabb with test_scroll_area_passes_no_string_object_props RED->GREEN, suite 283/283.
Task 8: Ruling: keep Quasar's default scrollbar like the rest of the studio instead of a :thumb-style JS-object binding — no haywire code styles scrollbars, and design guide 9.4 is wrong for this Quasar (proposal to owner: fix the guide) — cost if wrong: default scrollbar look.
Task 8 follow-up: owner asked why the fix needed a restart. Cause: 'from haybale_protokol.editors import layout' — core's DependencyGraph records the package, not the submodule, so layout.py had no reverse edge to the editors. Fixed in 78ec002 (full-path imports) with test_helpers_are_imported_by_full_module_path RED->GREEN (3 editors), suite 331/331.
Task 9 (owner feedback): Monitor line toggle no longer closes the tap; visibility icons (hui.icon.shown/hidden) hide/show a line; per-line Clear and Export (JSONL/CSV menu); a per-line "Stop watching" (hui.icon.close) releases the tap, since hiding no longer does. Gates icon -> hui.icon.network.
Task 9: Ruling: toolbar Clear/Export stay and act on all visible lines (merged timeline); per-line ones act on that line only; both respect the text filter — cost if wrong: two extra toolbar buttons.
Task 9: complete (commits ..1a4f2f6, tests: uv run --frozen pytest -q → 335 passed)
Task 10 (owner feedback): hidden lines drop Clear/Export and the active highlight; ui.splitter between lines and output (ErrorsEditor pattern), position kept across redraws.
Task 10: Ruling: the splitter keeps Quasar's default separator, as ErrorsEditor does, rather than the 4px hover strip of design guide 9.5 (which describes the shell's area handles) — consistent with the only splitter in the studio — cost if wrong: separator look.
Task 10: complete (commits ..c658509, tests: uv run --frozen pytest -q → 338 passed)
Task 11 (owner feedback): line rows = one row (eye, name, icons) + status below (layout.list_block); splitter separator-style background var(--hw-separator, var(--hw-border)) — Quasar types separatorStyle as Array|String|Object and passes it as style, so a string is safe (checked in quasar.umd.js).
Task 11: complete (commits ..7abbdf8, tests: uv run --frozen pytest -q → 340 passed)
Task 11 follow-up: owner asked why the 7abbdf8 change did not hot-reload. Cause: helpers layout.py/gate_form.py lived in editors/ (a registry-claimed folder); core's _is_demoted_component treats such a module as a component and re-promotes it to managed instead of reloading it as a helper with its dependents. Moved to package root in c16201d; test_component_folders_hold_only_component_modules RED->GREEN (2), suite 349/349.
Task 12 (owner feedback): Gates rows use editor_layout.list_block: name+tags+icons one row, status full-width below with tooltip. Complete (commits ..d7ced2a, tests: uv run --frozen pytest -q → 350 passed)
Task 13 (owner feedback): eye moved into the icon group (first icon), status line unindented to align with the name. Complete (commits ..41cc92d, tests: uv run --frozen pytest -q → 351 passed)
Task 14 (owner feedback): ArgPins._move_slot_last after each rebuild (Receive after timetag/status, Send after arg pins); descriptions on gate/address/arg_shape (Receive) and gate/arg_shape (Send). Complete (commits ..b2c1d6a, tests: uv run --frozen pytest -q → 357 passed)
Task 15 (owner feedback): OSC Receive always has args (every argument, raw list); shape tokens add typed outlets beside it. Complete (commits ..70bfe7b, tests: uv run --frozen pytest -q → 357 passed)
Task 16 (owner feedback): OSC Send setting 'Only send changes' (SendSettings bag, default off). Ruling: comparison on (address, tags, flattened args) of the last successful send; first tick of a run always sends; dropped sends retried — cost if wrong: none. Complete (commits ..d7a4e31, tests: uv run --frozen pytest -q → 360 passed)
Task 17 (owner request A): several gates per node + chip picker. Ruling: picker options come from widget properties {protocol, direction} resolved by the widget via ProtokolState.gate_choices — port widget_config must be JSON (no callables) — cost if wrong: none.
Task 17: Ruling: Receive outlet naming the source gate is from_gate (config owns id gate).
Task 17: complete (commits ..805243b, tests: uv run --frozen pytest -q → 375 passed)
Task 18 (owner chose B after comparing ModelRefWidget): keep chip select; behaviour driven by plain widget properties (protocol, direction, multiple, typed) like ModelRefWidget; chips coloured by gate status with hw-text tokens; stamp_requires(EDIT).
Task 18: complete (commits ..2bb7b97, tests: uv run --frozen pytest -q → 388 passed)
Owner decision: gate picker stays gate-specific (no generic chip-select/provider registry).
Task 19 (owner screenshot): chips showed {value,label} JSON in danger colour — template used props.opt instead of props.opt.label (NiceGUI option objects). Fixed + quiet chip (--hw-bg-elevated / --hw-text-body) with tone dot. Tests RED->GREEN; complete (commits ..43b6f89, suite 389 passed)
Final review: opus reviewer, verdict "with fixes"; 1 Critical, 2 Important; re-graded to Important: #4 (statuses name gate), #10 (slot left mid-list — owner asked for slot last), #11 (helper in component module — owner's rule), outlet order (declined-to-judge item; visible on every shaped node).
Final: fixed #1 icon clicks bubbled into row selection — test_row_icons_are_outside_the_clickable_area RED->GREEN, suite 402/402
Final: fixed #2/#6 change signals redrew whole editors (dialogs, typed text lost) — test_protokol_changes_never_redraw_the_whole_editor (x3) + test_change_signal_keeps_dialog_and_send_text RED->GREEN, suite 402/402
Final: fixed #3 only-changes per gate — test_only_changes_retries_a_gate_that_failed RED->GREEN, suite 402/402
Final: fixed #4 statuses name the gate — test_statuses_name_the_gate_that_failed RED->GREEN, suite 402/402
Final: fixed #10 slot back to the end after reorder — test_dragging_the_slot_among_the_args_puts_it_back_last RED->GREEN, suite 402/402
Final: fixed outlet order — test_receive_outlets_keep_their_order_with_a_shape RED->GREEN, suite 402/402
Final: fixed #11 gate_status out of a component module — test_no_helper_is_imported_from_a_component_module RED->GREEN, suite 402/402
Final: note: one unexplained single failure in a full run during the fix pass; two further full runs clean (402/402).
Final: minor (deferred): #5 rename/delete drop that gate's comments (and a comment stored above the next gate); a renamed gate moves to the file's end
Final: minor (deferred): #7 VIEW tooltip on a pointer-events-none button never shows
Final: minor (deferred): #8 a VIEW tap can reopen a Line whose grace period ends between check and use, and keeps a grace-period Line open
Final: minor (deferred): #9 gate chips show the remove x even when not editable (clicks are gated)
Final: OPEN for owner: #12 selecting a gate ticks its Monitor source with open_line=can_edit, so a click on a TCP client gate connects to the peer while the Monitor tab exists
Owner decision #12: A — selecting a gate ticks it in the Monitor only when its Line is already open.
Task 20 (owner paste): copied Monitor rows run together (no text separators between columns).
Task 20: complete (commits ..46e9b52, tests: uv run --frozen pytest -q → 404 passed)
Owner decision: Monitor order toggle (C): newest first (default) / oldest first like a log, following the bottom unless scrolled up; ms timestamps.
Task 21: order toggle complete (commits ..55c27e9, tests: uv run --frozen pytest -q → 407 passed)
Follow-up (2026-11-22): fixed #5 (rename rewrites the header in place; delete keeps the next gate's comment)
