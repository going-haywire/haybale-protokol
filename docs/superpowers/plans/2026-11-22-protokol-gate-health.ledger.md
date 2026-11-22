# Ledger — plan: docs/superpowers/plans/2026-11-22-protokol-gate-health.md

Owner approved Plan 4b (2026-11-22, #18 merged by request). Branch plan-4b-gate-health from master eb065bb.
Task 1: Ruling: the unbound reason keeps the existing text "unbound gate: no device 'x' on this machine" (node statuses, NOTES and editor tests use it), not the plan table's shorter form — cost if wrong: none.
Task 1: Ruling: an open failure is not remembered while the gate's Device is absent — health already says "not plugged in", and the failure must not turn the gate "error" after the replug — cost if wrong: none.
