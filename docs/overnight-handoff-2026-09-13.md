# Handoff — 2026-09-13 · six phases to `v0.1.0`

Baseline `7483a54` (`main`). Budget for the whole task: **$12**, against a cumulative
$90.01 of the $110 cap. One section per phase, appended as each merges.

---

## Phase 1 — the publication rule

Branch `feature/suppression-sources` · report:
[the score bar is removed](acceptance/2026-09-13-publication-rule.md) ·
decision [D-199](../DECISIONS.md) · **$0.00 of $0.00 reserved**

### The one sentence

**The score bar is gone: a reproduction the kernel accepted now publishes under the cap alone,
which a replay of every recorded ledger turns into +25 findings and −0, with the control side
at +0 under the intent policy in force — and the per-unit multiplicity cap is given up with it,
so the product from here offers the receipt and nothing statistical.**

### 1. Step 1, and the two readings the owner was shown

The 35 bar-suppressed receipts, each resolved to its review's own `(head, merge_base)` and
matched on **both** shas against the committed plans:

| population | suppressions | reviews |
|---|---|---|
| defect | 13 | 7 |
| **control** | **2** | 2 |
| neither (E-04 shadow 14, four-levels 6) | 20 | 8 |

The two control rows are `c02` `1d0af73c3e` and `c04` `33aa333ec0`; their `m_u` of 10 and 5 are
exactly the `m` column the 2026-09-03 real-traffic report prints for those cases, so the
classification does not rest on a sha match. **That reading fails your precondition, and phase 1
stopped on it.** Re-judged under the intent policy the product runs today, both are
`behavior_change` — *"the change states its own intent"* — and never become receipts at all:
**control side 0.** You were shown both and chose to proceed. The zero's denominator is four
control receipts, and no designated control arm has ever run under v4.x code (D-196).

### 2. Step 3, the replay

129 ledgers, 609 `publication_policy` rows, 91 carrying a certified set, **90 of 91 reproducing
their own record and 0 disagreeing**. The one exclusion is the copied external-receipt ledger,
which published 1 of 1 and suppressed nothing, so the rule changes nothing for it.

| population | added | removed | added, restricted to today's intent policy |
|---|---|---|---|
| defect | **+11** | −0 | +1 |
| **control** | **+2** | **−0** | **+0** |
| neither | **+12** | −0 | +5 |
| total | **+25** | **−0** | +6 |

Twenty-five from thirty-five, because **the hard cap and the cluster rule absorb ten** — the
first time the cap has bound anything: the census found it had suppressed 0 of 574 rows. The 25
are **identical, id for id, to the baseline D-182 filed and declined**, computed by a different
script under a differently-worded rule: two implementations agreeing on the same set.

### 3. What moved in the code, and what did not

`PUBLICATION_POLICY_SCHEMA_VERSION` `v3` → `v4`; the bar is computed and recorded, not applied;
`score_bar_applied: false` on every row; `pr_error_bound: 1.0` and
`e_value_validity: "not-applied"`; historical rows replay under their own version's rule and an
unknown version fails closed. **Unchanged:** `alpha`, every likelihood ratio, `k_samples`, the
hard cap, the supported interpreter range, the isolation backend. D-125's and D-174's own
behavioural tests are kept, pinned at `schema_version="attest.publication-policy.v3"` — the
replay rule exercising itself rather than a weakened assertion.

### 4. Also in this phase

- `docs/mainline.md` §5 A now carries the **arithmetic ceiling** as its own paragraph, marked as
  the ceiling *before* the change, and the new rule under it (your default-yes item 1 of the
  2026-09-12b handoff).
- `docs/backlog.md`: **`T` has never fired in 2,589 recorded reviews** — one of three evidence
  channels is dead on every measured path, and nobody has established whether that is
  configuration, pricing or a design conclusion. Free to diagnose. Filed P1.
- `G-CERT-004` amended: this is the first amendment to that gate that *removes* an assertion
  rather than correcting one, and it says so.

### 5. Gates

| | |
|---|---|
| `checks` on the pull request | **2,179 passed, 10 skipped**, 17m58s — success |
| `gates` on `main` after the merge | **2,201 passed, 10 skipped**, 20m58s; **coverage 93.39%** against the 90% kernel floor — success (run `34391843795`) |
| the `attest` self-review on the pull request | pass, 1m26s |
| `ruff` · `mypy` · `git diff --check` | clean |
| paid | **$0.125900** — the self-review the pull request buys, which is also **the first review ever run under D-199's rule**. It read 1 of 17 units, stopped on the discovery share, and published nothing |

