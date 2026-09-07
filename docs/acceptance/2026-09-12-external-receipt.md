# The receipt branch is taken: a repository this project does not develop in got a verified finding

**`IcantFind-a-username/us-stock-helper` #5, installed from `IcantFind-a-username/Attest@v0.1.0-rc.2`
with the quickstart's defaults and nothing else, received a `[red]` comment backed by a
reproduction receipt: head FAIL 3/3, base PASS 3/3, receipt `37e8cbfcabe1`, $0.0694, 1m42s.**
The regression was **placed by the owner on purpose** and the pull request said so; that is
stated everywhere in this report, because a planted defect measures the install path and the
publication path and it measures **no recall whatsoever**.

Continues [2026-09-04](2026-09-04-us-stock-helper-action-comment.md), which ended with the
Action's first outside comment saying `DEFER`. Mainline §1 condition 1's implied criterion —
*on a known regression, the comment is a finding* — had never been met. It is met now.

Full comment text, both bodies verbatim:
[`evidence/2026-09-12-us-stock-helper-pr5-comment.md`](evidence/2026-09-12-us-stock-helper-pr5-comment.md).
The run's whole ledger:
[`evidence/2026-09-12-us-stock-helper-pr5-ledger.jsonl`](evidence/2026-09-12-us-stock-helper-pr5-ledger.jsonl).

## 1. The install path, step by step, and the one step that failed

