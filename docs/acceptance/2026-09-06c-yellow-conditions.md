# Yellow (a): three conditions, measured one at a time — 2026-09-06c

Owner instruction 4 of this window: **keep "signature changed ∧ untested caller"; add "a new
`raise` or a changed return annotation ∧ untested caller"; go through the five disjunction
firings one by one and, where the precision is good enough, write a third condition. Report each
condition's trigger rate separately on the 79 units, and do not adopt one whose control rate
exceeds 3%.**

**Free: `$0.00`.** `ast` and `git` over trees already on disk; the scan makes no API call.
[Data](evidence/2026-09-06c-impact-conditions.json) · D-150 · code
[`impact.py`](../../src/attest/review/impact.py).

## 1. The five firings of D-143's disjunction, adjudicated

D-143 fired on `interface changed **or** an untested caller`. Over the 79 units that produced
**seven notes on five units** — six forward, one control. Here is every one of them:

| # | unit | note | untested callers | actionable? |
|---|---|---|---|---|
| 1 | fwd `click 0585f456ba` | `_format_default` changed its return annotation; **1** call site | **0** | no |
| 2 | fwd `click 0585f456ba` | `prompt` changed its return annotation; **14** call sites | **0** | no |
| 3 | fwd `click cd4674a6de` | `_pipepager` changed signature; **2** call sites | **0** | no |
| 4 | fwd `click cd4674a6de` | `_tempfilepager` changed signature; **2** call sites | **0** | no |
| 5 | fwd `more-itertools d63a26e56e` | `first_true` changed signature; **5** call sites | **0** | no |
| 6 | fwd `more-itertools 2deea20ead` | `random_product` changed signature; **2** call sites | **0** | no |
| 7 | **ctl** `jinja 73a94e00d4` | `make_attrgetter` changed; 9 call sites | **9** | no — no interface change |

**0 of 7 notes carried both halves.** Six said "the interface moved and every caller is tested",
which the test suite reports without this level's help; one said "nine untested callers under an
unchanged body change", which is a coverage remark this level has no standing to make.

Rows 3 and 4 are the interesting near-miss: `_pipepager` and `_tempfilepager` are exactly where
that commit's *"pager doesn't close std streams"* defect lives, so the level named the right
function — and said nothing an author could act on about it. **Naming the right function is not
the same as making a claim**, and a condition tuned to produce that would be tuned on n = 1.

**So no third condition was written from the seven.** What the seven show is not that the
threshold is wrong but that the *shape* is: every one of them pairs an interface fact with a
coverage proxy, and a coverage proxy cannot say whether anything is broken. a3 below is derived
from that shape — replace the proxy with a decidable consequence — rather than from any row.

## 2. The three conditions as shipped

| | condition | second half is |
|---|---|---|
| **a1** | the **signature** moved ∧ some caller is named by no test | a coverage proxy (D-145, unchanged) |
| **a2** | the function **raises an exception type the base did not**, or its **return annotation** moved, ∧ some caller is named by no test | a coverage proxy |
| **a3** | a **required parameter was added** ∧ some call site statically passes **fewer positional arguments** than the function now takes | **decidable** |

a3 has no coverage half on purpose: the call is wrong whether or not a test names the caller, so
a tested caller does not silence it, and it outranks a1 and a2 in the ≤ 2 cap. Every uncertainty
still abstains — `*args`, `**kwargs` or any keyword argument may supply the parameter, so those
call sites are dropped; an attribute call on a method discounts the implicit `self`; a name
defined twice in the tree produces no claim at all.

## 3. The trigger rates, per condition

| condition | forward (11) | **controls (68)** | notes | adopted? |
|---|---|---|---|---|
| a1 signature ∧ untested caller | **0** (0.0%) | **0** (0.0%) | 0 | yes |
| a2 new raise ∨ return annotation ∧ untested caller | **0** (0.0%) | **0** (0.0%) | 0 | yes |
| a3 added parameter ∧ arity break | **0** (0.0%) | **0** (0.0%) | 0 | yes |
| **all three, as shipped** | **0** (0.0%) | **0** (0.0%) | 0 | — |

Every condition clears the owner's 3% control ceiling by the widest margin available: the
95% upper bound on the control rate at 0 of 68 is **5.3%**, so *strictly* the ceiling is not
demonstrated at this n — what is demonstrated is that **nothing fired at all**, on either
population, under any condition.

## 4. What this is and is not

**It is a ceiling on noise.** Yellow (a) costs `$0.00`, runs on every pull request, and has never
spoken on a commit in either measured population. It cannot make ordinary traffic noisier.

**It is not evidence of value.** Three conditions that never fire have never been right about
anything. The 2026-09-06b demonstration of yellow (a) speaking had to be *constructed* — a
throwaway pull request written to trigger it — and that is still true of all three.

**a3 is the one worth watching**, and it is also the one with the thinnest evidence: it never
fired on 79 real commits, and the only cases it has ever produced are the D-145 fixture (where
`quote` gained a parameter and both call sites still passed one — a genuine break) and its unit
tests. Its claim is checkable by the reader in a way a1's and a2's are not, which is why it is
enabled despite firing on nothing: a wrong a3 note is a wrong statement of arithmetic and would
be caught immediately, where a wrong a1 note is a coverage opinion nobody can refute.
