# The binding layer, the exception hierarchy, and two statistics that were wrong

**2026-09-08 · D-174.** Everything in this report is **free**: `ast`, `git`, and ledgers already
on disk. **$0.00 spent, no model call, no execution, no network.** Driver:
`scripts/corpus/binding_recount.py`; data
[`evidence/2026-09-08-binding-recount.json`](evidence/2026-09-08-binding-recount.json).

Four things were asked of code that already existed. Two were defects with a counterexample each
— an exception a function catches itself, and two different functions normalising identically.
Two were claims this repository had written down and never checked: what a call site is, and what
the published `alpha` bounds. Both claims turned out to be wrong, and correcting them moves two
numbers the acceptance gates cite.

## 1. A call site was whatever wrote the name

Four modules asked *which definition does this name refer to?* and four of them answered by
comparing bare strings. `src/attest/review/binding.py` is now the one answer:
`resolve(Reference) -> Target | None`, supporting module-level `def`s of the referring file,
`from m import f [as g]`, `import m [as n]` then `m.f`, absolute and relative imports resolved by
**dotted suffix** (`src/` and `lib/` are layout, not packages; two files matching one suffix are
ambiguous), and `self.`/`cls.` to the innermost enclosing class of the same file. It refuses
inheritance, decorators, re-exports a package `__init__` does not define, calls through
variables, dynamic attributes, every bare name of a file holding `from m import *`, a name bound
twice in one file, and a name an enclosing function binds locally.

### The re-count the owner asked for: 224 new-code candidates

The static `through_caller` witness of [2026-09-05](2026-09-05-gate-shadow.md), re-run over the
same 224 recorded candidates of E-04 stratum v2, from the same 25 commits of the same three
repositories.

| | candidates | (a) a call site outside the added lines |
|---|---|---|
| recorded 2026-09-05, name-matched | 224 | **24 (10.7%)** |
| re-run, name-matched (this harness) | 224 | 23 |
| re-run, **bound** | 224 | **0 (0.0%)** |

**Every one of the 24 was a name collision.** Three examples, each checked by hand:

- `src/corum/dependence.py::_validate_examples` was witnessed at
  `src/corum/calibration.py:162` — where `calibration.py` defines its **own**
  `_validate_examples` at line 48 and calls that one;
- `scripts/release/drill.py::main` was witnessed at
  `scripts/acceptance/m01_offline_measurement_probe.py:379` — that script's own `main`;
- `services/…/tests/test_snapshot_contract_v3.py::_service` was witnessed in a different test
  file's own `_service` fixture.

The harness reproduces 23 of the recorded 24 rather than all of them. The 24th is
`super().__init__(...)` matched against a symbol named `__init__` anchored in a test file;
`dotted_name` refuses an attribute chain whose base is a call, so it is dropped on shape before
binding is consulted. It is refused either way.

### And the 9 that the cumulative gate figure rests on

`G-NEWCODE-001`'s pilot progress cites **9 of 314 (2.9%)** from
[2026-09-06c](2026-09-06c-gate-shadow.md). Re-adjudicated:

| witness | old call site | under binding |
|---|---|---|
| `click src/click/_termui_impl.py:391 __init__` | `src/click/_compat.py:69` | refused |
| `click src/click/exceptions.py:258 __init__` | `src/click/_compat.py:69` | refused |
| `click src/click/exceptions.py:264 __init__` | `src/click/_compat.py:69` | refused |
| `attest src/attest/github/presentation.py:186 _anchored` | `src/attest/review/executor.py:2216` | refused |
| `attest src/attest/github/presentation.py:188 _anchored` | `src/attest/review/executor.py:2216` | refused |
| `attest src/attest/review/impact.py:160 is_test_path` | `src/attest/review/structural.py:263` | refused |
| `corum src/corum/fusion.py:494/505/511 fuse_known_pair_likelihoods` | `tests/test_fusion.py:859` | **kept** (3) |

**6 of 9 were name collisions.** The 3 that survive are one symbol whose only caller is
`tests/test_fusion.py` — which D-166 already grades `through_test_caller` and never publishes.

### And the whole cumulative table

`G-NEWCODE-001` records **26 of 445 (5.8%)** across four populations. Re-adjudicated, all four:

| population | candidates | recorded `through_caller` | under binding |
|---|---|---|---|
| E-04 stratum v2 (2026-09-05) | 224 | 24 static (10.7%) | **0** |
| 11 forward pairs + 40 owner commits + 10 `corum` (2026-09-06c) | 90 | 6 | **0** |
| the 17 budget-starved commits at `--budget 1.00` (2026-09-07) | 128 | 20 | **0** |
| the 13 forward-pair fix commits (2026-09-07) | 3 | 0 | 0 |
| **cumulative** | **445** | **26 (5.8%)** | **0 (0.0%)** |

