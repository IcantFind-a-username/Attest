# attest

Attest is an experimental, evidence-first, LLM-driven code evaluator. Its target is simple
to state and deliberately hard to satisfy:

> Publish only a small number of important defect claims that have a trusted, replayable,
> claim-bound execution certificate; spend model and test budget where it is most likely to
> produce such a certificate; otherwise abstain explicitly.

The target architecture separates search from judgment:

```text
Candidate Discovery
  -> Evidence Scheduler/Core (chooses the next model/tool/test action)
  -> Evidence Executors
  -> independent Certification Kernel
  -> PR-level publication policy and presentation
```

Multi-model evaluation is useful for heterogeneous roles—proposal, skepticism, test design,
repair, and causal checking—and for learning marginal value per cost. Agreement is
correlated ranking information, not an independent vote or publication certificate.

## Current status

This repository is a research prototype under active evolution, not a published service.
It currently contains:

- an LLM proposal and candidate pipeline;
- fixed S/T/V ranking/gate machinery and an audit ledger;
- a Python generated-test executor that can run the same reproduction three times on head
  and base in detached worktrees;
- a GitHub composite Action and historical end-to-end smoke fixtures;
- corpus, replay, live-local, stability, baseline, receipt, and synthetic-experiment tools;
- a separate `attest.core` binary-judge research engine.

Important limits:

- the internal ranking score is not a statistical guarantee: it orders candidates for
  verification and never publishes anything by itself;
- Core's `Engine` is not used by the production review path and has not been activated as a
  scheduler;
- “no trusted differential receipt, no publication” is the target contract, but the current
  implementation does not yet enforce it for every configuration and manual path;
- head configuration is not yet cleanly separated from base-owned safety policy;
- current reproduction proves head/base behavioral difference but does not yet provide the
  complete exact-node, semantic/causal, fresh-state, authenticated evidence bundle required
  by the target;
- current process/network guards are best-effort and are not a security boundary for
  untrusted head code;
- the current three-finding setting limits inline layout, not every author-visible summary
  item;
- new-code candidates are typed/classified as an unpriced class and deliberately abstain;
- a head failure raised by a `raise`/`assert` on a changed line is classified as a
  *behavior change*, not a regression, and publishes only when the rejected input occurs in
  the base tree's own tests, fixtures or documentation; otherwise it stays in the drawer as
  "behavior change confirmed, intent unknown" (D-102, 2026-09-03);
- measured so far, each number with its sample and date:
  - **controls:** 0 false publications on 39 synthetic controls (test-only and docs-only
    commits of the held-out SWE-bench Verified slice; one pass, K = 4, containers;
    2026-09-03; [held-out report](docs/acceptance/2026-09-03-e02-heldout.md));
  - **adversarial tests:** 18 of 18 rejected by the changed-line binding policy (9 held-out
    cases × two constructed adversarial tests, container re-execution, no model call;
    2026-09-03; same report);
  - **defects:** certified on 5 of the 10 held-out defects whose environment built, and 5 of
    all 29 (one pass, 2026-09-03; the report's first prose count said 11 and 18 — the result
    files say 10 and 19, see its erratum); the 19 environments that failed to build were
    fixed afterwards and their supplementary run is reported apart from the one-time table,
    never merged into it;
  - **natural null:** 1 false publication on 20 real commits with no known defect (one
    repository, 7 refactor/test-only, 6 docs-only, 7 feature commits; K = 4, $0.25 per PR;
    2026-09-03; [natural-null report](docs/acceptance/2026-09-03-e01-natural-null.md)) —
    a valid receipt for an intended new rejection on an existing constructor, published as
    a defect because the kernel was regression-only (D-100); under D-102 the same receipt
    goes to the drawer ([replay report](docs/acceptance/2026-09-03-d102-intent-replay.md))
    while the 5 held-out regressions still publish;
  - **prospective shadow (E-04, stratum v1):** 0 shadow findings on 2 commits pushed to the
    owner's repositories after the protocol freeze (Attest's own two commits of 2026-09-03;
    22 candidates, none eligible, no reproduction ran; the 23-file commit had 1 of its 13
    change units read at the $0.25 per-unit budget) — a mechanism run, not a population
    estimate ([report](docs/acceptance/2026-09-03-e04-prospective-v1.md));
  - the earlier dev-slice figures are a development record, not a claim;
- historical null, stability, Action, corpus, and synthetic scheduling results are scoped
  observations, not production guarantees.

