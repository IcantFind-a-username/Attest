# The held-out corpus, rebuilt for the interpreter the product actually runs

**Owner instruction 2 of this window**, implementing [D-191](../../DECISIONS.md) and recorded as
D-195. D-186 left `G-RECALL-002` with an eligible-and-supported denominator of **7** — too few to
test a ≥70% bar at any confidence worth printing — and two of the four receipts the old number
rested on came from a `pytest` tree the product can no longer run. This is the replacement
population and the number taken on it.

**The one sentence.** On a population four times the size, at the factory configuration, the
crash-class recall is **2 of 28 — 7.1%, Wilson 95% [2.0%, 22.6%]** — and **both receipts come from
the seven cases the old denominator already contained**: the 21 new crash-class cases produced
none. `G-RECALL-002` asks for ≥70% and the interval's *upper* bound is 22.6%, so the gate fails by
a margin no sample size will close. **$4.1384 of the $5.00 reserved**, 35 of 39 cases run.

## 1. How the population was built, all of it before any money

Three filters, in order, none of which calls a model.

**(a) The same held-out slice.** Every case comes from `held_out` in
`benchmarks/attest-v2/splits/swebench-verified-v1.json`, the split committed on 2026-09-02 and
never edited. Nothing that was held out stops being held out, and the dev slice is not touched.

**(b) The declaration screen — free, no docker.** For each instance, `setup.py`, `setup.cfg` and
`pyproject.toml` are read **at that instance's `base_commit`** with `git show`, and
`project_python`'s own rule is applied to them. An instance is kept only when the rule selects an
interpreter inside the supported **3.10–3.13**. This is exactly D-186's refusal, applied before
the spend instead of after it.

| | |
|---|---|
| held-out instances in repositories cloned for this | **330** of 401 (`astropy`, `matplotlib` and `scikit-learn` were not cloned: 71 instances) |
| declaration inside 3.10–3.13 | **101** |
| declared range outside it — D-186's refusal, in advance | **229** |

**(c) The evaluability probe — free, docker only, no model call.** For each surviving instance the
case is built (base = `base_commit` + the gold code patch, head = base + its revert), the base
tree is archived out of the repository into the work root (D-138 moved bind-mount sources out of
`/Users/…` for a reason), the image **the product itself would build** is built from it, and a
collect-only runs inside it under the product's isolation flags — in the reproduction's own
shape: the stub in `.attest-repro/`, `rootdir` and `confcutdir` pinned to the tree.

**The probe was wrong on its first draft, and how it was wrong is the useful part.** It ran a
plain `pytest --collect-only` without the reproduction's environment, and `psf__requests-5414` —
a case that certifies in every column that could ever run it — came back *uncollectable*, because
an incompatible pin from the project's own `requirements-dev.txt` failed at pytest's plugin
autoload. A probe that does not run the environment the product runs is measuring a different
question. With `PYTEST_DISABLE_PLUGIN_AUTOLOAD`, `PYTHONSAFEPATH` and the tree's own import roots
— what `_reproduction_environment` sets — it agrees.

Of the 39 non-`django` instances that passed (b), **39 of 39 passed (c)**. The declaration screen
alone predicted evaluability perfectly on this sample: every project whose manifests name an
interpreter the product supports also built its image and collected. `django`'s 62 screened
instances were not probed — 39 already exceeds D-191's target of 20, and eight repositories is a
better population than one repository plus seven.

## 2. The corpus

**39 cases, eight repositories**, at [`.attest/corpora/heldout-supported-v1/plan.json`](../../.attest/corpora/heldout-supported-v1/plan.json),
each carrying its upstream `base_commit`, the case's own base and head shas, the interpreter its
manifests selected and the reason.

| repository | cases |
|---|---|
| `sympy/sympy` | 10 |
| `pydata/xarray` | 9 |
| `sphinx-doc/sphinx` | 7 |
| `pylint-dev/pylint` | 6 |
| `mwaskom/seaborn` | 2 |
| `psf/requests` | 2 |
| `pytest-dev/pytest` | 2 |
| `pallets/flask` | 1 |

