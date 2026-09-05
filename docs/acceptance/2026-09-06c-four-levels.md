# The four levels over 40 real commits — 2026-09-06c

Owner instruction 7 of this window, and this window's primary deliverable: **the most recent 20
real commits of `attest` and of `us-stock-helper`, all four levels in shadow, one row per commit
and one column per level, each column carrying the single line the level said or `—`.**

**Spend `$2.029` of an `$8.00` reservation** ($1.4403 for `attest`, $0.5890 for `us-stock-helper`),
plus `$0.2803` for `corum`'s ten commits under the gate item. Reviews ran in **clones**, head
checked out detached, `attest review --base <parent> --k 4 --budget 0.25 --explain`,
`attest.intent.v4.1` unchanged, containers, **local review only — no GitHub client is
constructed, so no publication surface exists**. `--budget 0.25` is this repository's own Action
setting (`pull-request.yml`), so the table describes what a real pull request in these
repositories would get.

Data: [`attest`](evidence/2026-09-06c-four-levels-attest.json) ·
[`us-stock-helper`](evidence/2026-09-06c-four-levels-us-stock-helper.json) ·
[`corum`](evidence/2026-09-06c-four-levels-corum.json) ·
[plan](../../benchmarks/attest-v2/runs/2026-09-06-four-levels-plan.json) ·
[driver](../../scripts/corpus/four_levels.py).

## 1. The speech rate, per level

| level | spoke on | rate | what it costs |
|---|---|---|---|
| **red** | **0 of 40** | 0.0% | the review's own budget |
| **yellow (a)** — impact scope | **0 of 40** | 0.0% | `$0.00` |
| **yellow (b)** — null/Optional | **0 of 40** | 0.0% | one model call per review |
| **green** — repeated implementation | **8 of 40** | **20.0%** | one wording call per note |
| **gate** (shadow, author-invisible) | 61 new-code candidates, 15 admissible, **3 reached `through_caller`** | — | free static witness |
| **every level silent** | **32 of 40** | 80.0% | — |

Over the same 40 commits the reviews read **40 of 40 change units**, proposed **141 candidates**
and drawered **141** — **not one candidate on ordinary owner traffic produced a receipt.**

The drawer's reasons, which is the part worth reading:

| reason class | count |
|---|---|
| the ranking never bought a reproduction for it | **87** |
| the per-review budget ran out before one could be bought | **40** |
| `attest.intent.v4.1`: intent stated in the change itself | 5 |
| the probe deferred on base | 3 |
| the test passed on head (no differential to have) | 3 |
| the probe did not execute the anchored file on base | 2 |
| unfaithful reproduction | 1 |

**The binding constraint on ordinary traffic is the budget, not the adjudicators.** 40 of 141
candidates died because `--budget 0.25` was gone, and 87 more were never ranked high enough to
be bought at all. Only **11 of 141** reached a verdict that any adjudicator is responsible for.

## 2. The third repository, for the gate level only

`corum`'s most recent 10 commits (owner instruction 6) are reported apart, because they are not
part of the 40:

| | corum (10 commits) |
|---|---|
| red | 0 |
| **yellow (a)** | **1** — the first time this level has spoken on a commit nobody constructed |
| yellow (b) | 0 |
| green | 1 |
| gate | 4 new-code candidates, 3 admissible, **3 `through_caller`** |
| every level silent | 9 of 10 |

The yellow (a) note, in full:

```
[yellow] scripts/benchmark_fusion.py:64 — `_build_context` changed signature; 1 call site(s)
name it, 1 of them named by no test — scripts/benchmark_fusion.py:194
```

## 3. The 40 rows

