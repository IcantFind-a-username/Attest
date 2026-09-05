# Yellow (a), the impact scope: offline on 79 units — 2026-09-06

D-143 builds the first yellow level: for every function the diff changed, the call sites that
name it, whether a test names each caller, and whether the signature or return annotation moved.
**Deterministic, no model, no execution, $0.00.** This is its first measurement, run before it is
ever author-visible, and it publishes nothing.

[Driver](../../scripts/corpus/impact_scan.py) · [data](evidence/2026-09-06-impact-scope-scan.json)

```bash
.venv/bin/python scripts/corpus/impact_scan.py scan --population both \
  --json docs/acceptance/evidence/2026-09-06-impact-scope-scan.json
```

## 1. The trigger rate

| population | what it is | units | trigger | notes | why they spoke |
|---|---|---|---|---|---|
| forward pairs | the 11 defect-**introducing** commits of D-140 | 11 | **4 (36.4%)** | 6 | 4 signature changed, 2 return annotation changed |
| null controls | the 68 independent `G-NULL-001a` controls — ordinary old commits nobody had to fix | 68 | **1 (1.5%)** | 1 | 1 a caller named by no test |
| | | **79** | **5 (6.3%)** | **7** | |

**The separation is the result.** On commits that introduced a defect the level speaks about a
third of the time; on ordinary commits it is quiet **98.5%** of the time, and it never once fired
there on an interface change. A level meant to say *"this change reaches somewhere untested"*
should have exactly that shape, and the numbers are free to recompute at any commit.

**What this is not.** Yellow (a) claims no defect, so 36.4% is **not** recall and 1.5% is **not**
a false-positive rate. Every note is a count over an abstract syntax tree, and the only way a
note can be *wrong* is if the count is wrong — which is what §3 checks.

167 changed functions were examined in the forward population and 90 in the controls; 7 notes
came out, so the level is silent about **97.3%** of the functions it looks at. The cap is 2 notes
per pull request and no unit reached it.

**Both numbers fell during this measurement, twice, and each time because a hand check found a
claim that was not true** (§3 and §4). Forward went 45.5% → 36.4% and controls 7.3% → 4.4% →
**1.5%**. Every figure in this document is at the final implementation.

## 2. Every line it produced

Rendered through the D-142 output contract, exactly as an author would see them.

**Forward pairs (6):**

```text
[yellow] src/click/termui.py:134 — `_format_default` changed its return annotation; 1 call site(s) name it, 0 of them named by no test — src/click/termui.py:130
[yellow] src/click/termui.py:151 — `prompt` changed its return annotation; 14 call site(s) name it, 0 of them named by no test — src/click/core.py:3497
[yellow] src/click/_termui_impl.py:455 — `_pipepager` changed signature; 2 call site(s) name it, 0 of them named by no test — src/click/_termui_impl.py:421
[yellow] src/click/_termui_impl.py:559 — `_tempfilepager` changed signature; 2 call site(s) name it, 0 of them named by no test — src/click/_termui_impl.py:420
[yellow] more_itertools/recipes.py:560 — `first_true` changed signature; 5 call site(s) name it, 0 of them named by no test — more_itertools/more.py:5230
[yellow] more_itertools/recipes.py:567 — `random_product` changed signature; 2 call site(s) name it, 0 of them named by no test — tests/test_recipes.py:549
```

**Null controls (1):**

```text
[yellow] src/jinja2/filters.py:58 — `make_attrgetter` changed; 9 call site(s) name it, 9 of them named by no test — src/jinja2/asyncfilters.py:77
```

## 3. Six lines checked by hand

