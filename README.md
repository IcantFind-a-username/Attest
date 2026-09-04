# attest

Attest is an experimental, evidence-first, LLM-driven code evaluator. Its target is simple
to state and deliberately hard to satisfy:

> Publish only a small number of important defect claims that have a trusted, replayable,
> claim-bound execution certificate; spend model and test budget where it is most likely to
> produce such a certificate; otherwise abstain explicitly.

## Install it in one file

There is exactly one supported way in: **a GitHub Action and a repository Secret.** attest
never touches, stores, transmits or logs your API key — it is read from your own runner's
environment and goes nowhere else. Save this as `.github/workflows/attest.yml`:

```yaml
name: attest pull request review

on:
  pull_request:
    types: [opened, reopened, synchronize]

permissions:
  contents: read
  pull-requests: write

concurrency:
  group: attest-${{ github.event.pull_request.number }}
  cancel-in-progress: true

jobs:
  attest:
    runs-on: ubuntu-latest
    steps:
      - name: Check out pull request
        uses: actions/checkout@v4
        with:
          ref: ${{ github.event.pull_request.head.sha }}
          fetch-depth: 0
      - name: Review pull request
        uses: IcantFind-a-username/Attest@v0.1.0-pilot.1
        with:
          github-token: ${{ secrets.GITHUB_TOKEN }}
          model-api-key: ${{ secrets.ANTHROPIC_API_KEY }}
      - name: Upload attest ledger
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: attest-ledger-pr-${{ github.event.pull_request.number }}-run-${{ github.run_id }}
          path: .attest/ledger.jsonl
          if-no-files-found: warn
```

Then add one secret, in **Settings → Secrets and variables → Actions → New repository
secret**, with the Name exactly `ANTHROPIC_API_KEY` and your Anthropic API key as the value.
`GITHUB_TOKEN` needs nothing — Actions supplies it. That is the whole installation; if the
secret is missing the run stops before any model call and the error says where to put it.

