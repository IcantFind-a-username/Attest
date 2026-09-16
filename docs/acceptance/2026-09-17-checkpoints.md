# P-04, 2026-09-17 — checkpoints from a repository's own statements: how many, how noisy, what they catch

**Owner direction of 2026-09-16 (the original idea, in the owner's words: have a model read the
repository, turn its structure into checkpoints, run the project, and localise the defect at the
point where the forward chain breaks).** This probe tests the cheapest sound instantiation of
that idea: **not** asking a model what should be true, but taking what the repository already
states about itself, checking it while the project's own workload runs, and measuring the two
numbers that decide whether the idea can work at all.

No model, no paid spend, no product change, nothing pushed. Instruments:
`scripts/probe/checkpoint_inventory.py`, `checkpoint_runtime_probe.py`, `checkpoint_type_probe.py`.
Records: [`evidence/2026-09-17-checkpoints/`](evidence/2026-09-17-checkpoints/).

## 0. The answers

| asked | result |
|---|---|
| how many checkpoints does a repository already contain | **2,744 functions of 8 libraries: 2,418 state a return type, 1,359 of those are checkable by a runtime rule, 852 doctest lines state a value, 50 asserts** |
| how many break on healthy code (the noise floor) | **3 of 485 exercised type checkpoints (0.6%)**, after two principled exemptions; **0 of 176** doctest checkpoints where the harness runs them |
| do they break when a defect is planted | **1 of 20** (doctests), **0 of 5** (types) |
| do they localise the defect | **0 of 20**: the one doctest that broke was not in the file the defect was planted in |
| does instrumenting the repository perturb it | **yes, measurably**: jinja's suite is 911 passed clean and 910 passed 1 failed under the wrapper |

The direction is sound in mechanism and weak in yield: a repository's own statements are dense
enough to check and clean enough to trust, and almost never break where its defects are.

## 1. What a repository already states (P-04a)

| library | functions | return types | runtime-checkable | doctest lines | asserts |
|---|---:|---:|---:|---:|---:|
| jinja | 774 | 762 | 399 | 30 | 16 |
| click | 584 | 580 | 298 | 0 | 13 |
| urllib3 | 513 | 501 | 370 | 8 | 7 |
| packaging | 466 | 466 | 224 | 214 | 11 |
| more-itertools | 280 | 0 | 0 | 600 | 2 |
| itsdangerous, python-dotenv, attrs | 127 | 109 | 68 | 0 | 1 |

Two facts shape everything below. **Type statements are everywhere and value statements are
rare**, and the value statements are concentrated in two libraries. A defect that returns the
wrong value of the right type -- which is what most real defects and all of this corpus's
planted ones are -- can only be caught by a value statement.

## 2. The value arm: doctests as checkpoints (P-04b)

Twenty mutation cases of four libraries. The workload is `pytest --doctest-modules` over the
library's own package, on the healthy revision and on the revision with the planted defect.

| library | checkpoints | broken on healthy code | what they are |
|---|---:|---:|---|
| more-itertools | 160 | **0** | a clean noise floor |
| jinja | 16 | **0** | a clean noise floor |
| packaging | 72 | 16 | **harness artifacts**: the examples assume a namespace (`SpecifierSet`) the project's own doctest configuration injects, so a naive runner manufactures `NameError` |
| urllib3 | 6 | unusable | six collection errors; its doctests never ran |

**Detection: 1 of 20. Localisation: 0 of 20.** The single break (`jinja-none_guard-13`) was in a
different file from the planted defect.

## 3. The type arm: return annotations as checkpoints (P-04c)

Five libraries, one case each. A checkpoint is one annotated function, wrapped after import;
it is *exercised* when the suite calls it and *broken* when the returned value is not of the
declared type.