| # | step | result |
|---|---|---|
| 1 | cut `v0.1.0-rc.2` from `main` at `a759083` | **failed.** `pyproject.toml` carries the package version *by hand*, so the wheel built at the tag said `0.1.0rc1` and the release workflow's own tag/version agreement step refused it: `tag 0.1.0-rc.2 does not match built version 0.1.0rc1` ([run 34121833875](https://github.com/IcantFind-a-username/Attest/actions/runs/34121833875)). The check did its job. No release object was ever created and no repository pointed at the name, so the tag was withdrawn, the version bumped in [#16](https://github.com/IcantFind-a-username/Attest/pull/16), and the tag re-cut at `e01ea4b` (D-193) |
| 2 | release workflow at the re-cut tag | **green** ([run 34122195722](https://github.com/IcantFind-a-username/Attest/actions/runs/34122195722)). Marked **pre-release**; `attest-0.1.0rc2-py3-none-any.whl` and `attest-0.1.0rc2.tar.gz` attached. Nothing published to PyPI, nothing listed on the Marketplace |
| 3 | edit the consuming repository's workflow: `uses: …@v0.1.0-rc.2`, and drop its two overrides so it runs the quickstart's defaults (`budget-usd` $1.00, `samples` unset → the shipped 5) | one four-line edit; no other change |
| 4 | secret | **nothing to do** — `ANTHROPIC_API_KEY` has been in that repository's Actions secrets since 2026-09-04 |
| 5 | open the pull request | the review started on its own and needed no manual step |
| 6 | the run | **success in 1m42s**, [34122326871](https://github.com/IcantFind-a-username/us-stock-helper/actions/runs/34122326871) |

**Step 1 is the finding of this section**, and it is worth more than the rest. The version is
hand-written in **two** places — `pyproject.toml` and `src/attest/__init__.py` — and the bump
changed only the first, so the ref that produced this receipt ships a wheel whose metadata says
`0.1.0rc2` and whose `attest.__version__` says `0.1.0rc1`. The external runner logged exactly
that:

```
Successfully installed attest-0.1.0rc2
attest 0.1.0rc1
```

The test that binds the two, `tests/release/test_packaging.py`, **does not gate a pull
request** — `gates` runs on push to `main`, so the repository's own suite gates a merge rather
than the change before it, and PR #16 merged red. The string is corrected forward and **the tag
is not moved**: `v0.1.0-rc.2` is the ref that produced this receipt, and re-pointing it would
invalidate this report. Both findings are filed in [`../backlog.md`](../backlog.md); the ref's
own limitation is written into D-193.

## 2. The pull request, and the defect the owner placed in it

| field | value |
|---|---|
| pull request | [#5](https://github.com/IcantFind-a-username/us-stock-helper/pull/5), head `7e5b0fd`, merge base `137c779` |
| the change | `services/analysis_core/us_stock_helper_core/indicators.py`: `ema_series` loses its empty-series guard, and its seed line gains a type annotation |
| the defect | on the merge base `ema_series([], 5)` returns `()`; on head it raises `IndexError` |
| reachable | `ema_series` is exported from `us_stock_helper_core.__init__` — the package's public API |
| **not** covered by the project's own tests | `services/analysis_core/tests` **passes on head** (274 passed, 188 subtests). The suite exercises `ema_series([1, 2, 3], 3)` and never the empty case |
| written to be plausible | an annotation added, a guard read as redundant and removed. A defect that announces itself in the diff tests the reader, not the tool |
| declared | the pull request title begins `DO NOT MERGE` and its body says the defect is owner-placed and why |

**Two facts this design deliberately does not have:** it is not sampled from any population,
and its author knew what the reviewer would be looking for. It therefore measures the install
path, the container, the publication policy and the copy — and it estimates **no** precision,
**no** recall, and nothing about defects nobody planted (`INV-MEASURE-001`).

## 3. What Attest said

The claim line, verbatim, inline on the changed line and again in the summary:

> `[red] services/analysis_core/us_stock_helper_core/indicators.py:60 — Removing the empty-check causes `checked[0]` to raise IndexError when `_validated` returns an empty sequence (e.g., input list shorter than period, or empty), instead of gracefully returning an empty tuple as before. (receipt 37e8cbfcabe1)`

and beneath it the evidence lines, the action clause, the generated test, the command, six run
outcomes and the logs. The test the kernel wrote:

```python
from us_stock_helper_core.indicators import ema_series


def test_attest_replay():
    _attest_value = ema_series([], 5)
    # recorded by executing the expression above on the merge base;
    # no model wrote this expectation
    assert _attest_value == ()
```

| stage | result |
|---|---|
| change units read | 1 of 1; not budget-limited |
| candidates | 1; **eligible: regression** |
| image | `attest-repro:55ef0e3569cdbbe3`, **built on the runner in 27.9 s**, not cached |
| executor | `linux-container-v1`, available; `network_blocked: true` |
| reproduction | **reproduced** — head FAIL 3/3, base PASS 3/3, 6.3 s |
| certification | **accepted**, `regression_reproduced`, receipt `37e8cbfc…6610c`, bundle digest `10d70ae0…f5e4f` |
| publication | α 0.1, eligible 1, unit threshold **10.0**, priority score **60.0**, hard cap 3 → **published 1, suppressed 0** |
| **spend** | **$0.069390** (`ci_final`); the review itself $0.032961, `claude-sonnet-5` proposing, `claude-opus-5` generating |

The score is the factory arithmetic exactly: S caps at 3.0 and a reproduced V is ×20, so 60
against a bar of `m_u/α` = 10 for the one eligible candidate in that change unit. **The
2026-09-04 DEFER was not the threshold biting** — that run never bought V at all, and ended at
a score of 3.0 with `authority: ranking`.

## 4. Offline verification of the bundle — and why it could not be run

**It could not be run from what the installation keeps, and that is a defect in the
quickstart, not in the receipt.** The comment ends by telling the author to run

```bash
attest verify --bundle .attest/evidence/20260907-123203-4561687e/34a9299741 --require-seal
```

and the workflow the quickstart ships uploads `path: .attest/ledger.jsonl` — the ledger and
nothing else. The bundle is written to `.attest/evidence/<task>/<candidate>/` and dies with the
runner. The artifact of this very run contains one file, `ledger.jsonl`. So an author who
follows the instruction finds nothing to point it at. Filed in [`../backlog.md`](../backlog.md);
changing the upload path to `.attest/` closes it, and whether a public repository should publish
its evidence bundles is an owner decision, which is why it is not fixed here.

What **can** be said about the bundle, stated at its real strength:

1. **An offline verification did run, on the runner, and publication was conditional on it.**
   D-124 makes the kernel verify its own bundle before anything is author-visible: *nothing is
   author-visible unless that pass accepts*. The receipt exists, so that pass accepted. This is
   the product checking itself, not an independent party checking it.
2. **The claim itself was reproduced independently, off the runner.** The comment's own test and
   command, copied verbatim onto both revisions on a different machine, a different interpreter
   (CPython 3.12 rather than the image's 3.13) and outside any container:

   ```
   head 7e5b0fd  FAILED test_repro.py::test_attest_replay - IndexError: tuple index out of range
   base 137c779  1 passed
   ```

   That is the differential the receipt asserts, re-observed by a third party. It is **not** a
   verification of the runner's bundle, and it is not offered as one.

## 5. The failure copy, as it actually rendered

The refusals D-190 wired into this path did not fire here — the run was supported end to end,
which is the outcome the copy exists to distinguish itself from. Two renderings were observed
this window instead:

- this repository's own [PR #15](https://github.com/IcantFind-a-username/Attest/pull/15) read
  **2 of 7 units** and deferred with `DEFER: verification deferred: probe did not execute
  src/attest/review/ci.py on base …`. **None of the seven refusals fired on it**, which is the
  new code's first correct silence: an ordinary DEFER was not dressed up as a refusal;
- **this repository's [PR #17](https://github.com/IcantFind-a-username/Attest/pull/17) — the one
  carrying this report — rendered D-187's clause cut mid-word**: ``unit 85bb5390cb57dc5b (…) was
  $0.0436 short of the discovery share; `budget-usd` $1.15 would ``. `BUDGET_SHORTFALL_LIMIT` is
  applied as a slice, so the sentence stops inside the word that carries the advice. D-190's
  line-level version of the same clause reduces in whole steps and cannot do this;
- the same comment's collapsed block carried D-187's clause — ``unit … was $0.0010 short of the
  discovery share; `budget-usd` $1.00 would have read it`` — with `budget-usd` **already** at
  $1.00. The needed figure is rounded to two decimals, so a shortfall under a cent advises no
  change. Filed in [`../backlog.md`](../backlog.md).

## 6. Spend

| item | cost |
|---|---|
| the external review, run `34122326871` | **$0.069390** |
| reserved for this item | $3.00 → **$2.930610 released** |
| this repository's own PR #15 self-review (the merge the owner asked for) | $0.345762 |
| PR #16 self-review (the version bump) | $0.007750 |
| PR #17 self-reviews, two of them (this report's own merge) | $0.166450 |
| **window total** | **$0.589352**; cumulative $85.64 of the $110 cap, leaving $24.36 |

No adjustment to the regression was needed: the owner allowed two, and the first attempt
published.

## 7. What this establishes, and what it does not

**Establishes.** An outside repository can install from a stable ref with the documented
configuration and receive a receipt-backed comment. The whole chain worked on a GitHub-hosted
runner it had never run on before: image built from the project's own manifests, head code
executed in `linux-container-v1` with the network blocked, a differential taken six times, a
receipt sealed, a publication policy applied, and one line an author can act on. **Mainline §1
condition 1 holds with its implied criterion, for the first time.**

**Does not establish.** Any recall or precision number — one planted defect, chosen by the
person who wrote the reviewer, is a demonstration and not a sample. Nor that a reader can check
the receipt: §4 says plainly that the bundle does not survive the installation the quickstart
prescribes. And nothing about the six other refusals in the register, none of which fired here.

**Four remote writes, and the end state.**

| write | result |
|---|---|
| workflow → `@v0.1.0-rc.2` on `feature/iphone-demo` | pushed `137c779`, then **reverted** in `fb416cf` |
| branch `attest/owner-placed-regression-2026-09-12` | pushed, then **deleted**; `GET /branches/…` answers 404 |
| pull request #5 | **closed unmerged** 2026-09-07T12:37:05Z; `mergedAt: null` |
| the Action's own comment and inline review | on the record, on a closed pull request |

`us-stock-helper`'s workflow file is now **byte-identical to its state before this drill**
(`git diff d6e9bf0 HEAD` over the workflow is empty): back to `@v0.1.0-pilot.1`, `budget-usd`
0.60, `samples` 4. Nothing else of this project's is in that repository.
