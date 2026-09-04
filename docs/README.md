# Documentation map

This directory separates current design authority from historical evidence. A coding
agent must not infer the current plan from an old acceptance report or implementation
plan.

## Normative documents

Authority is by domain:

| Document | Sole authority |
|---|---|
| [`../AGENTS.md`](../AGENTS.md) | repository authority, safety, work protocol, shortest reading path |
| [`architecture/target-algorithm.md`](architecture/target-algorithm.md) | target product boundaries and invariants |
| [`acceptance/evolution-gates.md`](acceptance/evolution-gates.md) | definitions of done, quantitative thresholds, permitted claims |
| [`roadmap.md`](roadmap.md) | dependency order, current phase/work-order status, progress |
| [`mainline.md`](mainline.md) | working sequence to the product, definition of product, corpus policy, owner-reserved decisions |
| [`implementation/agent-work-orders.md`](implementation/agent-work-orders.md) | implementation method, file seams, RED/GREEN steps, handoff format |
| [`../DECISIONS.md`](../DECISIONS.md) | narrow accepted trade-offs, evidence, consequences, reversal conditions |

The current owner/user instruction outranks repository documents for the task it actually
authorizes. A decision does not silently override an architecture invariant or acceptance
gate: the same change must update the owning normative document. A conflict between active
normative documents is a documentation failure; stop the affected work and repair it.

Code and tests describe the current implementation; they do not override target contracts.
If code contradicts a target contract, record the gap instead of rewriting the contract to
match the bug.

## Operational guides

- [`github-action.md`](github-action.md) documents how the current prototype Action behaves
  and its current safety limitations. It is non-normative: target architecture and release
  gates override its implementation-era usage instructions.
- the dated handoffs are SHA-bound records of one window each; the newest is
  [`overnight-handoff-2026-09-05b.md`](overnight-handoff-2026-09-05b.md) (`attest.intent.v4.1`,
  `G-NULL-001a` at n = 58 with 0 wrong publications, the hand adjudication of the drawered value
  class, and the gate-level design), preceded by `overnight-handoff-2026-09-05.md`,
  `overnight-handoff-2026-09-04{,b,c}.md`, `overnight-handoff-2026-09-03{,b,c,d,e,f,g}.md` and the
  older [`overnight-handoff.md`](overnight-handoff.md)
  (`feature/m01-authoritative-outcomes`). A handoff never owns status: roadmap status lives only
  in [`roadmap.md`](roadmap.md).
- `examples/` contains current fixtures/templates, not proof that their path is release-ready.
- `design/` holds **proposals that are not implemented**. A design document owns no contract and
  no gate; it states a shape, names the normative documents it would have to move, and ends with
  the RED that would open the work. [`design/gate-level.md`](design/gate-level.md) is the first
  one: the evidence form for the gate level of `mainline.md` §1.1, unimplemented, and it names
  the `G-NEWCODE-001` conflict it cannot resolve on its own.

## Evidence and historical documents

- [`real-data-evaluation-status.md`](real-data-evaluation-status.md) is a dated historical
  run report. Its banner lists later audit corrections. It is not a current roadmap.
- [`acceptance/README.md`](acceptance/README.md) defines the report/evidence format;
  [`acceptance/phase-3.md`](acceptance/phase-3.md) records two historical integration
  smoke runs. It is evidence, not a general statistical guarantee.
- [`superpowers/plans/README.md`](superpowers/plans/README.md) is the archive index.
  [`superpowers/plans/2026-08-29-phase-3-action.md`](superpowers/plans/2026-08-29-phase-3-action.md)
  and
  [`superpowers/plans/2026-08-29-real-data-evaluation.md`](superpowers/plans/2026-08-29-real-data-evaluation.md)
  are completed historical implementation plans. Some requirements in them intentionally
  describe behavior that the evolution roadmap now replaces.
- `benchmarks/attest-v1/` is a frozen corpus record. A hash-consistent receipt proves
  consistency of committed files, not independent authenticity or semantic correctness.
- `DEVSPEND.md` is the development-call cost ledger, not a product-cost benchmark.

## Anti-drift rule

Each fact has one owner:

| Fact | Canonical owner |
|---|---|
| Standing agent rules and current implementation warning | `AGENTS.md` |
| Target component boundaries and invariants | `architecture/target-algorithm.md` |
| Phase status and dependency order | `roadmap.md` |
| Exact implementation steps | `implementation/agent-work-orders.md` |
| Quantitative acceptance thresholds | `acceptance/evolution-gates.md` |
| Narrow settled trade-offs | `DECISIONS.md` plus synchronized normative owner |
| Raw historical outcomes | dated evidence/report files |

Other documents should link to the owner rather than copy its full text. When a phase
changes state, update `docs/roadmap.md`; do not update five status summaries. When a
metric changes, update the gate or add a dated result artifact, not both.

## Stable identifiers

- `INV-*` identifies an architecture invariant;
- `GAP-*` identifies a current-to-target implementation gap;
- `F/M/C/V/R/X/S/E/N/L-*` identifies one work order;
- `G-*` identifies one acceptance gate;
- `D-*` identifies a decision; and
- `RISK-*` identifies a roadmap risk.

References use exact IDs. Do not use a prose nickname as the only link between an
invariant, work order, gate, result, and decision.

## Fast reading routes

For implementation:

1. root `AGENTS.md`;
2. `roadmap.md` NOW/first-unblocked work order;
3. that work order's dependencies, files, RED, and traceability row;
4. only its linked `INV-*`/`G-*` sections and decisions;
5. affected source/tests.

For review, read the work order and Gate IDs before the diff. For an empirical study, read
the acceptance gate and frozen protocol before runner code. For an incident or historical
claim, start from the dated evidence bundle and then trace back to code/protocol versions.

## Update triggers

- architecture boundary/invariant changes: architecture + decision + affected gate/work
  order in one change;
- threshold/metric/claim changes: acceptance gate + decision, applied prospectively;
- task/phase status changes: roadmap only, with commit and evidence links;
- implementation-method changes without contract change: work order only;
- new historical observation: a dated evidence report/bundle, never AGENTS;
- spend change: `DEVSPEND.md` only;
- completed old plan correction: visible erratum/archive index, never retroactive checkbox
  rewriting.
