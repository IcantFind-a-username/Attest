# Yellow (b), first class, re-measured with annotation-independent premises

**D-165, owner instruction 1.2.**
[Data](evidence/2026-09-07-nullability-scan-v2.json) · driver
`scripts/corpus/nullability_scan.py` · policy
`attest.nullability.premised-hypothesis.**v2**` · **$0.106230**, against a $3.00
reservation.

## What was changed, and why

D-151 measured this class at **0 of 79**, and **11 of its 13 hypotheses died on premise
(i)** — *the parameter admits None* — for one structural reason: the corpus carries no
type annotations at all, so the premise was unverifiable however true it was. Its
binding constraint was recorded as *annotation coverage, not the model*.

The premises now read **three annotation-independent sources**, each of them a fact an
author wrote in code: a `None` default (already read), the function's **own `is None`
test**, and for the caller premise a **`return None` in the source function's body**
rather than only a return annotation. The annotation reading is kept — this widens the
disjunction, it does not replace it.

## The result: still 0 of 79

| | D-151 (v1) | **D-165 (v2)** |
|---|---|---|
| units scanned | 79 | **79** |
| forward pairs triggering | 0 of 11 | **0 of 11** |
| controls triggering | 0 of 68 | **0 of 68** |
| hypotheses proposed | 13 | **15** |
| surviving all three premises | **0** | **0** |
| cost | $0.1034 | **$0.1062** |

**First failing premise, 15 hypotheses:**

| premise | failed first |
|---|---|
| **(i)** the parameter admits None | **13** |
| (ii) an unguarded dereference at the named line | 2 |
| (iii) the caller supplies a value that can be None | 0 *(never reached)* |

And what the checker actually read, per void:

| reading | n |
|---|---|
| *no annotation admits None, the default is not None, **and the function never tests it against None*** | **10** |
| the named "parameter" is an attribute (`self.eta`, `self.name`, `self.default`), not a parameter | 3 |
| the named line does not dereference the named parameter | 1 |
| a guard stands above the dereference (`line 391 tests \`these\` is not None`) | 1 |

## What the widening bought, and what it did not

It bought **two more hypotheses** and **zero more notes**. Premise (i) still fails on 13
of 15 — proportionally exactly where it was (11 of 13). **So the wall was not only
annotations.** Ten of the thirteen failures are hypotheses about a parameter that has no
annotation, no `None` default **and no `is None` test anywhere in its function**: on
this corpus the model proposes parameters whose own code says nothing about nullability
in any of the three ways this level can read.

Three of the fifteen name **`self.x` as a parameter**, which is not a parameter at all —
a model-side error the checker catches, and one that no premise change addresses.

## Verdict: written into `limits`, and shelved

Per the owner's instruction, **this class is put down**. It has now been measured twice,
under two rules, on the same 79 units, and has produced **0 notes both times** — while
costing one model call on every review. The honest description is in the README's known
limitations:

> **Yellow (b)'s null/Optional class has never produced a sentence.** 0 of 79 units under
> two rule versions, 28 hypotheses proposed, 0 surviving. Its detection call is paid on
> every review whether or not anything is found. It ships because it cannot speak
> without three readings taken out of the tree; **it is not claimed to work.**

The second yellow (b) class ([exception propagation](2026-09-07-propagation-scan.md))
is also 0 of 79, but it is **free** and its refusals are informative, so the two are not
in the same position: the case for switching one of them off is a case about the paid
one. That is an owner decision and it is the third item of this window's handoff.
