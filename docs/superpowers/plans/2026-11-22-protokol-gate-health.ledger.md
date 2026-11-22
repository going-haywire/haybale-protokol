# Ledger — plan: docs/superpowers/plans/2026-11-22-protokol-gate-health.md

Owner approved Plan 4b (2026-11-22, #18 merged by request). Branch plan-4b-gate-health from master eb065bb.
Task 1: Ruling: the unbound reason keeps the existing text "unbound gate: no device 'x' on this machine" (node statuses, NOTES and editor tests use it), not the plan table's shorter form — cost if wrong: none.
Task 1: Ruling: an open failure is not remembered while the gate's Device is absent — health already says "not plugged in", and the failure must not turn the gate "error" after the replug — cost if wrong: none.
Task 1: complete (commit 6b55c7b, tests: 603 passed; ruff, mypy clean)
Task 2: Ruling: health reads a per-protocol cache of the last listing (filled live on first use, refreshed by the watch or refresh_devices), so drawing gate rows never lists ports — cost if wrong: health lags a plug event by up to one interval.
Task 2: Ruling: the watch thread is also the notifier — every _changed() pokes it, and listeners run there outside every lock (never on a Line thread) — cost if wrong: listener calls are coalesced, not one per change.
Task 2: Ruling: a device change forgets the protocol's remembered open failures — a failure seen before an unplug must not outlive the replug — cost if wrong: a real failure shows "closed" until the next open.
Task 2: Ruling: the watch thread runs in a copy of the starting thread's contextvars context — haywire's workspace root is ambient, and the first run failed with "workspace_root not set" in the thread — cost if wrong: none.
Task 2: complete (tests: 616 passed; ruff, mypy clean). MIDI probes verified live on ALSA: a kept MidiIn sees a virtual port appear and vanish.
Task 3: Ruling: an unplugged device's Line is closed at once (by the watch on a presence change, and by a binding that finds its Device gone), never kept for its grace period — on ALSA a port that went away never comes back to the same connection, and a replug inside the grace period would have reused a dead Line — plan gap — cost if wrong: a Monitor tap on that Line closes too (it has no device either).
Task 3: Ruling: each reconnect attempt holds a per-binding lock and re-checks "still waiting, no use yet" first — two attempts once both took the Line and a message was delivered twice in between (seen ~1 in 3 runs) — cost if wrong: none.
Task 3: Ruling: a successful open while the cached listing says the Device is absent, or a failed open while it says present, re-lists that driver at once — the suite's shared state showed a stale cache making a binding close its own working Line — cost if wrong: one extra listing per contradicting open.
Task 3: changed test: test_missing_device_status now expects "waiting for 'keys'" (the node waits for the Device, design §10.5) instead of "cannot open: no MIDI port …".
Task 3: complete (tests: 624 passed x3; ruff, mypy clean). Real ALSA virtual ports: unplug/replug mid-run and start-unplugged both reconnect.
Task 4: Ruling: the badge is a GateBadge object each node owns (start in post_init, refresh on the gate setting's on_change, in on_assembly and at the end of on_startup, stop in on_teardown) — core has on_teardown, so the weak listener is a fallback, not the mechanism — cost if wrong: none.
Task 4: Ruling: a remembered open failure now emits _changed(), so a badge turns "error" as soon as a graph's start fails to open a port — cost if wrong: one extra signal per failed open.
Task 4: note: a notification already under way when unwatch() runs may still call the listener once; GateBadge.refresh is harmless then (no wrapper → nothing).
Task 4: complete (tests: 642 passed x2; ruff, mypy clean)
Task 5: Ruling: the chip follows health with two tones only (success = healthy, danger = anything else); the old "warning" for unbound / protocol not installed becomes danger, as the owner asked for red — cost if wrong: unbound and broken look alike on the chip (the badge says which).
Task 5: note: the widget does not subscribe to ProtokolChanged; it is recoloured when the node card redraws, which replace_warnings triggers exactly when the gate badge changes — to confirm in the live check.
Task 5: complete (tests: 643 passed; ruff, mypy clean)
