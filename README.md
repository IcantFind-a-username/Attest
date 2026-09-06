# attest

Attest is an experimental, evidence-first, LLM-driven code evaluator. Its target is simple
to state and deliberately hard to satisfy:

> Publish only a small number of important defect claims that have a trusted, replayable,
> claim-bound execution certificate; spend model and test budget where it is most likely to
> produce such a certificate; otherwise abstain explicitly.

## What it says, in four levels

Every author-visible line is **one line** carrying a level marker, a coordinate, one sentence of
fact and its evidence (D-142). There are four levels and they never merge, never borrow each
other's words, and never speak for each other:

| | one sentence | costs a model call? | status |
|---|---|---|---|
| **red** | *this change broke something* — a generated test that fails on head and passes on the merge base, three runs each way, with an offline-verifiable receipt | yes | **live** |
| **gate** | *this new code crashes on an input a pre-existing caller produces* — new code has no merge base, so it is admitted only through a caller outside the added lines | yes | **shadow** — nothing on this path is author-visible, and on **0 of 445** recorded candidates has it found a publishing-grade witness |
| **yellow** | *here is a hypothesis, and here are the premises I checked* — (a) the change's impact scope, (b) a null/Optional dereference or an exception no caller handles | (a) no · (b) one for the null class, none for the exception class | **live**, ≤ 2 per pull request, shared across every class |
| **green** | *this is structurally so* — computed with no model at all; today, the same implementation in two places | only to word it | **live** |

```text
[red]    requests/models.py:389 — the generated test fails on head in 3/3 runs and passes on the
         merge base in 3/3 — receipt 3253ada5eff4
[yellow] src/click/parser.py:78 — `_unpack_args` changed signature; 3 call site(s) name it, 1 of
         them named by no test — scripts/cli.py:120
[green]  Structural (no defect claimed): a.py:10-40 and b.py:88-118 normalise to token sequences
         whose similarity is 0.98 (threshold 0.92)
[silent] read 13 of 13 units; nothing met an adjudicator's bar; $0.03, 41.2s.
```

**A level that has nothing to say contributes no line.** When every level is silent the product
still owes exactly one, and it names how many change units the silence covers — a silence over
1 of 13 units and a silence over 13 of 13 are different claims. A silence bought out by the
budget says so, and how many candidates it stopped.

### What each level has actually said

**On 40 real commits** — the most recent 20 of this repository and 20 of `us-stock-helper`,
reviewed in shadow at `--budget 0.25`
([table](docs/acceptance/2026-09-06c-four-levels.md)):

| level | spoke on | what the rate is **not** |
|---|---|---|
| **red** | **0 of 40** | not a precision number: no commit in the 40 is known to contain a defect |
| **yellow (a)** | **0 of 40** (1 of 10 more on a third repository, true and not actionable). Its **first unprompted trigger on this repository's own traffic** came later, on [PR #12](https://github.com/IcantFind-a-username/Attest/pull/12): true, and at the time it carried no action clause (D-178) | — |
| **yellow (b)** | **0 of 40**, and **0 of 79** on a separate scan, under two rule versions | — |
| **green** | **8 of 40** (20%), three of them the same duplicated `git` helper | — |
| **every level silent** | **32 of 40** (80%) | a silence is an abstention, never a true negative |

`$2.03` for 40 reviews — **$0.051 a commit**.

**And what four times the budget buys: nothing.**
[The 17 of those 40 whose candidates died with the budget gone were re-reviewed at
`--budget 1.00`](docs/acceptance/2026-09-07-budget-rerun.md). Spend **$1.64 → $10.32**,
candidates **105 → 331**, and **not one verdict moved** — red 0 both times, both yellows 0 both
times, green on the same 8 commits. Candidates refused *for budget* went **up**, 40 → 44:
raising the budget raises discovery, and discovery re-starves the budget. Exactly one candidate
reached an adjudicator that had not before, and it was drawered.

### Known limitations — the ones that would change your mind

