# Handoff — 2026-09-13 · six phases to `v0.1.0`

Baseline `7483a54` (`main`). Budget for the whole task: **$12**, against a cumulative
$90.01 of the $110 cap. One section per phase, appended as each merges.

---

## Phase 1 — the publication rule

Branch `feature/suppression-sources` · report:
[the score bar is removed](acceptance/2026-09-13-publication-rule.md) ·
decision [D-199](../DECISIONS.md) · **$0.00 of $0.00 reserved**

### The one sentence

**The score bar is gone: a reproduction the kernel accepted now publishes under the cap alone,
which a replay of every recorded ledger turns into +25 findings and −0, with the control side
at +0 under the intent policy in force — and the per-unit multiplicity cap is given up with it,
so the product from here offers the receipt and nothing statistical.**

### 1. Step 1, and the two readings the owner was shown

The 35 bar-suppressed receipts, each resolved to its review's own `(head, merge_base)` and
matched on **both** shas against the committed plans:

| population | suppressions | reviews |
|---|---|---|
| defect | 13 | 7 |
| **control** | **2** | 2 |
| neither (E-04 shadow 14, four-levels 6) | 20 | 8 |

The two control rows are `c02` `1d0af73c3e` and `c04` `33aa333ec0`; their `m_u` of 10 and 5 are
exactly the `m` column the 2026-09-03 real-traffic report prints for those cases, so the
classification does not rest on a sha match. **That reading fails your precondition, and phase 1
stopped on it.** Re-judged under the intent policy the product runs today, both are
`behavior_change` — *"the change states its own intent"* — and never become receipts at all:
**control side 0.** You were shown both and chose to proceed. The zero's denominator is four
control receipts, and no designated control arm has ever run under v4.x code (D-196).

### 2. Step 3, the replay

129 ledgers, 609 `publication_policy` rows, 91 carrying a certified set, **90 of 91 reproducing
their own record and 0 disagreeing**. The one exclusion is the copied external-receipt ledger,
which published 1 of 1 and suppressed nothing, so the rule changes nothing for it.

| population | added | removed | added, restricted to today's intent policy |
|---|---|---|---|
| defect | **+11** | −0 | +1 |
| **control** | **+2** | **−0** | **+0** |
| neither | **+12** | −0 | +5 |
| total | **+25** | **−0** | +6 |

Twenty-five from thirty-five, because **the hard cap and the cluster rule absorb ten** — the
first time the cap has bound anything: the census found it had suppressed 0 of 574 rows. The 25
are **identical, id for id, to the baseline D-182 filed and declined**, computed by a different
script under a differently-worded rule: two implementations agreeing on the same set.

### 3. What moved in the code, and what did not

`PUBLICATION_POLICY_SCHEMA_VERSION` `v3` → `v4`; the bar is computed and recorded, not applied;
`score_bar_applied: false` on every row; `pr_error_bound: 1.0` and
`e_value_validity: "not-applied"`; historical rows replay under their own version's rule and an
unknown version fails closed. **Unchanged:** `alpha`, every likelihood ratio, `k_samples`, the
hard cap, the supported interpreter range, the isolation backend. D-125's and D-174's own
behavioural tests are kept, pinned at `schema_version="attest.publication-policy.v3"` — the
replay rule exercising itself rather than a weakened assertion.

### 4. Also in this phase

- `docs/mainline.md` §5 A now carries the **arithmetic ceiling** as its own paragraph, marked as
  the ceiling *before* the change, and the new rule under it (your default-yes item 1 of the
  2026-09-12b handoff).
- `docs/backlog.md`: **`T` has never fired in 2,589 recorded reviews** — one of three evidence
  channels is dead on every measured path, and nobody has established whether that is
  configuration, pricing or a design conclusion. Free to diagnose. Filed P1.
- `G-CERT-004` amended: this is the first amendment to that gate that *removes* an assertion
  rather than correcting one, and it says so.

### 5. Gates