**The run order is fixed in the plan, before the run: round robin over repositories**, each
repository's cases by instance id. The run carries a cumulative cap and may stop part way; in
plain id order the cap would drop whole repositories off the end of the alphabet, and *which*
repositories the sample contained would then be a function of how much the earlier cases happened
to cost.

## 3. How each case is classified — by what its own run observed

D-158 governs what this corpus may be a denominator for: **crash/exception-class recall only.**
A case is put in one of four buckets, after the fact, from its own ledger:

| bucket | rule | counts toward |
|---|---|---|
| **refused** | a stated refusal before any evidence could exist — the interpreter range, an image that will not build, an unavailable executor | nothing: a refusal is neither a miss nor a detection |
| **value class** | the run reached `value change confirmed, intent unknown` — behaviour changed, nothing was raised, and the intent clause refused because the base tree does not say what the value should be | excluded from the crash denominator, and **not** a value-class recall figure either: this corpus is reversed by construction (D-158) |
| **crash class, certified** | a receipt | numerator **and** denominator |
| **crash class, no receipt** | reached a verdict, no receipt, not a value-class observation | denominator |

The screen and the probe are why the *refused* bucket should be near-empty: D-186's refusal was
applied before the money rather than after it.


## 4. The run

| | |
|---|---|
| configuration | **factory**: `--k 5` (the shipped `samples`, D-183), `--budget 1.00`, containers (`linux-container-v1`) |
| publication surface | **none** — local review only; no GitHub client is constructed |
| product code | `c958fb7`, the tree merged to `main` as `e8d3448` |
| cases run | **35 of 39**; the cumulative cap stopped the run before four |
| spend | **$4.138447** of the **$5.00** reserved; $0.861553 released |
| largest single review | $0.4613 (`pydata__xarray-6992`) |
| the stop, verbatim | `unit sympy__sympy-24443: skipped: cumulative cap: $4.1384 spent, reserving $1.0000 for this unit would project $5.1384 past the $5.00 cap` |

The four unattempted cases are named rather than dropped (D-172): `sympy__sympy-24443`,
`pydata__xarray-7393`, `sympy__sympy-24539`, `sympy__sympy-24562`.

## 5. The number

| | old slice (`.d186`, 2026-09-11) | **this corpus** |
|---|---|---|
| cases run | 16 | **35** |
| refused before any evidence | 9 | **0** |
| value class, excluded (D-158) | — | **7** |
| **crash-class denominator** | **7** | **28** |
| **certified** | **2** | **2** |
| point estimate | 28.6% | **7.1%** |
| Wilson 95% | [8.2%, 64.1%] | **[2.0%, 22.6%]** |
| `G-RECALL-002`'s ≥70% point bar | fail | **fail** |
| `G-RECALL-002`'s ≥50% clustered lower bound | fail | **fail** |

**The comparison that matters is not 28.6% → 7.1%.** All seven cases of the old denominator are
in this corpus — they are exactly the seven that survived D-186's refusal — and **both receipts
are theirs**: `psf__requests-5414` (`520c57974d`) and `pytest-dev__pytest-10356` (`e9223c7815`),
the same two candidate ids the `.d186` column certified. Of the **21 new crash-class cases**, the
product certified **zero**. The old figure was two receipts over a denominator small enough to
flatter them; the honest reading is that the denominator grew by 21 and the numerator did not
move at all.

**Zero refusals.** Every one of the 35 reached a verdict. That is the screen and the probe doing
their job: D-186's refusal was applied before the money instead of after it, so no dollar bought a
case the product was going to decline.

## 6. Where the receipts are lost, over all 56 verification attempts

