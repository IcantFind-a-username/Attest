# Handoff — 2026-09-11 · the refusal, and the denominator it exposed

`d361198` → `fix/d-185-collect-refusal` · **$1.4297 spent of a $5.00 reservation** ·
full report: [`docs/acceptance/2026-09-11-heldout-after-d186.md`](acceptance/2026-09-11-heldout-after-d186.md)

## The one sentence

**D-185 is repaired and the repair does exactly what it says — 17 of 17 `no JUnit artifact`
verdicts became a stated refusal and no other verdict moved — and the number it lets us re-take
is worse than the one it replaced: 9 of the 16 held-out cases are outside what this product can
review, so the crash-class denominator is 7, not 16, and 2 of the 4 receipts `G-RECALL-002` rests
on came from a `pytest` tree Attest can no longer run.**

## The four decisions you made, recorded

- **D-186** — the narrow repair. A run that collected **no test at all**, in a project whose own
  declaration puts it **outside 3.10–3.13**, is one stated refusal in D-159's register. Both
  facts are required: measured on the 16 cases (docker only, $0.00), fact one holds for exactly
  the 7 unreviewable `pytest` trees and **0 of the 7 whose probe collects** — the other two never
  get an image at all. The supported range is untouched.
- **D-187** — `budget-usd` $1.00 and factory `samples` 5 do not move. A truncation that really
  happens names the unit, the shortfall and the `budget-usd` that would have covered it; nothing
  is said on runs that fit.
- **D-188** — the clean K=4 control arm is not re-run; the 2026-09-10 caveat stands as written.
- **D-189** — found by this run, fixed here. See below.

**D-187 was amended by this branch's own pull request.** The clause first went only into the
review's notes, which the local report renders and the pull-request status does not — so PR #14's
self-review read **3 of 16 units** and told its author `budget-limited` and nothing else, on the
very branch that recorded the decision. A short form now sits inside that status line.

## What the re-measurement says

| | K=4 (2026-09-06) | K=5 (2026-09-10) | **now** |
|---|---|---|---|
| certified | **4 of 16** | 1 of 16 | **2 of 16** |
| reported as a broken host | 1 | 7 | **0** |
| refused, outside the interpreter range | 0 | 0 | **7** |
| refused, image will not build | 0 | 2 | **2** |
| **eligible and supported** | — | — | **7** |
| spend | $1.8347 | $1.6840 | **$1.4297** |

**Four candidate-level changes, and only two of them are D-162's doing:**
`pytest-6197 16694a06e5` and `pytest-7324 78e76aebd9` were receipts at K=4 and are now refused —
those are the two lost to the interpreter range. `pytest-10051 1af71a4893` is D-174's intent
clause, measured last window. `pytest-10356 e9223c7815` **gained** a receipt, and that is
**neither fix**: discovery was replayed byte-identically from the attempt cache, so what differs
is the freshly generated probe. One draw of generation variance, reported as that.

**`G-RECALL-002` can have a number again** — the blocker is gone, every case now reaches a
verdict or a stated refusal. The gate still fails, and its blocker has changed shape: it was
*"the corpus cannot be re-measured"* and it is now *"the corpus is too small once the unsupported
cases are removed"*.

## The defect the run found — D-189, fixed

`pytest-10356` could not be reviewed at all: `run_review` raised `ValueError: delivery member
does not match its ci_final surface decision` **before buying anything**, because the *previous*
review of that case posted one yellow (a) note and no receipt and journalled the note as a
delivery member. `ci_final` records candidates and knows nothing about a `file:line` coordinate.
**D-180's family: the product wrote a row it will refuse to read.** Note members are now skipped
by the reconciliation and, more importantly, kept **out of** the surfaced projection — which is
the precision window the alpha auto-tighten reads. Not reachable on the Action (no ledger
survives a fresh checkout); it bit every corpus driver. Nothing published is impeached.

## Release readiness — the four `FAIL`s

| # | was | **now** |
|---|---|---|
| 1 | held-out recall cannot be re-taken (D-185) | **blocker closed, gate still fails.** Needs a **larger eligible population** — cases whose projects run on 3.10+ |
| 2 | the factory K costs a receipt and nothing says so | **second half closed (D-187)**, first half stands by your decision |
| 3 | no outside repository has had a receipt-backed comment | **unmoved** — you name the repository |
| 4 | control noise at K=5 unmeasured | **unmoved** — ≈$126 at the cap |

Five unpassed gates, unchanged in count.

## Gates

```
python -m pytest --cov=src/attest --cov-report=term-missing
  2,193 passed in 1944.28s, exit 0
  Required test coverage of 90.0% reached. Total coverage: 93.33%
python -m ruff check .        All checks passed!
python -m mypy src/attest     Success: no issues found in 94 source files
git diff --check              clean
```

darwin / CPython 3.12.2 from `requirements-toolchain.lock`, no deselection, at `122abda`.
**No constant moved**: `alpha`, the likelihood ratios, `k_samples`, the hard cap, `budget-usd`
and the supported interpreter range 3.10–3.13 are all untouched.

**The branch carries the two 2026-09-10 commits as well** (`b8d42f9`, `d361198`): that window's
branch was pushed and never had a pull request, and this work builds directly on it — D-186
repairs D-185, and the decision numbering continues from it. Merging this brings both windows to
`main`.

## Owner items — three, each a yes/no with a default

1. **Add supported-interpreter cases to the held-out corpus, so `G-RECALL-002` has a denominator
   worth testing?** *Default: yes.* Seven eligible cases cannot test a ≥70% bar. The cheap
   version is to take the remaining SWE-bench Verified instances whose projects declare 3.10+
   and rebuild the crash-class slice on those; it is a corpus decision, not a code one, and it
   costs about $1 per 10 cases at the current rate.
2. **Wire the five refusals into the pull-request path as well?** *Default: yes, next window.*
   `attest ci` decides only on `preflight`, so `no docker`, `no pytest` and now the interpreter
   refusal reach the ledger and the run status but never the one-line `[silent]` sentence an
   author reads. Pre-existing for the first two; D-186 makes it three. It is an author-visible
   output change and D-142's contract governs that line, so it was left out of a narrow fix.
3. **Raise the development cap?** *Default: no, not yet.* $85.05 of $110 is spent, leaving
   $24.95, and the two things that would consume it — `G-NULL-001` (≈$53) and the K=5 control
   arm (≈$126) — do not fit either way. Nothing this window needs it.
