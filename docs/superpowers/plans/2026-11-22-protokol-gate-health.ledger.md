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
