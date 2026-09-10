# attest

**A pull-request reviewer that only says things it can prove, and abstains out loud when it
cannot.**

An LLM proposes; an algorithm that calls no model decides whether it may speak. A defect claim
is published only when a generated test **fails on your head commit and passes on the merge
base**, three runs each way, inside a network-free container, with a receipt anyone can verify
offline. That reproduction, an intent check, and a hard cap of three findings a pull request
are the whole publication rule — **a score decides only which three an author sees, never
whether a claim is true, and no number here is a pull-request-level error guarantee** (D-199).
Everything else is a stated silence.

It is **experimental**, and the numbers below say exactly how experimental. Its measured recall
on a held-out defect corpus is **6.5%**; it is silent far more often than it speaks; and a
silence from it is never evidence that your code is fine.

## What it says, in four levels

Every author-visible line is **one line** carrying a level marker, a coordinate, one sentence of
fact and its evidence (D-142). There are four levels and they never merge, never borrow each
other's words, and never speak for each other:

| | one sentence | costs a model call? | status |
|---|---|---|---|
| **red** | *this change broke something* — a generated test that fails on head and passes on the merge base, three runs each way, with an offline-verifiable receipt | yes | **live** |
| **gate** | *this new code crashes on an input a pre-existing caller produces* — new code has no merge base, so it is admitted only through a caller outside the added lines | yes | **shadow** — nothing on this path is author-visible, and on **0 of 445** recorded candidates has it found a publishing-grade witness |
| **yellow** | *here is a hypothesis, and here are the premises I checked* — a checker verifies each premise separately and only the verified ones are said | no | **(a) the impact scope is live**, ≤ 2 per pull request. **Its other two classes are not**: the null/Optional class is **closed** (0 of 79 under two rule versions) and exception propagation is a **shadow** that reaches no author-visible surface |
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

The long form of all of this — what each level has actually said, the limitations that
would change your mind, every measurement with its budget and its models, and the reports
already in this repository — is in [`docs/evidence.md`](docs/evidence.md).

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
        uses: IcantFind-a-username/Attest@v0.1.0   # docs/operations/install-ref.md
        with:
          github-token: ${{ secrets.GITHUB_TOKEN }}
          model-api-key: ${{ secrets.ANTHROPIC_API_KEY }}
      - name: Upload attest ledger
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: attest-ledger-pr-${{ github.event.pull_request.number }}-run-${{ github.run_id }}
          path: |
            .attest/ledger.jsonl
            .attest/evidence/
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

## What it has actually done, with intervals

Every number here links to the report it comes from. **Each is what it says and nothing more**;
the column on the right is the reason.

| measurement | number | what it is **not** |
|---|---|---|
| **crash-class recall**, held-out corpus of 31 SWE-bench Verified cases whose projects declare a supported interpreter, measured 2026-09-10 | **2 of 31 — 6.5%**, Wilson 95% **[1.8%, 20.7%]** ([report](docs/acceptance/2026-09-10-heldout-remeasurement.md)) | not a precision figure, and not a sample-size problem: the interval's **upper** bound is 20.7%. The denominator is the crash class of a 39-instance population, all of it bought; the 2026-09-12 figure of 2 of 28 was the same population with four cases left unbought by a cap |
| **false publications**, prospective shadow over 28 real pull requests with 13 reproductions that actually executed | **0** ([report](docs/acceptance/2026-09-13-e04-shadow-v3.md)) | not a precision figure either — **nothing certified**, so precision is undefined and utility is unproven |
| **false publications**, 68 independent null controls + 40 held-out controls, K=4 | **0** ([report](docs/acceptance/2026-09-05-g-null-001a-independent.md), [held-out](docs/acceptance/2026-09-03-e02-heldout.md)) | the last measured control arm is at **K=4**; the shipped `samples` is 5 and that arm has never been bought |
| **yellow (a) noise floor**, 68 null controls, deterministic | **1 of 68 — 1.47%**, Wilson 95% **[0.26%, 7.87%]** ([report](docs/acceptance/2026-09-13-yellow.md)) | the one note is **true**; the level claims no defect and has never been shown to find one |
| **yellow (b), exception propagation**, 68 null controls | **0 of 68 — 0.00%**, Wilson 95% **[0.00%, 5.35%]** | it is a **shadow**: it reaches no author-visible surface at all |
| **red-team attack classes** dispatched on the production backend, all marked and never certified | **13 of 13** ([matrix](docs/acceptance/2026-09-13-redteam-thirteen.md)) | observed from **inside** the product for 11 of the 13; an external kernel observer has watched seven syscalls, once |
| **cost of a review** | mean **$0.22**, hard cap `budget-usd` (default $1.00) | — |

## Known limitations, in the order they will bite you

1. **Recall is 6.5%** — Wilson 95% [1.8%, 20.7%], 2 of 31, measured 2026-09-10 on the held-out
   crash-class corpus. Three places the evidence is lost, measured over 67 verification attempts:
   **21** the generated probe does not collect at all; **18** the process guard refuses the probe
   **on the merge base**, where nothing untrusted runs; **14** the whole intent clause. Two
   mechanical categories hold 39 of 67. Deriving probes from the repository's own tests was tried
   against exactly this corpus and **changed no receipt**
   ([report](docs/acceptance/2026-09-10-heldout-remeasurement.md)).
2. **Python only.** Python, pytest, Linux containers, interpreters **3.10–3.13**. Anything else
   gets one line naming the reason and exit 0 — never a traceback, never a silence that reads
   as *nothing found*.
3. **The gate level is in shadow.** New-code findings are computed and written to the ledger and
   reach **no author-visible surface**; on 0 of 445 recorded candidates has it found a
   publishing-grade witness.
4. **Two things are known untested, for budget and not because they do not matter**
   ([decision](DECISIONS.md)): the red control arm at the shipped **K=5** (126 controls, ≈$126),
   and `G-NULL-001`'s full natural-null population (≈$53). Every control number above is a K=4
   number and says so.
5. **A silence is never a true negative.** Nothing here licenses *"attest found nothing, so it
   is fine"*.

A review costs about **$0.22** on average and is hard-capped by `budget-usd` (default
$1.00). **Do not lower it below $0.54**: at the default `samples: "5"` the discovery share is
$0.16 of output tokens alone, so a smaller budget defers the review before it reads anything
(measured 2026-09-09). See [`docs/github-action.md`](docs/github-action.md) and the
[support matrix](docs/operations/support-matrix.md) — GitHub-hosted `ubuntu-*` runners only.

## For contributors

Everything about changing attest — the local CLI, the development setup, the Action's internals,
the spend ledger, the decision records and the gates — is on one page:
**[`docs/contributing.md`](docs/contributing.md)**. Start there, then
[`AGENTS.md`](AGENTS.md).

## Origin

Attest grew out of Corum, a preregistered research project on dependence-aware aggregation
of unreliable reviewers. That project produced an important negative result: aggregation
heuristics and correlated panel agreement did not supply the hoped-for general confidence
guarantee. Attest keeps the useful engineering lessons—explicit evidence purchases,
correlation skepticism, auditability, and abstention—while moving final authority to a
separate executable-evidence certificate.

License: Apache-2.0. Copyright 2026 Franz Xu.