- **S·T is a priority score and a per-unit family cap. It is not an e-value, and it is not
  evidence.** *The only evidence this product publishes on is the differential reproduction (V).*
  S and T rank candidates and spend a publication budget; **they were proven not to be an e-value**
  (D-174), and this README's vocabulary was downgraded to match.
  Over **475 candidates of 276 control reviews** on eight public repositories the S·T score has
  mean **2.27** and a *minimum of 2.0* — it cannot fall below 1 at all, because S prices only
  positive evidence. That is a structural fact about the factor table, not a statistical one: the
  475 are not independent draws and no sample size changes it. A valid e-value satisfies
  `E[X] <= 1` under the null, so the `m_u / alpha` bar is a **fixed likelihood-ratio bar with a
  calibration claim attached**, not a proven error rate; every row records it as
  `assumed-calibrated`. And the per-unit cap binds **inside a change unit only**: across a pull
  request the union over the units searched is `min(1, U * alpha)`, measured at **0.65** for ten
  units at `alpha = 0.1` — where **`alpha` is the name of the configuration constant, not a
  claimed error rate**. Nothing here impeaches a published receipt — S·T tops out at 9 against a
  bar of 10 at the factory setting, so every publication rests on the differential execution — but
  that is a one-unit arithmetic margin rather than an invariant, and **no number in this README is
  a pull-request-level error guarantee** (D-174,
  [report](docs/acceptance/2026-09-08-binding-and-bounds.md)).
- **Every level now resolves a name before treating it as a call, and all of them got quieter.**
  Inheritance, decorators, a call through a variable, a package re-export, and any bare name in
  a file with a star import are abstentions. Re-counting what this changes: **all 26**
  recorded `through_caller` gate witnesses, across **445** new-code candidates in four
  populations, were name collisions — a function witnessed in a file that defines its own
  function of that name. The gate level's measured reachability on real traffic is **0.0%**,
  not 5.8%. Read the old numbers in those reports as name matches, not as reachability (D-174).
- **The value class is conservative and it costs recall.** A change that alters a returned value,
  where the base tree does not say what that value should be, is refused with *value change
  confirmed, intent unknown*. On a held-out slice of **known defects** that clause cost **four
  publications**; on forward pairs it is right where it fires. Two populations, two answers
  (D-158).
- **Reachability has a ceiling, and after D-174 the measured ceiling is zero.** The gate level
  requires a call site outside the added lines and a fully annotated signature; on real traffic
  **30 of 90** new-code candidates were admissible at all, and a caller reached only through a
  registry looks unreachable. Since call sites are resolved rather than name-matched, **none of
  the 445 recorded new-code candidates has produced a publishing-grade witness** — the level is
  in shadow, has never spoken, and the reason it has never spoken is now known.
- **Whether a test may be a gate witness is an open owner decision.** The gate level admits
  new code only through a caller *outside* the added lines. D-166 grades a caller that is
  itself a test as `through_test_caller` and **never publishes it** — a test naming the new
  code is the change's own coverage, not a pre-existing dependency on it. That rule is why the
  reachability number is **0 of 445** rather than **3 of 445**: the only three witnesses that
  survive name binding are all test callers. Both answers carry a false-positive risk and the
  owner has not chosen between them: **keeping the exclusion** risks silence on new code whose
  only pre-existing caller genuinely is a test fixture or a shared helper — a real dependency
  that happens to live under `tests/`; **admitting test callers** risks publishing a crash the
  change's own new test provokes, which is a claim about the test rather than about the code,
  and on the recorded populations it would move the level from *never having spoken* to
  speaking on 3 cases nobody has adjudicated. Until it is decided the level stays in shadow.
- **Non-deterministic functions cannot be certified.** A reproduction must agree with itself
  three times on head and three on base; anything that does not is an abstention, not a finding.
- **Yellow (b)'s null/Optional class is closed, and this is the reason it stayed open so long.**
  0 of 79 units under two rule versions, 28 hypotheses proposed, 0 surviving all three premises,
  and one model call paid on every review to keep the option alive. It is now **off** (D-169):
  the code, the rules and the tests remain, and one flag turns it back on. The argument for
  turning it on is the one that has never been tested — the corpus that defeated it carries no
  type annotations and many repositories do — so if your code is annotated, this class has not
  been measured on code like yours either way (D-151, D-165).
