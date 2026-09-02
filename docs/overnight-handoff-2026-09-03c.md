# Handoff — 2026-09-03, third window (`68408ad` → `a4e64aa`): the gates, three answers, and L-01

Status: **the coverage/property/review gates now bind the kernel only (D-105); E-04's two
answered questions are implemented; the L-01 document and private-pilot list is done and the
pilot ran on `us-stock-helper` at the tag `v0.1.0-pilot.1` — six commits, six documented
silences, four wiring fixes.** No PR, no GitHub comment, no remote setting changed.

## 0. Push and CI

`68408ad` and everything since is on `origin/main`. **There is no CI to confirm green: the
repository has no `.github/workflows/` and `gh run list` returns nothing.** The Action this
product ships has therefore never run on a GitHub-hosted runner — every gate in this project
has only ever run on the owner's machine. That is owner item 3.

## 1. Owner process fix (D-105)

`G-CODE-001`: `fail_under = 90` now covers `attest.certification` and `attest.execution`
(the kernel, receipt validation, policy, isolation protocol). `attest.review`, `attest.cli`,
`attest.github`, `attest.benchmark`, `attest.core` and `attest.deconstruct` print coverage as
an observation with no threshold. "All adjacent tests pass" deleted. Independent review is
required only for a change touching a kernel or security path. `G-CODE-002` (property and
mutation tests) applies to those paths only; peripheral modules write neither. Unchanged: one
named RED per behaviour change, one `pytest` / `ruff` / `mypy` run at the end of an order, no
test may touch the network, a secret or the clock. Synced in `agent-work-orders.md` §1.9,
§3.1, §5, `AGENTS.md` §11 and §13, and `pyproject.toml`. No test was deleted.

## 2. The three answers from the last window

| answer | what landed | commit |
|---|---|---|
| E-04 next layer: source units before documentation, budget unchanged, silence says `read N of M units, budget-limited` | `_unit_order` ranks `.py` before every other path in the plan; the proposal writes a `proposal_coverage` ledger row and the status stops reporting the *planned* count as if it had been *read* | `046422d` |
| Re-run `pytest-dev__pytest-10051` under post-`69921e0` code as a separate supplementary row | **not completed.** `docker build` for pytest's image hit the executor's 1800 s cap and `subprocess.TimeoutExpired` propagated out of `select_backend`, so the run crashed before any model call: no result file, **$0.00 spent**, reservation released. The held-out table and the README are untouched, as instructed. The crash is a real defect against the operator-facing contract — `failure-modes.md` promises `environment bootstrap failed: …` in the run status, not a traceback — and is fixed in `9df938f` (RED `test_an_image_build_that_times_out_is_a_bootstrap_failure_not_a_traceback`). The rerun is carried to the next window | — |
| E-04 blind reviewer: accept `INSUFFICIENT` | v1's units stay `unresolved`; precision and eligible detection stay `INSUFFICIENT`; nothing is blocked | `260e8d9` |

REDs for the first: `test_source_units_are_planned_before_documentation_units` (RED observed
on the old path-only ordering) and `test_a_budget_limited_run_says_how_many_units_it_read_of_how_many`.
Because it is a product-code change, the next prospective units run as **stratum v2**;
stratum v1's two units stand as recorded (D-103 amendment).

## 3. L-01 (mainline step 16), item by item

| item | state | where |
|---|---|---|
| stable install ref | **done** — annotated tag `v0.1.0-pilot.1` (`eedb656`), pushed; never moved | `docs/operations/install-ref.md` |
| quickstart | **done** — executed verbatim from a fresh clone; corrected where it did not match reality | `docs/operations/quickstart.md` |
| base-owned policy docs | **done** — every key, its factory default, and what a repository setting can never do | `docs/operations/base-policy.md` |
| executor support matrix | **done** (pre-existing) — checked against the pilot; nothing needed changing | `docs/operations/support-matrix.md` |
| privacy / retention | **blocked on the owner** — still headed "draft, for the owner's approval before any pilot"; the pilot ran anyway because it wrote nothing outward | `docs/operations/privacy-and-retention.md` |
| failure-mode copy | **done** — added the budget-bound partial review | `docs/operations/failure-modes.md` |
| kill switch and rollback | **done as documents**, and the rollback doc now names the oldest admissible target; **not exercised on the pilot repository** | `docs/operations/kill-switch-and-rollback.md` |
| private pilot | **done** — table below | `docs/acceptance/2026-09-03-l01-private-pilot.md` |
| `G-RELEASE-001` operational drills (`scripts/release/drill.py --offline --all`, `tests/release/`) | **not started** | — |

Pilot repository `IcantFind-a-username/us-stock-helper` cloned fresh into
`.attest/pilot/us-stock-helper` (default branch `feature/iphone-demo`, not `main` — which is
why there are two commit sets).

## 4. Private pilot: six reviews, no GitHub write

