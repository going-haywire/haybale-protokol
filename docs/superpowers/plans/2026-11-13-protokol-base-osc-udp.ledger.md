# SDD ledger — plan: docs/superpowers/plans/2026-11-13-protokol-base-osc-udp.md

Ruling: Phase A (Task 0 + checks 1-6) runs uncommitted on master; branch/commit question goes to the owner at the STOP — plan says ask before every commit, and checks only produce spikes + design.md findings — cost if wrong: one batch commit later instead of per-task commits.
Pre-flight: T9 Line/Connection consumed by T10 (use returns LineUse w/ line) and T12 (Connection.start raises OSError; T10 maps LineOpenError -> "cannot open: ..."): consistent. T11 ReceiveBinding consumes ProtokolState.use(gate,"in",subscriber): consistent. T14 encode returns (tags,args); T17 passes extra={"types": tags}, T12 UdpOutConnection reads extra["types"]: consistent. T16 shape_from_ports used by T17: T16 precedes T17, ok.
Task 0: complete (commits 508a3fa..508a3fa, tests: uv run --frozen pytest -q → 1 passed in 3.12s)
Tasks 1-6: findings written to docs/design.md section 8.1; spikes in scratchpad/spikes. Open for owner: Block mode stalls Line thread (check 1); out-of-range i (check 6); pad test pending (check 2).
STOP: reporting to owner.
Owner decision Q1: event route = CallbackEvent (design 6.1, 8.1, 9 updated).
Owner decision Q2: Block-mode Receive nodes forward through their own thread (design 6.1, 8.1). Affects Task 11 ReceiveBinding.
Owner decision Q3: out-of-range i on Send -> drop + count in status naming arg and suggesting h (design 8.1). Affects Task 14 encode / Task 17.
Owner decision Q4: branch plan-1-base-osc-udp, one commit per task, no per-commit asking, no push.
STOP resolved; Phase B starts.
Task 7: complete (commits 66b8eef..d2ec9b7, tests: uv run --frozen pytest -q tests/test_gates.py → 10 passed in 1.15s)
Task 8: complete (commits d2ec9b7..0b855ee, tests: uv run --frozen pytest -q tests/test_devices.py → 7 passed in 0.92s)
Task 9: complete (commits 0b855ee..03e3a1e, tests: uv run --frozen pytest -q tests/test_line.py → 10 passed in 1.93s)
Task 10: complete (commits 03e3a1e..dc7f682, tests: uv run --frozen pytest -q tests/test_protokol_state.py tests/test_library.py → 13 passed in 11.07s)
Task 11: Ruling: dispatch settings get an "Auto (by message kind)" choice (default) for queue mode and Start value instead of per-class defaults — MIDI has one Receive node whose kind (stream or event) changes at runtime, so class-level defaults cannot follow design 6.1; Drop always uses queue size 1 — cost if wrong: one extra choice in the settings UI.
Task 11: Ruling: ReceiveBinding takes block: bool; Block mode forwards via a per-binding daemon thread with a bounded queue (1024), overflow counted as dropped (owner Q2) — cost if wrong: a binding thread per Block-mode node.
Task 11: complete (commits dc7f682..7f67d93, tests: uv run --frozen pytest -q tests/test_receive_plumbing.py → 11 passed in 1.10s)
Task 12: Ruling: ProtokolState.use maps a driver's ValueError (line_key/open) to status "gate '<n>': <reason>" — a gate's bad options must be a node status, not a crash (design 3.1) — cost if wrong: none, status text only.
Task 12: Ruling: OSC bundles split with own recursion over OscBundle, timetag = innermost bundle's timestamp — python-osc's OscPacket replaces past timetags with now — cost if wrong: timetag semantics for nested bundles.
Task 12: note: OscState.on_enable relies on ProtokolState being enabled first (works with current load order; integration test covers it).
Task 12: complete (commits 7f67d93..c3b2da0, tests: uv run --frozen pytest -q tests/osc/test_udp_driver.py tests/test_protokol_state.py → 27 passed in 4.26s)
Task 13: Ruling: no Line-level exact-address index; each binding's accept compares an exact pattern by string equality (regex only for wildcards) — design 6.2's goal (no regex for exact addresses) holds; an index pays off only with many nodes per Line — cost if wrong: O(nodes) string compares per message.
Task 13: complete (commits c3b2da0..14dbb7a, tests: uv run --frozen pytest -q tests/osc/test_pattern.py → 13 passed in 1.02s)
Task 14: Ruling: shape tokens T and F both mean "a bool" (wire tag follows the value) — a user pasting a type-tag string like TF expects it to parse — cost if wrong: one extra accepted token.
Task 14: Ruling: decode accepts an int for f/d tokens (converted), never a float for i/h — senders often emit 1 for 1.0 — cost if wrong: an int silently read as float.
Task 14: complete (commits 14dbb7a..293da26, tests: uv run --frozen pytest -q tests/osc/test_shape.py → 19 passed in 1.01s)
Task 15: Ruling: the address outlet is id address_out (label Address) — the config port already owns id address — cost if wrong: an outlet id users see only in files.
Task 15: Ruling: config ports (gate, address, arg_shape) with TextWidget commit=True, not a settings bag — they need on_change to rebuild ports and are saved like settings — cost if wrong: not promotable like bag settings.
Task 15: Ruling: event_subscription is recomputed in on_assembly (and post_init) so a dispatch-setting change applies on the next start — cost if wrong: none.
Task 15: Ruling: capture outlets connect/release (hb_resolve_capture, release_pins) tested in Task 16/18 where a node with inlets exists — no inlet node in this repo yet — cost if wrong: capture typing untested until then.
Task 15: note: wrote node before tests; RED shown afterwards by moving the module aside (1 collection error), then GREEN.
Task 15: complete (commits 293da26..57a383e, tests: uv run --frozen pytest -q tests/osc/test_osc_receive_node.py → 16 passed in 5.06s)
Task 17 before Task 16: Ruling: order swapped — Task 16's pin-edit tests need the Send node's growing inlets — cost if wrong: none.
Task 17: Ruling: Send's arg inlets follow the Arg shape (typing it rebuilds them, plus a trailing ADD slot); connecting the slot appends the edge type's token — the shape stays the single source of truth (design 6.2) — cost if wrong: none.
Task 17: Ruling: shape outlet shows the wire type tags sent last (vf3 -> fff) — design: the node shows its resulting shape — cost if wrong: label semantics.
Task 17: Ruling: address is a STRING inlet (default '/') rather than config, so it can be wired — cost if wrong: none.
Task 17: complete (commits 57a383e..b6bcedd, tests: uv run --frozen pytest -q tests/osc/test_osc_send_node.py tests/osc/test_shape.py → 39 passed in 6.09s)
Task 16: Ruling: argument pins get stable ids (arg_<n>, never reused) kept in shape order in the node store; the first typed token takes the empty slot's id — an edge's id contains its port id, so positional ids would detach edges on reorder/removal — cost if wrong: ids in files are not positional.
Task 16: Ruling: deleting the edge that grew a pin removes the pin and its token (release_pins also serves undo of the connect, and core cannot tell the two apart); pins created by typing the shape stay when unplugged — cost if wrong: a user who unplugs a grown pin loses it (undo brings it back).
Task 16: Ruling: reorder via an override of reorder_ports (check 4); skips stay at their positions.
Task 16: OPEN for owner: removing a pin from the pin menu (RemovePortAction -> remove_port) gives the node no hook, so the Arg shape is not rewritten; no test written (plan: stop, proposal; xfail only with owner OK). Options: override rejig in ArgPins (works today, touches a core internal) or propose a core hook.
Task 16: note: ArgPins written before its tests; verified by mutation (no-op shape rewrites -> 4 of 6 fail).
Task 16: complete (commits b6bcedd..1a18639, tests: uv run --frozen pytest -q tests/osc → 89 passed in 6.25s)
Task 18: complete (commits 1a18639..f0ac916, tests: uv run --frozen pytest -q → 143 passed in 7.42s)
Final review: opus reviewer, verdict "with fixes"; 0 Critical, 4 Important (+#5 re-graded Minor->Important: a restart at grace expiry left the node dead with no visible reason).
Final: fixed #1 skip-only stream never shown — test_skips_show_even_when_nothing_fits RED->GREEN, suite 152/152
Final: fixed #2 (guard only) removed pin misaligns outlets — test_removed_pin_is_a_status_not_misaligned RED->GREEN, suite 152/152; real fix still OPEN for owner
Final: fixed #3 re.error escapes / invalid text wedges pin hooks — test_bad_ranges_raise_value_error, test_invalid_text_is_reverted, test_deleting_grown_edge_after_invalid_typing RED->GREEN, suite 152/152
Final: fixed #4 one bad gate disabled all — test_one_bad_gate_leaves_the_others_working RED->GREEN, suite 152/152
Final: fixed #5 use() during Line close — test_use_while_line_is_closing_gets_a_fresh_line RED->GREEN, suite 152/152
Final: Ruling: a rejected Address/Arg shape text is put back to the last one that applied (status says why) — keeps text and pins equal so pin hooks never see bad text — cost if wrong: user's typed text vanishes (status shows it).
Final: minor (deferred): #6 stale Drop subscriber may deliver once after close
Final: minor (deferred): #7 Block close() join 1s while fire may wait 5s
Final: minor (deferred): #8 on_startup does not release a still-held binding (stuck-run case)
Final: minor (deferred): #9 driver re-register / hot reload leaves nodes on a closed Line with stale status
Final: minor (deferred): #10 two binds on one port: first starter wins; NOTES says gates on a port share a Line
Final: minor (deferred): #11 [!x] can match '/'
Final: minor (deferred): #12 non-iterable vector value raises TypeError in Send
Final: minor (deferred): #13 short colour #fff encodes wrong
Final: minor (deferred): #14 host resolved on every send; no SO_BROADCAST
Final: minor (deferred): #15 non-string bind raises TypeError out of use()
Final: minor (deferred): #16 arg_released stash only grows
Final: minor (deferred): #17 empty gate field reads "no gate named ''"
Follow-up (2026-11-22): fixed #11 ([!x] never matches '/'; empty [] / [!] rejected) and #13 (#rgb, #rgba, #rrggbb, #rrggbbaa)
