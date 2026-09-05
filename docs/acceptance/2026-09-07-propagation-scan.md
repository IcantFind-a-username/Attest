# Yellow (b), second class: unhandled exception propagation, offline over 79 units

**D-164.** [Data](evidence/2026-09-07-propagation-scan.json) · driver
`scripts/corpus/propagation_scan.py` · **$0.00** — every premise is decided by `ast`
and `git`, and the driver never calls a model.

## The question

The first yellow (b) class asks about `None` and measured **0 of 79**, because the
corpus it reads carries no type annotations at all — its binding constraint is
*annotation coverage*, which no prompt change addresses. This class asks a question the
same code can answer, because it reads statements rather than declarations:

> the changed function now calls something that raises, and on the way out to a caller
> nobody catches it.

Three premises, **all three or nothing**: (i) the call is one the change introduced —
present at head, absent in the base revision of the *same* function; (ii) the callee
names an exception, in a `raise X` in its own body or in a docstring that declares
`Raises: X` / `:raises X:`; (iii) from the changed function out to some **non-test**
caller, nothing catches it.

## The result: 0 of 79, and this time the refusals say why

| population | units | scanned | spoke | trigger rate |
|---|---|---|---|---|
| forward pairs | 11 | 11 | **0** | 0% |
| null controls | 68 | 68 | **0** | 0% |

**Control noise 0%**, against the owner's 3% ceiling — the level clears the bar for
publication by never firing, which is the same thing the first class did.

**198 changed functions were considered.** What voided each one:

| premise that failed | count | share |
|---|---|---|
| **the change added no call** — premise (i) | **135** | 68% |
| the callee's name is not unique — premise (ii)'s resolution step | 43 | 22% |
| the callee names no exception — premise (ii) | 15 | 8% |
| the changed function catches everything — premise (iii) | 5 | 3% |
| *reached premise (iii)'s caller search and found a guard* | **0** | 0% |

## What that means, and how it differs from the first class

The first class died on a property of the **corpus** — no annotations — so its number
says nothing about the rule. This one dies on a property of **changes**: two thirds of
the changed functions in this population add no call at all, and of the third that do,
most call something whose name is defined more than once in the tree, which this level
treats as an abstention rather than a guess.

That is a more interesting negative. It says the conjunction is *rare*, not
*unverifiable*: nothing here suggests the rule is wrong, and nothing here is evidence
that it works either. **It is not claimed to work.** It ships for the same reason the
first class does — it cannot speak without three readings taken out of the trees, it
costs `$0.00`, and its refusals are counted — and it is recorded in `limits`.

The one lever that would plainly raise recall is resolving callee names by import
rather than by bare name, which would convert most of the 43 ambiguity abstentions into
decidable cases. That is a real piece of work and it is **not** done here: 43 of 198 is
a reason to consider it, not evidence that the answers would be right.
