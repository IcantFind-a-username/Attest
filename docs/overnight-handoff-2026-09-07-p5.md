# Checkpoint — 2026-09-07 p1/p4/p5/p7/p8 (`3781d7d` → `7fd9b7d`)

**Spend $10.43 of the $35 window cap** ($10.3202 for 1.1, $0.1062 for 1.2). Phases
**1.1, 1.2, 4, 5, 7, 8** done and **2.2** answered; 1.3 is running.

## 1.1 — the window's headline: **the budget was not the binding constraint**

[Report](acceptance/2026-09-07-budget-rerun.md) · D-166. The 17 commits of the 40-row table
whose candidates died with the budget gone, re-reviewed at `--budget 1.00`. **17 of 17 ran.**

| | $0.25 | $1.00 |
|---|---|---|
| spend | $1.6352 | **$10.3202** |
| candidates | 105 | **331** |
| red / yellow (a) / yellow (b) / green spoke on | 0 / 0 / 0 / **8** of 17 | 0 / 0 / 0 / **8** of 17 |
| refused **for budget** | 40 | **44** |
| median review elapsed | 29.6 s | 125.2 s |
| image cache lookups / hits | — | **15 / 15** |

**Six times the money, three times the candidates, and not one verdict moved.** Raising the
budget raises discovery, and discovery re-starves the budget. Exactly one candidate reached an
adjudicator that had not before — a `value change, intent unknown` — and it was drawered.

**2.2**: yellow (a)'s three conditions each fire **0 of 17** on the $1.00 table, as at $0.25.

**Reservation exceeded by $0.32**, recorded in DEVSPEND and the backlog: the driver's cap gates
*starting* a unit, not finishing it.

## 1.2 — yellow (b)'s null class, annotation-independent premises: still 0 of 79

[Report](acceptance/2026-09-07-nullability-v2.md) · D-165 · **$0.1062**. Premise (i) now reads a
`None` default, the function's own `is None` test, or a `return None` in the source function's
body. **15 hypotheses (13 before), 0 surviving.** Premise (i) still fails first on 13 of 15 —
and **10 of those name a parameter with no annotation, no `None` default and no `is None` test
anywhere in its function**, so the wall was not only annotations. Written into the README's
limitations and **shelved**.

## 5 — yellow (b)'s second class: exception propagation (D-164)

Free and deterministic; the model writes nothing that decides anything. **0 of 11 forward pairs,
0 of 68 controls, control noise 0%** against the 3% ceiling. Unlike the first class its refusals
are informative: of **198 changed functions**, 135 added no call at all and 43 called a name
defined more than once. Rare, not unverifiable. Twelve REDs.

## 4 — the red-team matrix covers nine attack classes

Five added to the four already dispatched: the controller's key file, a symlink escape, DNS
egress, a tampered sealed bundle (which **produces its own bundle** rather than hoping the
checkout holds one), bounded process exhaustion. The recorded matrix states that **the
external-observer item stays INSUFFICIENT** — every row is observed from inside the product.
`red-team.yml` writes the matrix into `docs/acceptance/`. **Not yet run on a runner.**

## 7 — the release pipeline

Metadata completed, version `0.1.0rc1` in one place, CI builds the wheel and sdist on every push
and runs the built wheel's CLI from a clean environment, `release.yml` attaches both to a `v*`
tag's Release (never PyPI) and refuses a tag whose version disagrees with its wheel, `action.yml`
gained `install-ref`. Thirteen REDs in `tests/release/test_packaging.py`.

## 8 — docs

README top rewritten (four levels in one sentence each, status, format, the empirical table with
D-158's caliber, and the limitations that would change a reader's mind); `docs/faq.md` explains
every drawer reason class; `docs/examples/` carries one real red, yellow and green comment
verbatim; the quickstart was **run on a fresh clone** and its stale output section fixed; the
CHANGELOG has a `v0.1.0-rc.1` entry.

## 9.1 — backlog triage

Two closed (numpy in the container, the truncated bootstrap tail — the latter fixed here with a
RED), priorities on the rest, four added. The **M-01 clean-tree probe is P1**: it has recurred in
four consecutive windows and cost two full-suite runs today.

## Not done yet

- **1.3** is running: the gate shadow over the 13 forward-pair **fix** commits. The re-grade of
  the recorded observations is already done: `$1.00` run **128 witnesses, 47 admissible, 20
  `through_caller`, 0 `through_test_caller`**; the 2026-09-06c four-level subset re-grades to
  **3 `through_caller` + 3 `through_test_caller`**, which is the owner's stated split.
- Nothing is **pushed** yet, and no runner workflow has been dispatched.
- 9.2 (the six conditions and the `v0.1.0-rc.1` tag) is last.