| # | line | checked against | verdict |
|---|---|---|---|
| 1 | `click cd4674a6de` — `_pipepager` changed signature | `git diff` of the two revisions: `(generator, cmd_parts, color) -> bool` became `(cmd_parts, color=None) -> Iterator[...]` | **correct**, and independently corroborated: D-140's generated test for the sibling `_tempfilepager` failed on base with *"missing 2 required positional arguments: 'cmd_parts' and 'color'"* |
| 2 | `more-itertools 2deea20ead` — `random_product` changed signature | `git diff`: `def random_product(*args, repeat=1)` → `def random_product(*iterables, repeat=1)` | **correct** |
| 3 | `jinja 73a94e00d4` — `make_attrgetter`, 9 of 9 callers named by no test | `git grep make_attrgetter` at that commit: `src/jinja2/filters.py` and `src/jinja2/asyncfilters.py` only, nothing under `tests/` | **correct** |
| 4 | `packaging 97db717567` — `_parse_requirement_marker`, 2 of 2 callers named by no test | `git grep`: definition at `_parser.py:139`, call sites at 115 and 126, no test names it | **correct**, and the note is gone anyway at the final implementation: both call sites sit in `_parse_requirement`, which the tests do reach |
| 5 | `urllib3 21671d8158` — `Timeout.get_connect_duration`, "2 of 5 callers named by no test" | `git grep read_timeout` under `test/`: **5 hits**. The two call sites sit inside the `read_timeout` **property**, which tests read as an attribute rather than call | **wrong, and it changed the implementation** |
| 6 | `itsdangerous 3703fbdedd` — `want_bytes`, "4 of 23 callers named by no test", witness `serializer.py:89` | that line is inside `Serializer.__init__`, and `tests/test_itsdangerous/test_encoding.py` names `want_bytes` four times while the whole suite instantiates `Serializer` constantly | **wrong, and it changed the implementation** |

Two of the six checks found a claim that was not true, and each fix made the level quieter.

**Check 5 — a property is read, not called.** The first implementation walked *call* sites only,
so `timeout.read_timeout` was invisible and the level said "named by no test" about something
five tests name. The reverse walk now traverses **mentions** — calls, attribute reads and bare
references — while a *caller* is still only a call. Control trigger rate: 7.3% → 4.4%.

**Check 6 — nothing outside a class writes `__init__`.** Asking whether a test names `__init__`
answers "no" for every constructor in every repository, so a class that ten tests instantiate was
being reported as untested. The **addressable name** of a dunder is now its class. Forward:
45.5% → 36.4%; controls: 4.4% → **1.5%**.

Both were found by reading the level's own output against the repositories it was describing,
which is the only check that catches a claim whose arithmetic is correct and whose meaning is
wrong.

## 4. What the level refuses to say, and why the sentence is worded as it is

- **"named by no test", never "not covered".** No coverage was measured and no test was run. A
  caller reached only through a registry, a dispatch table or `getattr` is invisible to a static
  name walk, and the published wording says exactly what was computed.
- **An ambiguous name is an abstention.** A changed function whose bare name is defined more than
  once in the repository produces nothing: two `save` methods are two functions and a name cannot
  tell their callers apart.
- **New code is not this level's claim.** A function with no counterpart in the base revision is
  dropped here; that is the gate level (N-01, D-137).
- **A dunder is addressed by its class.** `__init__` is never written by a caller, so the name a
  test would have to use for a constructor is the class's.
- **A function with no caller produces nothing**, and neither does a body change all of whose
  callers a test names — the case the owner named as the silent one.

## 5. What carries the level now, and the one rule question

After both fixes, **all six forward notes are interface changes whose every caller is already
named by a test**, and the "untested caller" trigger fires exactly once in 79 units — on a
control. The signature clause is what makes this level speak at all.

Two of the six are **annotation-only** (`-> str` added), which is a declaration change and not a
behavioural one; an author may reasonably read those two as noise. Dropping the annotation-only
case when no caller is untested would leave **4 forward notes on 2 of 11 pairs** and the same
single control note. Narrowing further — *"an interface change **with** an untested caller, or an
untested caller"* — would leave the level speaking on **0 of 11 forward pairs and 1 of 68
controls**, which is a level that does not exist.

**Neither narrowing is made here.** The rule is the owner's, and the numbers for each option are
above.