The 20 of the budget re-run are the same shape as the rest: `nasdaq.py::_parse_rss` witnessed
in `generic.py`, which holds its own `_parse_rss`; a test helper named `sample` witnessed in a
script's own `sample`; `output_contract.py::check` witnessed at `drill.check(...)`, a method on
a local variable. **Not one recorded new-code candidate has ever produced a publishing-grade
witness**, and `2.9%` and `5.8%` are rates of name matches.

Driver: `scripts/corpus/binding_recount.py`, data
[`evidence/2026-09-08-binding-recount.json`](evidence/2026-09-08-binding-recount.json). It
reports **29 recorded and 3 kept**, where the gate table reports 26: the shadow evidence files
were written before D-166 split `through_test_caller` out, so they record all 9 of the
2026-09-06c observations as `through_caller`. The 3 the driver keeps are exactly the 3 the gate
table already counts as `through_test_caller`. Of the **26** that are `through_caller` under
today's grading, **0** survive.

### What the resolution costs in wall clock

One extra parse per file, and the resolution itself. On this repository's own tree — **232
Python files** — `build_call_graph` takes **2.35 s** including binding, against 6.38 s to read
the files off disk; **10,384 of 33,812** written call sites resolve (31%), the rest being the
standard library, third-party packages, and methods on local variables. The levels that use it
are still free of model, execution and network cost.

### The four policy versions this moves

`attest.impact.caller-scope.v2`, `attest.propagation.unhandled-exception.v2`,
`attest.structural.duplicate-implementation.v2` and `attest.intent.v4.2`. A note or receipt
recorded under an earlier version keeps its own rules (D-121); nothing already written is
re-judged.

### What it buys back