| # | repo | commit | subject | red | yellow (a) | yellow (b) | green | gate (shadow) |
|---|---|---|---|---|---|---|---|---|
| 1 | `attest` | `eede42194d` | feat(yellow): three measured conditions, and a | — | — | — | scripts/corpus/impact_scan.py:62-68 `git` and scripts/corpus/qualify_controls.py:45-54 `git` normalise to token … | 4 new-code cand., no witness |
| 2 | `attest` | `9b1c9a8699` | fix(journal): a delivery row is read under the | — | — | — | src/attest/benchmark/measurement.py:1763-1769 `_exact_number` and src/attest/review/ci.py:914-920 `_delivery_num… | — |
| 3 | `attest` | `e8468bae12` | docs: the 2026-09-06b handoff | — | — | — | — | — |
| 4 | `attest` | `8537f6a9d3` | docs: the probe generator measured, yellow pub | — | — | — | — | — |
| 5 | `attest` | `150804a34b` | fix(publication): an inline comment is placed  | — | — | — | src/attest/review/executor.py:816-905 `generate_repro` and src/attest/review/executor.py:908-997 `generate_probe… | **through-caller ×2** — src/attest/github/presentation.py:186 `_anchored` |
| 6 | `attest` | `993ae171e7` | fix(m01): the measurement probe replays the ge | — | — | — | — | — |
| 7 | `attest` | `1408232462` | docs(v0.1): a changelog, and the gap list re-r | — | — | — | — | — |
| 8 | `attest` | `48b418c895` | feat(repro): the merge base writes the asserti | — | — | — | src/attest/review/executor.py:812-901 `generate_repro` and src/attest/review/executor.py:904-993 `generate_probe… | 4 new-code cand., no witness |
| 9 | `attest` | `c88f67e599` | feat(yellow): the impact scope speaks, and the | — | — | — | src/attest/benchmark/measurement.py:1763-1769 `_exact_number` and src/attest/review/ci.py:890-896 `_delivery_num… | 6 new-code cand., no witness |
| 10 | `attest` | `e7472cd5fd` | docs(null): the independent population closes  | — | — | — | — | — |
| 11 | `attest` | `1f4283bea8` | docs: the 2026-09-06 handoff, with the gate re | — | — | — | — | — |
| 12 | `attest` | `0abdb8a8ce` | docs(impact): the four-hop bound produces spee | — | — | — | — | — |
| 13 | `attest` | `820b973d09` | fix(impact): a constructor is addressed by its | — | — | — | — | 3 new-code cand., no witness |
| 14 | `attest` | `95ea011b86` | refactor(impact): drop the two indexes nothing | — | — | — | — | — |
| 15 | `attest` | `8c0ceaf22d` | fix(output): a CJK hedge has no word boundary  | — | — | — | — | 2 new-code cand., no witness |
| 16 | `attest` | `84c75985a0` | feat(output): one line per finding, and a form | — | — | — | scripts/corpus/impact_scan.py:56-62 `git` and scripts/corpus/qualify_controls.py:45-54 `git` normalise to token … | **through-caller ×1** — src/attest/review/impact.py:160 `is_test_path` |
| 17 | `attest` | `6579a8fec7` | feat(gnull): the stop rule is a probe, and the | — | — | — | scripts/corpus/null_study.py:148-154 `git` and scripts/corpus/qualify_controls.py:45-54 `git` normalise to token… | 5 new-code cand., no witness |
| 18 | `attest` | `abad758265` | docs: the 2026-09-05d handoff, cut to a page,  | — | — | — | — | — |
| 19 | `attest` | `8c83d897de` | docs: the 2026-09-05d handoff, and the docs ma | — | — | — | — | — |
| 20 | `attest` | `4c3492065c` | feat(fwd): 11 forward pairs reviewed - 3 publi | — | — | — | — | — |
| 21 | `us-stock-helper` | `b2fb91af28` | ci: review pull requests with Attest, same-rep | — | — | — | — | — |
| 22 | `us-stock-helper` | `9a68477722` | docs: verify dual-entry fix in production and  | — | — | — | — | — |
| 23 | `us-stock-helper` | `aa2a4cff8c` | docs: log nasdaq halt-timestamp fix in adapter | — | — | — | — | — |
| 24 | `us-stock-helper` | `3f6b67b0b6` | fix: stamp nasdaq halts at the halt time, not  | — | — | — | — | 2 new-code cand., no witness |
| 25 | `us-stock-helper` | `fa85b21778` | docs: hand the branch over to a sonnet-tier ag | — | — | — | — | — |
| 26 | `us-stock-helper` | `44d396cabf` | docs: record the dual-entry republication fix  | — | — | — | — | — |
| 27 | `us-stock-helper` | `ead0bd75d4` | fix: stop republishing multi-party filings as  | — | — | — | — | — |
| 28 | `us-stock-helper` | `4b1ad18ab9` | fix(analysis_core): use fsum in moving_average | — | — | — | — | — |
| 29 | `us-stock-helper` | `381c0a051c` | backlog: mark fixture cross-platform float ite | — | — | — | — | — |
| 30 | `us-stock-helper` | `07a6946b7f` | docs: record the follow-up round in the ledger | — | — | — | — | — |
| 31 | `us-stock-helper` | `540b0a8154` | chore: add a one-shot evidence-gate measuremen | — | — | — | — | 9 new-code cand., no witness |
| 32 | `us-stock-helper` | `58bf76382b` | test: pin agency positive attribution and 13g  | — | — | — | — | — |
| 33 | `us-stock-helper` | `9c023e6b16` | docs: propose a fix plan for dual-entry filing | — | — | — | — | — |
| 34 | `us-stock-helper` | `bdeaf675a8` | docs: record the widened evidence sources and  | — | — | — | — | — |
| 35 | `us-stock-helper` | `4ef2226bcf` | fix: remember what each feed already published | — | — | — | scripts/local_runtime_support.py:1150-1168 `_require_private_directory` and scripts/local_runtime_support.py:117… | 7 new-code cand., no witness |
| 36 | `us-stock-helper` | `801fb292ce` | feat: add verified regulatory and agency sourc | — | — | — | — | — |
| 37 | `us-stock-helper` | `abefa25f7d` | feat: register verified company ir feeds | — | — | — | — | — |
| 38 | `us-stock-helper` | `8cfab6c5a7` | feat: widen sec current-filings coverage to 10 | — | — | — | — | 2 new-code cand., no witness |
| 39 | `us-stock-helper` | `e820bd182d` | docs: adapt the handoff for cursor's toolset | — | — | — | — | — |
| 40 | `us-stock-helper` | `0f11a61479` | docs: specify the authoritative source adapter | — | — | — | — | — |

