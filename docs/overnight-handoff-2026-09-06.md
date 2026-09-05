# Handoff — 2026-09-06 (`abad758` → `0abdb8a`, plus this document)

**Spend $0.374300 of $10; cumulative $56.061237 of $90.** Remote writes: push to `main` only.
Seven owner instructions, all seven done; only the first cost money.

## 1. The stop rule is a probe, and the independent population finished (D-141)

A control that publishes stops the run **until an independent probe** — no product code, a
minimal reproduction, **at least two Python versions** — says whether the defect is real. Real ⇒
`true_positive_on_control`, not a wrong publication, run continues. Not real, or not adjudicated
at all ⇒ the run stays stopped. Two interpreters is content, not ceremony: `divide()`'s defect is
**invisible on 3.11 and present on 3.12**. The last 14 controls ran, published nothing, and
`G-NULL-001a`'s independent population is complete
([report](acceptance/2026-09-06-g-null-001a-final.md)).

| n | reviewed | answered | **wrong** | true positive on control | bound |
|---|---|---|---|---|---|
| **68** | 68 | **7** | **0** | **1** (`more-itertools f4f2cfec9d`) | **42.9%** (3/7) |

The bound is arithmetically valid and useless, and the reason is on the record: **57 of the 68
controls produced no candidate at all**, so this population measures discovery's silence more
than the rule's restraint. D-134's 5.2% at n = 58 remains the only bound this gate has.

## 2. The other six, all free

- **The upstream report is written and not filed**
  ([draft](acceptance/2026-09-06-more-itertools-issue.md)): title, one-line reproduction,
  affected range (**more-itertools ≥ 8.1.0**, **Python ≥ 3.12** for a plain `dict`, *every*
  version for a non-`TypeError` `__getitem__`), root cause, the `except (TypeError, KeyError)`
  fix with the residual `IndexError` case named, and the bundle path with the verify command
  that returns *accepted … seal verified*. **README says "draft prepared, not yet filed" rather
  than "reported"** — it is not filed, and the row can flip to `#NNN` in one word once it is.
- **The 20 forward-pair generation failures, classified** free from the recorded ledgers
  ([report](acceptance/2026-09-06-forward-pair-generation-failures.md)): **environment 0**,
  *asserted a behaviour base lacks* **18** (11 fail identically on both sides, 7 encode a
  head-era contract), head-only signature **1**, other **1** (a test that inlined its own copy
  of the function). The owner's conditional backlog item **does not fire**; what the data does
  support — observe the base before writing the assertion — is in `backlog.md`, not implemented.
- **README** carries two new rows with budget and models: the 11 forward pairs, and the
  third-party defect found as a control.
- **The `v0.1` gap list** ([doc](acceptance/2026-09-06-v01-tag-readiness.md)): **four of seven
  conditions hold** (1, 2, 6 and the new 7); blocked on **3** (`G-SEC-002`: 9 of 13 fixture
  classes and no external observer — the largest gap), **4** (no gate-grade null bound; no
  held-out recall number under the current policy) and **5** (no *prospective* shadow window).
  Eight items, listed and not started.
- **The output contract (D-142)**: every author-visible line is one line — level marker,
  `file:line`, one sentence of fact, evidence. Preamble, PR restatement, unlocated hedge,
  evaluation and disclaimer are refused; the model's fix moves to a `<details>` block; a wholly
  silent review says **one** line naming the units read. Green's wording rule was **generalised**
  into the format adjudicator. Non-conformance is not published — but a certified finding is
  never silenced by phrasing: the receipt's own sentence is published instead.
- **Yellow (a), the impact scope (D-143)**: call sites of each changed function, whether a test
  *names* each caller, whether the signature or return annotation moved — `ast` and `git`, no
  model, **$0.00**. Offline on 79 units
  ([report](acceptance/2026-09-06-impact-scope-scan.md)): **4 of 11 forward pairs (36.4%)** and
  **1 of 68 controls (1.5%)**, 7 notes over 257 changed functions, cap 2 per PR, **not wired into
  the publication path**. Reading its own output against the repositories found **two claims that
  were not true** — a property tests read as an attribute, and `__init__`, which no caller ever
  writes — and both fixes made it quieter: forward 45.5% → 36.4%, controls 7.3% → 4.4% → 1.5%.

## 3. For the owner — three items

1. **Yellow (a) now speaks almost only on interface changes**: all 6 forward notes are signature
   or annotation changes whose every caller is already tested, and the "untested caller" trigger
   fires once in 79 units. Narrow it? **Default: drop the annotation-only case when no caller is
   untested (2 of the 6, both on one pair; 4 notes on 3 pairs remain), keep signature changes** —
   narrowing further to "interface change *with* an untested caller" leaves 0 of 11 forward
   pairs, which is no level at all.
2. **Should yellow (a) become author-visible?** It costs $0, caps at 2 per PR, and is quiet on
   **98.5%** of ordinary commits. **Default: yes, after item 1's narrowing** — the cheapest test
   of whether the contract holds up on a second level.
3. **What null claim does `v0.1` make?** (a) quote **5.2% at n = 58** with its "regression test
   as much as a null study" caveat; (b) raise the cap by ~$65 to reach `G-NULL-001`'s n ≥ 300;
   (c) ship with no null claim. **Default: (a)** — (b) does not fit the $34 left under the cap.

## 4. Gates at this tip

`ruff check .` clean; `mypy` clean over 86 source files; **`pytest --cov=src/attest`: 1,903
tests, all passed, none failed, none skipped**, coverage **92.70%** against the 90% floor — the
previous tip's 1,864 plus this window's 39. Zero skips again means the container backend was up.
New tests: `test_null_study_stop_rule.py` (7),
`test_output_contract.py` (21), `test_impact_scope.py` (11); 7 of 7, 21 of 21 and 11 of 11 fail
on the previous implementations. Two existing assertions were **deliberately** changed by D-142:
the wholly silent body is now the contract's silence line, and a summary finding line must carry
`[red]` for the delivery journal to accept it.