It is not only a subtraction. `from mathlib import sqrt as root; root(v)` is now a call site of
`sqrt` and was invisible before — the old index stored the name as written and nothing ever
wrote `sqrt`. Propagation's `43 of 198 changed functions refused because the callee's name is
defined more than once` is likewise mostly not ambiguity: a second definition in a file the
caller does not import is nothing to choose between.

## 2. A `raise` a function catches itself was counted as raised

`_raised_types` read every `raise` statement in a body. `exception_caught(handlers, raised)` is
new and three-valued — **True**, **False**, and **undecidable**:

- a bare `except:`, `except Exception` or `except BaseException` catches everything;
- the same name catches it;
- `builtins` decides the rest, so `except LookupError` catches a `KeyError`;
- `except ProjectError` against a `StorageError` is `None`, and **`None` is never read as
  "unhandled"**.

A `try` guards its **body**: a `raise` in an `except` clause, an `else` or a `finally` still
escapes it. Policy `attest.propagation.unhandled-exception.v2`.

## 3. `charge(...)` and `refund(...)` normalised identically

The green level's docstring said callee names were kept. Only **attribute** callees were; a
bare-name call was erased to `NAME`, so a body that charges and a body that refunds measured
**1.000**. `normalize` now emits `CALLEE:<name>`, everything the call passes is normalised as
before, and renaming every local still leaves a copy a copy. The evidence sentence said
"attribute and callee names are **not**" — the opposite of both the docstring and the intent.
Policy `attest.structural.duplicate-implementation.v2`.

## 4. Two statistics

### `hard_cap * alpha` was not a pull-request bound

D-125 said per-unit Bonferroni gives `alpha` within a unit and `hard_cap * alpha` across a pull
request, because at most `hard_cap` claims are visible. **The cap truncates the display, not the
search.** A Monte-Carlo over the real `select_for_publication` — 10 units, `alpha = 0.1`, one
candidate each whose e-value is valid under the null (10 with probability 0.1, else 0):

| | |
|---|---|
| measured publish-something rate over 4,000 trials | **0.65** |
| analytic `1 - 0.9**10` | 0.651 |
| the bound D-125 claimed (`hard_cap * alpha`) | 0.30 |
| the bound that holds (`min(1, U * alpha)`) | 1.00 |

`Selection` now carries `units_searched`, `pr_error_bound` and `e_value_validity`; the
`publication_policy` ledger row records all three at
`attest.publication-policy.v3`. **No threshold, `alpha`, likelihood ratio, `K` or cap moved.**

### The factor table is not a valid e-value, and the controls say so directly

Every candidate of every control review on disk — the eight `G-NULL-001a` null repositories,
**276 review runs, 475 candidates**. Each candidate's S·T wealth with V divided out — and
**not one of the 475 ever bought V**: every one records `channels_bought == ["S"]`, so no
division was needed and T never fired on a control either.

| | |
|---|---|
| n | **475** |
| mean | **2.274** |
| 95% CI | **[2.238, 2.310]** |
| sd | 0.403 |
| one-sample *t* against 1.0 | **68.9** |
| minimum observed | **2.000** |
| maximum observed | 3.000 |

| S·T wealth | candidates | share |
|---|---|---|
| 2.000 | 318 | 66.9% |
| 2.639 | 71 | 14.9% |
| 2.949 | 23 | 4.8% |
| 3.000 | 63 | 13.3% |

| repository | n | mean |
|---|---|---|
| attrs | 22 | 2.376 |
| click | 317 | 2.163 |
| itsdangerous | 33 | 2.418 |
| jinja | 24 | 2.516 |
| more-itertools | 35 | 2.623 |
| packaging | 7 | 2.707 |
| python-dotenv | 6 | 2.759 |
| urllib3 | 31 | 2.413 |

**One version.** Every one of the 475 was produced under the same frozen D-007 factor table
(`src/attest/review/channels.py` has one commit in its history) and the same
`claude-sonnet-5` / `claude-opus-5` pair, so the grouping by version is a single group and is
reported as one.

**A valid e-value satisfies `E[X] <= 1` under the null. This one has a measured mean of 2.27 and
a measured *minimum of 2.0*: it cannot go below 1 at all**, because S prices only positive
evidence and a candidate that exists has at least one vote (LR 2). Every one of these 475 is a
null candidate by construction — a control commit has no defect to find.

**The interval is decoration and the minimum is the finding.** The 276 runs are not 276 distinct
controls: the two preregistered populations hold 58 and 68 commits, and several were re-reviewed
under successive rule versions, so the 475 candidates are not independent draws and the CI and
the *t* are quoted for shape only. None of that matters to the conclusion. The refutation is
structural — a quantity whose support starts at 2 cannot have expectation ≤ 1 — and no sample
size, and no correction for dependence, would change it.

Two consequences, neither of them a code change here:

1. the `m_u / alpha` threshold is a threshold on a quantity that is not an e-value, so the
   `alpha` reading of it is not licensed. It is a fixed likelihood-ratio bar with a calibration
   claim attached to it, and `e_value_validity: "assumed-calibrated"` now says so on every row;
2. **no published receipt is impeached by this.** All 475 controls bought **S only**; S·T tops
   out at `S_CAP * T_CAP = 9` against a bar of `m_u / alpha >= 10` at the factory `alpha = 0.1`,
   so S·T alone has never published anything and cannot. Every publication this product has made
   rests on V — a differential execution — which is what `docs/architecture` already said carries
   the empirical signal. **The margin is one unit of wealth and it is arithmetic, not an
   invariant** (AGENTS §4): at `alpha >= 1/9` the bar for a single-candidate unit falls to 9 or
   below and S·T alone would clear it. Nothing in this change alters `alpha`; the point is that
   the protection is a coincidence of the factory numbers and should be read as one.

Owner item: whether to price the factors as a real e-process, restore a PR-level `alpha`, or
keep the current bar and the stated caveat. That is §16 and is not an agent's call.

## Which measured ceilings survive, and one that does not

Every level in this repository was enabled against a measured **control-noise rate** — the share
of null commits on which it speaks. If a change can only make a level quieter, those ceilings
remain valid upper bounds and nothing has to be re-run. Checked one at a time:

- **impact (a1–a4)** — **monotone down.** `callers_of` returns a subset of what it returned
  (bound sites are a subset of name-matched sites), so `untested` is a subset, `arity_breaks` is
  a subset, and a4's fan-out counts can only fall; `named_by_a_test_directly` reads `mentions`,
  which is untouched. Every note produced under v2 would have been produced under v1. a4's
  **2.9% of 68 controls** therefore still bounds it, conservatively.
- **structural (green)** — **monotone down.** Two bodies calling the *same* function get the
  same token at the same position, so their similarity is unchanged; two calling *different*
  functions get a mismatching token where they had a matching one, so it falls. A pair that
  clears the threshold under v2 cleared it under v1.
- **intent (red's value class)** — **monotone down.** v4.2 only removes sites from
  `find_specifications`, and fewer specifications means more drawers.
- **gate** — **monotone down**, measured above: 26 witnesses to 0.
- **propagation (yellow (b))** — **not monotone, and this is stated rather than assumed.**
  Premise (i) compares the calls a change *added*, and it now compares expressions as written
  rather than bare names: a base `read(x)` rewritten to `self.read(x)` was "no call added" under
  v1 and *is* an added call under v2. The other two premises still have to hold, so a new note is
  unlikely — but the class's **0 of 79 controls is a v1 measurement and does not carry over**.
  The class reaches no author-visible surface (D-164, `PROPAGATION_SHADOW`), so nothing an author
  reads depends on it; re-measuring it is free and belongs to whichever window next runs a scan.

## What was not changed

`alpha`, the likelihood ratio, `K`, the family policy, the hard cap, `PROPOSAL_SHARE`, the
verification cap, `ENABLED_CONDITIONS`, and every threshold in the tree.