| library | wrapped | exercised | calls | broken |
|---|---:|---:|---:|---:|
| jinja | 363 | 255 | 234,419 | **3** |
| packaging | 201 | 193 | 8,213,061 | 0 |
| python-dotenv | 31 | 14 | 332 | 0 |
| itsdangerous | 22 | 22 | 5,165 | 0 |
| more-itertools | 1 | 1 | 112 | 0 |

**Detection of the planted defects: 0 of 5.**

Two exemptions were needed, and both are properties of the language rather than of the
repositories:

- **A coroutine or a generator is not the value the annotation describes.** An `async def`
  annotated `-> str` returns a coroutine when called. Ten of jinja's first-pass violations were
  this; they are skipped, not counted.
- **`NotImplemented` is the comparison protocol.** All 23 of packaging's first-pass violations
  were `__eq__`, `__lt__` and friends, annotated `-> bool`, correctly returning `NotImplemented`
  to hand the question to the other operand. With the exemption, packaging's noise floor is zero.

Without those two exemptions the noise floor is 26 of 485; with them it is **3 of 485**.

**Those three are genuine.** In `src/jinja2/runtime.py`, `BlockReference.__call__` and
`Macro.__call__` and `Macro._invoke` are each declared `-> str`, and under jinja's own test suite
they returned `int` and `list`. A mature library contradicting its own signature in three places,
found by running its own tests with a two-hundred-line checker and no model.

## 4. Instrumentation is not free

Wrapping module attributes replaces function objects, and code that relies on their identity
notices. jinja's suite is **911 passed** clean and **910 passed, 1 failed** under the wrapper:
`test_pickle` fails with `Can't pickle <function do_capitalize>: it's not the same object as
jinja2.filters.do_capitalize`. The perturbation is small, visible and fixable -- `sys.monitoring`,
an import hook or a coverage-style tracer observes without rebinding -- but a design that
instruments a repository has to prove it did not change what it measured.

## 5. What this says about the direction, and how to sharpen it

The original idea has three parts: a model derives checkpoints from structure, the project runs,
and the first broken link localises the defect. What this probe measured is the part that can be
tested without a model, and it gives five concrete corrections:

1. **The repository's own statements will not break at the defect.** They are type-shaped, and
   real defects are value-shaped. Detection was 1 of 25 across both arms. If the chain is to
   break where the bug is, the value-level checkpoints have to be *authored*, and then the
   question "is the code wrong or is the checkpoint wrong" comes back, which is exactly what the
   differential design exists to answer.
2. **Where a statement does break on healthy code, it is usually the rule's fault, not the
   repository's.** Two language idioms accounted for 23 of 26 type violations and a missing
   doctest namespace for all 16 doctest failures. Every checkpoint rule needs an explicit,
   recorded exemption list, and the honest noise floor is only the number that survives it.
3. **Coverage of the chain is partial**: jinja exercised 255 of 363 checkpoints, python-dotenv 14
   of 31. A chain with holes cannot localise by first break; the most it can say is "the earliest
   broken checkpoint, among those the workload reached".
4. **Observation must not perturb.** Attribute rebinding is the easy way and it changed the
   subject's behaviour on the first library tried.
5. **What it does produce today is a different, cheaper thing than defect discovery**: findings of
   the form *this repository contradicts its own declared type here, and here is the run that
   shows it*, at a noise floor of 0.6% and a cost of zero model calls. Three in jinja. That is a
   repository-level audit, it needs no pull request and no second revision, and its evidence is
   exactly the kind this project already knows how to record.

## 6. Limits

Five libraries for the type arm and four for the value arm, all Python, all from a corpus this
project has used before. One case per library in the type arm, so the detection figure (0 of 5)
is a floor, not an estimate. The checkable annotation rule covers builtin shapes and optionals of
them, not generics, protocols or forward references: 1,359 of 2,418 stated return types. Doctest
checkpoints were run without each project's own doctest configuration, which is why packaging's
sixteen are artifacts. Nothing here used a model, so the part of the original idea that depends
on a model reading structure is untested.