| attempts | outcome |
|---|---|
| **17** | **the generated probe does not collect** — `pytest collection/import/syntax or infrastructure failure (exit code 2)` on base |
| **12** | **the process guard: the reproduction attempted to create a child process** |
| **8** | intent: value change confirmed, intent unknown |
| **5** | **the process guard: the reproduction attempted to create a thread** |
| 3 | unfaithful generated test |
| 3 | intent: the diff states its own intent |
| 2 | probe recorded no observation on base |
| **2** | **reproduced** |
| 2 | intent: behaviour change confirmed, intent unknown (D-102) |
| 1 | probe observation not stable on base |
| 1 | changed lines not executed |

**Two categories are 34 of 56 attempts, and neither is the intent clause.**

- **The generated probe does not collect (17).** The *stub* collects — the free probe proved that
  for all 39 cases before a dollar was spent — but the probe the model writes does not, because it
  imports something the tree cannot import in that shape. This is D-114's territory and it is now
  the single largest loss.
- **The process guard refuses a probe on base (17).** `seaborn`, `sphinx` and several others spawn
  a thread or a child process **during an ordinary import**, and the containment that exists to
  stop *head* code from doing it refuses the probe on the **merge base**, where there is no
  untrusted code to contain — the base is the revision the defect was fixed in. Every one of these
  is a case the product declined to look at for a reason that has nothing to do with the diff.

The intent clause, which the last three windows treated as the main cost, accounts for **13 of
56** and only **8** of those are the value class D-158 already excludes from this denominator.

## 7. Per case