| | |
|---|---|
| `checks` on the pull request | **2,179 passed, 10 skipped**, 17m58s — success |
| `gates` on `main` after the merge | **2,201 passed, 10 skipped**, 20m58s; **coverage 93.39%** against the 90% kernel floor — success (run `34391843795`) |
| the `attest` self-review on the pull request | pass, 1m26s |
| `ruff` · `mypy` · `git diff --check` | clean |
| paid | **$0.125900** — the self-review the pull request buys, which is also **the first review ever run under D-199's rule**. It read 1 of 17 units, stopped on the discovery share, and published nothing |

Merged at `18:54:14Z`; `main` is green.

---

## Phase 2 — E-04 prospective shadow

Branch `feature/e04-shadow-v3` · report:
[29 pull requests, 0 published, and a zero that means nothing yet](acceptance/2026-09-13-e04-shadow-v3.md) ·
study `benchmarks/studies/e04-prospective-v3` · **$1.793201 of $6.00 reserved**

### The one sentence

**Twenty-nine pull requests ran and none published — but all 24 reproduction attempts died at
`environment bootstrap failed`, so no publication was ever reachable, and a zero over a closed
path is not a safety result.**

### 1. The population, and the estimate that sized it

29 pull requests across the six repositories under the owner's account that are Python-primary
and have at least one pull request; `Sovereign-Founder-OS` (Rust, 64 pull requests) excluded for
language and named. **Five drills excluded before any unit ran**, by a title rule written into
the protocol — a publication on a planted defect is a true positive and may not sit in a
false-publication denominator.