The next work is therefore not “turn Core on as a voter.” It is to make certification
non-bypassable, make receipts semantically and operationally trustworthy, improve recall
without weakening that kernel, add secretless OS isolation, and only then evaluate Core as
a shadow within-PR evidence scheduler.

See the [target architecture](docs/architecture/target-algorithm.md),
[evolution roadmap](docs/roadmap.md), [agent work orders](docs/implementation/agent-work-orders.md),
and [acceptance gates](docs/acceptance/evolution-gates.md).

## Outcomes

The target product distinguishes:

- **certified** — a trusted receipt passed the kernel and the PR publication policy selected
  the finding;
- **certified but suppressed** — valid receipt, but duplicate/family/cap policy kept it
  private;
- **silent** — no candidate became eligible for publication;
- **DEFER** — generation, execution, policy, security, budget, or infrastructure could not
  produce a decisive trusted result;
- **self-reported** — a human/local bookkeeping observation, not an autonomous certificate.

DEFER is an abstention, not a true negative or evidence of precision. When nothing is
published, finding precision is undefined.

## Local development usage

The current CLI remains available while the receipt-only architecture is implemented:

```text
attest review [--base REF] [--alpha X] [--budget USD] [--k N]
attest verify <finding-id> --reproduced|--not-reproduced
attest feedback <finding-id> --fix|--good|--dismiss
attest stats
```

`attest verify --reproduced` currently updates local legacy gate bookkeeping. Do not treat
it as a trusted differential receipt or include it in autonomous-certification metrics.

BYOK model credentials are resolved through the provider SDK's standard credential chain.
Never expose them to generated tests or project code. Per-repository configuration currently
lives in `.attest.toml`; the evolution roadmap moves safety policy to a trusted base-owned
source. The local ledger under `.attest/` is gitignored.

## GitHub Action

The repository includes a self-installing composite Action and an
[example workflow](examples/pull-request.yml). Read the
[current safety guide](docs/github-action.md) before using it.

The Action is not yet approved for untrusted production deployment. Forks are skipped, and
same-repository head code still runs in a best-effort same-runner boundary. The roadmap
requires a privileged-controller/secretless-executor split and OS-level isolation before an
external pilot.

The historical 60-second acceptance criterion covered the initial status comment from job
start, not completion of differential verification; the current verification deadline can
be longer. No final-review-under-60-seconds claim is made.

## Development

Python 3.11 or newer is required. A typical local setup is:

```bash
python -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/python -m pytest
.venv/bin/python -m ruff check .
.venv/bin/python -m mypy src/attest
```

On Windows, use `.venv\Scripts\python` in place of `.venv/bin/python`. The supported
Gate toolchain is pinned in `requirements-toolchain.lock`; use the current branch's lock
and record exact interpreter/tool versions with every Gate result.

Coding agents start with [AGENTS.md](AGENTS.md). The complete documentation map is
[docs/README.md](docs/README.md). Design decisions are preserved in
[DECISIONS.md](DECISIONS.md); dated reports remain evidence rather than current plans.

## Evidence already in the repository

- `docs/acceptance/2026-08-31-m01-task5-recovery.md` — superseding M-01 / Phase 0
  acceptance with exact dual-Python evidence;
- `docs/acceptance/phase-3.md` — two historical Action integration smoke runs;
- `docs/real-data-evaluation-status.md` — the dated overnight report plus audit errata;
- `benchmarks/attest-v1/` — frozen corpus metadata and a historical hash-bound receipt;
- `DEVSPEND.md` — development API spend ledger;
- `DECISIONS.md` D-020 through D-037 — differential/evaluation history.
- `docs/acceptance/2026-09-03-e02-heldout.md` and `docs/acceptance/2026-09-03-e01-natural-null.md`
  — the held-out and natural-null measurements with their sample sizes and stop conditions;
- `docs/acceptance/2026-09-03-d102-intent-replay.md` — the intent discriminator replayed on
  the eight real receipts (the natural-null publication to the drawer, the five held-out
  regressions unchanged).

Read each with its stated limitations. In particular, hash consistency is not execution
authenticity, a reverse-fix corpus is not natural PR traffic, and an all-abstain result does
not estimate precision.

## Origin

Attest grew out of Corum, a preregistered research project on dependence-aware aggregation
of unreliable reviewers. That project produced an important negative result: aggregation
heuristics and correlated panel agreement did not supply the hoped-for general confidence
guarantee. Attest keeps the useful engineering lessons—explicit evidence purchases,
correlation skepticism, auditability, and abstention—while moving final authority to a
separate executable-evidence certificate.

License: Apache-2.0. Copyright 2026 Franz Xu.
