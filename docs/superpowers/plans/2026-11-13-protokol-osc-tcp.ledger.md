# SDD ledger — plan: docs/superpowers/plans/2026-11-13-protokol-osc-tcp.md

Owner approved Plan 2 incl. gate keys role/framing (2026-11-13). Branch plan-2-osc-tcp from 1e00248.
Ruling: ledger kept by hand (task-start/task-done/sdd-workspace scripts no longer installed); same format — cost if wrong: none.
Pre-flight: T1 framing (encode_frame, FrameReader, FrameError) consumed by T3/T4: consistent. T2 Line.gate + line_options consumed via ProtokolState.use: consistent. T3/T4 reuse Plan 1 _split/build_message: consistent.
Task 1: complete (commits 1e00248..4594fb4, tests: uv run --frozen pytest -q tests/osc/test_framing.py → 10 passed)
Task 2: Ruling: OscDriver.open raises ValueError for tcp keys until Tasks 3/4 add the connections — keeps each task green — cost if wrong: none.
Task 2: folded Plan 1 minor #15 (bind/host must be text) via _text_option.
Task 2: complete (commits ..3bb196e, tests: uv run --frozen pytest -q → 173 passed)
Task 3: Ruling: the backoff wait comes before the first reconnect attempt after a lost connection (0.5 s), and the status counts failed or lost connections since the last good one — cost if wrong: half a second slower to reconnect.
Task 3: complete (commits ..7b1ebe5, tests: uv run --frozen pytest -q → 182 passed)
Task 4: complete (commits ..67de70a, tests: uv run --frozen pytest -q → 193 passed)
Task 5: note: end-to-end tests passed on first run (no new node code in this task; they verify Tasks 1-4 through the nodes).
Task 5: folded Plan 1 minor #10 (NOTES wording on shared Lines).
Task 5: complete (commits ..9ec18ed, tests: uv run --frozen pytest -q → 198 passed)
Final review: opus reviewer, verdict "with fixes"; 1 Critical, 2 Important; #4 re-graded Minor->Important (Send nodes in different flows run on different threads, so concurrent sends on one server gate can corrupt frames).
Final: fixed #1 invalid SLIP escape killed client thread — test_invalid_slip_escape_is_a_frame_error, test_invalid_slip_escape_reconnects RED->GREEN, suite 205/205
Final: fixed #2 server re-listen EADDRINUSE after peers — test_restart_on_same_port_after_peers RED->GREEN, suite 205/205
Final: fixed #3 silent peer never detected — test_client_socket_has_keepalive, test_peer_sockets_have_keepalive RED->GREEN, suite 205/205
Final: fixed #4 concurrent server sends interleave — test_concurrent_sends_do_not_interleave RED->GREEN, suite 205/205
Final: Ruling: keepalive 5 s idle, 2 s interval, 3 probes (~11 s to notice a dead peer); SO_REUSEADDR only on POSIX (on Windows it would allow port hijacking) — cost if wrong: detection speed / Windows re-listen delay.
Final: minor (deferred): #5 a stalled peer blocks one send for 0.2 s then is dropped (documented in NOTES)
Final: minor (deferred): #6 hostname lookup not bounded by connect timeout; close() may return before the thread exits
Final: minor (deferred): #7 IPv6: sockets are AF_INET only; bracketed hosts retry forever without a hint
Final: minor (deferred): #8 changing a gate's framing within the grace period reuses the old framing silently; Line.gate can name a deleted gate
Final: minor (deferred): #9 "reconnecting (1)" shown for a peer never reached
