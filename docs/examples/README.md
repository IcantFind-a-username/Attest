# Three real comments, one per level

*Audited element by element on 2026-09-09; the audit and what it changed are at the bottom of this file.*

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

---

## The audit, and the fourth element (D-178)

Every comment above was checked on 2026-09-09 against the four things a comment owes —
**position**, **fact**, **evidence**, **action** — together with the first unprompted yellow (a)
comment on real traffic, which arrived after they were written.

| comment | position | fact | evidence | action |
|---|---|---|---|---|
| `[red]` `four_levels.py:212` | ✅ the changed line, in the diff | ✅ a reproduction, three runs each way | ✅ receipt `e89b0fe548b6` and the bundle | ⚠️ **present but unlabelled** — the body carried the `pytest` command and `attest verify --bundle …`, in prose no adjudicator read |
| `[yellow]` `four_levels.py:212` | ✅ | ✅ counts from `ast` at both revisions | ✅ second coordinate `four_levels.py:202` | ❌ **absent** |
| `[green]` `impact_scan.py:62-68` | ✅ | ✅ a similarity measure over two token sequences | ✅ second coordinate `qualify_controls.py:45-54` | ❌ **absent** — the model's advice was collapsed and explicitly *not part of the claim*, so nothing said what to do |
| `[yellow]` `gate_level.py:252`, [PR #12](https://github.com/IcantFind-a-username/Attest/pull/12) | ✅ | ✅ 3 call sites resolve to it, no test names it — re-resolved and confirmed | ✅ `scripts/corpus/binding_recount.py:102`, and every site listed | ❌ **absent** |

Three of four had nothing to act on, and the fourth had it only in prose. **D-178 makes the
action clause a fifth adjudicated element**: `output_contract.check_comment` refuses a comment
that does not carry exactly one `Action:` line naming something to run, open or change, and each
level assembles its clause from coordinates it already holds — so wording can never be what
suppresses a finding. The clauses those same comments carry now:

```
[red]    Action: reproduce it — `python -m pytest .attest-repro/test_repro.py::test_case` —
         then check the receipt offline with `attest verify --bundle <path> --require-seal`.

[yellow] Action: add a test that names `scripts/corpus/four_levels.py:202`, or change the
         caller there to match the new interface.

[green]  Action: keep one of `scripts/corpus/impact_scan.py:62` and
         `scripts/corpus/qualify_controls.py:45`, and call it from the other.
```

The `gate` level is still in shadow and publishes nothing; its clause — the reachable path and
the input that triggers it — is defined with the others and ships when the level does.

**One more thing the audit changed.** The yellow (a) comment ended with *"Static reachability
over names: a caller reached only through a registry or `getattr` is invisible here"*. D-174 had
already made a call site the thing a name **resolves to**, so that sentence described a rule the
product no longer runs. It now states the resolution and keeps the honesty clause verbatim:

> Resolved statically: a call reached only through inheritance, a decorator, a package
> re-export, a variable or `getattr` does not resolve and is not listed, so this says
> *named by no test*, never *not covered*.
