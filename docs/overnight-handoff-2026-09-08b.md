# Handoff — 2026-09-08b, the read-only review's repairs (baseline `d058c58`)

Branch `fix/d-174-binding-and-bounds`, one commit, **not pushed**.

**Spend $0.00.** No provider is constructed anywhere in this window; every measurement is `ast`,
`git`, or a ledger already on disk. No remote write, no push. Six items instructed, six done.
Detail in **D-174** and [the report](acceptance/2026-09-08-binding-and-bounds.md); driver
`scripts/corpus/binding_recount.py`, data
[`evidence/2026-09-08-binding-recount.json`](acceptance/evidence/2026-09-08-binding-recount.json).

## What was confirmed, and what it cost

| # | item | RED observed | outcome |
|---|---|---|---|
| 1 | shared binding layer + 4 consumers | 26 tests; 3 impact, 1 propagation, 1 gate | **confirmed** — `attest.review.binding` |
| 2 | escaping-raise semantics | 4 of 6 | **confirmed** — `unhandled-exception.v2` |
| 3 | `CALLEE:` token | 2 of 3 | **confirmed** — `duplicate-implementation.v2` |
| 4a | `hard_cap * alpha` | 2 of 3 (the Monte-Carlo passed on first write, at 0.65) | **confirmed wrong** — withdrawn, `publication-policy.v3` |
| 4b | e-value assumption | n/a (measurement) | **falsified** — see below |
| 4c | D-111 K=4 vs K=5 | n/a | **confirmed** — amendment is the live arithmetic |
| 5 | discovery schedule | n/a | **already done** (D-168); verified, not re-implemented |
| 6 | documentation | n/a | D-174, CHANGELOG, README, mainline, roadmap, architecture, `G-CERT-004`, `G-NEWCODE-001` |

A fifth version moved that the instruction did not name: **`attest.impact.caller-scope.v2`**.
The impact level's notes changed meaning, and leaving them at v1 would have made two
incomparable things share a version. One pre-existing broken relative link in D-170 was fixed
in passing; the whole tree's markdown links now resolve.

**Policy versions moved:** `attest.impact.caller-scope.v2`,
`attest.propagation.unhandled-exception.v2`, `attest.structural.duplicate-implementation.v2`,
`attest.intent.v4.2`. A note or receipt recorded under an earlier version keeps its own rules.

## The two numbers that changed a claim

**Gate reachability was measuring name collisions.** Re-adjudicating every recorded
`through_caller` witness — **445 new-code candidates, 4 populations, 26 witnesses** —
under name binding, **all 26 fall**. `_validate_examples` was witnessed in a file holding its
own `_validate_examples`; `drill.py::main` in another script's `main`;
`output_contract.py::check` at `drill.check(...)`, a method on a local variable. The three
`through_test_caller` observations stand and never publish. `G-NEWCODE-001`'s pilot progress is
**0 of 445**, not 26 (5.8%).

**The factor table is not a valid e-value.** Over every control review on disk — 276 runs, **475
candidates** — the S·T wealth has mean **2.274**, CI [2.238, 2.310], and a **minimum of 2.000**.
It cannot fall below 1 at all: S prices only positive evidence and a candidate that exists has
one vote (LR 2). Structural, not statistical — the 475 are not independent draws and no *n*
changes a support that starts at 2. Related, and measured on the real selector: the pull-request
bound is `min(1, U * alpha)`, **0.65** for ten units at α = 0.1, not the `hard_cap * alpha` = 0.30
D-125 claimed. **No published receipt is impeached**: S·T tops out at 9 against a bar of 10 at the
factory alpha, so every publication rests on V — a one-unit margin that is arithmetic, not an
invariant (at `alpha >= 1/9` it would vanish).

## Positives retained, abstentions added

Retained: an imported call site is still a caller (and an **aliased** one now is, which is new
recall); `except ValueError` still does not catch `KeyError`; a `raise` in an `except` clause
still escapes; renaming every local still measures 1.000; `assert convert.convert(1) == 7` and
`from convert import convert; assert convert(1) == 7` are both specifications.

Added abstentions: inheritance, decorators, package re-exports, calls through variables, any
bare name in a file with a star import, a name bound twice in one file, a name an enclosing
function binds locally; an undecidable exception relation; a base-tree assertion whose scope
does not name the anchored symbol; a change that touches no def or class at all.

## Measured ceilings

Four of the five level changes are **monotone down** — any note they produce now would have been
produced before — so a4's 2.9%-of-68 control rate, green's, and the value class's remain valid
upper bounds without re-running anything. **Propagation is the exception**: premise (i) now
compares call expressions as written, so `read(x)` → `self.read(x)` is an added call where it
was not, and its **0 of 79 controls is a v1 number that does not carry over**. It is shadow-only,
so nothing an author reads depends on it; re-measuring is free.

## Not proven

- **e-value validity** — falsified for S·T, not repaired. `e_value_validity` is
  `assumed-calibrated` on every row.
- **Concurrency speed-up** — untouched this window; `repro_concurrency = 1` remains the pinned
  default (D-157).
- **Multi-model gain** — the statement stays *same model, K samples, correlated ranking, not an
  independent vote*. D-113's Opus `0 → 2` is now marked **`n = 1`**: one case, one run per model,
  different budgets. It is a pair of observations, not an effect size.

## Gates

`python -m pytest --cov=src/attest --cov-report=term-missing` on darwin / CPython 3.12.2 from
`requirements-toolchain.lock`, no deselection: **2,142 passed, 0 failed, 0 skipped, exit 0**
(2,087 at `d058c58`; the 55 new tests are this window's REDs). Kernel + execution coverage
**93.25%** against the 90% floor — `attest.certification` and `attest.execution` only, as
`G-CODE-001` defines it. Informational: review 87%, cli 91%, github 93%, benchmark 89%, core 99%.
`ruff check .` clean, `mypy src/attest` clean over 94 files, `git diff --check` clean, and every
relative markdown link in the tree resolves (one pre-existing break in D-170 fixed).

**`-q` hides the count line** (the same trap as the 2026-09-08 window): the run's own tail ends
at the coverage threshold, so the 2,142 above is the dot count against `--collect-only`, and the
authority is exit 0 with zero `F` and zero `E` in the progress stream.

## Owner items

1. **PR-level `alpha`.** Restore a pull-request-level rate (split `alpha` across units, giving
   back the `m/alpha` bar D-125 replaced), or keep per-unit control and the reported
   `min(1, U*alpha)`? **Default: keep, and report.**
2. **The e-value result.** Price the factors as a real e-process (both directions, so wealth can
   fall below 1), or keep the current bar as an explicitly calibration-assuming likelihood-ratio
   threshold? **Default: keep and state, since V carries every publication.**
3. **Push.** These commits are local. **Default: do not push.**
