# Quickstart: from a fresh clone to the first receipt-backed comment or an explicit silence

This is the L-01 quickstart for one outside Python repository. It is written to be executed
verbatim. Every step either produces a verified comment backed by an evidence bundle or an
explicit, explained silence; there is no third outcome.

## What you need

- a Linux or macOS machine with Python 3.11+ and Docker (the production backend runs every
  reproduction in a container; without Docker the local `attest review` falls back to the
  host adapter and says so — CI never does);
- a model API key for the provider in `src/attest/data/pricing.toml` (`ANTHROPIC_API_KEY`),
  kept in the shell, never in the repository;
- for the GitHub Action: a repository token that may update pull-request comments.

## 1. Install attest from a stable ref

```bash
git clone https://github.com/IcantFind-a-username/Attest.git
cd Attest
git checkout v0.1.0-rc.1       # the ref in docs/operations/install-ref.md
python3 -m venv .venv          # `python` is often absent on macOS
.venv/bin/python -m pip install -r requirements-toolchain.lock
.venv/bin/python -m pip install --no-deps --no-build-isolation -e .
.venv/bin/attest --help
```

## 2. Review one change locally

In the repository you want reviewed, commit the change on a branch so the head is immutable,
then:

```bash
cd /path/to/your-repo
ANTHROPIC_API_KEY=... /path/to/Attest/.venv/bin/attest review --base main --k 4 --budget 1.00
```

`attest review` proposes candidates, runs the differential reproduction stage (the generated
test must fail on your head three times and pass on the merge-base three times, inside a
container), and prints **one line per claim** (D-142) followed by **one accounting line that is
always present**:

```text
[red] calc.py:2 — average() divides by zero on an empty list … (receipt 3253ada5eff4)
read 1/1 units, candidates 1, drawer 0; verified 1, discarded 0; spend $0.31 of $1.00; 41.2s.
```

When nothing met a bar, the levels are replaced by exactly one line that names how many change
units the silence covers — and, when the budget is what stopped it, how many candidates went
unverified:

```text
[silent] read 1 of 13 units; nothing met an adjudicator's bar; $0.0156, 4.4s.
[silent] read 3 of 13 units; the budget ceiling was reached; 8 candidate(s) were not
         verified; $1.0000, 194.3s.
```

Add **`--explain`** for one line per silent candidate — its coordinate, the class of reason the
drawer holds it for, and what it cost — and **`--json`** for the same run as one machine-readable
object. Neither is on by default: a drawer reason is not a claim about the code.

The accounting line's drawer histogram is the thing to read first; every class in it is
explained in [the FAQ](../faq.md). Nothing except a `[red]` line is a finding.
`attest stats --drawer` lists what was held back and why, `attest stats --json` summarises a
repository, and `attest feedback <id> --fix|--good|--dismiss` labels a finding.

### What a review typically costs

Measured, not estimated. Every figure is a per-review mean over reviews that actually ran, at
the budget named; a review never spends more than its budget, and most spend far less.

| population | budget it ran at | reviews | **mean spend per review** | source |
|---|---|---|---|---|
| real pull-request traffic, all strata | $0.60 | 43 | **$0.22** | [corpus](../acceptance/2026-09-03-real-traffic-corpus.md) |
| — defect pairs (a change with something in it) | $0.60 | 19 | **$0.31** | same |
| — refactor commits | $0.60 | 5 | $0.34 | same |
| — test-only commits | $0.60 | 9 | $0.12 | same |
| — documentation-only commits | $0.60 | 10 | $0.06 | same |
| the three largest changes measured, unconstrained | $1.20 | 3 | **$0.91** (max $1.03) | [budget wall](../acceptance/2026-09-04-budget-wall.md) |

**So: a typical review costs about $0.20–$0.35, and the $1.00 default is the ceiling for the
few large changes that need it, not the price of an ordinary one.** And raising it past that
default is measured to buy nothing: the 17 commits whose candidates died with the budget gone
were re-reviewed at four times the budget and **not one verdict moved**
([report](../acceptance/2026-09-07-budget-rerun.md)). A documentation-only pull
request costs a few cents. You are billed by your model provider for what is actually spent;
attest never spends past the cap and says so explicitly when it stops.

### Changing the budget

The factory default is **$1.00 per review** (raised from $0.25 on 2026-09-04, D-126). It is a
*cap*, not a price: the table above is what reviews actually cost, and the cap exists so that
the few large changes that need more evidence can buy it. Below $0.60, real reviews stopped
before generating a reproduction they could otherwise have produced — that is the measurement
the default rests on.

A change larger than anything yet measured can still exhaust it, and the run status says so in
as many words (`read N of M units, budget-limited`, or a reproduction line reading `budget:`).
Two ways to change what a review may spend:

- **one local run**: `--budget 1.20` on the command line above;
- **every review of a branch**: `budget_usd` in `.attest.toml` **on the base branch**, which
  is where CI reads it from (the head of a pull request cannot raise its own budget):

```toml
# .attest.toml on the base branch
budget_usd = 1.20
```

Lowering it is equally supported and equally explicit: at a smaller cap the product abstains
sooner and says which units it did not read.

Every key and its factory default is in [`base-policy.md`](base-policy.md). Spend is capped
before each call, never truncated mid-answer, so raising the budget buys more units read and
more reproductions attempted — never a weaker receipt.

## 3. Verify a receipt offline

```bash
/path/to/Attest/.venv/bin/attest verify --bundle .attest/evidence/<task>/<candidate> --require-seal
```

This recomputes every digest and the controller seal from the bundle alone.

## 4. Enable the Action on pull requests

Copy [`examples/pull-request.yml`](../../examples/pull-request.yml) into
`.github/workflows/`, pin `uses:` to the same ref you installed
(`IcantFind-a-username/Attest@v0.1.0-rc.1`, see [`install-ref.md`](install-ref.md)), and
set the two secrets the workflow names. Fork pull requests are skipped before any credential or head code is touched.
The Action posts a running comment, then a final comment that is either the verified
findings (each with its test) or an explicit abstention, always with a collapsed run status.

The base branch owns the policy the review runs under; see
[`base-policy.md`](base-policy.md) for every key and its factory default.

## 5. Turn it off without a deploy

Commit `enabled = false` in `.attest.toml` on the base branch (see
[`kill-switch-and-rollback.md`](kill-switch-and-rollback.md)). The head of a pull request
cannot override it.