## 4. Three rows checked by hand, per level

### green — 3 of the 8 checked, **3 correct, 1 of the 3 not worth saying**

1. **`attest eede4219`** — `impact_scan.py:62-68 git` vs `qualify_controls.py:45-54 git`,
   similarity 1.000. **Correct.** Both are a five-line `subprocess.run(["git", "-C", …])`
   wrapper that raises `RuntimeError` on a non-zero return code; they differ only in the local
   name (`done` vs `result`) and the error truncation (`[:160]` vs `[:300]`). The level's
   normalisation erases exactly those two differences, which is what it says it does.
2. **`attest eede4219`** — `impact_scan.py:62-68 git` vs `null_study.py:148-154 git`,
   similarity 0.971. **Correct**, and it is the same `git` wrapper a third time. Two notes about
   one duplicated helper is the cap doing its job badly: an author reads "this helper exists
   twice" and then reads it again.
3. **`attest eede4219`** — `measurement.py:1763-1769 _exact_number` vs
   `ci.py:914-920 _delivery_number`, similarity 0.960. **Correct and the most useful of the
   three**: both are a seven-line exact-number validator with the same `type(value) not in
   {int, float}` / `math.isfinite` / lower-bound shape, in two subsystems that do not import each
   other. This is the case the level was built for.

**Judgment: green is right about what it measures and says nothing about whether the duplication
matters.** Its failure mode on this corpus is repetition, not error — three of the eight notes
are the same `git` helper.

### yellow (a) — the 1 note there is, checked in full: **true, and not actionable**

`corum 14c363dd` (`feat: fuse calibrated reviewer pairs`):

- `_build_context` did gain a keyword-only `pair_block` parameter — **true**;
- it has exactly one call site, `scripts/benchmark_fusion.py:194`, inside `run_benchmark` —
  **true**;
- no test in the repository names `run_benchmark` — **true** (three tests name
  `_build_context` *directly*, which is why the level says *named by no test* and never *not
  covered*).

**And the author updated that call site in the same commit.** So every clause is correct and the
note tells the author nothing to do. This is precisely the failure D-145's adjudication found on
the six disjunctive firings, reproduced on the one commit where the conjunction fires: a1 pairs an
interface fact with a coverage proxy, and a coverage proxy cannot say whether anything is broken.
**a3 is the condition that would have said something here, and it correctly did not fire —
the caller passes the right arguments.**

