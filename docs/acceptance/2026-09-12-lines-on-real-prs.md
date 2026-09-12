# Lines on real pull requests, 2026-09-12 — the owner's five and the eight libraries' twenty-four

**Work order PR 3 f of the 2026-09-12 overnight window.** Two paid runs on the declared CI platform, both on the local review path — no GitHub client, nothing written to any repository — with `value_notes_visible` and `gate_notes_visible` on, `per_pr_budget_usd` $1.00, K=5, `linux-container-v1`. **This time the ledgers came back**, so every drawer observation that did not become a line is read to its reason rather than guessed at (D-225 could not).

- **run A (the owner's five)** — run [`34646556092`](https://github.com/IcantFind-a-username/Attest/actions/runs/34646556092), study `e04-prospective-v3`: 2 units run, 0 with at least one line, 0 lines (none), 1 drawer observations, $0.6536.
- **run B (eight libraries)** — run [`34650336318`](https://github.com/IcantFind-a-username/Attest/actions/runs/34650336318), study `e05-external-v1`: 24 units run, 4 with at least one line, 6 lines (value 2, red 2, impact 2), 7 drawer observations, $2.7248.

**Wrong = 0 is the owner's to establish, not this report's.** Every line below has three empty columns.

## 1. Every line, verbatim — the owner fills the last three columns

| # | run | pull request | level | the line, as it would have been shown | what stands behind it | useful | true but useless | wrong |
|---|---|---|---|---|---|---|---|---|
| 1 | run B (eight libraries) | `more-itertools/more-itertools#1270` | value | [yellow] more_itertools/more.py:4955 — for list(g), the merge base returned [(b'12345', b'123')] and head raises ValueError (3/3 and 3/3 runs each side); no base test, docstring or changelog pins either — note 85d0b40bda6d | note 85d0b40bda6d — `list(g)`; base value: [(b'12345', b'123')]; head exception: ValueError; 3/3 head, 3/3 base; drawer: intent: behavior change confirmed, intent unknown: head raises ValueError from a raise statement on a changed line; no rejected input could be identified from the test's literals (行为变化已证实，意图未知) | | | |
| 2 | run B (eight libraries) | `python-attrs/attrs#1603` | red | [red] src/attr/_make.py:3115 — Factory.__setstate__ was changed to zip with strict=True, which will now raise ValueError instead of silently ignoring extra or missing values when unpickling Factory objects pickled with a different attrs version. — receipt 5e6243428178 | receipt 5e6243428178, regression_reproduced | | | |
| 3 | run B (eight libraries) | `python-attrs/attrs#1603` | red | [red] src/attr/_make.py:2683 — Attribute.__setstate__ now uses zip(..., strict=True) when reconstructing from a pickle with alias_is_default already present, but if a pickle was produced by an older attrs version with a different number of slots (fewer or more fields), this will raise ValueError instead of silently truncating/ignoring extra state as before, breaking backward-compatible unpickling for some legacy versions. — receipt 4e43dbc40ec2 | receipt 4e43dbc40ec2, regression_reproduced | | | |
| 4 | run B (eight libraries) | `pallets/jinja#2096` | impact | [yellow] src/jinja2/parser.py:681 — `Parser.parse_tuple` changed its return annotation; 6 call site(s) name it, 3 of them named by no test — src/jinja2/parser.py:226 | yellow (a), 6 caller(s): the return annotation changed and a caller is named by no test | | | |
| 5 | run B (eight libraries) | `pallets/jinja#2096` | impact | [yellow] src/jinja2/parser.py:866 — `Parser.parse_call_args` changed its return annotation; 3 call site(s) name it, 3 of them named by no test — src/jinja2/parser.py:926 | yellow (a), 3 caller(s): the return annotation changed and a caller is named by no test | | | |
| 6 | run B (eight libraries) | `theskumar/python-dotenv#640` | value | [yellow] src/dotenv/parser.py:71 — for list(parse_stream(stream)), the merge base returned <list len=198 sha256 d82b44cc> and head returns <list len=186 sha256 3829bf0c> (3/3 and 3/3 runs each side); no base test, docstring or changelog pins either — note 3ea6ff202b82 | note 3ea6ff202b82 — `list(parse_stream(stream))`; base value: [Binding(key='\ufeffFOO', value='bar', original=Original(string='\ufeffFOO=bar\n', line=1), error=False), Binding(key='BAZ', value='qux', original=Original(string='BAZ=qux\n', line=2), error=False)]; head value: [Binding(key='FOO', value='bar', original=Original(string='FOO=bar\n', line=1), error=False), Binding(key='BAZ', value='qux', original=Original(string='BAZ=qux\n', line=2), error=False)]; 3/3 head, 3/3 base; drawer: intent: value change confirmed, intent unknown: the base tree does not specify the value this assertion pins about the symbol this change touched -- no base test asserts it and no docstring or documentation writes it down (返回值变化已证实，意图未知) | | | |

## 1b. The same lines under D-232, D-233 and D-234

**Replayed 2026-09-13 from the committed ledgers, under the three rules that followed the owner's reading of the six lines above.** D-232 reads a new rejection off the exception's *frame* rather than the statement that raised it, so a builtin raising on a line the change wrote is a behaviour change with unknown intent -- the drawer, and under D-218 a value line -- not a red receipt; D-233 withdraws yellow (a) where only a return annotation moved; D-234 renders a container value by the first element that differs. The table in §1 is what the run showed and stays as it is; this is what the same ledgers say now. Nothing was re-executed and no model was called.

| # | run | pull request | level before → after | the line, as it would be shown now | what moved it |
|---|---|---|---|---|---|
| 1 | run B (eight libraries) | `more-itertools/more-itertools#1270` | value | [yellow] more_itertools/more.py:4955 — for list(g), the merge base returned [(b'12345', b'123')] and head raises ValueError (3/3 and 3/3 runs each side); no base test, docstring or changelog pins either — note 85d0b40bda6d | unchanged |
| 2 | run B (eight libraries) | `python-attrs/attrs#1603` | red → value | [yellow] src/attr/_make.py:2683 — for a.__setstate__(state), the merge base returned None and head raises ValueError (3/3 and 3/3 runs each side); no base test, docstring or changelog pins either — note 3407c699d80f | was red; D-232 moves the receipt to the drawer and D-218 writes the note |
| 3 | run B (eight libraries) | `python-attrs/attrs#1603` | red → value | [yellow] src/attr/_make.py:3115 — for f.__setstate__(short_state), the merge base returned None and head raises ValueError (3/3 and 3/3 runs each side); no base test, docstring or changelog pins either — note 186ba7208392 | was red; D-232 moves the receipt to the drawer and D-218 writes the note |
| 4 | run B (eight libraries) | `pallets/jinja#2096` | impact → (none) | *withdrawn* — was: [yellow] src/jinja2/parser.py:681 — `Parser.parse_tuple` changed its return annotation; 6 call site(s) name it, 3 of them named by no test — src/jinja2/parser.py:226 | withdrawn by D-233: the return annotation moved and nothing else |
| 5 | run B (eight libraries) | `pallets/jinja#2096` | impact → (none) | *withdrawn* — was: [yellow] src/jinja2/parser.py:866 — `Parser.parse_call_args` changed its return annotation; 3 call site(s) name it, 3 of them named by no test — src/jinja2/parser.py:926 | withdrawn by D-233: the return annotation moved and nothing else |
| 6 | run B (eight libraries) | `theskumar/python-dotenv#640` | value | [yellow] src/dotenv/parser.py:71 — for list(parse_stream(stream)), base and head lists of 2 first differ at index 0 (3/3 and 3/3 runs): base Binding(key='\ufeffFOO', value='bar', original=Original(string='\ufeffFOO=bar\n', line=1), error=False) → head Binding(key='FOO', value='bar', original=Original(string='FOO=bar\n', line=1), error=False); nothing in the base tree pins it — note 3ea6ff202b82 | re-rendered under D-234 |

**Before: 6 lines** (impact 2, red 2, value 2). **After: 4 lines** (value 4). The D-232 replay itself: 4 reproduced rows over 95 verification rows, 2 moved to the drawer (both `python-attrs/attrs#1603`), 0 kept, 2 unchanged ([evidence](evidence/2026-09-13-d232-replay.json)).

The three empty columns of §1 are still the owner's; a line that changed level here is adjudicated as it is shown now, and a withdrawn line is not adjudicated at all.


## 2. One row per pull request

### run A (the owner's five)

| pull request | cand | elig | att | cert | drawers | red | value | gate | yellow (a) | units read | spend |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `IcantFind-a-username/Attest#18` | 7 | 2 | 2 | 0 | 1 | 0 | 0 | 0 | 0 | 1 of 2 (budget-limited) | $0.2017 |
| `IcantFind-a-username/us-stock-helper#1` | 16 | 6 | 5 | 0 | 0 | 0 | 0 | 0 | 0 | 2 of 2 | $0.4520 |

Refused by the cap, by name (3): `IcantFind-a-username/Attest#15`, `IcantFind-a-username/Attest#14`, `IcantFind-a-username/Attest#10`. cumulative cap: $0.6536 spent, reserving $1.0000 for this unit would project $1.6536 past the $1.50 cap
Not selected by `--only` (24): the rest of the frozen sample, recorded as such.

### run B (eight libraries)

| pull request | cand | elig | att | cert | drawers | red | value | gate | yellow (a) | units read | spend |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `more-itertools/more-itertools#1270` | 1 | 1 | 1 | 0 | 1 | 0 | 1 | 0 | 0 | 1 of 1 | $0.0902 |
| `pallets/click#3861` | 13 | 13 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 2 of 2 | $0.2936 |
| `pallets/itsdangerous#406` | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 1 of 1 | $0.0357 |
| `pallets/jinja#2099` | 2 | 2 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 1 of 1 | $0.1186 |
| `pypa/packaging#611` | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 of 1 | $0.0371 |
| `python-attrs/attrs#1606` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 of 1 | $0.0093 |
| `theskumar/python-dotenv#680` | 5 | 5 | 5 | 0 | 2 | 0 | 0 | 0 | 0 | 1 of 1 | $0.2539 |
| `urllib3/urllib3#5239` | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 1 of 1 | $0.1252 |
| `more-itertools/more-itertools#1266` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 of 1 | $0.0096 |
| `pallets/click#3858` | 9 | 9 | 3 | 0 | 1 | 0 | 0 | 0 | 0 | 1 of 1 | $0.2968 |
| `pallets/itsdangerous#405` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 of 3 (budget-limited) | $0.0087 |
| `pallets/jinja#2098` | 4 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 of 1 | $0.0333 |
| `pypa/packaging#1392` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 of 1 | $0.0217 |
| `python-attrs/attrs#1603` | 5 | 5 | 3 | 2 | 0 | 2 | 0 | 0 | 0 | 2 of 5 (budget-limited) | $0.2397 |
| `theskumar/python-dotenv#638` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 of 1 | $0.0126 |
| `urllib3/urllib3#5212` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 of 1 | $0.0140 |
| `more-itertools/more-itertools#1261` | 4 | 4 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 1 of 1 | $0.2490 |
| `pallets/click#3851` | 9 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 2 of 5 (budget-limited) | $0.1047 |
| `pallets/itsdangerous#378` | 4 | 2 | 2 | 0 | 1 | 0 | 0 | 0 | 0 | 1 of 1 | $0.1241 |
| `pallets/jinja#2096` | 4 | 4 | 3 | 0 | 0 | 0 | 0 | 0 | 2 | 1 of 16 (budget-limited) | $0.3198 |
| `pypa/packaging#1384` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 of 1 | $0.0165 |
| `python-attrs/attrs#1571` | 4 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 of 1 | $0.0404 |
| `theskumar/python-dotenv#640` | 2 | 2 | 2 | 0 | 2 | 0 | 1 | 0 | 0 | 1 of 1 | $0.0705 |
| `urllib3/urllib3#5221` | 6 | 6 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 1 of 1 | $0.1997 |


## 3. Where every drawer observation went, read from the ledger

A drawer observation is a `verification` row of evidence class `behavior_change` whose outcome is not `reproduced`: the differential was real and the intent clause would not publish it. D-218 writes a value note only for the two drawers whose intent is *unreadable* (`value change confirmed, intent unknown` and `behavior change confirmed, intent unknown`); the drawer `intent stated in the change itself` means the author already said what they meant, and D-218 deliberately writes nothing for it. A written note is then shown only when it is not anchored inside `tests/`, is the first for its `(path, expression)`, and the contract admits the line (D-222).

| run | pull request | candidate | drawer | fate | detail |
|---|---|---|---|---|---|
| run A (the owner's five) | `IcantFind-a-username/Attest#18` | `dc84e95612` | intent stated in the change itself | note not written: drawer excluded by D-218 (intent stated / constant / unanchored) | intent stated in the change itself |
| run B (eight libraries) | `more-itertools/more-itertools#1270` | `f610cc5b46` | behavior change confirmed, intent unknown | shown as a line |  |
| run B (eight libraries) | `theskumar/python-dotenv#680` | `ebe78d458f` | intent stated in the change itself | note not written: drawer excluded by D-218 (intent stated / constant / unanchored) | intent stated in the change itself |
| run B (eight libraries) | `theskumar/python-dotenv#680` | `9b297d51ab` | intent stated in the change itself | note not written: drawer excluded by D-218 (intent stated / constant / unanchored) | intent stated in the change itself |
| run B (eight libraries) | `pallets/click#3858` | `b3a78daaaa` | intent stated in the change itself | note not written: drawer excluded by D-218 (intent stated / constant / unanchored) | intent stated in the change itself |
| run B (eight libraries) | `pallets/itsdangerous#378` | `e21c7319a9` | intent stated in the change itself | note not written: drawer excluded by D-218 (intent stated / constant / unanchored) | intent stated in the change itself |
| run B (eight libraries) | `theskumar/python-dotenv#640` | `515fc8ee16` | value change confirmed, intent unknown | shown as a line |  |
| run B (eight libraries) | `theskumar/python-dotenv#640` | `84443a4f92` | value change confirmed, intent unknown | note written, filtered: duplicate (path, expression) | src/dotenv/parser.py / list(parse_stream(stream)) |

Fates, counted:

- run A (the owner's five): **1** — note not written: drawer excluded by D-218 (intent stated / constant / unanchored)
- run B (eight libraries): **4** — note not written: drawer excluded by D-218 (intent stated / constant / unanchored)
- run B (eight libraries): **1** — note written, filtered: duplicate (path, expression)
- run B (eight libraries): **2** — shown as a line

## 4. The owner's five against the libraries' twenty-four

| | run A (the owner's five) | run B (eight libraries) |
|---|---|---|
| units run | 2 | 24 |
| candidates | 23 | 76 |
| eligible | 8 | 55 |
| reproductions attempted | 7 | 32 |
| certified | 0 | 2 |
| drawer observations | 1 | 7 |
| pull requests with a line | 0 | 4 |
| lines | 0 | 6 |
| spend | $0.6536 | $2.7248 |

