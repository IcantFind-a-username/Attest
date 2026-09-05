# Yellow (b), the null/Optional class: 13 hypotheses, 0 survived — 2026-09-06c

Owner instruction 5 of this window: **a model proposes hypotheses with premises about the changed
function; the premises may only be of three checkable kinds; a deterministic checker verifies each
one; any premise that fails voids the hypothesis and is recorded in the ledger; only all-three
produces one D-142 line, and yellow's ≤ 2 per pull request is shared with (a). Run it offline over
the 11 forward pairs, the 68 controls and the 79 units, and report the trigger rate, the premise
pass rate and the control triggers — over 3% is not published.**

**Spend `$0.1034` of a `$5.00` reservation.** One `claude-sonnet-5` call per unit that had a
changed function short enough to show. **No publication surface exists on this path**: the driver
constructs no GitHub client. D-151 ·
[data](evidence/2026-09-06c-nullability-scan.json) ·
[`nullability.py`](../../src/attest/review/nullability.py) ·
[driver](../../scripts/corpus/nullability_scan.py).

## 1. The division of labour

| | who decides |
|---|---|
| **which parameter, which line, which caller** | the model |
| **whether the three premises hold** | `ast` and `git`, over the head tree |
| **the sentence** | the kernel, from the verified premises |

Nothing the model writes reaches an author. A hypothesis missing any premise is **void** — not
softened, not hedged, not published with a caveat — and its refusal goes to the ledger with the
premise that failed, so the void rate is measurable rather than assumed.

## 2. The three premises, exactly as the owner specified them

| | premise | what the checker reads |
|---|---|---|
| **(i)** | the parameter admits None | its annotation (`Optional[…]`, `… \| None`, `Union[…, None]`) or a `None` default, from the AST |
| **(ii)** | the code dereferences it anyway | the named line takes an attribute, subscript or call of the parameter, and **no recognised guard** stands between the function's entry and that line |
| **(iii)** | some caller can actually supply None | the argument that caller passes for that parameter traces to a function whose own **return annotation** admits None |

**Eight guard forms are recognised** in (ii), and an unrecognised guard voids the hypothesis
rather than producing a claim: `if p is not None`, truthiness `if p`, `isinstance`/`hasattr`/
`getattr`, `assert p is not None`, an early `return`/`raise`/`continue`/`break` under
`if p is None`, any rebinding of `p`, a `try` whose handler catches the dereference, and an inline
ternary. Every direction of doubt costs recall and none costs precision.

## 3. The measurement, over the same 79 units

| | forward (11 pairs) | **controls (68)** |
|---|---|---|
| units scanned | 11 | 68 |
| units with a function short enough to show | 11 | 68 |
| **hypotheses the model proposed** | 5 | 8 |
| **hypotheses surviving all three premises** | **0** | **0** |
| premise pass rate | **0.0%** | **0.0%** |
| **units triggering** | **0 (0.0%)** | **0 (0.0%)** |
| spend | $0.0261 | $0.0773 |

**The control trigger rate is 0 of 68, so the 3% ceiling is met** — and it is met the same way
yellow (a)'s three conditions meet it: by never firing.

## 4. Why all thirteen died, which is the useful part

| premise that failed | count | what the checker read |
|---|---|---|
| **(i)** the parameter admits None | **11** | *"the annotation does not admit None and the default is not None"* — 10 of them; *"no parameter named `self.default`"* — 1 |
| **(ii)** the dereference is unguarded | **2** | *"line 881 does not dereference `fillvalue`"*, *"line 1809 does not dereference `keyfunc`"* |
| **(iii)** a caller supplies None | 0 reached | no hypothesis survived far enough for (iii) to decide anything |

Two of the eleven, checked by hand:

- `more-itertools d63a26e56e`, `nth_prime(n, approximate=False)` — `n` carries **no annotation
  and no default at all**. The model's hypothesis may be perfectly sensible; premise (i) is not
  verifiable.
- `packaging 527be81862`, `Specifier.contains(self, item, prereleases=None)` — the model named
  `item`, which has no annotation and no default. (`prereleases` does default to `None`, and the
  function's very first statement guards it.)

**So the binding constraint is annotation coverage in the code being read, not the model's
judgement.** The corpus is old open-source Python — `attrs`, `click`, `jinja`, `more-itertools`,
`packaging`, `python-dotenv`, `urllib3` at commits from 2016–2020 — and premise (i) as the owner
defined it requires a type annotation that mostly does not exist there. No prompt change
addresses that; a different corpus would.

The two (ii) failures are the checker doing its job in the other direction: the model named a
line, the checker read the line, and the parameter is not dereferenced on it.

## 5. What is shipped, and on what terms

It is on the publication path, because it costs about **$0.005 a review**, it cannot speak
without three readings taken from the tree, and its refusals are recorded. It is **not** claimed
to work: over 79 real commits it has produced no note at all, and the honest summary is that it
has a measured noise ceiling of 0 and no measured recall.

One cost is real and is stated rather than hidden: unlike green's wording call — paid only once a
finding already exists — yellow (b)'s call is a **detection** call, so **every review now pays one
extra model call whether or not anything is found**. The benchmark's product arm moved from
$0.0108 to $0.0144 a case for exactly this reason, and that pin was updated rather than relaxed.