### red — **0 of 40**, so the three checked are from elsewhere, and that is the point

Nothing on 40 commits of ordinary owner traffic. The three most recent red publications this
project has, all from constructed or historical work:

1. [PR #11](evidence/2026-09-06c-pr11-comment.md) `scripts/corpus/four_levels.py:212` —
   `_latest_task` gained a required parameter, receipt `e89b0fe548b6`. **Correct**: the test
   calls it with one argument, base returns `'task-two'`, head raises `TypeError`, three runs each
   way. This defect was **constructed** for the demonstration.
2. [PR #11](evidence/2026-09-06c-pr11-comment.md) `src/attest/review/impact.py:492` —
   `_addressable_name` indexes `parts[-2]` for a top-level dunder, receipt `c8e0ac213e2d`.
   **Correct**, and also constructed.
3. `itsdangerous 3703fbdedd` from the forward-pair run
   ([report](2026-09-06b-forward-pairs-probe.md)) — a real historical defect, published with a
   receipt whose bundle verifies offline.

**Judgment: red's precision is not what the 0 of 40 measures.** What it measures is that a
defect-introducing commit is rare in this traffic and that `--budget 0.25` stops the search early
— 40 of 141 candidates died with the budget gone.

### gate (shadow) — 3 `through_caller` grades checked, **3 correct**

1. `attest 150804a34b` `presentation.py:186 _anchored` — the reproduction enters at
   `executor.py:2216` and `_anchored` runs underneath. **Correct**: the added function is reached
   through a caller outside the added lines, which is the grade's whole definition.
2. `attest 84c75985a0` `impact.py:160 is_test_path` — enters at `structural.py:263`. **Correct.**
3. `corum 14c363dd` `fusion.py:494 fuse_known_pair_likelihoods` — enters at
   `tests/test_fusion.py:859`. **Correct**, and it is the interesting one: the entry point is a
   *test*, so the caller exists but the witness comes from the suite rather than from production
   code. The grade does not distinguish those, and it should be asked to.

**Judgment: the witness is doing what D-137 says.** 3 of 61 new-code candidates reached
`through_caller` — a 4.9% ceiling on how often the gate level could speak at all if it were live,
which is the number the pilot needs and is now **9 of 224+61 = 285 candidates** cumulatively
(2026-09-05's 0 of 224 plus this window's 3 of 61, plus 6 more on the forward pairs — §5).

### yellow (b) — nothing to check

0 notes on 40 commits, 0 on the 79-unit scan, and 13 of 13 hypotheses void. The level has never
produced a sentence.

## 5. The gate level's cumulative shadow, across every population

| population | new-code candidates | admissible | **`through_caller`** | `direct` |
|---|---|---|---|---|
| E-04 stratum v2 (2026-09-05) | 224 | 0 | **0** | 0 |
| 11 forward pairs (this window, free replay) | 25 | 12 | **3** | 0 |
| `attest` + `us-stock-helper`, 40 commits | 61 | 15 | **3** | 0 |
| `corum`, 10 commits | 4 | 3 | **3** | 0 |
| **cumulative** | **314** | **30** | **9** | **0** |

`G-NEWCODE-001`'s pilot has **9 observations at the publishing grade out of 314 new-code
candidates (2.9%)** and **zero at `direct`**. The 2026-09-05 run's 0 of 224 is no longer the whole
record, and the reason it was zero is now visible: that run's witness had no reproduction to
enter through, so `through_caller` could not be reached at all.

## 6. What the table is for, and what it is not

**It is the first honest picture of what this product says to an author.** On 40 commits of the
owner's own work it speaks 8 times, all green, all about repeated implementation, and three of
those eight are one duplicated `git` helper. It is silent on 32 of 40.

**It is not a precision or a recall measurement.** No commit in the 40 is known to contain a
defect, so a silence cannot be scored, and the one non-green note (on `corum`, outside the 40)
was true and useless. What the table does settle is the **cost of speech**: `$2.03` for 40
reviews, `$0.051` a commit, and 80% of them produce one line that says only how much was read.