| case | class | candidates | attempts | certified | published | candidate id(s) | first failure category | spend |
|---|---|---|---|---|---|---|---|---|
| `mwaskom__seaborn-3069` | crash class, no receipt | 2 | 2 | 0 | 0 | — | other x2 | $0.1815 |
| `pallets__flask-5014` | crash class, no receipt | 1 | 1 | 0 | 0 | — | other x1 | $0.0696 |
| `psf__requests-5414` | crash class, certified | 1 | 1 | 1 | 1 | `520c57974d` | — | $0.0394 |
| `pydata__xarray-4687` | crash class, no receipt | 2 | 2 | 0 | 0 | — | collection failure x2 | $0.1945 |
| `pylint-dev__pylint-4661` | crash class, no receipt | 1 | 1 | 0 | 0 | — | collection failure x1 | $0.0248 |
| `pytest-dev__pytest-10051` | crash class, no receipt | 2 | 2 | 0 | 0 | — | unfaithful test x2 | $0.1009 |
| `sphinx-doc__sphinx-10435` | crash class, no receipt | 4 | 3 | 0 | 0 | — | other x3 | $0.2413 |
| `sympy__sympy-22914` | crash class, no receipt | 1 | 1 | 0 | 0 | — | changed lines not executed x1 | $0.0472 |
| `mwaskom__seaborn-3187` | crash class, no receipt | 3 | 3 | 0 | 0 | — | other x3 | $0.1743 |
| `psf__requests-6028` | crash class, no receipt | 1 | 1 | 0 | 0 | — | unfaithful test x1 | $0.0319 |
| `pydata__xarray-6461` | crash class, no receipt | 1 | 1 | 0 | 0 | — | collection failure x1 | $0.1103 |
| `pylint-dev__pylint-6528` | crash class, no receipt | 1 | 1 | 0 | 0 | — | other x1 | $0.0564 |
| `pytest-dev__pytest-10356` | crash class, certified | 3 | 3 | 1 | 1 | `e9223c7815` | other x2 | $0.1663 |
| `sphinx-doc__sphinx-10449` | crash class, no receipt | 2 | 2 | 0 | 0 | — | other x2 | $0.1550 |
| `sympy__sympy-23262` | value class | 2 | 2 | 0 | 0 | — | behavior change, intent unknown x2 | $0.1067 |
| `pydata__xarray-6599` | crash class, no receipt | 1 | 1 | 0 | 0 | — | collection failure x1 | $0.0883 |
| `pylint-dev__pylint-6903` | crash class, no receipt | 1 | 1 | 0 | 0 | — | other x1 | $0.0429 |
| `sphinx-doc__sphinx-10466` | value class | 1 | 1 | 0 | 0 | — | behavior change, intent unknown x1 | $0.0613 |
| `sympy__sympy-23413` | crash class, no receipt | 1 | 1 | 0 | 0 | — | other x1 | $0.0893 |
| `pydata__xarray-6721` | crash class, no receipt | 1 | 1 | 0 | 0 | — | collection failure x1 | $0.1036 |
| `pylint-dev__pylint-7080` | value class | 1 | 1 | 0 | 0 | — | behavior change, intent unknown x1 | $0.0373 |
| `sphinx-doc__sphinx-10614` | crash class, no receipt | 2 | 2 | 0 | 0 | — | other x2 | $0.2383 |
| `sympy__sympy-23534` | value class | 1 | 1 | 0 | 0 | — | behavior change, intent unknown x1 | $0.0711 |
| `pydata__xarray-6744` | crash class, no receipt | 2 | 2 | 0 | 0 | — | collection failure x2 | $0.1310 |
| `pylint-dev__pylint-7277` | value class | 1 | 1 | 0 | 0 | — | behavior change, intent unknown x1 | $0.0527 |
| `sphinx-doc__sphinx-11445` | crash class, no receipt | 6 | 3 | 0 | 0 | — | other x3 | $0.1432 |
| `sympy__sympy-23824` | value class | 1 | 1 | 0 | 0 | — | behavior change, intent unknown x1 | $0.1053 |
| `pydata__xarray-6938` | crash class, no receipt | 4 | 4 | 0 | 0 | — | collection failure x4 | $0.3270 |
| `pylint-dev__pylint-8898` | value class | 1 | 1 | 0 | 0 | — | behavior change, intent unknown x1 | $0.0511 |
| `sphinx-doc__sphinx-11510` | crash class, no receipt | 1 | 1 | 0 | 0 | — | other x1 | $0.0895 |
| `sympy__sympy-23950` | crash class, no receipt | 1 | 1 | 0 | 0 | — | behavior change, intent unknown x1 | $0.0388 |
| `pydata__xarray-6992` | crash class, no receipt | 10 | 4 | 0 | 0 | — | collection failure x4 | $0.4613 |
| `sphinx-doc__sphinx-9711` | crash class, no receipt | 1 | 1 | 0 | 0 | — | other x1 | $0.0569 |
| `sympy__sympy-24213` | crash class, no receipt | 1 | 1 | 0 | 0 | — | behavior change, intent unknown x1 | $0.0871 |
| `pydata__xarray-7229` | crash class, no receipt | 1 | 1 | 0 | 0 | — | collection failure x1 | $0.1623 |

## 8. What this establishes, and what it does not

**Establishes.** `G-RECALL-002` now has a number over a population that was pre-specified,
screened for supportability before anything was bought, drawn from the same held-out slice, and
spread over eight repositories. **It fails the gate, and it fails it by a margin no sample size
closes.** It also says *where*: two mechanical categories, not the adjudicator, hold 61% of the
attempts.

**Does not establish.** Any precision or control figure — no controls were run in this item, and
the last measured red control arm is at K=4 (D-188, D-196). Nor a value-class recall: seven cases
reached that observation and D-158 forbids reading them as a rate on a corpus reversed by
construction. Nor anything about the four cases the cap stopped, or about `django`, `astropy`,
`matplotlib` and `scikit-learn`, none of which was probed.

**One operational note.** `sympy__sympy-23262` took **18m 47s** against a 20–135 s norm for every
other case. A stack sample showed two worker threads contending for the GIL inside a list
comprehension while a third waited on the provider; nothing was wrong, the tree is simply large.
The driver has no per-case wall-clock limit, so a slower case than this one would stall a run
rather than fail it.
