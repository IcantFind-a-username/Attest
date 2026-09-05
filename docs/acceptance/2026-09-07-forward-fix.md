# The gate level over the forward pairs' fix commits — the new-code direction

**Owner instruction 1.3.** [Data](evidence/2026-09-07-forward-fix.json) · log
`.attest/real-traffic/2026-09-07-forward-fix.log` · product code pinned at `42afd78` ·
**$1.6972** of a $5.00 reservation.

## Why this population

Every gate-level shadow so far has been taken over ordinary commits. A **repair** is the one
change shape where new code is the point: it adds a branch, a guard, a helper — code that by
construction has no merge base, which is exactly what the gate level exists for. The 13 fix
commits of D-135's resolved forward pairs are that population, each paired with its first
parent, and no previous run has covered them.

**13 of 13 ran.**

## The result

| | |
|---|---|
| commits reviewed | **13 of 13** |
| spend | **$1.6972** at `--budget 0.50` |
| **new-code candidates with a witness** | **3** |
| — admissible (`(b)` ∧ (`(a)` ∨ `(c)`)) | **0** |
| — `through_caller` / `through_test_caller` / `direct` | **0 / 0 / 0** |
| red spoke on | 0 of 13 |
| yellow (a) / yellow (b) spoke on | 0 / 0 of 13 |
| green spoke on | **6 of 13** |
| median review elapsed | 32.0 s |
| **image cache lookups / hits** | **7 / 3 — 43%** |

## What it says

**A repair adds almost no new code the gate can see.** Thirteen repairs produced **three**
new-code candidates between them, and not one was admissible: none had a fully annotated
signature together with either a call site outside the added lines or a documented domain.

That is a finding about the level's population, not about its rule. The gate level was designed
for *new code has no counterfactual, so admit it only through a pre-existing caller* — and on
the change shape where new code is most concentrated, discovery produces almost nothing for it
to grade. Its 5.8% cumulative ceiling is not lifted by looking at repairs.

## The image cache, on a population that actually exercises it

**7 lookups, 3 reused — 43%**, across six different repositories. Compare the 1.1 re-run's
**15 of 15**: that run stayed inside two repositories whose dependencies never moved. Together
the two numbers say the same thing from both sides — **the image is built once per repository
per dependency change and reused by every commit in between** — and this is the run that
contains the cold builds.
