# Handoff — 2026-09-03, fourth window (`6364010` → PENDING): three owner decisions, the runner, and the wall

Status: **the three owner decisions are done. Privacy/retention is approved (D-107). The
Action has run on a GitHub-hosted runner for the first time and posted one comment (D-108).
The receipt-bearing pilot produced no receipt and stopped one commit short on budget
(D-109).** `9df938f` was independently reviewed and three of its findings fixed; the carried
`pytest-10051` rerun completed without building anything; `scripts/release/drill.py` exists
in its minimal form.

## 0. Owner decisions, as executed

| # | decision | done? | where |
|---|---|---|---|
| 1 | approve `privacy-and-retention.md`, drop the draft heading, add the provider-retention sentence | **yes** | `b58ffb7`, D-107 |
| 2 | receipt-bearing pilot, three later-repaired `us-stock-helper` commits, $0.30, reserve first | **partly — two of three; no receipt** | `6dfcf4b`, D-109, [report](acceptance/2026-09-03-l01-receipt-pilot.md) |
| 3 | `pull_request` workflow on Attest, same-repo only, throwaway branch, one comment, then close and delete | **yes** | `67703a6`, D-108, [report](acceptance/2026-09-03-first-runner-review.md) |

## 1. The independent review of `9df938f` (D-105), and what it changed

The review found **no blockers and four reproduced defects**, and refused to count the
commit as reviewed until two were fixed. Fixed in `34affaf`, each with a RED:

| # | finding | fix |
|---|---|---|
| 1 | `shutil.copytree` two lines above the fixed call raises `shutil.Error` (an `OSError`) for a dangling symlink anywhere in the reviewed tree, and plain `OSError` for a full `/tmp` — the same traceback out of `select_backend` the commit's subject says is not allowed | assembling the build context now fails like the rest of the bootstrap |
| 2 | `image_digest` — the only other subprocess on the `select_backend` path — had **no timeout at all**, so a daemon that will not answer hangs the review forever with no DEFER, no status line and no traceback | bounded at 60 s; a probe that cannot answer returns `""`, which is what both call sites already mean by "unknown" |
| 4 | the timeout branch discarded the build-log tail that `TimeoutExpired` does carry — the one signal naming which step was still running — and those attributes are **bytes** even under `text=True` | one message builder for every branch, tail decoded, not spliced in as a `b'…'` repr |
| 5, 6 | the test patched the global stdlib `subprocess.run`; nothing pinned the status category of a reason containing both `bootstrap failed` and `timed out` | narrowed to the build call; one categorisation test added |

Finding 3 is real, reproduced, and **not fixed**: `IMAGE_BUILD_TIMEOUT_S = 1800` is three
times the 600 s verification deadline it runs under, and `select_backend` is called before
the first deadline check — so a build of 601–1800 s "succeeds" and then every candidate
DEFERs with `shared verification deadline exceeded`, wrong category and 10–30 minutes of
runner time for nothing. Lowering it is a backend-policy change and the instruction for this
window was not to touch the cap. Owner question 2. Findings 7, 8, 10, 11 are in
`docs/backlog.md`, one line each, per D-049.

## 2. `pytest-dev__pytest-10051`: no build was needed at all

$0.019502. 1 candidate, **1 eligible**, 1 containerised reproduction, 0 certified —
DEFER `unfaithful generated test: fails on base as well`. The D-104 shadow false positive is
gone; the candidate now clears binding and fails at faithfulness instead.

**The `docker build` that timed out last window was never necessary.** The image for this
exact tree, `attest-repro:523d6f3b150c6681`, had already been built during the `5fc03fa` run
and was still on the host. It was not reused because `docker image inspect <name:tag>` was
answering *No such image* for tags the same daemon listed in `docker images` and resolved by
image id — observed directly again this window, on several tags, and it cleared on its own.
`image_digest` reads that as "absent" and rebuilds. **The 1800 s cap was not raised.**

Later in the window the host's docker daemon stopped completing **any** build: a one-line
`FROM python:3.9-slim` context hung past three minutes while `image inspect`, `info` and
`docker run` all answered normally. A full Docker Desktop restart did not fix it. The cause
is registry egress from the VM — `python:3.9-slim` is not local and `docker pull` hangs,
while the *host* reaches `registry-1.docker.io` in 0.7 s. `--quiet` hides the pull entirely,
which is why this looks like "the build is slow". **Docker Desktop was restarted once** on
the owner's machine to try to clear it; no containers were running and nothing was removed.

## 3. The Action on a GitHub-hosted runner — the results table

