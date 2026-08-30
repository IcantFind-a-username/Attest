# Review: the evolution scaffold (external branch)

Date: 2026-08-31
Subject: `feature/evidence-scheduler-roadmap` at `bcfd9d8` (scaffold commit
`e52a43b` on baseline `main@c945788`), reviewed from the checkout at
`~/Documents/Codex/2026-08-30/https-github-com-icantfind-a-username/Attest`.
Method: two independent full-document reviews (architecture+gates;
work-orders+roadmap) plus a direct read of the rewritten AGENTS.md and
DECISIONS.md against this repository as ground truth.

## Verdict

**Adopt with amendments.** The scaffold is factually accurate about the current
system to an unusual degree, statistically sounder than our own pre-correction
D-023, internally coherent (all 16 INV-*, 29 G-*, 30 work-order IDs resolve,
dependency graph acyclic), and it correctly downgrades three of our own
overnight phrasings (D-037 "precision held", D-035 generality, D-034's
11.5-33% as simulation-only). It moves no factory constant. It also grants
itself a status only the owner can grant.

## Required amendments

1. **Owner ratification of D-038/D-039/D-044 by name.** They reverse both
   clauses of architecture red line 1 (wealth threshold as sole speech
   authority; cap-as-placement-never-suppression) and D-008's loosen-alpha
   reverse clause, and replace AGENTS.md wholesale. Ground rule 8 and
   continuation priority 5 reserve exactly this to the owner; "accepted" is a
   status the scaffold could not self-assign. The change is loud and
   well-traced - the defect is authorization, not concealment.
2. **Reword D-039.** At factory alpha the S/T direct-surface path is
   arithmetically dead (9 < 10 strictly); the real vector is narrower and real:
   a same-repository PR can carry `.attest.toml` with alpha >= 1/9 and obtain
   unverified inline findings (head-owned config + terminal-skip together).
   That justifies the fix as an integrity tightening for the owner to approve,
   not a "security regression" - the current behaviour is pinned, reviewed
   Task-1 design.
3. **Repair G-SCHED-002.** The +0.25pp noninferiority margin cannot be met at
   its own 300-PR floor even with zero events in both arms (Wilson upper at
   ~150/arm is ~2.5pp; the margin needs ~1,530 PRs/arm). Fix margin, floor, or
   endpoint.
4. **State budget reality.** The empirical gates (G-NULL-001, G-CORPUS-001,
   G-SHADOW-001, G-SCHED-002) and the two-adjudicator kappa requirement imply
   spend and capacity one to two orders of magnitude beyond the remaining
   development cap, and the roadmap never says so; add the budget/capacity
   decision to the owner-decision table.
5. **Re-lane the measured bottleneck.** D-037 ranks reproduction-generation
   robustness and containment-vs-shelling-tests as the blockers; the roadmap
   parks them behind ~5 and ~10 work orders respectively while a certification
   rewrite occupies NEXT. A bounded R-02 (precommitted, non-outcome-aware
   schema repair) plus a minimal D-017-compatible subprocess-profile pilot can
   run after M-01 with publication frozen at factory settings.

Minor: restore append-only handling of docs/acceptance/phase-3.md (it was
edited in place, against the scaffold's own rule); G-SCHED-003 per-family
sensitivity is unpassable at 30/family (declare pooled primary); give the
differential repeat count N a canonical owner; property-test phrasing for
"all allowed alpha values"; a size floor for G-RECALL-001's null slice; X-02
needs its Linux infrastructure scoped as a prerequisite.

## Defects in THIS repository found by the review, and their status

- **Date-bound test**: `test_spend_insertion_is_idempotent_by_run_id_and_updates_total`
  asserted a literal date against a wall-clock stamp; the suite was a snapshot
  that failed the day after it was written. Fixed at `346b7c7` (fixed clock
  injected).
- **Skip-as-pass**: JUnit accounting reads only failures/errors, so an
  all-skipped run (e.g. `pytest.importorskip`) exits 0 and reads as a genuine
  pass - head FAIL + base all-skip could certify as `regression_reproduced`
  (the D-029 class of hole, reopened through skips), and a head-side all-skip
  buys V_FAILED from a test that never executed. Fixed (D-045): a run counts as a pass only if at least one test executed
  un-skipped; an all-skip run defers with "no test executed".

## What the scaffold got right that we should keep regardless of adoption

- Invariant 13 (no outcome-aware retry) as the design constraint on any
  reproduction-generation retry work.
- The D-037 erratum: with zero surfaced findings, precision is undefined - the
  defensible statement is surfaced delivery 0/5 with recorded abstention modes.
- The current-implementation warning list (AGENTS.md section 4 of the scaffold)
  is an accurate gap inventory.
- The one-fact-one-owner documentation rule; our own AGENTS.md is stale in the
  ways the scaffold names.