Estimate at the last measured rate ($0.118/case on the 2026-09-12b corpus rebuild; $0.0078–$0.35
on this repository's own self-reviews): 29 × ~$0.12 ≈ **$3.5**, comfortably inside $6.
**Measured: $1.793201**, mean $0.062, largest single review $0.1696. The cap was never
approached and **$4.206799 was released**.

### 2. Result

| | |
|---|---|
| units | **29 of 29** |
| candidates · eligible · attempted | 223 · 33 · 24 |
| certified | **0** |
| **published** | **0** |
| budget-limited units | 11 (179 of 298 change units read) |

One line per pull request is in the report's §2.

### 3. Why the zero is vacuous, diagnosed rather than assumed

Every one of the 24 attempts: `environment bootstrap failed … the image build timed out after
~897 s`. Four observations pin it on the host:

1. `docker run python:3.13-slim` works and reaches PyPI with a `200` — container networking is fine;
2. `ensure_image` with an hour's headroom still fails at the builder's own 1800 s ceiling;
3. a two-line Dockerfile whose base image is **already local** hangs >90 s at
   `#2 [internal] load metadata for docker.io/library/python:3.13-slim`;
4. the build cache holds **77.8 kB** — the failed builds cached essentially nothing.

**Buildkit cannot resolve registry metadata on this host.** The same build takes **27.9 s** on a
GitHub runner, measured on this project's own external receipt. The product did nothing wrong:
all 24 are recorded DEFERs naming their reason.

### 4. `G-SHADOW-001`: FAIL, and two of three reasons are structural

1. **all-silence** — the gate's own text calls it a utility failure regardless of precision;
2. **scale** — the design asks ≥500 pull requests across ≥30 repositories, ≥100 adjudicated
   findings, ≥200 adjudicated silences. The owner's whole account holds **29** reviewable pull
   requests across **6** supported repositories. **No budget fixes this**;
3. **prospectivity** — 1 unit of 29 is genuinely prospective (`Attest#19`).

What the population *can* establish is mainline §1 condition 5 — one prospective run, no false
publication — and that still needs a working executor.

### 5. The re-take

`.github/workflows/e04-shadow.yml` (`workflow_dispatch`) runs **the same frozen sample** on
`ubuntu-latest`. Nothing about the study changes; the local review path still constructs no
GitHub client, so no comment can reach any repository. `OneTapVocal` is private and
`GITHUB_TOKEN` cannot clone it, so the runner reports it **skipped by name** rather than dropping
it. The local trials are kept as `trials-local-host.jsonl` so both columns stay readable.

### 6. One thing that cost money and bought nothing

The driver's first draft resolved a pull request's base as `merge-base(head, the base branch
today)`. For a **merged** pull request the base branch already contains the head, so that is the
head itself and the diff is empty: **nine units reviewed nothing for $0.19**. Caught before any
unit produced a non-empty review, protocol re-frozen against the API's own `base.sha`, those
trials discarded rather than counted, and the dollar recorded in `DEVSPEND.md` as spend that
bought nothing.

---

## Phase 3 — the red-team matrix, thirteen of thirteen

Branch `feature/redteam-thirteen` · report:
[the matrix](acceptance/2026-09-13-redteam-thirteen.md) · decision
[D-200](../DECISIONS.md) · **$0.00** — the matrix calls no model

### The one sentence

**All thirteen preregistered attack classes are now dispatched for real on the production
backend and every one is marked, never certified — and the two new fixtures that were built to
ask whether the *kernel* refuses were both refused by the *product's own guard*, which is the
gate's open half restated in sharper form.**

### 1. The four classes, and what each was missing

| class | what the old matrix lacked |
|---|---|
| **`/proc`** | the `keyfile` fixture opened `/proc/1/environ` for **one canary string** — a secret test that happens to touch `/proc`, asking nothing about `/proc` itself |
| **home / git** | nothing at all: no `.gitconfig`, no `.git-credentials`, no ssh key, no `gh` token, no check that the reviewed tree's `.git` is absent |
| **native syscall** | nothing dispatched below Python. `socket`, `dns` and `processes` all go through the interpreter, so all three are consistent with a hook refusing and the kernel doing nothing |
| **namespace** | nothing |

### 2. Result

**PASS — 13 attack fixtures, 13 actually dispatched, 1 positive control** (run `34408444454`
at `9657f40`, `Linux x86_64`, docker 28.0.4, `linux-container-v1`). Nothing skipped, nothing
`xfail`ed, no assertion relaxed. **Nothing needed fixing**, so no isolation change was made —
the owner's rule that a fix must be a tightening of the isolation layer never came into play.

### 3. The half that stays open, and it is sharper now

`native` and `namespace` were both refused with `reproduction attempted to create a child
process` — **the product's own containment guard**, at the first repeat. Correct refusals,
correctly marked. But those two fixtures exist to ask whether the **kernel** refuses, and the
run does not say. The one external observation on file watches seven syscalls and attests
**network egress and process creation only**; **eleven of thirteen classes have no external
observation of any kind.**

### 4. Where an operator reads it

`SECURITY.md` gains **Known unmitigated**, four numbered items each with **attack preconditions**
and **blast radius**: the observation gap, the per-interpreter audit, the no-Docker fallback
having no OS boundary at all, and no third-party penetration test. The external observer's real
coverage is written there in those words.

---

## Phase 2b — the E-04 re-take, on the platform the product ships to

**$2.761259** over two dispatches ·
[report §R](acceptance/2026-09-13-e04-shadow-v3.md)

| | local host | **the runner** |
|---|---|---|
| units | 29 | **28** (`OneTapVocal` private, **skipped by name**) |
| candidates · eligible · **attempted** | 223 · 33 · 24 | 191 · 19 · **13** |
| **bootstrap failures** | **24 of 24** | **0** |
| certified · **published** | 0 · 0 *(vacuous)* | 0 · **0** |

**Zero false publications over 28 real pull requests with a working executor, under D-199's
rule.** Thirteen reproductions actually ran in `linux-container-v1`; their outcomes are
adjudications — 4 collection failures, 3 unfaithful tests, 6 other — not a closed door. That is
the substance of mainline condition 5.

`G-SHADOW-001` **stays FAIL**: all-silence is a utility failure by its own text, and the scale
and prospectivity reasons are structural. Nothing certified, so **precision is undefined** and
this measures no recall either.

The first dispatch died after 4 units on the private repository the workflow skips and the
driver did not — [PR #21](https://github.com/IcantFind-a-username/Attest/pull/21), the same
family as D-177 and D-190: a missing input is a stated refusal, not a crash.

---

## Phase 4 — the yellow census, the control rate, and a line that was not a line

Branch `feature/yellow-census` · report:
[every yellow and green line](acceptance/2026-09-13-yellow.md) · decisions
[D-201](../DECISIONS.md), [D-202](../DECISIONS.md) · **$0.00**

### The one sentence

**Yellow (a) speaks about 1 in 68 commits nobody had to fix and what it says there is true; and
while counting the lines the product has shown its own authors, six of the eleven turned out not
to be lines at all.**

### 1. The census, eleven self-reviews since D-174

| green | yellow (a) | yellow (b) | propagation | red | `[silent]` | **unmarked `DEFER:`** |
|---|---|---|---|---|---|---|
| 4 | **1** | 0 | 0 | **0** | 3 | **6** |

Yellow (a) spoke on **1 of 11 pull requests (9.1%)**, once, truly, and not actionably. A counting
correction is inside the report: the first pass said two notes and they are **one note read
twice**, because a note reaches an author as an inline comment *and* in the summary.

### 2. The controls, deterministic, no model call

| level | population | triggered | rate | Wilson 95% |
|---|---|---|---|---|
| **yellow (a)** | **68 controls** | **1** | **1.47%** | **[0.26%, 7.87%]** |
| yellow (a) | 11 forward pairs | 0 | 0.00% | [0.00%, 25.88%] |
| yellow (b), propagation | 68 controls | 0 | 0.00% | [0.00%, 5.35%] |
| yellow (b), null/Optional | — | closed by D-169, reaches no surface | — | — |

**The control count is 1, not 0.** It is a true statement (`9 call sites in 2 files and no test
names this function`) and the only way to silence it is to raise a4's threshold — a loosening,
which your rule for this phase forbids. It stands as a known limitation, in the README, with its
interval.

**Why the number moved from 2 of 68.** `482b6a5` — D-174's *"a call site is what the name
resolves to"* — **is not an ancestor of the commit that recorded the 2026-09-08 evidence**. That
number was taken before the fix. This is the first measurement of yellow (a) after D-174, and the
backlog's standing a4 concern now has a margin of two events instead of one.

### 3. Condition 7 did not hold, and still does not — but for one reason instead of two

Six of the eleven published `DEFER: verification deferred: … (3 candidates)` — no level marker,
no coordinate, no unit count — including **this task's own #20, #21 and #22**. The product's own
adjudicator refuses that line; it was published anyway because nothing adjudicated it. Fixed as
**D-201** in the shape you chose: a fifth silence verdict, same register, four classes, and the
published sentence is the register's own so no traceback, runner path or key can reach it.

**And the pull request that fixed it found the next one.** Its own self-review published two
well-formed green lines under a header the contract forbids outright — `Review complete.` /
`No finding was verified by a reproduction; abstained.` Condition 7 says *"no preamble"*. That
text comes from `render_complete`, it pre-dates D-142, and **the summary body has never been
adjudicated at all** — only the lines inside it. **I did not fix it**: this surface's copy is
yours, taken four times, D-201 was one narrowly-scoped change you approved, and rewriting the
summary header is a second and larger one nobody asked for. **Condition 7 is `FAIL` in the
release checklist**, with one gap closed and one open, and it is item 1 of the three at the end
of this handoff.

---

## Phase 4b — three owner decisions

Branch `feature/owner-three` · decisions [D-203](../DECISIONS.md), [D-204](../DECISIONS.md),
[D-205](../DECISIONS.md) · **$0.00**

### 1. D-203 — the trailers stay, and D-002 binds forward

**249 commits** on `main` carry `Co-Authored-By: Claude Opus 5`, plus 5 merge subjects naming a
`claude/*` branch. Rewriting them would invalidate every sha in every acceptance report, every
receipt's `head_sha`, and every install ref — the evidence chain the product's claims rest on.
D-002 now binds **commits made after D-002**, and the checklist item is judged on **this task's
commits**, which are clean. What is *not* claimed: that this history is free of vendor names. It
is not, 249 times, and `git log --grep` finds them in a second.

### 2. D-204 — the summary body is adjudicated end to end

`Review complete.` and `No finding was verified by a reproduction; abstained.` are **deleted**. A
body is now: the headings the product owns, contract lines, collapsed blocks, one spend footer —
and **a review with nothing to say *is* its silence line**, no header above, no footer after,
because that line already carries the spend. `check_summary` refuses anything else as
`summary_preamble`; a refused body is replaced by the deterministic silence line and the
substitution is written to the ledger. **No receipt can be lost**: certified findings reach the
author through the inline review, independent of the summary since D-180.

**The deletion broke one branch and the tests caught it.** A **mixed** outcome spliced its
`DEFER:` text over the `Review complete.` header; with the header gone the splice matched nothing
and dropped the notice entirely. A mixed outcome is now the findings' lines, with the deferral in
the collapsed run status — which carries the counts *and* each reproduction's own failure reason,
strictly more than the one line of prose it replaced.

**Condition 7 now holds**: both gaps the census found are closed, D-201 and D-204.

### 3. D-205 — the gate asks what the evidence can answer

`G-SHADOW-001`'s bar becomes mainline condition 5's own sentence: one prospective run, real
executed reproductions, zero false publications. **PASS** on the runner re-take — 28 units, 13
executions, 0 bootstrap failures, 0 published. The scale design (≥500 pull requests, ≥30
repositories, ≥100 adjudicated findings) moves to a **post-release goal**, with the reason: this
account holds **29 across 6**, so no budget reaches it.

**Three caveats travel with the PASS, in the gate's own text**: all-silence, so **precision is
undefined and utility unproven**; **no recall measured**; **one prospective unit of 29**.

---

## Phase 5 — the release documentation

Branch `feature/release-docs` · **$0.00**

### 1. The README, rewritten for someone who does not work here

- **One sentence at the top**, and it leads with the constraint rather than the ambition: *a
  pull-request reviewer that only says things it can prove, and abstains out loud when it
  cannot* — followed immediately by the number that sizes it, **7.1% recall**.
- **A results table where every row carries its interval and its report link**, and a right-hand
  column saying what each number is *not*: recall 2 of 28 [2.0%, 22.6%]; 0 false publications on
  28 shadow pull requests with 13 real executions; 0 on 68 + 40 controls **at K=4**; yellow (a)
  1 of 68 [0.26%, 7.87%]; propagation 0 of 68 [0.00%, 5.35%]; 13 of 13 red-team classes.
- **Known limitations, ordered by what bites first**: the 7.1% and its three loss sources (17
  probes that do not collect, 17 refused **on the merge base**, 13 the intent clause); Python
  and pytest only, 3.10–3.13; the gate level in shadow at 0 of 445; the two known-untested arms
  with their prices; and a silence is never a true negative.
- **The quickstart workflow is copyable whole** and pins `@v0.1.0`.

### 2. Developer material moved out

`docs/contributing.md` is new and holds the local CLI, the development setup, the Action's
internals and a table pointing at `DECISIONS.md`, `DEVSPEND.md`, the gates, the backlog and the
acceptance reports — plus the five rules that are not obvious to a newcomer. The README keeps a
four-line pointer. `docs/README.md` indexes it.

### 3. The L-01 exit list, checked item by item

All eight documents exist and were read against the code: install ref, quickstart, base-owned
policy, support matrix, privacy and retention, failure copy, kill switch, rollback.

### 4. What the consistency pass caught

**`docs/operations/us-stock-helper-attest-review.yml` still uploaded `.attest/ledger.jsonl` and
not `.attest/evidence/`** — the exact gap D-194 closed in the other three copies, left behind in
the fourth. It is the file an outside repository would have copied, so it would have shipped a
workflow whose `attest verify --bundle` line had nothing to point at. All five copies now pin
`@v0.1.0` and upload the same two paths.

`pyproject.toml` is `0.1.0` — **the one hand-written place**; `attest.__version__` reads the
installed metadata, so the `0.1.0rc1`/`0.1.0rc2` disagreement `v0.1.0-rc.2` shipped cannot recur.
The packaging test failed locally until the editable install was refreshed, which is the stale-
install failure mode the backlog predicted after D-194.

### 5. And D-201/D-204 on real traffic, first sighting

[PR #24](https://github.com/IcantFind-a-username/Attest/pull/24)'s own self-review published a
contract line where its six predecessors published prose:

```
[silent] read 2 of 5 units; deferred (probe-base-collection): pytest could not collect the
probe on the merge base, so the base side of the differential never ran; nothing was
verified; ledger: https://…/runs/34422433277; $0.3126, 107.2s.
```

Marker, units read, named class, the register's own sentence, the ledger link, spend and elapsed
— with no preamble above it.

---

## Phase 6 — the release checklist and the tag

Branch `feature/v010-release` · checklist:
[the `v0.1.0` release checklist](acceptance/2026-09-13-v0.1.0-release.md) · announcement draft:
[not published](announcement-draft.md)

### The verdict

**Every checklist item passes.** One mainline condition — 4, recall — **fails on its own gate and
is recorded as failing**; by your decision at the start of this window `G-RECALL-002`'s 70% is a
post-release target that does not block `v0.1.0`. It is written as a fail that does not block,
**not** as a pass, and **the gate was not restated at a number the evidence happens to meet**.

### Mainline's seven conditions: six hold, and three of them closed here

| # | 2026-09-12 | now |
|---|---|---|
| 3 — head code cannot read secrets, reach the network, forge a result | **FAILS**, 9 of 13 classes | **holds** — 13 of 13 dispatched and marked (D-200) |
| 4 — a non-trivial share of eligible defects certified | **FAILS** | **FAILS, and does not block** — 7.1% [2.0%, 22.6%] |
| 5 — one prospective run, no false publication | **FAILS**, never ran | **holds** — 28 units, 13 real executions, 0 published (D-205) |
| 7 — every author-visible line obeys the contract | holds *(wrongly)* | **holds** — it did not; 6 of 11 reviews published bare `DEFER:` prose and **every** review with a note carried a preamble. D-201, D-204 |

### The checklist

| item | verdict |
|---|---|
| readiness conditions, FAILs clearly marked | **PASS** |
| `G-SHADOW-001` | **PASS**, with all-silence / no-recall / one-prospective-unit in the gate's own text |
| new publication rule replay, control-side false publications | **PASS — +0** |
| red team, 13 classes | **PASS — 13 of 13**; the observation gap in `SECURITY.md` |
| yellow control rate and interval in the README | **PASS** |
| `gates` green on `main`, `checks` green on the last PR | **PASS** |
| every reference at `@v0.1.0` | **PASS** — 5 copies; 3 historical `rc.2`/`pilot.1` mentions kept deliberately |
| no key value; no vendor name in this task's commits | **PASS** — 0 of 14; and §6 says plainly that 249 historical commits do carry one |

### What the release is not, in the checklist's own words

Not accurate (7.1%, upper bound 22.6%). Not proven useful (the prospective run published
nothing). Not measured at the shipped K (every control number is K=4). Not externally observed
for 11 of 13 attack classes. Not on the Marketplace and not on PyPI.

### The tag

**`v0.1.0`, annotated, at `289d74f`.** `gates` on that commit: **2,206 passed, 10 skipped,
coverage 93.39%**. Release workflow success; `tag=0.1.0 built=0.1.0`, *"tag and wheel agree"*;
`attest-0.1.0-py3-none-any.whl` and `attest-0.1.0.tar.gz` attached; **`prerelease: false`** and
the *latest release* API returns `v0.1.0`. **Nothing on PyPI, nothing on the Marketplace.**
