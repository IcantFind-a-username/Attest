# E-04 shadow, stratum v2 — 100 units on the owner's recent traffic

Study ID: `attest.e04-prospective.v2`. Gate: `G-SHADOW-001`, second stratum. Ordered by the
owner on 2026-09-04 ("E-04 to 100 units, prospective shadow on my repositories' recent
commits, no publication").

## What this stratum is, and what it is not

**It is not prospective.** Stratum v1 reviewed commits made *after* its protocol was frozen —
two of them, which is why a second stratum was ordered. The units here already existed when
this protocol was frozen: they are the most recent non-merge commits in the authorized
repositories. Every claim from this stratum must say so. `G-SHADOW-001` asks for a prospective
run and **this stratum does not supply one**; it supplies volume on real, recent, unseen-by-the-
product changes, which is what the owner asked for and what v1's n = 2 could not give.

The product has still never reviewed these commits, and the review is blind to any later
history: head = the commit, base = its parent, exactly as CI would see the pull request.

**Nothing is published.** The local review path only; no GitHub client is constructed, so no
comment, review or status can be written. The study bundle carries counts and candidate ids,
never a claim, file or line.

## Population and units

Every non-merge commit reachable from the default branch of a repository the authorization
names (clones under `.attest/corpora/<name>/`), reviewed as head = the commit, base = its
parent. Strata by subject prefix: `docs`, `refactor` (chore/style/test/build/ci/perf),
`feature`, `fix`, `other`. No unit is excluded after it is recorded; a unit whose review cannot
run is recorded with its DEFER reason.

**Allocation.** Newest first **within each repository, round-robin across repositories in name
order**, until `target_units` is reached or every repository is exhausted. A repository with a
short history contributes what it has and the remainder is taken from the others.

> **Correction, before any unit ran.** The first draft of this clause said "newest first, up to
> `target_units`" over the population as a whole. On this population that is degenerate: `Attest`
> is by far the most recently active repository, so all 100 units would have come from it — the
> product's own repository, the standing disclosed conflict of interest, and no breadth at all.
> The rule was corrected and this protocol re-frozen **before a single review ran and before a
> single paid call**; the discarded sample file was deleted with it. The freeze exists to stop a
> rule being chosen after outcomes are seen, and no outcome existed.

## Procedure

1. `freeze` writes the digest over this file, `preregistration.json` and
   `authorization.json`; the preflight refuses any later edit.
2. `select` records each unit with its stratum and the seeded silent-audit draw **before** any
   review runs.
3. `run` reviews each recorded unit through the local review path — the same verification stage
   CI uses, so the would-publish set equals what CI would post — at K = `k_samples` and the
   **shipped product default** per-review budget, containers. It records counts, the
   would-publish candidate ids, the DEFER reason, cost and latency.
4. **Every silence carries `read N of M units`.** A review that read fewer change units than the
   commit contains covers only what it read, and the record says which — a silence over a
   partly-read commit is not evidence about the part that was never priced.
5. Truth: every would-publish finding is adjudicated product-blind. With zero findings there is
   nothing to adjudicate and eligible detection stays `INSUFFICIENT`.

## Stops

`safety_stop_wrong_findings` wrong shadow findings; **any publication at all** (there is no
publication surface, so one would be a defect in the harness); the cost cap; any receipt or
security bypass.

## Product code

This stratum runs at the window's tip, which includes D-124 (the bundle carries the test that
ran, and certification verifies its own output), D-125 (the publication family is the change
unit) and D-126 (the default budget is $1.00). Stratum v1 ran before all three and its numbers
are not comparable; they are reported apart, never merged.