Merged at `18:54:14Z`; `main` is green.

---

## Phase 2 — E-04 prospective shadow

Branch `feature/e04-shadow-v3` · report:
[29 pull requests, 0 published, and a zero that means nothing yet](acceptance/2026-09-13-e04-shadow-v3.md) ·
study `benchmarks/studies/e04-prospective-v3` · **$1.793201 of $6.00 reserved**

### The one sentence

**Twenty-nine pull requests ran and none published — but all 24 reproduction attempts died at
`environment bootstrap failed`, so no publication was ever reachable, and a zero over a closed
path is not a safety result.**

### 1. The population, and the estimate that sized it

29 pull requests across the six repositories under the owner's account that are Python-primary
and have at least one pull request; `Sovereign-Founder-OS` (Rust, 64 pull requests) excluded for
language and named. **Five drills excluded before any unit ran**, by a title rule written into
the protocol — a publication on a planted defect is a true positive and may not sit in a
false-publication denominator.

Estimate at the last measured rate ($0.118/case on the 2026-09-12b corpus rebuild; $0.0078–$0.35
on this repository's own self-reviews): 29 × ~$0.12 ≈ **$3.5**, comfortably inside $6.
**Measured: $1.793201**, mean $0.062, largest single review $0.1696. The cap was never
approached and **$4.206799 was released**.

### 2. Result

| | |
|---|---|
| units | **29 of 29** |
| candidates · eligible · attempted | 223 · 33 · 24 |
| certified | **0** |
| **published** | **0** |
| budget-limited units | 11 (179 of 298 change units read) |

One line per pull request is in the report's §2.

### 3. Why the zero is vacuous, diagnosed rather than assumed

Every one of the 24 attempts: `environment bootstrap failed … the image build timed out after
~897 s`. Four observations pin it on the host:

1. `docker run python:3.13-slim` works and reaches PyPI with a `200` — container networking is fine;
2. `ensure_image` with an hour's headroom still fails at the builder's own 1800 s ceiling;
3. a two-line Dockerfile whose base image is **already local** hangs >90 s at
   `#2 [internal] load metadata for docker.io/library/python:3.13-slim`;
4. the build cache holds **77.8 kB** — the failed builds cached essentially nothing.

**Buildkit cannot resolve registry metadata on this host.** The same build takes **27.9 s** on a
GitHub runner, measured on this project's own external receipt. The product did nothing wrong:
all 24 are recorded DEFERs naming their reason.

### 4. `G-SHADOW-001`: FAIL, and two of three reasons are structural

1. **all-silence** — the gate's own text calls it a utility failure regardless of precision;
2. **scale** — the design asks ≥500 pull requests across ≥30 repositories, ≥100 adjudicated
   findings, ≥200 adjudicated silences. The owner's whole account holds **29** reviewable pull
   requests across **6** supported repositories. **No budget fixes this**;
3. **prospectivity** — 1 unit of 29 is genuinely prospective (`Attest#19`).

What the population *can* establish is mainline §1 condition 5 — one prospective run, no false
publication — and that still needs a working executor.

### 5. The re-take

`.github/workflows/e04-shadow.yml` (`workflow_dispatch`) runs **the same frozen sample** on
`ubuntu-latest`. Nothing about the study changes; the local review path still constructs no
GitHub client, so no comment can reach any repository. `OneTapVocal` is private and
`GITHUB_TOKEN` cannot clone it, so the runner reports it **skipped by name** rather than dropping
it. The local trials are kept as `trials-local-host.jsonl` so both columns stay readable.

### 6. One thing that cost money and bought nothing

The driver's first draft resolved a pull request's base as `merge-base(head, the base branch
today)`. For a **merged** pull request the base branch already contains the head, so that is the
head itself and the diff is empty: **nine units reviewed nothing for $0.19**. Caught before any
unit produced a non-empty review, protocol re-frozen against the API's own `base.sha`, those
trials discarded rather than counted, and the dollar recorded in `DEVSPEND.md` as spend that
bought nothing.
