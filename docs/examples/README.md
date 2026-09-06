# Three real comments, one per level

Every line below is **verbatim output from a real run** on a real repository — not a mockup and
not an illustration. Each carries the coordinate a reader can open and the evidence a reader can
follow, and nothing else.

Coordinates are real and public (this repository and the owner's own), so nothing is redacted;
where a pull request no longer exists the comment is reproduced from the recorded evidence.

---

## `[red]` — a defect, with a receipt

Posted by the Action on a GitHub runner to
[pull request #11](https://github.com/IcantFind-a-username/Attest/pull/11), 2026-09-06
([full comment](../acceptance/evidence/2026-09-06c-pr11-comment.md)):

```
[red] scripts/corpus/four_levels.py:212 — `_latest_task` now requires a `ledger_name`
      argument but its only known caller at `four_levels.py:202` still calls it with a
      single argument, causing a `TypeError` at runtime. (receipt e89b0fe548b6)
```

**What stands behind it.** A generated test that failed on head in 3 of 3 runs and passed on the
merge base in 3 of 3, inside a container with no network; the test's own bytes, the six run
records and the manifest that digests them are in the bundle the receipt names. The comment
carries the `pytest` command, so a reader who does not believe it can run it.

**What it is careful not to say.** Not *"this may break"*, not *"consider adding a default"* —
one located fact and one receipt. The assertion in the test was **not written by a model**: the
call was executed on the merge base and the expectation was recorded from what it returned.

---

## `[yellow]` — a hypothesis, with the premises that were checked

Same pull request, same run:

```
[yellow] scripts/corpus/four_levels.py:212 — `_latest_task` gained a required parameter;
         1 call site(s) pass fewer than 2 positional argument(s) —
         scripts/corpus/four_levels.py:202
```

**What stands behind it.** No model at all: `ast` read the signature at both revisions, and
`git grep` found the call site that still passes one argument. The collapsed block under the
comment lists every caller and which of them a test names.

**What it is careful not to say.** It does not claim the code is broken — red said that, from a
reproduction. Yellow says *a static reading holds*, names both coordinates, and stops. Yellow
never publishes more than **two** comments on one pull request, across all of its classes.

---

## `[green]` — something structurally so, with no model in the detection path

From the shadow review of `attest` at `48b418c8`, 2026-09-07
(`.attest/real-traffic/2026-09-07-budget-attest.log`), with the sentence in the shape
`attest.structural.duplicate-implementation.v2` prints it (D-174; the recorded line said
"attribute and callee names are not", which read as the opposite of what it meant, and v1 kept
only *attribute* callees anyway):

```
[green] Structural (no defect claimed): scripts/corpus/impact_scan.py:62-68 `git` and
        scripts/corpus/qualify_controls.py:45-54 `git` normalise to token sequences of
        50 and 50 tokens whose token-sequence similarity is 1.000 (threshold 0.92), not
        semantic equivalence; identifiers and literal values erased, attribute and callee
        names kept.
```

**What stands behind it.** Two function bodies, normalised to token sequences by `ast`, whose
similarity clears a fixed threshold. A model is called **once, afterwards**, only to word the
finding and propose a fix — and if its sentence hedges or names no coordinate, the deterministic
sentence above is published instead.

**What it is careful not to say.** *"no defect claimed"* is in the line itself. Green states a
measurement with two coordinates and a number; the advice lives in a collapsed block that a
reader can ignore without losing the claim. And a pair it has already reported, whose two spans
are both unchanged, is **not reported again**.

---

## `[silent]` — the fourth thing it says, and the most common

```
[silent] read 1 of 13 units; nothing met an adjudicator's bar; $0.0156, 4.4s.
```

32 of 40 recent real commits ended here. The line names how many change units the silence covers,
because a silence over 1 of 13 and a silence over 13 of 13 are different claims. When the budget
is what stopped the run it says that instead, and how many candidates it stopped.

**A silence is an abstention, never a true negative.**