| | |
|---|---|
| run | [33715576314](https://github.com/IcantFind-a-username/Attest/actions/runs/33715576314) on PR [#8](https://github.com/IcantFind-a-username/Attest/pull/8) |
| conclusion | **success**, every step green |
| wall clock | **76 s** (`04:35:04Z` → `04:36:20Z`); comment posted at `04:35:38Z`, 34 s in |
| spend | **$0.0301** (`ci_final`); `review_run` $0.017778, model `claude-sonnet-5` |
| backend | **`linux-container-v1`**, image `attest-repro:96b9871908772ebd`, built on the runner inside those 34 s |
| planted defect | `_normal_path` in `benchmark/matcher.py` loses backslash normalisation; the repo's own suite stays green |
| eligibility | 1 candidate, **eligible** — `definition _normal_path exists at the merge-base` |
| outcome | **DEFER** — `unfaithful generated test: fails on base as well`; 0 certified, 0 published |
| comment | posted once and upserted (3 `github_comment` rows, all `posted`) |
| after | PR closed unmerged, branch deleted, workflow file kept |

Comment, verbatim:

```
DEFER: verification deferred: unfaithful generated test: fails on base as well

Run status
- change units read: 1; candidates: 1; eligible: 1; reproductions attempted: 1; certified: 0; published: 0
- proposal prompt tokens: 5456; cache_read_input_tokens: 4086
- reproduction 1: unfaithful test — unfaithful generated test: fails on base as well
```

The run found one product defect, fixed in `d62bcd6`: the `certification` ledger row for a
not-attempted outcome reported `local_development_best_effort` while the runs had executed
under `linux-container-v1`. It buys nothing, but it is the row an audit reads to learn where
the code ran.

## 4. L-01, item by item

| item | state |
|---|---|
| stable install ref | **done** — `v0.1.0-pilot.1`, never moved |
| quickstart | **done** |
| base-owned policy docs | **done** |
| executor support matrix | **done** |
| privacy / retention | **done this window** — approved, draft heading gone, provider-side retention named as out of scope (D-107) |
| failure-mode copy | **done** |
| kill switch and rollback | **documents done; drills now exist and pass** ([record](acceptance/2026-09-03-release-drills.md)); still **not** exercised on the pilot repository |
| private pilot | **done** — 6 documented silences (2026-09-03c) + 2 more reviews this window; **0 receipts in 9 reviewed commits** |
| `G-RELEASE-001` drills | **2 of 9** — kill switch and rollback, each with a negative control, offline; the other seven not started |
| `G-SEC-002` red-team matrix on the CI platform | **not started** |
| **the step-16 exit itself** | **not met** — the exit wants a receipt-backed comment *or* a documented silence per commit; only the silence branch has ever been taken |

## 5. The one number that matters

**Every reproduction that has ever executed on real traffic — six of six across four
populations — was rejected as an unfaithful generated test.** Not all for the same reason;
three distinct ones, all at the same stage:

| population | executed | verdict |
|---|---|---|
| this window's receipt pilot (`d7be758` ×2, `e17c686` ×1) | 3 | `pytest passed on head in 3/3 runs; base not executed` |
| the runner review (PR #8) | 1 | `fails on base as well` |
| `pytest-10051` | 1 | `fails on base as well` |
| 2026-09-03c pilot (`f58bf64`) | 1 | `references a symbol absent from head` |

Three generated tests do not fail on the buggy side; two fail on both sides; one names a
symbol that is not there. **6 / 6.**

Every other stage now works on real traffic: candidates are produced, 12 of 13 were
**eligible** on the receipt pilot, the container builds and runs, and the kernel refuses for
a stated reason every time. Generation is the wall. That is a measurement question — why
does a test generated against a real diff not discriminate the two sides? — and it precedes
any further pilot spend. n = 6 is small; the point is that it is 6 of 6 and that no
reproduction has ever cleared the stage.

## 6. Gates

**The window-end gate is not green on this host, and the reason is the host.**

| gate | result |
|---|---|
| Ruff | clean |
| Mypy | clean over 79 files |
| `git diff --check` | clean |
| `pytest` (no coverage), `test_linux_isolation.py` deselected | **1,764 passed, 0 failed, exit 0** |
| `pytest --cov`, same deselection | **1,763 passed, 1 failed**; kernel coverage **88.35 %**, below the 90 % floor |

Both failures trace to the same host condition, not to this window's changes:

- `tests/execution/test_linux_isolation.py` was **deselected and did not run.** It calls
  `ensure_image` on a manifest-less tree, which needs `python:3.9-slim`, which this host
  cannot pull. It is the §12 change-impact row for executor changes, so the kernel change in
  `34affaf` has **not** been exercised against the real container backend here. The PR #8
  review did build and run an image on a GitHub runner, but that is not this test.
- That deselection *is* the coverage shortfall. The entire gap is one module:
  `container_adapter.py` at **43 %** (58 of 102 statements missed — the whole
  `ContainerAdapter.run` path), which is exactly what `test_linux_isolation.py` covers.
  Arithmetic, not a measurement: covering those 58 statements and nothing else would put the
  total at 92.71 %, against 91.10 % measured last window.
- The one failing test, `tests/benchmark/test_cli.py::test_replay_with_a_prepared_root_runs_the_real_product_path`,
  **passed in the plain run and failed under coverage.** Rerun alone it does not fail either
  — it *hangs*, and `ps` shows why: it spawns `docker build`, which never returns. It is the
  daemon condition again, arriving through a different door.

**The floor was not lowered and no test was skipped, deleted or xfailed.** The honest
statement is that this window's kernel change is covered by its own REDs and by the full
suite, and is *not* covered by the container-backed isolation tests, which no one can run on
this machine until its Docker VM can reach a registry. That is the first thing the next
window should check.

## 7. Spend

| item | reserved | spent |
|---|---|---|
| `pytest-10051` rerun (carried) | $0.10 | $0.019502 |
| L-01 receipt pilot | $0.30 | $0.247200 recorded + $0.05 charged for an interrupted run = **$0.2972** |
| first runner review | $0.30 | $0.030100 |
| **window** (cap $3) | $0.70 | **$0.346802**; cumulative **$20.556976** of $30 |

The $0.05 is conservative, not measured: the third pilot review was stopped ~15 s in with
only a `review_plan` row settled, and proposal samples may have been in flight and billed
without a ledger row (AGENTS §9).

## 8. What this window did not do, and why

- **The third pilot commit (`20c7260`) was not reviewed.** After two reviews $0.0528 of the
  owner's $0.30 remained, which cannot fund a review at the product default $0.25. Three
  commits and $0.30 are not jointly satisfiable; the money was treated as the harder
  constraint, because DEVSPEND already records one $0.29 overrun from a driver with no
  cumulative cap. Owner question 3.
- **No receipt was produced**, which was decision 2's whole point. See §5.
- **`tests/execution/test_linux_isolation.py` did not run, the coverage floor was
  therefore missed at 88.35 %, and one unrelated test failed under coverage.** All three
  are the same host condition. See §6.
- **Seven of the nine `G-RELEASE-001` drills are not implemented** — the instruction was the
  minimal two.
- **Kill switch and rollback were still not exercised on the pilot repository**, only as
  drills against a synthetic repository the drill builds itself.
- **The fork path of the new workflow was exercised only in the affirmative.** No fork pull
  request was opened, so both guards were watched admitting, never refusing.
- **Finding 3 of the review was not fixed** (the 1800 s cap against the 600 s deadline).
  Owner question 2.
- **The fixes in `34affaf` were not themselves independently reviewed**, although they touch
  `attest.execution`. D-049 bounds the loop at exactly one review pass per work-order branch,
  and a second round's findings go to the backlog rather than to more code; so the reviewed
  artefact is `9df938f`, and the repairs it prompted are self-checked (§11 step 6) plus their
  own REDs. If the owner wants the repairs reviewed as well, that is a new pass on a new
  branch, not a continuation of this one. `d62bcd6` touches `attest.review.certify`, which is
  peripheral under D-105 and needs no independent review.
- **The host's docker registry egress was not repaired.** A restart did not fix it and
  anything further (resetting the VM, changing its DNS) risks the owner's images and volumes.
- **One thing outside instruction:** Docker Desktop was restarted once, to try to unblock an
  authorised paid run. It is local and reversible, nothing was running, and it did not help.

## 9. For the owner — three yes/no questions, defaults in brackets

1. **Make the next window a measurement work order on reproduction generation** — why a test
   generated against a real diff does not discriminate the two sides — before any further
   pilot spend? Six of six executed reproductions across four populations were rejected as
   unfaithful, and every stage around it now works. [yes]
2. **Cap the image build at the remaining verification budget** (`min(1800 s, remaining)`)
   so a 601–1800 s build cannot consume the 600 s deadline and then report the wrong failure
   category? This lowers an effective backend timeout, which is why it was not done
   unasked. [yes]
3. **Reserve a floor for verification inside the per-review budget** — for example,
   proposals may spend at most 60% of it — so breadth cannot starve every reproduction? On
   `d7be758` the proposal stage produced 12 candidates from a 210-line change and left nine
   of eleven reproductions with no budget to generate a test at all. [yes]
