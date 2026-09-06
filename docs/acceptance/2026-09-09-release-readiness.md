# Release-readiness acceptance — 2026-09-09

**The question.** Is current `main` at a level an outside user could be given, as a Marketplace
release candidate? This report answers it in five sections, one table each, every row
`PASS` / `FAIL (fixed)` / `FAIL (not fixed)` / `UNFINISHED`.

**Ground rules this run held to.** One remote write — pushing `fix/d-174-binding-and-bounds`
and opening [PR #12](https://github.com/IcantFind-a-username/Attest/pull/12), which the owner
authorised and has since merged as `1bf4110`. Nothing else was pushed, nothing was published,
no protected parameter moved, and **$0.00 was spent**. Anything that needs a real outside trial
or new budget is `UNFINISHED` with its completion condition and cost — never substituted with a
simulation, a historical success, or a local test.

**Every `PASS` below cites something a reader can re-run or open.** No row is passed on
"a previous acceptance said so". Raw data:
[ledger replay](evidence/2026-09-09-ledger-replay.json) ·
[propagation](evidence/2026-09-09-propagation-scan.json) ·
[impact](evidence/2026-09-09-impact-scan.json) ·
[structural](evidence/2026-09-09-structural-offline.json).

---

## 0. The pre-work

| # | item | verdict | evidence |
|---|---|---|---|
| a | push `fix/d-174-binding-and-bounds`, open a PR to `main` | **PASS** | [PR #12](https://github.com/IcantFind-a-username/Attest/pull/12), merged `1bf4110`. It is also the subject of item 2.5 below: the review of that pull request is where yellow (a) first spoke unprompted on real traffic |
| b | downgrade the vocabulary: *e-value* / *alpha* / *family-wise error* → **priority score** / **per-unit family cap** | **PASS** | `README.md` (limitations bullet), `docs/mainline.md` §2 step 8 and §5 decision A, `src/attest/certification/selection.py` (module docstring, `ScoredFinding`, `FamilyPolicy`, `pr_error_bound`, `select_for_publication`), `docs/operations/base-policy.md` (`alpha` row). Each now states: **the only evidence is the differential reproduction (V); S/T rank candidates and spend a multiplicity budget, and D-174 proved they are not an e-value.** No constant moved — `alpha = 0.1`, the likelihood ratios, `K` and the cap are untouched; the identifiers `alpha`, `e_value`, `E_VALUE_VALIDITY` and `PUBLICATION_METHOD` keep their names because they are **recorded ledger keys** and renaming them would rewrite 528 historical `publication_policy` rows |
| b′ | the same vocabulary in author-visible comment copy | **PASS, and it was already true** | `grep -i "e-value\|family-wise\|\balpha\b" src/attest/github/presentation.py src/attest/review/report.py src/attest/review/output_contract.py` → **no match**. `failure-modes.md`'s claim that "the statistical vocabulary never appears" holds |
| c | free ledger replay: three counts for owner decision 2 | **PASS** | `scripts/acceptance/ledger_replay.py` (new), over **104 ledgers / 528 `publication_policy` rows / 82 selections carrying a certified finding**. Table below |
| d | re-weigh yellow (b) propagation on the 79 units at the current code | **PASS — and it is still 0/79** | `scripts/corpus/propagation_scan.py`, `$0.00`. Table below |
| e | README: `G-NEWCODE-001` → **0/445 `through_caller`**, 3 `through_test_caller` listed apart; the test-caller question written as a decision item | **PASS** | `README.md` "measured so far" table, new row; the decision item is in the limitations list with both options' false-positive risk |

### 0c — the three counts (offline, `$0.00`)

```
$ python scripts/acceptance/ledger_replay.py
ledger files                       104
publication_policy rows            528
  ... carrying a certified finding 82
```

| # | question | answer |
|---|---|---|
| **i** | candidates that **reproduced under V and passed intent**, suppressed **only** by the `m_u/α` cap | **35 rows / 35 distinct (task, finding) / 33 distinct findings**, across **17 review tasks**. Every one carries an `accepted` certification and a `reproduced` verification — the replay asserts it rather than assuming it. Distribution: 22 in this repository, 12 in `us-stock-helper`, 1 in a pilot. **None of the 35 was close.** Their priority scores are **2.0, 2.639, 2.9485 and 3.0** against bars of **50 to 120** (20 rows judged per-unit at `m_u ∈ {5,7,8,11,12}`) and **50 to 140** (15 older rows judged PR-wide, pre-D-125). The nearest miss is a factor of **17**, which is D-174's point restated from the other side: S·T tops out at 9, so every one of these publications rests on V and nothing else |
| **ii** | candidates **published with no V** | **0**, of 77 published rows. This is the check of `INV-CERT-001` against the raw rows, not a restatement of it |
| **iii** | if the rule became **V ∧ intent ∧ per-unit top N (N = 3)** | **17 of 82 selections change.** With the global hard cap kept: **+25 published, −0**. With it dropped: **+26, −0**. Published total 77 → 102 (capped) or 103. All 25 additions were previously suppressed `below family threshold`; **10 of the 35 stay suppressed** — the 14-candidate file keeps only its top 3, and the global cap takes the rest |

**What this is for and what it is not.** It is the arithmetic behind owner decision 3. It is
**not implemented**, and nothing in it says the new rule would be *right* — every one of the 25
would be a new author-visible claim, and this replay says only how many, not whether any is
true. The direction is one-way: the current rule publishes a strict subset.

**The one thing the owner should read before deciding.** Because no suppressed finding's score
is within a factor of 17 of its bar, `V ∧ intent ∧ per-unit top 3` is **not a slightly lower
bar** — it removes the score threshold and replaces it with a rank. That is a coherent thing to
want (the score was never an e-value, so a bar drawn on it was never an error rate) and it is
also the whole of the change: after it, the only thing standing between a certified receipt and
an author is the differential reproduction itself and a cap on how many are shown.

### 0d — propagation, re-weighed at the current code

| | 2026-09-07 (`unhandled-exception.v1`) | **2026-09-09 (`v2`, D-174 binding)** |
|---|---|---|
| forward pairs | 0 of 11 | **0 of 11** |
| null controls | 0 of 68 | **0 of 68** |
| changed functions considered | 198 | 198 |
| the change added no call | 135 | **134** |
| the callee does not resolve to one definition | 43 (*"the name is not unique"*) | **45** |
| the callee names no exception | 15 | **14** |
| the changed function catches everything | 5 | 5 |

**The lever the last report proposed has now been pulled, and it made the class quieter, not
louder.** 2026-09-07 named "resolving callee names by import rather than by bare name" as the
one change that would plainly raise recall, on the grounds that it would convert most of the 43
ambiguity abstentions into decidable cases. Binding landed in D-174 and the ambiguity count went
**up, 43 → 45**: two functions that used to look decidable are now known not to be. `0/79` is
unchanged and the replacement of `0 of 79` with a different number **did not happen** — the
honest replacement is this table.

---

## 1. Can it be installed?

Everything in this section was done on **`tenacity`** (`https://github.com/jd/tenacity`, cloned
to `.attest/corpora/tenacity` at `26f719d`), a public pytest project unrelated to this one and
owned by nobody here. 20 Python files, `pyproject.toml`, `requires-python >= 3.10`, classifiers
through 3.14.

| # | item | verdict | evidence |
|---|---|---|---|
| 1.1 | a wheel of the install ref installs in a clean venv and reviews an outside repository | **FAIL (fixed) — two defects, D-175 and D-176** | below |
| 1.2 | the support range is one table and it matches the implementation | **PASS (fixed)** | `docs/operations/support-matrix.md`, rewritten in two tables |
| 1.3 | fork pull requests are not reviewed and leave nothing behind | **PASS** | below |
| 1.4 | the README example and `install-ref.md` name the same ref | **FAIL (fixed)** | README pinned `@v0.1.0-pilot.1` and `docs/github-action.md` used `@main`; both now `@v0.1.0-rc.1`, with `install-ref.md` named as the source |

### 1.1 — what actually happened

The install itself was clean, and it is the part that passed first:

```bash
git archive v0.1.0-rc.1 | tar -x -C <scratch>     # the tag's tree, not the working tree
python -m build --outdir dist                     # attest-0.1.0rc1-py3-none-any.whl
python3.12 -m venv <clean>                        # a venv with nothing in it
<clean>/bin/pip install -r requirements-toolchain.lock
<clean>/bin/pip install --no-deps --no-build-isolation <dist>/attest-0.1.0rc1-py3-none-any.whl
<clean>/bin/pip check                             # No broken requirements found.
<clean>/bin/python -c "import attest; print(attest.__version__)"   # 0.1.0rc1
```

Then, in the `tenacity` clone at `26f719d` with the parent as base, under a **scrubbed
environment** (`env -i` keeping only `HOME` and a minimal `PATH`) so nothing of this development
machine could be reached:

```
[silent] unsupported: pytest could not be provided in the reproduction image, and every
claim Attest makes is a pytest run on two revisions; nothing was verified.
```

**Two defects, and the second one is the one that matters.**

- **D-176 — the whole image build died.** `tenacity` versions itself with `hatch-vcs`; the tree
  is copied into the build context **without `.git`**, so `pip install /attest/build` failed
  with `LookupError: Error getting the version from source 'vcs'`. The mechanism to fix this
  already existed (`ENV SETUPTOOLS_SCM_PRETEND_VERSION`, from a committed `_version.py`) — the
  detector looked only for `setuptools_scm`/`setuptools-scm` and not for `hatch-vcs`, which is
  the same library reached through `hatchling`. **One tuple.** Verified independently by hand:
  the identical Dockerfile with the env var added builds and imports both `tenacity` and
  `pytest`.
- **D-175 — the refusal named the wrong cause.** BuildKit echoes the whole Dockerfile around a
  failure, so the log tail of a failure at line 5 (`pip install /attest/build`) contained the
  *successful* line 3 (`RUN pip install pytest`), and a substring search for the word `pytest`
  sent the operator to fix a dependency that had installed fine. The refusal is now decided by
  the **failing step the builder itself names**, and a project that will not install gets the
  documented `environment bootstrap failed …` row instead.

**After both fixes, from a wheel built off the working tree into a second clean venv, same
scrubbed environment:**

```
[green] Structural (no defect claimed): tenacity/__init__.py:381-395 `wrapped_f` and
tenacity/asyncio/__init__.py:223-237 `async_wrapped` normalise to token sequences of 45 and
47 tokens whose token-sequence similarity is 0.957 (threshold 0.92), not semantic
equivalence; identifiers and literal values erased, attribute and callee names kept.
silent candidates, with the reason the drawer holds each:
  [8858cdcf9f] tenacity/__init__.py:541 ($0.0095) — generation-failed: ...
read 1/1 units, candidates 1, drawer 1 (generation-failed 1); verified 0, discarded 0;
spend $0.0370 of $1.00; 4.4s.
```

The clone's own ledger records `image_cache` (built in 3.0 s), `executor_backend`
`linux-container-v1 available: true`, and an interpreter of **3.13** — chosen by D-162 from
`tenacity`'s own classifiers (ceiling 3.14, clipped to the supported 3.13). **The whole pipeline
ran from a packaged install on an unrelated repository, with no development machine, no hidden
file and no hand-patched environment**, and it produced a real green note on real code.

**Two limits on this row, stated rather than buried.** The run is the **local equivalent** of
`scripts/action-entrypoint.sh` — `attest review --mock <payload>`, labelled — because
`attest ci` posts to the GitHub API, and this project does not write to a repository it does not
own. And the single red candidate died at `ProbeRefused: probe output does not match the probe
schema`, which is the mock payload not being a valid probe answer, not a product defect; a real
red path on `tenacity` needs a paid run and is `UNFINISHED` (§3.7).

### 1.3 — forks

- **`pull_request_target` appears nowhere** in `.github/`, `action.yml`, `scripts/` or the docs:
  `grep -rn "pull_request_target" .github/ docs/ README.md action.yml scripts/` → no match.
- Two independent gates. The workflow's
  `if: github.event.pull_request.head.repo.full_name == github.repository` stops the job before
  any step holds the secret; `scripts/action-gate.sh` classifies the event **before any
  credential is introduced** and writes `trusted=false`; `scripts/action-entrypoint.sh` refuses
  the same event again. Constructed and run:

  ```
  $ GITHUB_EVENT_PATH=<fork-event.json> sh scripts/action-gate.sh
  ::notice title=attest::Fork pull request skipped before credentials or head-code execution
  [exit 0]   trusted=false
  $ GITHUB_EVENT_PATH=<fork-event.json> sh scripts/action-entrypoint.sh
  attest: fork pull request skipped before credentials or head-code execution
  [exit 0]
  ```

- **Nothing is left behind that could read as "reviewed, no problems":** no comment, no review,
  no check annotation, no ledger, no artifact — only the Actions notice above. Written into
  `README.md`, `docs/github-action.md` (new *"Fork pull requests are not reviewed"* section) and
  the support matrix. Pinned by
  `tests/test_action_entrypoint.py::test_cross_repository_event_skips_before_the_attest_executable_runs`,
  `::test_credential_free_gate_marks_cross_repository_event_untrusted` and
  `::test_this_repository_workflow_runs_only_for_same_repository_branches`.

---

## 2. Is it actually useful?

**Method.** Fixed samples, no new paid review. The three levels whose adjudicator is `ast`
alone were **re-run offline at the current code** and are today's numbers. Red cannot be
re-run free — it needs execution and a generation call — so its rows are the recorded runs,
each carried with the code version it ran under. That distinction is in the table and is not
smoothed over.

| # | item | verdict | evidence |
|---|---|---|---|
| 2.4 | per-level table on the fixed sample, with the D-158 corpus in its own column | **PASS for the free levels · UNFINISHED for red at K=5** | below, and §3.7 |
| 2.5 | the comment contract gains an **action** clause, adjudicated by D-142 | **FAIL (fixed) — D-178** | below |

### 2.4 — what each level says, on the fixed sample

Denominator is the whole sample in every cell, and the value class is a **column**, never a
subtraction: the held-out slice is **29 cases = 16 crash/exception + 12 value class + 1 that
cannot be run at all** (`pytest-8399`, D-154), and all three appear. `—` means the level has no
run on that population, which is itself a gap and is not hidden by omitting the column.

| level | 11 forward pairs | 16 held-out crash cases | 58 controls | 68 controls | value class (D-158) — **separate, never in a denominator** |
|---|---|---|---|---|---|
| **red** | **3 published, 3 true** (two are the exact defect the later repairing commit fixed; the third a different real regression in the same commit) · 8 abstentions · **0 false** | **4 certified of 16 (25%)** · 12 abstentions · **0 false** | **0 wrong publications**, 95% upper bound **5.2%** | **0 wrong publications**, plus **1 true positive on a control** (`more-itertools f4f2cfec9d`, probe-adjudicated on four interpreters). 57 of 68 produced no candidate at all, so the rule-of-three bound is 42.9% and is not quoted as a bound | forward: **0 certified of 1 candidate.** Held-out: **0 of 12**, and **4 of those 12 the old generator had published**. Both are the clause's cost, not a recall rate |
| **gate** | 0 (shadow) | — | — | — | — |
| **yellow (a)** | **0 of 11** | — | — | **1 of 68 (1.5%)** | — |
| **yellow (b) null** | 0 of 11 | — | — | 0 of 68 | — |
| **yellow (b) propagation** | **0 of 11** | — | — | **0 of 68** | — |
| **green** | — | — | **13 of 58 (22.4%)** | — | — |

Provenance of every cell, because the populations were bought at different times under
different code:

| cell | when | code | free? |
|---|---|---|---|
| red, forward pairs | 2026-09-06b, K=4, `--budget 1.00`, probe generator | `attest.intent.v4.1` | no — $4.06 recorded |
| red, held-out 16 | 2026-09-06c, K=4, `--budget 1.00`, probe generator | `attest.intent.v4.1` | no — $3.01 recorded |
| red, 58 controls | 2026-09-05, K=4 | `attest.intent.v4.1` | no |
| red, 68 controls | 2026-09-05d + 2026-09-06, K=4 | `attest.intent.v4.1` | no |
| **yellow (a), both** | **2026-09-09, today** | **`attest.impact.caller-scope.v2`** | **yes, `$0.00`** |
| **yellow (b) propagation, both** | **2026-09-09, today** | **`attest.propagation.unhandled-exception.v2`** | **yes, `$0.00`** |
| **green, 58 controls + 100 traffic units** | **2026-09-09, today** | **`attest.structural.duplicate-implementation.v2`** | **yes, `$0.00`** |
| gate | 2026-09-08 recount over 445 recorded candidates | binding | yes, `$0.00` |

**Against the previous version — and which class of error moved.** Only one number improved,
and it is attributable to exactly one class:

| level | before | now | which error fell |
|---|---|---|---|
| yellow (a), controls | **2 of 68 (2.9%)**, reasons `3 call sites in 3 files` and `9 call sites in 2 files` | **1 of 68 (1.5%)**, reason `9 call sites in 2 files` (`jinja src/jinja2/filters.py:58 make_attrgetter`) | the note that disappeared is the `3 call sites in 3 files` one, and it disappeared because those call sites **do not resolve** to the changed definition. **Name-collision callers**, not "the level said less" |
| yellow (a), forward | 1 of 11 | **0 of 11** | the same class, on the recall side: the one forward note was also a name-collision caller. Neither note was a defect claim — yellow (a) claims none — so what changed is that two wrong *counts* stopped being published |
| yellow (b) propagation | 0 of 79 | 0 of 79 | nothing moved; the refusal mix did (0d) |
| gate | 26 of 445 `through_caller` | **0 of 445** | every one of the 26 was a name collision. This is a correction, not an improvement: the old number was never reachability |
| green | 8 of 40 commits (2026-09-06c) | 13 of 58 controls / 8 of 100 traffic units today | not comparable — different populations, and green claims no defect either way |

**What this table does not say.** Not one of these numbers is a precision figure. Red's forward
`3 of 11` is a recall figure on a corpus built by looking for defects; the controls' zeros are
abstentions, never true negatives; green's 22.4% on null controls is a *trigger* rate for a
level that claims no defect. The one thing the fixed sample supports is the comparison in the
table above, and each row of it names the error class rather than the total.

### 2.5 — the action clause

The three comments in `docs/examples/` plus the first unprompted yellow (a) comment on real
traffic were checked element by element:

| comment | position | fact | evidence | action |
|---|---|---|---|---|
| `[red]` `scripts/corpus/four_levels.py:212` | ✅ | ✅ | ✅ receipt `e89b0fe548b6` + bundle | ⚠️ present as prose, **unlabelled and unadjudicated** |
| `[yellow]` `scripts/corpus/four_levels.py:212` | ✅ | ✅ | ✅ second coordinate `:202` | ❌ **absent** |
| `[green]` `scripts/corpus/impact_scan.py:62-68` | ✅ | ✅ | ✅ second coordinate | ❌ **absent** — the model's advice is collapsed and explicitly not part of the claim, so nothing said what to do |
| `[yellow]` `src/attest/review/gate_level.py:252`, **PR #12** | ✅ | ✅ | ✅ `scripts/corpus/binding_recount.py:102` + all sites | ❌ **absent** |

**D-178.** `output_contract.check_comment` now refuses a comment that does not carry exactly one
`Action:` line naming something to run, open or change. Each level assembles its clause from
coordinates it already holds — never from a model. **A certified finding is never gated on it**:
`inline_comments` appends red's clause and does not adjudicate, so no wording can suppress a
receipt. Green and yellow *are* gated, and the narrower true statement for them is that the only
text the adjudicator reads is text the product wrote — which took two fixes to make true (see
*The independent review* below). `gate`'s clause (the reachable path and the triggering input) is
defined and ships when the level leaves shadow. RED: `tests/test_action_clause.py` (14).

**The fourth sample, in full.** On PR #12 attest said, of its own change:

> `[yellow] src/attest/review/gate_level.py:252 — calls_in changed; 3 call site(s) in 2 file(s)
> name it and no test names it — scripts/corpus/binding_recount.py:102`

- **Position, fact and evidence check out.** Re-resolving the three sites through
  `attest.review.binding` at the current tree returns exactly
  `scripts/corpus/binding_recount.py:102`, `src/attest/review/gate_level.py:372` and `:432`, and
  no test names `calls_in`.
- **Correcting one thing about its provenance.** This repository's workflow uses `uses: ./` —
  the action as it stands *in the pull request* — so the comment was produced by
  `attest.impact.caller-scope.v2`, the **binding** rule, not by the older name-matching one. The
  three call sites were binding-resolved when it spoke, and they still are.
- **It is true and it is not a defect.** `scripts/corpus/binding_recount.py` is new in that same
  commit and is written against the new `WrittenCall` signature (`call.line`, `call.caller`); it
  was executed as part of this acceptance and completes: `224 candidates: name-matched 23 → bound
  0; through_caller: 29 recorded → 3 kept`. Recorded in the handoff as **found by attest's own
  review of itself**.
- **The one thing it got wrong was its own wording.** The comment ended *"Static reachability
  over names: a caller reached only through a registry or `getattr` is invisible here"* — a
  description of the rule D-174 replaced. It now states the resolution and keeps the honesty
  clause verbatim: *"Resolved statically: a call reached only through inheritance, a decorator, a
  package re-export, a variable or `getattr` does not resolve and is not listed, so this says
  **named by no test**, never **not covered**."*

---

## 3. Is the default configuration usable?

| # | item | verdict | evidence |
|---|---|---|---|
| 3.6 | the whole factory configuration, what each key does, and the ledger field that shows it | **PASS (fixed)** | `docs/operations/base-policy.md`, rewritten: 13 policy keys in a five-column table plus 12 shipped constants that are not keys |
| 3.7 | which measurements are K=4 and which are the K=5 factory setting | **FAIL (not fixed) — every empirical number in this repository is K=4** | below |
| 3.8 | the default budget's real boundary | **PASS, and it moves an owner item** | below |

### 3.7 — the K provenance, and why it is a `FAIL`

`ReviewConfig.k_samples = 5` is the shipped default, and `action.yml`'s `samples` input
defaults to `"5"`, so **5 is what an outside repository gets**. **Every empirical number this
project quotes was taken at K=4** — the forward pairs, the held-out slice, both control
populations, the four-level table, the shadow runs, the budget re-run. Even this repository's
own `pull-request.yml` overrides the default with `samples: "4"`, so **K=5 has never run
anywhere in this project's recorded history.**

The factory configuration has therefore **never been measured on the fixed sample**, and the
gap is not cosmetic: D-168 already records that at K=5 one of 28 recorded reviews
(`click cd4674a6`) is refused its first change unit on discovery alone — and that review is one
of the three that ever published a receipt.

**`UNFINISHED`. Completion condition:** the fixed sample re-reviewed at K=5, `--budget 1.00`,
`--code` pinned, on the same clones. **Cost at the maximum unit price** (the `--budget` cap of
$1.00 per review, which is the reservation basis this project uses):

| scope | n | at the $1.00 cap | at the measured means |
|---|---|---|---|
| the whole fixed sample (11 forward + 16 held-out + 58 + 68 controls) | **153** | **$153.00** | ≈ $6.31 |
| **the minimum sample that can move a verdict** — only the 27 reviews where a verdict exists; the 126 controls' verdicts are silences and K moves discovery, not adjudication | **27** | **$27.00** | ≈ $3.41 |

`DEVSPEND.md` records **$80.33 of the $110 cap**, so **$29.67 remains**. The 153-review form
**cannot be reserved** without a cap raise (AGENTS §9 forbids starting a study that cannot reach
its preregistered n inside the remaining cap). The 27-review form fits, barely. **Owner item 1.**

### 3.8 — the default budget's boundary

At the factory setting (`budget_usd = 1.00`, `k_samples = 5`, `PROPOSAL_SHARE = 0.3`,
`PROPOSER_MAX_OUTPUT_TOKENS = 3200`, proposals on `claude-sonnet-5` at $2/$10 per Mtok):

```
discovery ceiling            0.3 × $1.00                     = $0.3000
output floor for 5 samples   5 × 3200 × $10/Mtok             = $0.1600
headroom left for input      $0.3000 − $0.1600               = $0.1400
largest first unit that fits $0.1400 ÷ (5 × $2/Mtok ÷ 3 chars/token) = 42,000 characters
```

**Two consequences, both measured on `tenacity` rather than derived:**

| budget | K | what happens |
|---|---|---|
| `$0.25` | 5 | `DEFER: budget: call 'sample-1' … projected total $0.0849 exceeds the discovery share $0.0750 of budget $0.25`. **One of five samples bought.** Red produces nothing |
| `$0.50` | 5 | `DEFER: budget: call 'sample-3' … exceeds the discovery share $0.1500`. Three of five |
| `$1.00` | 5 | all five samples, one candidate, `$0.0749` spent |

The output floor alone is $0.16, so **no budget below $0.534 can buy five samples at any diff
size**. `$0.25` — the pre-D-126 default, and the value still used by this repository's own
four-level measurement — is unusable at the factory K.

- **The first-unit residual is closed, and reversed.** D-111 exempted the first change unit from
  the share so a review could always read something; D-168 removed the exemption. The residual
  is now the other way round: a first unit above ~42,000 prompt characters defers the whole
  review. The planner packs units to `MAX_UNIT_CHARS = 30,000`, but a **single file's block
  larger than that becomes its own unit** and may exceed it — which is exactly
  `click cd4674a6`'s 47,448 characters.
- **`read N of M units` appears** when the proposal stage stops before every planned unit is
  read; the count comes from the `proposal_coverage` row (`units_read`, `units_planned`,
  `budget_limited`) and the silence line carries it. The M − N unread units were **not**
  reviewed.
- **What the verification cap truncated.** `verification_cap_per_unit = 3`: over the 28 recorded
  reviews of D-168's replay it cut reproductions **168 → 79** and spend **$10.27 → $5.24** while
  keeping **all 3** receipts, and **0** candidates that had been verified were lost. It cannot
  make anything publish that would not have: the family denominator `m_u` is unchanged.
- **Offline prediction and real cost are two columns and are never mixed.** Everything in this
  section except the three `tenacity` rows is arithmetic over the shipped constants; the three
  `tenacity` rows are real runs, and they cost `$0.0022`, `$0.0022` and `$0.0749` under `--mock`
  — that is *mocked* spend accounting, not provider spend, and no provider was called.

**Should the default budget change?** The arithmetic says the shipped `$1.00` is the *minimum*
at which K=5 completes discovery, not a comfortable one — `$1.06` is D-168's own figure for
clearing `click cd4674a6`. Changing it is a factory default and an owner decision under §16.
**Not changed. Owner item 3** (see the end).

---

## 4. Safety and the failure experience

| # | item | verdict | evidence |
|---|---|---|---|
| 4.9 | five failures constructed; each has its own copy and a next step; none says *nothing met an adjudicator's bar* | **FAIL (fixed) — D-177, D-179** | below |
| 4.10 | `G-SEC-002`'s nine classes still hold for current `main` | **PASS** (main) · **UNFINISHED** (this branch, and the external observer) | below |
| 4.11 | the privacy document enumerates every model call from the code | **FAIL (fixed)** | `docs/operations/privacy-and-retention.md`, rewritten as a per-call table |

### 4.9 — the five failures, as they actually print

| # | failure | how it was constructed | what came out | verdict |
|---|---|---|---|---|
| 1 | **the model API is unreachable** (network) | injected provider raising `APIConnectionError` | *was* `DEFER: all provider samples failed or were malformed`. **Now** `DEFER: the model API could not be reached from this runner (network or DNS); nothing was spent and nothing was reviewed -- check the runner's egress, then re-run this job` | **FAIL (fixed)**, D-179 |
| 2 | **the model key is missing** | `INPUT_MODEL_API_KEY=` through `scripts/action-entrypoint.sh` | exit 2 with a message naming the secret, the repository's own `settings/secrets/actions/new` URL, `Name: ANTHROPIC_API_KEY`, and *"Nothing was sent anywhere. No model was called, no code left this runner, and no key was read, stored or logged."* | **PASS** |
| 3 | **no Docker** | `select_backend(production=True)` with an empty `PATH` | `isolation backend unavailable: docker not found` → `[silent] unsupported: docker is not available here, and Attest runs head code only inside a container; nothing was verified.` | **PASS** |
| 4 | **`budget-usd` is `0.00`** | `attest review --budget 0.00` | *was* `error: budget must be a finite positive number`. **Now** `error: budget must be a finite positive number of US dollars: set the Action's` `budget-usd` `(or` `--budget` `locally) above 0, for example 1.00`, exit 2 | **FAIL (fixed)**, D-179 |
| 5 | **every call answers 429** | injected provider raising a rate-limit error | *was* `DEFER: all provider samples failed or were malformed`. **Now** `DEFER: the model API refused every proposal for rate or capacity (HTTP 429/529); nothing was spent and nothing was reviewed -- re-run this job, or lower` `samples` `if it happens on every run` | **FAIL (fixed)**, D-179 |
| + | **fork pull request** (bonus) | a cross-repository event | `attest: fork pull request skipped before credentials or head-code execution`, exit 0, nothing published | **PASS** |

**The named defect at `output_contract.py:297` — confirmed, fixed, and one thing about it
corrected.** When the host cannot run the executor, every candidate is classified
`unsupported_executor` *before* generation, nothing is verified, and the review printed
`nothing met an adjudicator's bar` — a clean bill of health for code nothing looked at. It now
prints:

```
[silent] read 3 of 3 units; executor unavailable: process containment unavailable for
privileged POSIX user; 4 candidate(s) not verified; $0.0184, 2.5s.
```

The correction: **there is no `M-01` ledger in this tree, and no recorded ledger anywhere carries
an `unsupported_executor` row** — 2,452 eligibility rows across 104 ledgers are
`regression`/`new_code`/`non_python` only. The defect is reproduced from the eligibility rows
such a host writes, not from history, and that is said rather than dressed up as a replay.

**A second defect found in the same line.** D-161 gave the silence line a budget-ceiling verdict
without widening `_SILENCE_SHAPE`, so `output_contract.check` **refused a line the product
emits** — latent only because no caller adjudicates the silent line. All three verdicts are now
admitted, and a test asserts each passes the contract that judges it.

### 4.10 — security

- **The nine-class matrix still holds for `main`.**
  `git log f09a213..main -- src/attest/execution src/attest/review/executor.py scripts/release/redteam.py`
  is **empty**: not one byte of the isolation path, the executor or the matrix itself has changed
  since the run at `f09a213` that produced
  [2026-09-07-redteam-nine.md](2026-09-07-redteam-nine.md) — 9 fixtures dispatched, 9 marked,
  positive control certified in the same run. **No re-run is needed for `main`, and none was
  dispatched.**
- **`UNFINISHED` for this branch.** D-176 touches `src/attest/execution/container_images.py`. It
  adds one `ENV` line to a generated Dockerfile and changes **no** field of the container run
  profile — no mount, uid, capability, network setting or limit — but it is inside
  `attest.execution`, so the matrix must be dispatched on the branch before release, and
  AGENTS §11.7 requires an independent review of that diff. **Completion condition:** one
  `workflow_dispatch` of `red-team.yml` on the branch, `$0.00`, plus one independent review.
- **The external observer stays `INSUFFICIENT`.** One run has a kernel audit record beside the
  container (945 syscalls at the container's uid; 0 `socket`, 0 `connect`, 0 `clone` —
  [report](2026-09-08-external-observer.md)). The **matrix has not been run under it**, so the
  nine rows remain observed from inside the product. `UNFINISHED`, and no number of internal
  passes closes it.
- **The four boundaries each have a test pointing at them**, listed in the new `SECURITY.md`:
  fork path (3 tests), privileged-user refusal (2), credentials only in the controller (3), log
  and ledger redaction (2).

---

## 5. Maintainable, and reversible

| # | item | verdict | evidence |
|---|---|---|---|
| 5.12 | `SECURITY.md` | **PASS (new)** | reporting channel, supported versions, disclosure, scope, out of scope, and a *"what is not claimed"* section |
| 5.13 | install-ref / quickstart / support matrix / CHANGELOG / kill switch / rollback all agree with the implementation | **FAIL (fixed) — four inconsistencies** | below |
| 5.14 | the unpassed gates, each with its completion condition | **PASS** | below |

### 5.13 — the four inconsistencies, all fixed in the documents

| where | it said | the implementation | fixed |
|---|---|---|---|
| `README.md:160` | `uses: …@v0.1.0-pilot.1` | `install-ref.md` names `v0.1.0-rc.1` | pinned to `@v0.1.0-rc.1`, with the source file named in a comment |
| `docs/github-action.md:18` | `uses: …@main` | an outside repository must pin an immutable ref | same |
| `docs/github-action.md` | *"a temporary `uv` virtual environment"* | `action.yml` uses `python -m venv` and `pip`, pinned by `requirements-toolchain.lock`. **`uv` is not used anywhere** | corrected, with the erratum visible |
| `docs/operations/failure-modes.md` | the missing-credential row quoted `trusted pull requests require both action credentials` | that sentence exists only in 2026-09-03 reports; the product now prints a multi-line message naming the secret and the URL | replaced with the real text, erratum visible |

`kill-switch-and-rollback.md`, `quickstart.md` and the `CHANGELOG` were checked against the
implementation and agree. Where a document was wrong the **document** was changed, never the
implementation.

### 5.14 — the gates that do not pass

No bar was lowered, no `beta` label was used to route around one, and the `rc` tag says
*internal trial* and nothing more.

| gate | state | completion condition | cost |
|---|---|---|---|
| **`G-SEC-002`, external observer** | `INSUFFICIENT` | run the nine-class matrix **under** the kernel audit observer on a GitHub runner and publish the joint record — the harness's claim and the kernel's, side by side, for all nine fixtures | **$0.00**, one `workflow_dispatch` |
| **`G-SEC-002`, on this branch** | not re-run | one `workflow_dispatch` of `red-team.yml` on `docs/release-readiness-acceptance` after D-176, plus the independent review AGENTS §11.7 requires for an `attest.execution` change | **$0.00** |
| **`G-NULL-001`** | fails | 95% upper bound ≤ 1% needs **n ≥ 300 answered** controls. The independent population answered **7 of 68 reviewed**, so ~2,900 more controls at $0.0184 each | ≈ **$53**, above the $29.67 remaining. Needs a cap raise **and** a public corpus that yields answers rather than silences |
| **`G-NEWCODE-001`** | fails | a **120-case blind pilot** of the gate level. Progress is **0 of 445** — no publishing-grade witness has ever been produced, so the pilot has nothing to adjudicate until either the reachability rule changes or the test-caller question is decided (owner item 2) | unknown until the rule is settled |
| **`G-SHADOW-001`** | fails | one **prospective** shadow run on live repositories with an **independent adjudicator**. Every shadow run so far reviews commits that existed before the protocol, which is retrospective by construction | ≈ $0.02–0.19 a commit; the binding constraint is time and an adjudicator who is not the implementer |
| **an outside real trial** | **never done** | at least one repository **this project does not own** installs the Action at the install ref and runs it on a real pull request. The one production comment to date was on `us-stock-helper`, which the owner owns | the owner names the repository; ≈ $1 a pull request. **Owner item 2 of the L-01 exit list; this cannot be substituted by anything in this report** |
| **mainline conditions 3, 4, 5** | fail | as at [2026-09-07](2026-09-07-v01-tag-readiness.md); nothing in this window moved them | — |

---

---

## The independent review

AGENTS §11.7 requires an independent review for `attest.certification` and `attest.execution`
changes; this window touched both. A reviewer that did not write the code read the two diffs,
the five decisions and the surrounding modules, and reproduced every finding locally.

| # | severity | finding | resolution |
|---|---|---|---|
| 1 | **P0** | `_VERSION_FILE_RE`'s capture class `[^'"]+` matches newlines, and the capture is interpolated into a Dockerfile that `docker build` runs **with network access**. A `_version.py` in the tree under review can append its own `RUN` step: arbitrary code execution with egress, from untrusted project content. **Pre-existing** — `setuptools-scm` already reached it — but inside the function D-176 touches | **fixed**: `_SAFE_VERSION_RE` gates the capture; an unmatched value falls back to `0.0.1` |
| 2 | **P1** | Stripping `<details>…</details>` before scanning for the action clause is not enough: a model paragraph containing a literal `</details>` closes the block early, so its text is both scanned (two clauses → the note is dropped for a word the model chose) **and rendered as product copy** outside the container that marks it as not part of the claim | **fixed**: `collapsed` neutralises `<details>`/`<summary>` in the body it wraps. The first attempt at that broke the evidence renderer's own nested *Full logs* block — caught by `tests/test_ci_flow.py` on the full gate run — so there is one explicit `trusted=True` opt-out, and the default stays *neutralise* |
| 3 | **P1** | `provider_defer_reason` classified over **every** sample error, including `all findings malformed; raw=<model text>`. A review of retry code could be told the API rate-limited it — and that path *settles* its reservation, so `nothing was spent` would have been **false** | **fixed**: `ProposalRun.transport_errors` carries only call-raised failures, and both sentences are reachable only when every failure is one |
| 4 | P2 | `ci._executor_unavailable` swallows a ledger read error and returns `("", 0)`, reinstating `nothing met an adjudicator's bar`; the docstring called that "no claim, never a wrong one" | **fixed** in the docstring, which now names it. The fallback stands: the same unreadable ledger yields `read 0 of 0 units` |
| 5 | P2 | the blocked count counted **rows** where its neighbours count distinct findings | **fixed**: a set of finding ids |
| 6 | P2 | `_bounded` allows 1,400 characters for text containing *isolation backend unavailable*, against the contract's 400-character line | **fixed**: `EXECUTOR_REASON_LIMIT` bounds it independently |
| 7 | P2 | a `check_comment` refusal is discarded — no reason, no ledger row, no trace | **backlog** |

**What the review confirmed rather than found.** `selection.py` is behaviourally identical: the
reviewer parsed both revisions, deleted every docstring, and compared `ast.dump` — identical, so
the vocabulary downgrade moved no constant, no threshold and no field. D-176's security claim
holds: no field of the container run profile derives from the version, the runtime entrypoint is
`env -i` so the image's `ENV` never reaches the job, and the image tag hashes the whole
Dockerfile, so the extra line makes the cache key **more** discriminating, not less. Red is
genuinely never gated on the action clause. No new path logs, transmits or persists a credential;
no new network call and no new spend.

**Verdict: APPROVE WITH FIXES.** Findings 1, 2 and 3 were named release-blocking and are fixed
here; 4, 5 and 6 are fixed in the same pass; 7 is in the backlog.

## Gates for this report's own changes

Command, code and result are in the handoff. Nothing here weakens a regression pin, skips a
security test, lowers a coverage threshold or changes a denominator.

## Spend

**$0.00.** Every measurement in this report is `ast`, `git`, a ledger already on disk, a mocked
provider, or a container build. No provider was constructed with a real key at any point.
`DEVSPEND.md` is unchanged: **$80.33 of $110**.