- **Yellow (b)'s second class, exception propagation, is a shadow.** Also 0 of 79 — but free, and
  its refusals say why: of 198 changed functions, 135 added no call at all and 43 called a name
  defined more than once — a count taken **before** D-174, when a second definition anywhere in
  the tree was read as ambiguity; under name binding most of those 43 are not ambiguous. It runs on every review and writes to the ledger; it reaches **no
  author-visible surface**, because a level that has never said anything has not yet earned a
  reader's attention (D-164, D-169).
- **A review reads only what 30% of its budget buys, and verifies at most three candidates per
  changed file.** Discovery is capped at 30% of one review's budget and reproductions are ranked
  by cluster size and a static credibility score, so a large change is read **partially and
  visibly** — the accounting line says `read 3/10 units`, and a candidate the cap held back says
  `ranked below verification cap` under `--explain`. Replayed over 28 recorded reviews this
  halves the spend and keeps every receipt, but it is a *replay*: no paid run has been taken
  under it yet (D-168).
- **The boundary is Python, pytest and Linux containers.** A repository with no Python source, an
  unparsable lock file, no docker, or an image that cannot provide pytest gets **one line naming
  the reason and exit 0** — never a traceback and never a silence that reads as *nothing found*
  (D-159). Interpreters are **3.10–3.13**, primary 3.12 (D-162).
- **A silence is never a true negative.** Nothing here licenses "attest found nothing, so it is
  fine".

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
        uses: IcantFind-a-username/Attest@v0.1.0-rc.1   # docs/operations/install-ref.md
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

**Fork pull requests are never reviewed and never commented on.** Two independent gates
skip them before any credential enters a runner step, and this repository uses no
`pull_request_target` trigger anywhere. A skipped fork leaves **no comment, no review, no
check annotation and no artifact** — nothing that could read as *reviewed, nothing found* —
only one Actions notice in the run log saying it was skipped.

A review costs about **$0.22** on average and is hard-capped by `budget-usd` (default
$1.00). **Do not lower it below $0.54**: at the default `samples: "5"` the discovery share is
$0.16 of output tokens alone, so a smaller budget defers the review before it reads anything
(measured 2026-09-09). See [`docs/github-action.md`](docs/github-action.md) and the
[support matrix](docs/operations/support-matrix.md) — GitHub-hosted `ubuntu-*` runners only.

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
- **a changed return value publishes only against a base specification the change left
  standing, and only when the diff says nothing about the symbol under test** — the failing
  assertion must pin a distinctive value (not `None`/`True`/`0`/`""`), the base tree must
  state it, head must still state it, and no test, docstring, doc, changelog line or inline
  comment in the same diff may touch the anchored symbol (`attest.intent.v4`, D-132,
  2026-09-05) **in a recognisable form** — backticked, dot-qualified, or a long bare name
  English does not supply (`attest.intent.v4.1`, D-134, 2026-09-05), and the specification must
  be **about the symbol the change touched** — an `assert` counts only when its own scope names
  that symbol, a docstring only when it belongs to it or names it, a documentation paragraph
  only when that paragraph names it, and a change touching no function or class can have no
  specification at all (`attest.intent.v4.2`, D-174, 2026-09-08). On the whole corpus
  replay this class certifies **0 of 48** receipts under both: the recall cost is the
  decision, and it is large. **That 48 is a reversed corpus and therefore inflates the
  class** (D-135). The first number taken where time runs forwards is **0 certified of 1
  value-class candidate over 11 forward pairs** (D-140, 2026-09-05) — `n = 11`, one candidate,
  a 95% upper bound of 95%, and no recall rate is estimable from it. What eleven forward pairs
  did show is that value-class candidates are *rare* in natural defect-introducing commits:
  nine of the eleven produced only crash-shaped or unfaithful ones
  ([report](docs/acceptance/2026-09-05-forward-pair-reviews.md));
