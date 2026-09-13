# The forty under D-245, 2026-09-14 — the tree index, case by case against the 12 of 40

**0.3.0 step 4, the owner instruction of 2026-09-14.** Run [`34736200356`](https://github.com/IcantFind-a-username/Attest/actions/runs/34736200356), `mutation-recall.yml` over all 40 cases into `trials-with-index.jsonl`, the code of `main` at `a16312a` (D-245: the tree index, the package block by import distance, the literals hint), $1.00 per case, K=5, `linux-container-v1`, both yellow switches on, the local review path -- no GitHub client, nothing written anywhere. **The same forty as every run before it: the code changed and the corpus did not.** The reservation that admitted each case was the D-244 p95: **$0.0970** from 169 trials of history, under the $1.00 ceiling and the $5.00 cap; **0 case(s) refused by the cap**, 0 not run for another reason. **$2.8245 in all.** Compared case by case with the D-240 run (`trials-search-v3b.jsonl`, runs [`34711985142`](https://github.com/IcantFind-a-username/Attest/actions/runs/34711985142) and [`34712819526`](https://github.com/IcantFind-a-username/Attest/actions/runs/34712819526), $2.7521, §1e of the [2026-09-13 report](2026-09-13-mutation-recall.md)). The denominator is forty whatever the cap or the runner did; a case not run keeps its latest class.

## 1. The number, and the boundary thirteen in their own column

AGENTS.md §9: one re-run of a forty-case corpus moves about ±2 cases on its own, so the net count is reported beside the gained and lost lists and a change is attributed only case by case (§3, §4).

|  | D-240 run (before) | D-245 run (after) | boundary, of 13 (before) | boundary, of 13 (after) |
|---|---|---|---|---|
| certified | **12** | **11** | **1** | **1** |
| point estimate | 30.0% | **27.5%** | 7.7% | **7.7%** |
| Wilson 95% | [18.1%, 45.4%] | **[16.1%, 42.8%]** | — | — |
| value class | 16 | 19 | 7 | 8 |
| no receipt | 11 | 10 | 4 | 4 |
| no reproduction attempted | 1 | 0 | 1 | 0 |
| drawer (D-232 or a statement) | 0 | 0 | 0 | 0 |
| record a probe on the merge base | 31 | 33 | 9 | 10 |
| a probe made the two revisions differ | 31 | 33 | 9 | 10 |
| spend | $2.7521 | $2.8245 | $0.8394 | $0.8506 |

Cases newly certified: **1** (`more-itertools-none_guard-17--forward`); cases that lost a receipt: **2** (`urllib3-none_guard-15--forward`, `python-dotenv-guard_raise-04--forward`); net -1. Cases, never candidates: an extra receipt inside a case already certified counts for nothing here. The other two strata: `guard_raise` 6 → 5 of 17, `none_guard` 5 → 5 of 10.

## 2. Every case, against the 12 of 40

`boundary` marks the thirteen of that stratum. *before* is the case's class in the D-240 run; *after* its class now; *recordings* is how many probes recorded on the merge base; *why now* is the wording that decided the class.

| case | boundary | before | after | recordings | verifications | lines | why now | spend |
|---|---|---|---|---|---|---|---|---|
| `attrs-boundary-09--forward` | ✓ | no receipt | no receipt | 0 | 1 | none | 3 probes tried and none produced a differential: 3 recorded nothing usable on the merge base -- probe did not execute src/attr/_compat.py on base, so it recorde | $0.0529 |
| `click-boundary-07--forward` | ✓ | value class | value class | 1 | 1 | value 1 | intent: value change confirmed, intent unknown: the base tree does not specify the value this assertion pins about the symbol this change touched -- no base tes | $0.0667 |
| `itsdangerous-boundary-07--forward` | ✓ | certified | certified | 1 | 1 | red 1 | head FAIL 3/3, base PASS 3/3 | $0.0560 |
| `jinja-boundary-09--forward` | ✓ | no reproduction attempted | **value class** | 1 | 1 | value 1 | intent: value change confirmed, intent unknown: the base tree does not specify the value this assertion pins about the symbol this change touched -- no base tes | $0.0552 |
| `more-itertools-boundary-08--forward` | ✓ | no receipt | no receipt | 0 | 1 | none | 3 probes tried and none produced a differential: 2 reached the changed lines and observed no difference; 1 recorded nothing usable on the merge base -- probe re | $0.0864 |
| `packaging-boundary-08--forward` | ✓ | value class | value class | 1 | 1 | value 1 | intent: value change confirmed, intent unknown: the base tree does not specify the value this assertion pins about the symbol this change touched -- no base tes | $0.0438 |
| `python-dotenv-boundary-06--forward` | ✓ | value class | value class | 1 | 1 | value 1 | intent: value change confirmed, intent unknown: the base tree does not specify the value this assertion pins about the symbol this change touched -- no base tes | $0.0549 |
| `urllib3-boundary-07--forward` | ✓ | value class | value class | 1 | 1 | value 1 | intent: value change confirmed, intent unknown: the base tree does not specify the value this assertion pins about the symbol this change touched -- no base tes | $0.0808 |
| `attrs-guard_raise-03--forward` |  | value class | value class | 1 | 1 | value 1 | intent: value change confirmed, intent unknown: the base tree does not specify the value this assertion pins about the symbol this change touched -- no base tes | $0.0862 |
| `click-boundary-10--forward` | ✓ | value class | value class | 1 | 1 | value 1 | intent: value change confirmed, intent unknown: the failing assertion pins only a generic constant, which almost any tree asserts somewhere and which therefore  | $0.0793 |
| `itsdangerous-guard_raise-01--forward` |  | value class | value class | 1 | 1 | value 1 | intent: value change confirmed, intent unknown: the base tree does not specify the value this assertion pins about the symbol this change touched -- no base tes | $0.0545 |
| `jinja-boundary-12--forward` | ✓ | value class | value class | 1 | 1 | value 1 | intent: value change confirmed, intent unknown: the base tree does not specify the value this assertion pins about the symbol this change touched -- no base tes | $0.0712 |
| `more-itertools-boundary-10--forward` | ✓ | no receipt | no receipt | 1 | 1 | none | intent: value change confirmed, no symbol to specify: this change touches no function or class of the anchored file, so no test, docstring or document can speci | $0.0793 |
| `packaging-boundary-11--forward` | ✓ | no receipt | no receipt | 0 | 1 | none | 3 probes tried and none produced a differential: 3 reached the changed lines and observed no difference | $0.0840 |
| `python-dotenv-boundary-08--forward` | ✓ | value class | value class | 1 | 1 | value 1 | intent: value change confirmed, intent unknown: the base tree does not specify the value this assertion pins about the symbol this change touched -- no base tes | $0.0400 |
| `urllib3-guard_raise-03--forward` |  | value class | value class | 1 | 1 | value 1 | intent: value change confirmed, intent unknown: the base tree does not specify the value this assertion pins about the symbol this change touched -- no base tes | $0.0779 |
| `attrs-none_guard-14--forward` |  | certified | certified | 1 | 1 | red 1 | head FAIL 3/3, base PASS 3/3 | $0.0725 |
| `click-guard_raise-03--forward` |  | no receipt | no receipt | 0 | 1 | impact 1 | 3 probes tried and none produced a differential: 3 reached the changed lines and observed no difference | $0.1211 |
| `itsdangerous-guard_raise-04--forward` |  | no receipt | no receipt | 0 | 2 | none | 3 probes tried and none produced a differential: 1 did not reach the changed lines; 2 reached the changed lines and observed no difference | $0.1432 |
| `jinja-guard_raise-01--forward` |  | value class | value class | 1 | 1 | value 1 | intent: value change confirmed, intent unknown: the base tree does not specify the value this assertion pins about the symbol this change touched -- no base tes | $0.0527 |
| `more-itertools-guard_raise-04--forward` |  | no receipt | no receipt | 1 | 1 | none | intent: value change confirmed, no symbol to specify: this change touches no function or class of the anchored file, so no test, docstring or document can speci | $0.0601 |
| `packaging-guard_raise-01--forward` |  | certified | certified | 1 | 1 | red 1 | head FAIL 3/3, base PASS 3/3 | $0.0639 |
| `python-dotenv-guard_raise-01--forward` |  | certified | certified | 1 | 1 | red 1 | head FAIL 3/3, base PASS 3/3 | $0.0709 |
| `urllib3-guard_raise-04--forward` |  | certified | certified | 1 | 1 | red 1 | head FAIL 3/3, base PASS 3/3 | $0.0778 |
| `attrs-none_guard-15--forward` |  | certified | certified | 1 | 1 | red 1 | head FAIL 3/3, base PASS 3/3 | $0.0370 |
| `click-guard_raise-05--forward` |  | value class | value class | 1 | 1 | impact 1, value 1 | intent: value change confirmed, intent unknown: the base tree does not specify the value this assertion pins about the symbol this change touched -- no base tes | $0.0940 |
| `itsdangerous-guard_raise-05--forward` |  | certified | certified | 1 | 1 | red 1 | head FAIL 3/3, base PASS 3/3 | $0.0571 |
| `jinja-none_guard-13--forward` |  | value class | value class | 1 | 1 | value 1 | intent: value change confirmed, intent unknown: the base tree does not specify the value this assertion pins about the symbol this change touched -- no base tes | $0.0613 |
| `more-itertools-guard_raise-05--forward` |  | no receipt | no receipt | 1 | 1 | none | intent: value change confirmed, no symbol to specify: this change touches no function or class of the anchored file, so no test, docstring or document can speci | $0.0677 |
| `packaging-guard_raise-06--forward` |  | value class | value class | 1 | 1 | value 1 | intent: value change confirmed, intent unknown: the base tree does not specify the value this assertion pins about the symbol this change touched -- no base tes | $0.0531 |
| `python-dotenv-guard_raise-02--forward` |  | value class | value class | 2 | 2 | value 1 | intent: value change confirmed, intent unknown: the base tree does not specify the value this assertion pins about the symbol this change touched -- no base tes | $0.0863 |
| `urllib3-none_guard-15--forward` |  | certified | **value class** | 1 | 1 | value 1 | intent: value change confirmed, intent unknown: the base tree does not specify the value this assertion pins about the symbol this change touched -- no base tes | $0.0792 |
| `attrs-none_guard-17--forward` |  | certified | certified | 1 | 1 | red 1 | head FAIL 3/3, base PASS 3/3 | $0.0495 |
| `click-none_guard-15--forward` |  | no receipt | no receipt | 0 | 1 | none | generation failed: ProbeRefused: probe setup assigns an attribute of the imported name _ti (_ti.isatty = lambda stream: True); replacing part of the tree before | $0.0909 |
| `itsdangerous-guard_raise-06--forward` |  | certified | certified | 1 | 1 | red 1 | head FAIL 3/3, base PASS 3/3 | $0.0589 |
| `jinja-none_guard-14--forward` |  | certified | certified | 1 | 1 | red 1 | head FAIL 3/3, base PASS 3/3 | $0.0712 |
| `more-itertools-none_guard-17--forward` |  | no receipt | **certified** | 1 | 1 | red 1 | head FAIL 3/3, base PASS 3/3 | $0.0716 |
| `packaging-none_guard-13--forward` |  | no receipt | no receipt | 0 | 1 | none | 3 probes tried and none produced a differential: 2 did not reach the changed lines; 1 reached the changed lines and observed no difference | $0.1035 |
| `python-dotenv-guard_raise-04--forward` |  | certified | **value class** | 1 | 1 | value 1 | intent: value change confirmed, intent unknown: the base tree does not specify the value this assertion pins about the symbol this change touched -- no base tes | $0.0457 |
| `urllib3-none_guard-18--forward` |  | value class | value class | 1 | 1 | value 1 | intent: value change confirmed, intent unknown: the failing assertion pins only a generic constant, which almost any tree asserts somewhere and which therefore  | $0.0661 |

## 3. The cases newly certified: what the probe used

For each case that certifies now and did not in the D-240 run, read from the run's ledger and from the case's own tree rebuilt locally at the same site: the literals the D-245 hint offered for the changed definitions (the executor's own `_literal_arguments` on the head tree), the boundary D-240 named, the probe whose recording certified, whether that probe's text carries one of the offered literals or one of the named values, the call sites the index resolved for the changed symbols (`exact` through an import binding, `attribute` on an untyped receiver whose file imports the module), and how many caller snippets the planner put in the discovery context before and after. A literal in the probe's text is a fact about the text, not proof of where the model got it; the reading is below the table.

| case | stratum | literals the hint offered | the boundary D-240 named | the certifying probe | offered literal in the probe | named value in the probe | index call sites (exact / attribute) | caller snippets in the plan (before → after) |
|---|---|---|---|---|---|---|---|---|
| `more-itertools-none_guard-17--forward` | none_guard | none | in `repeatfunc`: the guard `times is None` was removed (it returned early) | ` ⏎ mi.take(6, mi.repeatfunc(add, None, 3, 5))` | no | no | 0 / 0 | 2 → **0** |


**Reading.** The one case gained is not this decision's. `more-itertools-none_guard-17` certified on
the original run and under D-238, lost its receipt under D-240 (three probes: two reached the changed
lines and saw no difference, one was unstable on the merge base) and has it back now with
`mi.take(6, mi.repeatfunc(add, None, 3, 5))`. The probe passed `None`, the value the D-240
conditions block names -- *the guard `times is None` was removed (it returned early)* -- and that
block was in the D-240 run's prompt too. The D-245 hint offered no literal (the tree's only callers
of `repeatfunc` are its tests, which the index reports separately, and they pass it no literal), the
index resolved no call site, and the two caller snippets the regex had put in the plan became none.
What differs between the two runs is the second probe's choice, which is the search's own variance.

## 4. The cases that lost a receipt: jitter, or a squeezed context

For each case certified in the D-240 run and not now, the two runs' figures side by side: the discovery context the planner built (characters, caller snippets, what it omitted), whether discovery read every unit under the budget, how many candidates were proposed and eligible, how many probes recorded and whether any made the revisions differ, and the spend. A context that grew or an omission that appeared is the mark of a squeezed context; the same figures with a different outcome is the search's and discovery's own variance, the ±2 of AGENTS.md §9. The reading is below the table.

| case | stratum | before → after | why now | context chars (before → after) | caller snippets (before → after) | omissions (before → after) | discovery read (before → after) | candidates / eligible (before → after) | probes recorded, differing (before → after) | discovery input tokens (before → after) | spend (before → after) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `urllib3-none_guard-15--forward` | none_guard | certified → **value class** | intent: value change confirmed, intent unknown: the base tree does not specify the value this assertion pins about the symbol this change to | 1209 → 1209 | 0 → 0 | none → none | 1 of 1 → 1 of 1 | 1 / 1 → 1 / 1 | 1, 1 → 1, 1 | 7490 → 7490 | $0.0778 → $0.0792 |
| `python-dotenv-guard_raise-04--forward` | guard_raise | certified → **value class** | intent: value change confirmed, intent unknown: the base tree does not specify the value this assertion pins about the symbol this change to | 1975 → **837** | 4 → **0** | 8 further caller(s) of read_regex omitted → none | 1 of 1 → 1 of 1 | 1 / 1 → 1 / 1 | 1, 1 → 1, 1 | 9250 → 6865 | $0.0493 → $0.0457 |

- `urllib3-none_guard-15--forward`: the probe that certified before -- `d = HTTPHeaderDict(a='1') ⏎ 5 \| d`; the probes now -- `d = HTTPHeaderDict(Cookie='foo') ⏎ d.__ror__(5)` (base value, head value).
- `python-dotenv-guard_raise-04--forward`: the probe that certified before -- `content = "A='unterminated\n" stream = io.StringIO(content) ⏎ list(parse_stream(stream))`; the probes now -- `reader = Reader(io.StringIO("'unterminated\n")) pattern = re.compile(r"'([^']+)'") ⏎ reader.read_regex(pattern)` (base exception, head exception).

**Reading.** One of the two is jitter and one is the index's declared bound. Neither is a squeezed
context: no context grew, no omission appeared, no discovery run was budget-limited or cut at
`max_tokens` in either run, and the D-245 contexts are smaller, not fuller (§7).

- `urllib3-none_guard-15` -- **jitter.** The discovery context is the same to the byte (1,209
  characters, no caller snippet, 7,490 discovery tokens both times), one candidate, one eligible, one
  probe recorded each time. The D-240 run's probe wrote `5 | d`: the merge base raised `TypeError`
  (its `__ror__` guard returns `NotImplemented`, which the operator turns into a rejection), and a
  base test's `pytest.raises(TypeError)` specifies that under D-240 (b). This run's probe wrote
  `d.__ror__(5)`: the merge base returned `NotImplemented` as a value, which no base test asserts, so
  the same behaviour change is the value class. The hint's first literal, `Cookie='foo'`, is in the
  probe -- the D-245 hint was read, and the receipt was lost on the call's form, not its input.
- `python-dotenv-guard_raise-04` -- **the index's bound, not a squeeze.** `parser.py` calls
  `reader.read_regex(...)` twelve times from its module-level `parse_*` functions, on a parameter
  annotated `Reader` that the index does not type; the attribute rule counts such a call only from a
  file that imports the defining module, and this file *is* the defining module. The regex had found
  them (four snippets and *8 further callers omitted*); the index reports none, and the discovery
  context fell from 1,975 to 837 characters. The D-240 run's probe went in through a caller,
  `list(parse_stream(stream))` on `"A='unterminated\n"`: the merge base returned a binding list where
  head raised `AttributeError`, a crash receipt. This run's probe called `reader.read_regex(pattern)`
  directly, and the merge base raised `Error` on the same input -- the deleted guard's own rejection --
  so head's `AttributeError` against base's `Error` is a changed value with unknown intent. D-245 says
  a caller reached through an object passed in from elsewhere is not found; here the object is the
  module's own reader, and the cost is a receipt. One case cannot separate this from variance, but the
  mechanism is readable in both ledgers, and it names the next repair: a parameter annotated with an
  in-tree class is a typed receiver the index could resolve.

## 5. The boundary thirteen

The stratum D-245 was expected to move most: a `>=`/`>` swap changes behaviour on one input, and the literals hint names the inputs the tree already passes. *boundary hit* is §1f's reading -- a probe whose head observation differs from its base observation found the input; *offered literal in a probe* and *named value in a probe* are read over every probe the case recorded, not only the certifying one.

| case | before | after | boundary hit (before → after) | literals the hint offered | offered literal in a probe | named value in a probe | why now |
|---|---|---|---|---|---|---|---|
| `attrs-boundary-09--forward` | no receipt | no receipt | yes → no | none | no | no | 3 probes tried and none produced a differential: 3 recorded nothing usable on the merge base -- probe did not execute src/attr/_compat.py on |
| `click-boundary-07--forward` | value class | value class | yes → yes | none | no | `0` | intent: value change confirmed, intent unknown: the base tree does not specify the value this assertion pins about the symbol this change to |
| `itsdangerous-boundary-07--forward` | certified | certified | yes → yes | `max_age=10`, `return_timestamp=True` | `max_age=10` | no | head FAIL 3/3, base PASS 3/3 |
| `jinja-boundary-09--forward` | no reproduction attempted | **value class** | no → yes | none | no | no | intent: value change confirmed, intent unknown: the base tree does not specify the value this assertion pins about the symbol this change to |
| `more-itertools-boundary-08--forward` | no receipt | no receipt | no → no | none | no | no | 3 probes tried and none produced a differential: 2 reached the changed lines and observed no difference; 1 recorded nothing usable on the me |
| `packaging-boundary-08--forward` | value class | value class | yes → yes | none | no | no | intent: value change confirmed, intent unknown: the base tree does not specify the value this assertion pins about the symbol this change to |
| `python-dotenv-boundary-06--forward` | value class | value class | yes → yes | none | no | no | intent: value change confirmed, intent unknown: the base tree does not specify the value this assertion pins about the symbol this change to |
| `urllib3-boundary-07--forward` | value class | value class | yes → yes | `5`, `0` | no | no | intent: value change confirmed, intent unknown: the base tree does not specify the value this assertion pins about the symbol this change to |
| `click-boundary-10--forward` | value class | value class | yes → yes | `1`, `2`, `3` | `1`, `2`, `3` | no | intent: value change confirmed, intent unknown: the failing assertion pins only a generic constant, which almost any tree asserts somewhere  |
| `jinja-boundary-12--forward` | value class | value class | yes → yes | none | no | no | intent: value change confirmed, intent unknown: the base tree does not specify the value this assertion pins about the symbol this change to |
| `more-itertools-boundary-10--forward` | no receipt | no receipt | no → yes | none | no | `0` | intent: value change confirmed, no symbol to specify: this change touches no function or class of the anchored file, so no test, docstring o |
| `packaging-boundary-11--forward` | no receipt | no receipt | no → no | none | no | no | 3 probes tried and none produced a differential: 3 reached the changed lines and observed no difference |
| `python-dotenv-boundary-08--forward` | value class | value class | yes → yes | none | no | no | intent: value change confirmed, intent unknown: the base tree does not specify the value this assertion pins about the symbol this change to |

|  | cases |
|---|---|
| the hint offered at least one literal | 3 of 13 |
| a probe carried an offered literal | 2 of 13 |
| a probe carried a value the moved condition named | 2 of 13 |
| a probe made the two revisions differ | 10 of 13 (9 before) |
| certified | 1 of 13 (1 before) |

**Reading.** The literals hint reached the boundary class less than expected and changed nothing on
it. It offered a literal in 3 of the 13 -- `itsdangerous-boundary-07` (`max_age=10`,
`return_timestamp=True`), `urllib3-boundary-07` (`5`, `0`), `click-boundary-10` (`1`, `2`, `3`) --
because the changed definitions of the other ten take no literal from any in-tree call the index
resolves; two of the three probes carried an offered literal, and the one certified case of the class
is the one that always was, `itsdangerous-boundary-07`, certified before the hint existed (1 of 13 on
the original run and under D-240, 2 of 13 under D-238 when `jinja-boundary-09` certified once). Ten of
the thirteen probes now find the input on which the two revisions differ (nine before:
`jinja-boundary-09` and `more-itertools-boundary-10` hit it now, `attrs-boundary-09` no longer
executes the module's import-time constant), and eight of the ten are drawered as the value class
because no base test asserts the value the probe pinned about the touched symbol (D-127, D-174), one
more than in the D-240 run. The search is not the wall on this class, as §1f of the 2026-09-13 report
found; a hint that names the inputs the tree already passes cannot make a test assert the value a
boundary swap changes.

## 6. Spend, and the reservation that admitted each case

|  |  |
|---|---|
| cases run | 40 of 40 |
| reservation per case (D-244 p95 of the most recent 169 trials) | $0.0970 (ceiling $1.00) |
| refused by the $5.00 cap | 0 |
| spend, all cases | $2.8245 (D-240 run: $2.7521) |
| per case: mean, median, largest | $0.0706, $0.0709, $0.1432 (`itsdangerous-guard_raise-04--forward`) |
| cases above the reservation | 3 |
| by stage (D-243) | discovery $0.9786, probe $1.8460 |
| the driver's cap summary | cap $5.00; reservation $0.0970 per unit; started 40; refused 0; spent $2.824511 |

## 7. What is and is not claimed

- **Nothing on the forty is attributable to D-245, in either direction.** 12 → 11 is inside the ±2 a
  re-run moves on its own (AGENTS.md §9); the one case gained used a value D-240 named, and of the two
  lost one is the search's variance under an identical context and one is the index's declared bound
  with a receipt on it.
- **The index reports fewer callers than the regex did**: 76 → 34 caller snippets over the forty, 17
  plans smaller and one larger (`click-boundary-10`, where the generic-name gate had refused to search
  `update`), and every *further caller(s) omitted* omission is gone; the discovery input fell 5%
  (461k → 437k tokens) and the run cost $2.8245 against $2.7521, the probe stage $1.8460 of it by
  D-243's breakdown. Whether the callers dropped were signal or noise is answered here for one case
  (python-dotenv: signal). The real-PR batches, where the generic-name gate and the alphabetical
  package block were the complaint, are unmeasured under it.
- **The literals hint is read and buys nothing on this corpus.** A probe carried an offered literal
  in 9 of 40 cases: four stayed certified, four stayed the value class, one lost its receipt; none
  changed class upward. The boundary class is 1 of 13.
- **The p95 reservation did what D-244 says**: $0.0970 per case from 169 trials of history, 40 of 40
  admitted under the $5.00 cap, nothing refused, three cases above the reservation and the largest at
  $0.1432, nowhere near the $1.00 ceiling.
- **Not natural traffic, and not comparable to the held-out figure**, as the 2026-09-13 report says.
  A case the cap refused or the runner could not build would be a miss; there was none.
- **README's recall line stays at 12 of 40** by the owner's instruction; the figure of record for
  this code is this report's 11 of 40, and the two are one re-run apart.