| set | commit | candidates | eligible | reproductions | certified | published / silence | spend |
|---|---|---|---|---|---|---|---|
| 1 `main` | `00549e4` LICENSE | 0 | 0 | 0 | 0 | documented silence | $0.0146 |
| 1 | `4170859` new indicator package (all-new files) | 9 | 0 | 0 | 0 | documented silence; **read 1 of 2 units, budget-limited** | $0.0852 |
| 1 | `dd75a7e` `.gitignore` | 0 | 0 | 0 | 0 | documented silence | $0.0072 |
| 2 newest by date | `8687625` `CLAUDE.md` | 0 | 0 | 0 | 0 | documented silence | $0.0053 |
| 2 | `f57fc39` backlog | 0 | 0 | 0 | 0 | documented silence | $0.0137 |
| 2 | `f58bf64` options-flow slice (changes existing Python) | 15 | **1** | **1** | 0 | documented silence: *unfaithful generated test — it references a symbol absent from head*; **read 2 of 3 units, budget-limited** | $0.1512 |

**0 publications of 6; $0.2772 total.** The one reproduction ran the production path:
`linux-container-v1`, image built from the project's own manifests, container executed. The
new budget-bound wording appeared in the field on two of six commits.

Wiring problems found and fixed, one commit each: the example workflow pinned `@main` instead
of an immutable ref (RED `test_example_workflow_pins_the_action_to_an_immutable_ref`); the CLI
help never named the offline bundle verifier the quickstart tells the operator to run (RED
`test_top_level_help_says_verify_checks_a_bundle_offline`); `python -m venv` in step 1 fails on
a stock macOS (now `python3`); the quickstart promised two local outcomes and omitted the
drawer list and the budget-bound status. Checked and correct, unchanged: the workflow's
`permissions:` block against the two endpoints the client actually calls, `fetch-depth: 0`,
the `pull_request` event payload shape, the 3.12.8 interpreter pin.

## 5. Gates

Window-end gate on the clean primary checkout at `260e8d9`:
**`pytest` exit 0, every test passed, kernel coverage 91.10 % against the new
`attest.certification` + `attest.execution` floor**, Ruff clean, Mypy clean over 79 files,
`git diff --check` clean. Peripheral coverage, printed as observations with no threshold:
`attest.review` 91 %, `attest.cli` 93 %, `attest.github` 95 %. The earlier dirty-tree run
reproduced the known M-01 probe failures (its clean-tree guard); on the committed tree they
pass. Two commits landed after the gate (`9df938f`, `3d5cba6`); their own tests, Ruff and
Mypy passed, and the full suite was not re-run for them.

## 6. Spend

| item | reserved | spent |
|---|---|---|
| `pytest-10051` post-fix rerun | $0.10 | **$0.00** (released) |
| L-01 private pilot, set 1 | $0.80 | $0.1070 |
| L-01 private pilot, set 2 | $0.80 | $0.1702 |
| **window** (cap $4) | | **$0.2772**; cumulative $20.210174 of $30 |

## 7. What this window did not do, and why

- **No `G-RELEASE-001` drill script.** The nine named drills (revoked credential, GitHub
  outage, executor unavailable, budget exhaustion, superseded PR, malicious same-repo change,
  verifier failure, rollback, retention failure) have no `scripts/release/drill.py` and no
  `tests/release/`. L-01's operational pass cannot be claimed without it. It was cut to reach
  the pilot inside the window; it is the next task and needs no owner input.
- **The pilot never produced a receipt.** None of the six commits regressed against its own
  parent, so the receipt-backed branch of the step-16 exit is unexercised on real pilot
  traffic. The pilot proves the wiring, not recall.
- **No GitHub write path ran**, by instruction: `upsert_issue_comment` and `create_review`
  were not exercised against the API, and the Action has never run on a GitHub runner.
- **Kill switch and rollback were not exercised on the pilot repository** — only their tests.
- **No independent review** of this window's changes: the owner waived it for this window.
  One change would otherwise have required it under D-105 — `9df938f` touches
  `attest.execution` (the image-build timeout). It is the one item to review next window.
- **`scripts/corpus/natural_null.py`'s table regex** did not read the new budget-bound status
  line and degraded to dashes; fixed in `3d5cba6`. No existing report changed.
- One thing that is arguably outward-facing was done without asking: the annotated tag
  `v0.1.0-pilot.1` was pushed to `origin`. A stable install ref that exists only locally is
  not an install ref; it is additive and never moved.

## 8. For the owner — three yes/no questions, defaults in brackets

1. Approve `privacy-and-retention.md` as written (bundles kept indefinitely, work dirs removed
   after the run, cache and ledger the operator's choice, key rotated by deletion) so the
   "draft, for the owner's approval" heading can come off and `G-RELEASE-001` can count it?
   [yes]
2. Run a receipt-bearing pilot next window: pick three `us-stock-helper` commits that a later
   `fix:` commit repairs, review each with `head` = the buggy commit, and show a real
   receipt-backed comment end to end. ≈$0.30. [yes]
3. The Action has never run on a GitHub-hosted runner and this repository has no CI. Add a
   `pull_request` workflow to **Attest itself** and let it review one throwaway branch, so the
   runner path is exercised once before an outside repository depends on it? This is a remote
   write and a public comment on the owner's own repository. [yes]