- **a function whose value is not reproducible cannot be recorded, so it is never
  certified** (`attest.probe.record-replay.v1`, D-146/D-148, 2026-09-06). The generator
  records what the merge base does and the kernel writes the assertion from the recording,
  so a function that returns a different value on each call has no expectation to write. The
  probe executes the merge base **three times** and refuses the recording unless all three
  observations are identical; the refusal is `probe refused: the merge base returned X, then
  the merge base returned Y`. The measured case is `more-itertools random_product`, which
  returns one of four tuples uniformly: the legacy generator published it (by asserting the
  *shape* of the result), the probe path drawers it, and **that is a real recall cost of
  recording and not a defect** — a value that is not reproducible is not a differential.
  Nothing finite closes the hole; what bounds it is that the replay's own three base runs
  must agree too, so six identical observations stand behind a receipt;
- **measured so far.** Every row names the per-review budget and the models it ran under,
  because both move every number in it. `S` is the proposal model, `G` the reproduction
  generator. The shipped default budget is **$1.00** as of 2026-09-04 (D-126); it was $0.25
  before, and no row below ran at $1.00 except the last two.

  | what | population, one run each | result | budget | models | date |
  |---|---|---|---|---|---|
  | **held-out, crash/exception class** | the 29-case slice re-run under the probe generator and `attest.intent.v4.1`, **minus the 12 cases whose reproduction observed a value change and nothing raised** ([report](docs/acceptance/2026-09-06c-heldout-probe.md)) | **certified 4 of 16 (25%)**; **28 of 28 environments built**, against 10 of 29 before. The denominator is 16 and not 28 by **D-158**: this corpus is reversed by construction, so it may not carry a value-class number | $1.00 | S `claude-sonnet-5`, G `claude-opus-5` | **2026-09-06** |
  | **held-out, value class** | the 12 cases of the same slice whose reproduction observed a behaviour change with no exception | **not a recall figure, by D-158.** All 12 were refused by the value clause — *value change confirmed, intent unknown* — and **four of them the old generator had published**. That is the clause's **cost on a reversed corpus**, which is where clause (c) is measured wrong on 4 of 4 (D-135). The value-class recall number comes from forward pairs only, where it is **0 of 1** (D-140) | $1.00 | same | **2026-09-06** |
  | — *old generator*, kept for comparison | the same 29 cases, legacy generator, before the bootstrap fix | certified 5 of 29, i.e. 5 of the 10 whose environment built; a supplementary run of the other 19 certified 10 of 19 and was reported apart ([report](docs/acceptance/2026-09-03-e02-heldout.md)) | $0.25 / $0.60 | S `claude-sonnet-5` | 2026-09-03 |
  | **held-out controls** | 40 synthetic controls (test-only and docs-only from the same instances), re-run under the probe generator | **0 false publications** (old generator: 0 of 39) | $1.00 | S `claude-sonnet-5` | **2026-09-06** |
  | **adversarial tests** | 9 held-out cases × 2 constructed adversarial tests | **18 of 18 rejected** by the changed-line binding policy; container re-execution, **no model call** | — | — | 2026-09-03 |
  | **real-traffic corpus, defects** | 19 defect pairs on 3 repositories, D-116 construction ([report](docs/acceptance/2026-09-03-real-traffic-corpus.md)) | **6 of 19 pairs certified (32%)**, 4 of 19 published (21%); 16 receipts, 6 publications standing after the D-124 correction | **$0.60** (not the default) | S `claude-sonnet-5`, G `claude-opus-5` | 2026-09-03 |
  | **real-traffic corpus, controls** | 24 controls from the same repositories | **0 false publications** — but two controls carried real defects, so this population cannot support a false-publication *rate* | **$0.60** | same | 2026-09-03 |
  | **natural null (E-01)** | 20 real commits, one repository | 1 publication, since reclassified to the drawer by D-102 ([report](docs/acceptance/2026-09-03-e01-natural-null.md)) | $0.25 | S `claude-sonnet-5` | 2026-09-03 |
  | **`G-NULL-001a`** | 15 of 58 preregistered qualified null commits, 5 public repositories ([report](docs/acceptance/2026-09-04-g-null-001a.md)) | **1 wrong publication** — the gate **does not pass**, the run stopped under `RISK-CERT-01` on the fifteenth control, and the cause is structural (D-127) | **$1.00** | S `claude-sonnet-5`, G `claude-opus-5` | 2026-09-04 |
  | **shadow (E-04 v1)** | 2 prospective units | 22 candidates, 0 eligible, **0 shadow findings** ([report](docs/acceptance/2026-09-03-e04-prospective-v1.md)) | $0.25 | S `claude-sonnet-5` | 2026-09-03 |
  | **shadow (E-04 v2)** | **100 units** of the owner's most recent traffic, 4 repositories ([report](docs/acceptance/2026-09-04-e04-stratum-v2.md)) | 495 candidates, 129 eligible, **21 receipts, 7 shadow findings, 0 published**; all 7 **unadjudicated** | **$1.00** | S `claude-sonnet-5`, G `claude-opus-5` | 2026-09-04 |
  | **shadow findings adjudicated** | the **2** E-04 shadow findings that survived the v3 re-judging, checked by exhaustive static search at the reviewed head ([report](docs/acceptance/2026-09-05-shadow-adjudication.md)) | **both false**: the change deletes `institutional_flow_reading` and the `FactorSnapshot.institutional_flow` field and **every reference to either, in the same diff** — 0 dangling references found | — | — (no model) | 2026-09-05 |
  | **`G-NULL-001a` finished** | the **7** preregistered qualified null controls never reached, under `attest.intent.v4` ([report](docs/acceptance/2026-09-05-g-null-001a-final.md)) | **0 wrong publications** — but n = 7, so the 95% upper bound is ~43% and says nothing; **58 of 58 controls have now run**, under three discriminator versions, with **2 wrong publications** across that history, so **the gate does not pass** | **$1.00** | S `claude-sonnet-5`, G `claude-opus-5` | 2026-09-05 |
  | **`G-NULL-001a` re-run under one version** | all **58** preregistered qualified null controls, `attest.intent.v4.1`, 8 public repositories ([report](docs/acceptance/2026-09-05-g-null-001a-v41.md)) | **0 wrong publications at n = 58**, 95% upper bound **5.2%**; the two commits that once published reproduced their receipts and were **both drawered live**. The population is no longer independent of the rule, so this is a regression test as much as a null study | **$1.00** | S `claude-sonnet-5`, G `claude-opus-5` | 2026-09-05 |
  | **`G-NULL-001a`, the independent population — closed** | **68** preregistered qualified null controls drawn on a shifted seed, disjoint from the 58 the intent rule was revised against, 8 public repositories ([report](docs/acceptance/2026-09-06-g-null-001a-final.md)) | **answered n = 7, 0 wrong publications, 1 true positive on a control** (`more-itertools f4f2cfec9d`, probe-adjudicated on four interpreters, D-141). The rule-of-three bound is 42.9% and is **not quoted as a bound**: **57 of the 68 controls produced no candidate at all**, so this population measures discovery's silence, not the rule's restraint. **The population is closed** — no further control is added to it: at **7 answered per 68 reviewed** and $0.0184 a control, `G-NULL-001`'s n ≥ 300 *answered* would need about 2,900 more controls and ~$53, more than the whole remaining cap (D-144). D-134's 5.2% at n = 58 remains the only bound this gate has | **$1.00** | S `claude-sonnet-5`, G `claude-opus-5` | 2026-09-06 |
  | **the green channel, in production** | **1** pull-request comment on this repository, a throwaway since closed ([report](docs/acceptance/2026-09-05-green-channel.md#4-one-real-comment-on-a-real-pull-request-owner-instruction-4c)) | one `structural` comment, coordinates and a measure, partitioned from red, **no defect claimed**; the model's sentence was dropped for a hedge and the run exposed that no one recorded why | **$0.25** | S `claude-sonnet-5` | 2026-09-05 |
  | **forward pairs — time runs forwards** | **11** distinct defect-introducing commits and their parents, 5 public repositories ([report](docs/acceptance/2026-09-05-forward-pair-reviews.md)) | 75 candidates, **31 answered about the code**, **3 certified and 3 published** — two of them the exact defect the later repairing commit fixed, the third a different real regression in the same commit. **Value class: 0 certified of 1 candidate**, so no value-class recall rate exists at n = 11. 20 of the 31 answers were unfaithful generated tests, [classified here](docs/acceptance/2026-09-06-forward-pair-generation-failures.md): 18 of them assert a behaviour the base revision does not have either, and **none** is an environment failure | **$1.00** | S `claude-sonnet-5`, G `claude-opus-5` | 2026-09-05 |
  | **the same 11 forward pairs, under the probe generator** | the **11** distinct defect-introducing commits of the row above, re-reviewed with `attest.probe.record-replay.v1` and `attest.intent.v4.1` **unchanged** ([report](docs/acceptance/2026-09-06b-forward-pairs-probe.md)) | **unfaithful generated tests 20 → 0**, and by construction rather than by better judgement: the assertion is what the merge base itself produced three times. **Certified 3 → 3, published 3 → 3**; the bottleneck moved to intent, whose value-class drawers went **1 → 15**. One publication was lost and one gained: `random_product` returns one of four tuples uniformly and **cannot be recorded at all**, which is a real recall cost of recording, and `click`'s `_unpack_args` certified where the legacy generator certified nothing | **$1.00** | S `claude-sonnet-5`, G `claude-opus-5` | 2026-09-06 |
  | **yellow (a), in production** | **1** pull-request comment on this repository, a throwaway since closed ([report](docs/acceptance/2026-09-06b-yellow-published.md#3-the-one-real-comment-and-the-defect-it-found)) | one `[yellow]` comment, one contract line, in its own section, **no defect claimed** and **$0.00** for the level itself. The first attempt posted **nothing** — `HTTP 422`, because a green note named a line the diff does not carry and GitHub refuses the whole review for it (D-147) | **$0.25** | S `claude-sonnet-5` | 2026-09-06 |
  | **a live defect in a third-party library**, found as a *control* | `more-itertools f4f2cfec9d` (2019), drawn as a null control of `G-NULL-001a` ([adjudication](docs/acceptance/2026-09-06-g-null-001a-final.md), [draft report](docs/acceptance/2026-09-06-more-itertools-issue.md)) | **real and still live**: `divide()` raises `KeyError` on a plain `dict` from **Python 3.12** — where `slice` became hashable — and on any `__getitem__` raising a non-`TypeError` on every version; present since **8.1.0** and at the clone's default-branch tip (`d92f081a08`, fetched 2026-09-05). Adjudicated by a probe with **no product code** on four interpreters; the receipt's bundle verifies offline with its seal. **Upstream: draft prepared 2026-09-06, not yet filed — issue number pending** | **$1.00** | S `claude-sonnet-5`, G `claude-opus-5` | 2026-09-05 |
  | **outside repository, in production** | **1** pull-request comment on a repository this project does not develop in ([report](docs/acceptance/2026-09-04-us-stock-helper-action-comment.md)) | the Action installed at `@v0.1.0-pilot.1`, built the container on a GitHub runner, ran a reproduction and **posted one comment — a `DEFER`** | **$0.60** | S `claude-sonnet-5`, G `claude-opus-5` | 2026-09-04 |
  | **`G-NEWCODE-001`, the gate level's reachability** | every recorded new-code candidate of four shadow populations, re-adjudicated under name binding ([report](docs/acceptance/2026-09-08-binding-and-bounds.md)) | **0 of 445 `through_caller`** — a publishing-grade witness has never been produced. Of 29 recorded `through_caller` grades, **26 were name collisions** and **3 resolve to a caller that is itself a test**; those 3 are `through_test_caller` under D-166 and are listed apart because that grade **never publishes** — a test naming the new code is the change's own coverage, not a pre-existing dependency on it. The earlier **26 of 445 (5.8%)** was a name-match count, not reachability | — | — (no model, `$0.00`) | 2026-09-08 |
  | **yellow (a), unprompted on real traffic** | **1** review comment on [PR #12](https://github.com/IcantFind-a-username/Attest/pull/12) of this repository, produced by the workflow's own run — not a drill and not a constructed case | `[yellow] src/attest/review/gate_level.py:252` — `calls_in` changed; **3 call sites in 2 files** resolve to it and **no test names it**. Produced by `attest.impact.caller-scope.v2`, so the sites were **binding-resolved, not name-matched**, and re-resolving them here confirms all three. **True, and not a defect**: `scripts/corpus/binding_recount.py:102` was rewritten for the new `WrittenCall` signature in the same commit and runs. **The comment carried no action clause** — the fourth check sample of the comment contract, and the reason for D-178 | `$1.00` cap, `$0.1390` spent | S `claude-sonnet-5`, G `claude-opus-5` | 2026-09-09 |

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
- **a reproduction's expectation is recorded on the merge base, not written by a model**
  (`attest.probe.record-replay.v1`, D-146, 2026-09-06). The model chooses one call — imports,
  setup, one expression, no assertion; the kernel executes that probe on the base revision
  **twice**, records what it did (a `repr`, or an exception's type name), refuses the recording
  unless the probe reached the anchored file and both recordings agree, and writes the assertion
  from the recording. `unfaithful generated test: fails on base as well` — **20 of 31 answered
  candidates on forward pairs** before this (D-140) — is structurally impossible on that path,
  and the branch that would report it says so in its own words. The legacy generator, where the
  model writes the assertion from the diff alone, remains as `probe_generation = false` and is
  the reversal;
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
attest stats [--since 7d|2026-09-01] [--drawer] [--json]
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
  one, and why no `v0.1.0-pilot.2` was cut;
- `docs/acceptance/2026-09-05-intent-v4-replay.md` — v2, v3 and v4 side by side on 57 receipts:
  control publications 2 → 1 → 0, and the value class 48 → 12 → 0;
- `docs/acceptance/2026-09-05-shadow-adjudication.md` — the two surviving shadow findings
  adjudicated by exhaustive static search, both false;
- `docs/acceptance/2026-09-05-green-channel.md` — the wording adjudicator against the real
  default model, twenty calls, and the author-visible green channel it gates;
- `docs/acceptance/2026-09-05-forward-pair-reviews.md` — 11 forward pairs reviewed, 3 published
  and 2 of those the defect the later repair fixed, the value class 0 of 1, and the measurement
  that forward pairs cost recall in *generation*: 20 of 31 answered candidates produced a
  reproduction that fails on base as well;
- `docs/acceptance/2026-09-05-g-null-001a-independent.md` — the independent null population run
  to a stop on control 54, and the adjudication that its one publication is a **true positive**
  on a live `more-itertools` defect rather than a false one;
- `docs/acceptance/2026-09-06-g-null-001a-final.md` — the same population finished under the
  probe-adjudicated stop rule and then **closed** (D-144): **answered n = 7, 0 wrong
  publications, 1 true positive on a control**, 68 of 68 reviewed, and a rule-of-three bound of
  42.9% the report states only to refuse — 57 of the 68 controls produced no candidate at all;
- `docs/acceptance/2026-09-06-forward-pair-generation-failures.md` — all 20 unfaithful
  reproductions opened and classified: **0 environment failures**, 18 asserting a behaviour the
  base revision does not have either;
- `docs/acceptance/2026-09-06-impact-scope-scan.md` — yellow (a), the impact scope, measured
  offline on 79 units before it is ever author-visible: it speaks on 4 of 11 defect-introducing
  commits and 1 of 68 ordinary ones, at $0.00;
- `docs/acceptance/2026-09-06-v01-tag-readiness.md` — the seven product conditions re-checked
  and the eight things a `v0.1` tag still needs, listed and not started;
- `docs/acceptance/2026-09-06b-yellow-published.md` — yellow (a) wired into the publication
  path under the owner's conjunction, and the cost of that rule: **0 of 79 units**, where the
  disjunction spoke on 5;
- `docs/acceptance/2026-09-06b-forward-pairs-probe.md` — the same 11 forward pairs under the
  probe generator, old column beside new;
- `docs/acceptance/2026-09-06b-v01-tag-readiness.md` — the gap list re-read, its documentation
  items done and its code items listed;
- [`CHANGELOG.md`](CHANGELOG.md) — what changed since the pilot tag and what each change cost.

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