Fork pull requests are skipped before credentials or head code are touched, by design.
A review costs about **$0.22** on average and is hard-capped by `budget-usd` (default
$1.00) — see [`docs/github-action.md`](docs/github-action.md).

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
- **measured so far.** Every row names the per-review budget and the models it ran under,
  because both move every number in it. `S` is the proposal model, `G` the reproduction
  generator. The shipped default budget is **$1.00** as of 2026-09-04 (D-126); it was $0.25
  before, and no row below ran at $1.00 except the last two.

  | what | population, one run each | result | budget | models | date |
  |---|---|---|---|---|---|
  | **held-out defects** | 29 SWE-bench Verified regressions, held-out slice, containers, K=4 ([report](docs/acceptance/2026-09-03-e02-heldout.md)) | **certified 5 of 29**; 5 of the 10 whose environment built | $0.25 | S `claude-sonnet-5` | 2026-09-03 |
  | — supplementary, after the bootstrap fix | the 19 whose environment had failed to build | certified on **10 of 19**, 0 bootstrap failures; reported apart, never merged | $0.60 | S `claude-sonnet-5`, G `claude-opus-5` | 2026-09-03 |
  | **held-out controls** | 39 synthetic controls (test-only and docs-only from the same instances) | **0 false publications** | $0.25 | S `claude-sonnet-5` | 2026-09-03 |
  | **adversarial tests** | 9 held-out cases × 2 constructed adversarial tests | **18 of 18 rejected** by the changed-line binding policy; container re-execution, **no model call** | — | — | 2026-09-03 |
  | **real-traffic corpus, defects** | 19 defect pairs on 3 repositories, D-116 construction ([report](docs/acceptance/2026-09-03-real-traffic-corpus.md)) | **6 of 19 pairs certified (32%)**, 4 of 19 published (21%); 16 receipts, 6 publications standing after the D-124 correction | **$0.60** (not the default) | S `claude-sonnet-5`, G `claude-opus-5` | 2026-09-03 |
  | **real-traffic corpus, controls** | 24 controls from the same repositories | **0 false publications** — but two controls carried real defects, so this population cannot support a false-publication *rate* | **$0.60** | same | 2026-09-03 |
  | **natural null (E-01)** | 20 real commits, one repository | 1 publication, since reclassified to the drawer by D-102 ([report](docs/acceptance/2026-09-03-e01-natural-null.md)) | $0.25 | S `claude-sonnet-5` | 2026-09-03 |
  | **`G-NULL-001a`** | 15 of 58 preregistered qualified null commits, 5 public repositories ([report](docs/acceptance/2026-09-04-g-null-001a.md)) | **1 wrong publication** — the gate **does not pass**, the run stopped under `RISK-CERT-01` on the fifteenth control, and the cause is structural (D-127) | **$1.00** | S `claude-sonnet-5`, G `claude-opus-5` | 2026-09-04 |
  | **shadow (E-04 v1)** | 2 prospective units | 22 candidates, 0 eligible, **0 shadow findings** ([report](docs/acceptance/2026-09-03-e04-prospective-v1.md)) | $0.25 | S `claude-sonnet-5` | 2026-09-03 |
  | **shadow (E-04 v2)** | **100 units** of the owner's most recent traffic, 4 repositories ([report](docs/acceptance/2026-09-04-e04-stratum-v2.md)) | 495 candidates, 129 eligible, **21 receipts, 7 shadow findings, 0 published**; all 7 **unadjudicated** | **$1.00** | S `claude-sonnet-5`, G `claude-opus-5` | 2026-09-04 |
  | **outside repository, in production** | **1** pull-request comment on a repository this project does not develop in ([report](docs/acceptance/2026-09-04-us-stock-helper-action-comment.md)) | the Action installed at `@v0.1.0-pilot.1`, built the container on a GitHub runner, ran a reproduction and **posted one comment — a `DEFER`** | **$0.60** | S `claude-sonnet-5`, G `claude-opus-5` | 2026-09-04 |

  Read every row with its limits. A silence is an abstention, never a true negative; a
  reverse-fix corpus is not natural pull-request traffic; `Attest`'s own repository appears in
  the corpus and shadow populations and is a **disclosed conflict of interest**; and the
  earlier dev-slice figures are a development record, not a claim.
- **the product publishes false claims, and one has been measured.** On 2026-09-04 a properly
  qualified null control published a defect claim about a change its author made deliberately
  and documented in the same diff (D-127,
  [report](docs/acceptance/2026-09-04-g-null-001a.md)). The receipt was mechanically perfect —
  head fails, base passes, changed lines executed, bundle verifies. **Every rule in the chain
  asks whether the behaviour changed and whether the change is bound to the diff; only one
  narrow rule (D-102) asks whether the author meant it, and it covers new rejections only.** An
  intended change of a returned value is invisible to every discriminator the product owns. The
  earlier "0 false publications" rows above are counts on their own populations, not a rate, and
  they do not survive this as a general claim.
- **the evidence bundles are not all verifiable.** 86 bundles on this host were re-verified on
  2026-09-04: **44 accept, 42 do not** ([report](docs/acceptance/2026-09-04-bundle-reverification.md)).
  Four carried a `test_repro.py` that was not the test the runs executed — one of them
  published — and are fixed at the source, with certification now verifying its own bundle
  before anything is author-visible (D-124). The other 38 fail for **schema drift**: they
  predate fields the receipt has since grown. That is an accepted trade (`INV-VERSION-001`),
  and it means the headline claim decays every time the receipt schema moves.
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
  regressions unchanged);
- `docs/acceptance/2026-09-04-bundle-reverification.md` — every evidence bundle on the
  development host re-verified, with the four that a published claim rested on;
- `docs/acceptance/2026-09-04-family-per-change-unit.md` — the publication family recomputed
  over the whole corpus, old rule against new, with the control condition that decided it;
- `docs/acceptance/2026-09-04-e04-stratum-v2.md` — 100 shadow units, 7 findings, none shown to
  anyone and none adjudicated;
- `docs/acceptance/2026-09-04-mainline-six-conditions.md` — the release conditions read one by
  one, and why no `v0.1.0-pilot.2` was cut.

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
