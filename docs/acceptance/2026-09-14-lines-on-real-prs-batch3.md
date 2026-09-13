# Lines on real pull requests, batch 3 — twenty-four merged pull requests of six libraries the probe kept

**Owner instruction 2 of 2026-09-14.** One paid run on the declared CI platform, the local review path — no GitHub client, nothing written to any repository — with `value_notes_visible` and `gate_notes_visible` on, `per_pr_budget_usd` $1.00, K=5, `linux-container-v1`, under the code of `main` at `153937bc`: D-235 to D-244 in force, `attest.intent.v5.1`, and the value line carrying how its call was built (D-241) for the first time on traffic the product had never seen. The population is the six of eight candidate libraries whose free evaluability probe passed ([protocol](../../benchmarks/studies/e05-external-v3/protocol.md)); four merged pull requests each, frozen at `8b828f45cbddc024` before any ran. **The owner adjudicates every line below before reading the agent's opinion of any of them**; the ledgers came back, so every drawer observation is read to its reason.

- **run D (six libraries)** — run [`34717191401`](https://github.com/IcantFind-a-username/Attest/actions/runs/34717191401), study `e05-external-v3`: 24 units run, 4 with at least one line, 7 lines (value 7), 20 drawer observations, $2.3848.

**Wrong = 0 is the owner's to establish, not this report's.** Every line below has three empty columns.

## 1. Every line, verbatim — the owner fills the last three columns

| # | run | pull request | level | the line, as it would have been shown | what stands behind it | useful | true but useless | wrong |
|---|---|---|---|---|---|---|---|---|
| 1 | run D (six libraries) | `Delgan/loguru#1504` | value | [yellow] loguru/_string_parsers.py:198 — for _string_parsers.parse_duration('1e400s'), the merge base raised OverflowError and head raises ValueError (3/3 and 3/3 runs each side); no base test, docstring or changelog pins either — note b83ef8427231 | note b83ef8427231 — `_string_parsers.parse_duration('1e400s')`; base exception: OverflowError; head exception: ValueError; 3/3 head, 3/3 base; drawer: intent: behavior change confirmed, intent unknown: head raises ValueError from a raise statement on a changed line; the rejected input is not in the base tree's tests, fixtures or documentation (行为变化已证实，意图未知) | | | |
| 2 | run D (six libraries) | `Delgan/loguru#1508` | value | [yellow] loguru/_datetime.py:114 — for format(dt, 'x'), the merge base returned '-500000' and head returns '-1500000' (3/3 and 3/3 runs each side); no base test, docstring or changelog pins either — note 7472fb676667 | note 7472fb676667 — `format(dt, 'x')`; base value: '-500000'; head value: '-1500000'; 3/3 head, 3/3 base; drawer: intent: value change confirmed, intent unknown: the base tree does not specify the value this assertion pins about the symbol this change touched -- no base test asserts it and no docstring or documentation writes it down (返回值变化已证实，意图未知) | | | |
| 3 | run D (six libraries) | `marshmallow-code/marshmallow#3024` | value | [yellow] src/marshmallow/utils.py:97 — for utils.get_value(obj, 1), the merge base returned 2 and head raises TypeError (3/3 and 3/3 runs each side); no base test, docstring or changelog pins either — note b205e48ce0b7 | note b205e48ce0b7 — `utils.get_value(obj, 1)`; base value: 2; head exception: TypeError; 3/3 head, 3/3 base; drawer: intent: behavior change confirmed, intent unknown: head raises TypeError from a call or expression on a changed line; no rejected input could be identified from the test's literals (行为变化已证实，意图未知) | | | |
| 4 | run D (six libraries) | `marshmallow-code/marshmallow#3024` | value | [yellow] src/marshmallow/utils.py:108 — for utils.get_value(obj, key), the merge base returned {'x': 42} and head raises TypeError (3/3 and 3/3 runs each side); no base test, docstring or changelog pins either — note 2c14b8263a28 | note 2c14b8263a28 — `utils.get_value(obj, key)`; base value: {'x': 42}; head exception: TypeError; 3/3 head, 3/3 base; drawer: intent: behavior change confirmed, intent unknown: head raises TypeError from a call or expression on a changed line; no rejected input could be identified from the test's literals (行为变化已证实，意图未知) | | | |
| 5 | run D (six libraries) | `marshmallow-code/marshmallow#3024` | value | [yellow] src/marshmallow/utils.py:106 — for utils.get_value(obj, 0), the merge base returned {'x': 42} and head raises TypeError (3/3 and 3/3 runs each side); no base test, docstring or changelog pins either — note e6453ddab7ce | note e6453ddab7ce — `utils.get_value(obj, 0)`; base value: {'x': 42}; head exception: TypeError; 3/3 head, 3/3 base; drawer: intent: behavior change confirmed, intent unknown: head raises TypeError from a call or expression on a changed line; no rejected input could be identified from the test's literals (行为变化已证实，意图未知) | | | |
| 6 | run D (six libraries) | `mahmoud/boltons#467` | value | [yellow] boltons/statsutils.py:564 — for s.get_histogram_counts(), the merge base raised ZeroDivisionError and head returns [(0.0, 11)] (3/3 and 3/3 runs each side); no base test, docstring or changelog pins either — note 8b21aa6e8626 | note 8b21aa6e8626 — `s.get_histogram_counts()`; base exception: ZeroDivisionError; head value: [(0.0, 11)]; 3/3 head, 3/3 base; drawer: intent: value change confirmed, intent unknown: the base tree does not specify the value this assertion pins about the symbol this change touched -- no base test asserts it and no docstring or documentation writes it down (返回值变化已证实，意图未知) | | | |
| 7 | run D (six libraries) | `mahmoud/boltons#467` | value | [yellow] boltons/statsutils.py:563 — for s._get_bin_bounds(), the merge base raised ZeroDivisionError and head returns [5.0] (3/3 and 3/3 runs each side); no base test, docstring or changelog pins either — note 3b750bb997b9 | note 3b750bb997b9 — `s._get_bin_bounds()`; base exception: ZeroDivisionError; head value: [5.0]; 3/3 head, 3/3 base; drawer: intent: value change confirmed, intent unknown: the base tree does not specify the value this assertion pins about the symbol this change touched -- no base test asserts it and no docstring or documentation writes it down (返回值变化已证实，意图未知) | | | |

## 2. One row per pull request

### run D (six libraries)

| pull request | cand | elig | att | cert | drawers | red | value | gate | yellow (a) | units read | spend |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `Delgan/loguru#1510` | 3 | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 1 of 1 | $0.1222 |
| `mahmoud/boltons#481` | 6 | 6 | 5 | 0 | 4 | 0 | 0 | 0 | 0 | 1 of 2 (budget-limited) | $0.2806 |
| `marshmallow-code/marshmallow#3034` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 2 of 2 | $0.0444 |
| `pyparsing/pyparsing#653` | 13 | 7 | 3 | 0 | 3 | 0 | 0 | 0 | 0 | 1 of 1 | $0.2033 |
| `python-babel/babel#1318` | 2 | 2 | 2 | 0 | 1 | 0 | 0 | 0 | 0 | 1 of 1 | $0.1461 |
| `tkem/cachetools#413` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 of 1 | $0.0121 |
| `Delgan/loguru#1504` | 1 | 1 | 1 | 0 | 1 | 0 | 1 | 0 | 0 | 1 of 1 | $0.0748 |
| `mahmoud/boltons#434` | 10 | 8 | 3 | 0 | 2 | 0 | 0 | 0 | 0 | 1 of 10 (budget-limited) | $0.2796 |
| `marshmallow-code/marshmallow#3004` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 of 1 | $0.0117 |
| `pyparsing/pyparsing#645` | 8 | 8 | 6 | 0 | 2 | 0 | 0 | 0 | 0 | 1 of 1 | $0.3729 |
| `python-babel/babel#1319` | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 of 1 | $0.0205 |
| `tkem/cachetools#386` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 of 1 | $0.0149 |
| `Delgan/loguru#1508` | 1 | 1 | 1 | 0 | 1 | 0 | 1 | 0 | 0 | 1 of 1 | $0.0812 |
| `mahmoud/boltons#475` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 of 1 | $0.0106 |
| `marshmallow-code/marshmallow#3024` | 5 | 5 | 3 | 0 | 3 | 0 | 3 | 0 | 0 | 1 of 1 | $0.1621 |
| `pyparsing/pyparsing#649` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 of 1 | $0.0126 |
| `python-babel/babel#1161` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 2 of 5 (budget-limited) | $0.0707 |
| `tkem/cachetools#365` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 of 1 | $0.0064 |
| `Delgan/loguru#1507` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 of 1 | $0.0125 |
| `mahmoud/boltons#467` | 3 | 3 | 3 | 0 | 3 | 0 | 2 | 0 | 0 | 1 of 1 | $0.1449 |
| `marshmallow-code/marshmallow#3016` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 of 1 | $0.0175 |
| `pyparsing/pyparsing#648` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 of 1 | $0.0089 |
| `python-babel/babel#1291` | 2 | 2 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 1 of 1 | $0.2683 |
| `tkem/cachetools#340` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 of 1 | $0.0060 |


## 3. Where every drawer observation went, read from the ledger

A drawer observation is a `verification` row of evidence class `behavior_change` whose outcome is not `reproduced`: the differential was real and the intent clause would not publish it. D-218 writes a value note only for the two drawers whose intent is *unreadable* (`value change confirmed, intent unknown` and `behavior change confirmed, intent unknown`); the drawer `intent stated in the change itself` means the author already said what they meant, and D-218 deliberately writes nothing for it. A written note is then shown only when it is not anchored inside `tests/`, is the first for its `(path, expression)`, and the contract admits the line (D-222).

| run | pull request | candidate | drawer | fate | detail |
|---|---|---|---|---|---|
| run D (six libraries) | `mahmoud/boltons#481` | `f4c9722cab` | intent stated in the change itself | note not written: drawer excluded by D-218 (intent stated / constant / unanchored) | intent stated in the change itself |
| run D (six libraries) | `mahmoud/boltons#481` | `3c92444661` | intent stated in the change itself | note not written: drawer excluded by D-218 (intent stated / constant / unanchored) | intent stated in the change itself |
| run D (six libraries) | `mahmoud/boltons#481` | `688548cad6` | intent stated in the change itself | note not written: drawer excluded by D-218 (intent stated / constant / unanchored) | intent stated in the change itself |
| run D (six libraries) | `mahmoud/boltons#481` | `a43b2529dc` | intent stated in the change itself | note not written: drawer excluded by D-218 (intent stated / constant / unanchored) | intent stated in the change itself |
| run D (six libraries) | `pyparsing/pyparsing#653` | `8b31a0f024` | intent stated in the change itself | note not written: drawer excluded by D-218 (intent stated / constant / unanchored) | intent stated in the change itself |
| run D (six libraries) | `pyparsing/pyparsing#653` | `1ff4305a83` | intent stated in the change itself | note not written: drawer excluded by D-218 (intent stated / constant / unanchored) | intent stated in the change itself |
| run D (six libraries) | `pyparsing/pyparsing#653` | `052074725f` | intent stated in the change itself | note not written: drawer excluded by D-218 (intent stated / constant / unanchored) | intent stated in the change itself |
| run D (six libraries) | `python-babel/babel#1318` | `6084e20573` | intent stated in the change itself | note not written: drawer excluded by D-218 (intent stated / constant / unanchored) | intent stated in the change itself |
| run D (six libraries) | `Delgan/loguru#1504` | `97bc7930e8` | behavior change confirmed, intent unknown | shown as a line |  |
| run D (six libraries) | `mahmoud/boltons#434` | `a8e7349bae` | intent stated in the change itself | note not written: drawer excluded by D-218 (intent stated / constant / unanchored) | intent stated in the change itself |
| run D (six libraries) | `mahmoud/boltons#434` | `e7b5d1c5d3` | intent stated in the change itself | note not written: drawer excluded by D-218 (intent stated / constant / unanchored) | intent stated in the change itself |
| run D (six libraries) | `pyparsing/pyparsing#645` | `f6677f2c17` | intent stated in the change itself | note not written: drawer excluded by D-218 (intent stated / constant / unanchored) | intent stated in the change itself |
| run D (six libraries) | `pyparsing/pyparsing#645` | `882dc9ae4e` | intent stated in the change itself | note not written: drawer excluded by D-218 (intent stated / constant / unanchored) | intent stated in the change itself |
| run D (six libraries) | `Delgan/loguru#1508` | `6a921f8d27` | value change confirmed, intent unknown | shown as a line |  |
| run D (six libraries) | `marshmallow-code/marshmallow#3024` | `498f1199b4` | behavior change confirmed, intent unknown | shown as a line |  |
| run D (six libraries) | `marshmallow-code/marshmallow#3024` | `83bcdb72c4` | behavior change confirmed, intent unknown | shown as a line |  |
| run D (six libraries) | `marshmallow-code/marshmallow#3024` | `41a685599a` | behavior change confirmed, intent unknown | shown as a line |  |
| run D (six libraries) | `mahmoud/boltons#467` | `a4f48fa271` | value change confirmed, intent unknown | shown as a line |  |
| run D (six libraries) | `mahmoud/boltons#467` | `0b105d1cda` | value change confirmed, intent unknown | note written, filtered: duplicate (path, expression) | boltons/statsutils.py / s.get_histogram_counts() |
| run D (six libraries) | `mahmoud/boltons#467` | `1272d28113` | value change confirmed, intent unknown | shown as a line |  |

Fates, counted:

- run D (six libraries): **12** — note not written: drawer excluded by D-218 (intent stated / constant / unanchored)
- run D (six libraries): **1** — note written, filtered: duplicate (path, expression)
- run D (six libraries): **7** — shown as a line

## 4. The run, in one column

| | run D (six libraries) |
|---|---|
| units run | 24 |
| candidates | 55 |
| eligible | 44 |
| reproductions attempted | 30 |
| certified | 0 |
| drawer observations | 20 |
| pull requests with a line | 4 |
| lines | 7 |
| spend | $2.3848 |

