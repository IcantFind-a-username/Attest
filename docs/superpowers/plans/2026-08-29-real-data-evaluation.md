# Real-Data Evaluation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a reproducible benchmark that evaluates Attest on traceable real Python bug/fix pairs, reports accuracy/abstention/latency/cost with confidence intervals, and produces calibration evidence without silently changing factory statistical constants.

**Architecture:** A benchmark package wraps the existing `run_ci` product path rather than duplicating review logic. A corpus adapter imports metadata from a pinned BugsInPy checkout, materializes paired counterfactual bug-introducing diffs and developer-fix controls, and validates the upstream regression oracle. Scoring joins final ledger decisions to candidates and uses a differential reproduction oracle: a generated test is faithful only when it fails on the real buggy tree and passes on the developer-fixed tree. Local validation and replay are default/offline; live model calls are explicit, resumable, budgeted observations.

**Tech Stack:** Python 3.11+, dataclasses, pathlib, hashlib, json, subprocess, git, pytest, existing Attest provider/CI/executor/ledger boundaries.

## Global Constraints

- Follow root `AGENTS.md`, including no third-party writes, no public release, no secret output, conventional commits, and independent review.
- Do not change `alpha`, S/T/V likelihood ratios, correlation schedules, channel caps, or any factory statistical constant. This work may report calibration recommendations only; changing constants requires a later explicit owner decision and at least 500 global labels.
- Pin the initial external corpus to BugsInPy commit `316b95e2353ecda832bad9b42f86fa7c2fcec8ac`; store provenance, hashes, and source-license metadata, not copied third-party repositories.
- Label inverse developer fixes honestly as `historical_bug_replay`; never call them natural bug-introducing PRs. Preserve `bug_introducing_commit` as a separate future provenance kind.
- Ground truth, fixed-tree content, fix messages, test output, and role labels must not enter proposer or generator prompts. Case identifiers exposed to the product are opaque.
- Default mode performs no network, GitHub, or model calls even if credentials exist. Live local calls require `--allow-paid-api`; remote calls require a separate `--allow-remote` flag.
- Every paid call is pre-reserved, settled, resumable without duplicate calls, and recorded in `DEVSPEND.md`; the existing $10 development cap remains binding.
- Report precision, recall/detection, clean FPR/specificity, abstention, duplicates, delivery, p50/p95 latency, and spend. Coverage is never reported as review accuracy.
- A generated test is benchmark-confirmed evidence only if it fails on the buggy tree and passes on the corresponding fixed tree under the same limits.
- Use strict TDD: observe a relevant RED before production changes, then immediately run the focused GREEN test.

---

### Task 1: Preserve Terminal Gate Decisions in CI

**Files:**
- Modify: `src/attest/review/ci.py`
- Test: `tests/test_ci_flow.py`

**Interfaces:**
- Consumes: `ReviewRun.results`, `StoredCandidate.action`, `verify_candidate`.
- Produces: a CI verification loop that purchases V only for candidates whose current action is `drawer`.

- [ ] **Step 1: Write the failing regression test**

Create a real `run_ci` test with `alpha=0.15`, a proposal and Tier-0 evidence that reach `surface` before V, and a generator provider that would fail the test if called. Assert one surfaced finding, no `verification` ledger row, no V purchase, no generator call, and a `ci_final` surface decision.

- [ ] **Step 2: Run the focused test and observe RED**

Run:

```bash
.venv/bin/pytest tests/test_ci_flow.py::test_ci_does_not_verify_an_already_terminal_surface -q
```

Expected: FAIL because `run_ci` currently calls `verify_candidate` for every stored candidate.

- [ ] **Step 3: Implement the minimal terminal-decision filter**

Filter the candidate list before deadline accounting so only `candidate.action == "drawer"` enters verification. Do not create fake verification evidence for terminal surface/discard candidates; `ci_final` remains the authoritative final decision.

- [ ] **Step 4: Run focused and neighboring tests**

```bash
.venv/bin/pytest tests/test_ci_flow.py tests/test_gate.py tests/test_budget_ledger.py -q
```

- [ ] **Step 5: Commit**

```bash
git add src/attest/review/ci.py tests/test_ci_flow.py
git commit -m "fix: preserve terminal review decisions"
```

---

### Task 2: Define Corpus, Predictions, Matching, and Metrics

**Files:**
- Create: `src/attest/benchmark/__init__.py`
- Create: `src/attest/benchmark/schema.py`
- Create: `src/attest/benchmark/matcher.py`
- Create: `src/attest/benchmark/metrics.py`
- Create: `tests/benchmark/test_schema.py`
- Create: `tests/benchmark/test_matcher.py`
- Create: `tests/benchmark/test_metrics.py`

**Interfaces:**
- Produces: `BenchmarkManifest`, `BenchmarkCase`, `TruthDefect`, `Prediction`, `RunRecord`, `MatchResult`, `BenchmarkReport`, `load_manifest`, `match_findings`, `aggregate`, and `wilson_interval`.
- `Prediction` comes from joined `ci_final` decisions and candidate rows; `placement` is independent of `action`.

- [ ] **Step 1: Write schema/hash/opacity RED tests**

Use literal JSON fixtures. Require schema/protocol versions, corpus commit, case/pair/source IDs, role, provenance kind, source license, buggy/fixed commits, patch/test hashes, changed locations, and split. Reject path traversal, duplicate IDs, missing pair roles, non-opaque exposed IDs containing `bug`, `clean`, or defect terms, hash mismatch, and unknown enum values.

- [ ] **Step 2: Run schema RED**

```bash
.venv/bin/pytest tests/benchmark/test_schema.py -q
```

Expected: collection failure because `attest.benchmark` does not exist.

- [ ] **Step 3: Implement immutable schema and loader**

Use frozen dataclasses and explicit validation. Hash canonical JSON with sorted keys and compact separators. Keep truth separate from the product-visible case metadata.

- [ ] **Step 4: Write matcher RED tests**

Cover normalized exact paths, line ranges with preregistered slack, one-to-one maximum matching, duplicate surfaced findings becoming FP, overflow surfaces being scored, drawer/discard exclusion, wrong-location surface as FP plus FN, and differential repro status as a required match condition.

- [ ] **Step 5: Implement deterministic matcher**

Create edges only for compatible file/line and `buggy_fail_fixed_pass` differential evidence. Maximize cardinality; break ties by anchor distance then `(defect_id, finding_id)`. Never derive truth from claims or generated tests.

- [ ] **Step 6: Write metrics/Wilson RED tests**

Pin these 95% Wilson intervals: `40/40 -> [0.912378, 1]`, `38/40 -> [0.834961, 0.986179]`, `20/40 -> [0.351995, 0.648005]`, `0/40 -> [0, 0.087622]`. Cover TP/FP/FN/TN, clean FPR, specificity, all-positive detection, finding precision, conditional recall, abstention, duplicates, delivery, nearest-rank p50/p95, deadline censoring, and `n=0 -> null`.

- [ ] **Step 7: Implement aggregation**

Treat a positive with only wrong findings as both PR-level FN and finding-level FP. Clean with any surface is FP even if the run later defers. Repeats never enlarge the Wilson denominator; headline intervals use preregistered repeat zero.

- [ ] **Step 8: Run focused GREEN and commit**

```bash
.venv/bin/pytest tests/benchmark/test_schema.py tests/benchmark/test_matcher.py tests/benchmark/test_metrics.py -q
.venv/bin/ruff check src/attest/benchmark tests/benchmark
.venv/bin/mypy src/attest/benchmark
git add src/attest/benchmark tests/benchmark
git commit -m "feat: score real-data review benchmarks"
```

---

### Task 3: Import and Validate Real BugsInPy Pairs

**Files:**
- Create: `src/attest/benchmark/corpus.py`
- Create: `scripts/benchmark.py`
- Create: `benchmarks/attest-v1/protocol.md`
- Create: `benchmarks/attest-v1/manifest.json`
- Create: `benchmarks/attest-v1/preregistration.sha256`
- Create: `tests/benchmark/test_corpus.py`
- Create: `tests/benchmark/test_cli.py`

**Interfaces:**
- Consumes: a user-supplied pinned BugsInPy checkout and its `project.info`, `bug.info`, `bug_patch.txt`, `run_test.sh`, buggy/fixed output, and upstream project URL.
- Produces: `import_bugsinpy(source, output, limit, seed)`, `validate_corpus(manifest, root, runner)`, opaque paired cases, and CLI modes `import-bugsinpy` and `validate`.

- [ ] **Step 1: Write importer RED tests**

Build a miniature real-layout BugsInPy fixture. Assert deterministic selection by seed, exact pinned corpus commit, source URL/license, buggy/fixed commit IDs, normalized patch paths/ranges, patch/test SHA-256, paired `historical_bug_replay` and `developer_fix_control` roles, and opaque case IDs. Reject missing license, symlinks escaping the source, binary patches, non-Python changes, oversized diffs, and missing regression tests.

- [ ] **Step 2: Run importer RED**

```bash
.venv/bin/pytest tests/benchmark/test_corpus.py -q
```

- [ ] **Step 3: Implement metadata-only import**

Do not copy third-party source into this repository. The committed manifest contains provenance, hashes, commands, changed locations, and upstream references. Materialization clones/fetches only into a caller-provided cache and verifies commits/hashes before use.

- [ ] **Step 4: Write oracle RED tests**

Use a tiny local git project with an actual failing/passing pytest. Require three consecutive fixed PASS and buggy FAIL runs with the same normalized failure signature. Mark flaky, dependency/setup failure, timeout, or inconsistent signatures as excluded rather than silently negative.

- [ ] **Step 5: Implement isolated oracle validation**

Use argv arrays, explicit cwd/env, finite timeout, bounded output, and caller-provided interpreters. Never execute corpus setup scripts automatically in default validation; require a prepared environment or an explicit container command.

- [ ] **Step 6: Write CLI fail-closed RED tests and implement**

Default `validate` must not invoke network, `gh`, or a provider even if credentials exist. `import-bugsinpy` requires an existing local source path. JSON output is deterministic and contains exclusions with reasons.

- [ ] **Step 7: Import the initial real metadata pilot**

From the pinned checkout, deterministically select at least 20 paired cases from at least four Python projects after license/diff/test filters. Freeze the manifest and preregistration hash before observing Attest results. If fewer qualify, record every exclusion and freeze the largest qualifying set without weakening filters.

- [ ] **Step 8: Run focused GREEN and commit**

```bash
.venv/bin/pytest tests/benchmark/test_corpus.py tests/benchmark/test_cli.py -q
.venv/bin/python scripts/benchmark.py validate --manifest benchmarks/attest-v1/manifest.json --offline
git add src/attest/benchmark/corpus.py scripts/benchmark.py benchmarks/attest-v1 tests/benchmark
git commit -m "feat: import reproducible Python bug pairs"
```

---

### Task 4: Run Product Replay, Differential Evidence, and Artifacts

**Files:**
- Create: `src/attest/benchmark/runner.py`
- Create: `src/attest/benchmark/artifacts.py`
- Create: `src/attest/benchmark/report.py`
- Modify: `scripts/benchmark.py`
- Create: `tests/benchmark/test_runner.py`
- Create: `tests/benchmark/test_artifacts.py`
- Create: `tests/benchmark/test_report.py`

**Interfaces:**
- Produces: `BenchmarkRunner.run_case`, `ArtifactStore`, `extract_predictions`, `run_differential_repro`, deterministic JSON/Markdown reports, and CLI mode `replay`.
- Reuses: real `run_ci`, `Ledger`, `CandidateStore`, executor subprocess/JUnit parsing, a replay `Provider`, and a loopback GitHub adapter.

- [ ] **Step 1: Write real-path runner RED test**

Use a temporary git pair, a recorded complete proposer/generator response, real `run_ci`, real pytest subprocess, and loopback GitHub HTTP. Assert task identity, `ci_final` join, surface/overflow extraction, spend, verification outcome, and comment delivery without asserting mock call existence.

- [ ] **Step 2: Implement the replay runner**

External uncertainty is frozen, but product review/gate/executor/ledger code remains real. Re-running the same cassette and manifest must produce equivalent scored output except explicitly excluded timestamps.

- [ ] **Step 3: Write differential-repro RED tests**

Cover fail-on-buggy/pass-on-fixed as confirmed, fail/fail as unfaithful generated test, pass/pass as not reproduced, collection/setup/timeout as DEFER, and identical limits/interpreter on both trees.

- [ ] **Step 4: Implement differential evidence scoring**

Do not mutate product V decisions retrospectively. Store benchmark oracle status separately and use it only for benchmark matching/calibration diagnostics.

- [ ] **Step 5: Write artifact security/integrity RED tests**

Allowlist `manifest`, product ledger, joined predictions, bounded repro/JUnit output, scored run, and sanitized GitHub summaries. Reject private keys, token patterns, `.env`, path traversal, unknown files, hash mismatch, and raw unbounded provider prompts/responses. Recursively redact known in-process secret values.

- [ ] **Step 6: Implement atomic artifacts and deterministic reports**

Every artifact gets SHA-256 in a manifest written last via atomic replace. Reports state provenance limitations, exclusions, repeats, Wilson intervals, and distinguish replay regression from live observation.

- [ ] **Step 7: Run focused GREEN and commit**

```bash
.venv/bin/pytest tests/benchmark/test_runner.py tests/benchmark/test_artifacts.py tests/benchmark/test_report.py -q
.venv/bin/python scripts/benchmark.py replay --manifest benchmarks/attest-v1/manifest.json --cassette-root benchmarks/attest-v1/cassettes --output work/benchmark-replay
git add src/attest/benchmark scripts/benchmark.py tests/benchmark
git commit -m "feat: replay real-data review benchmarks"
```

---

### Task 5: Add Resumable Live-Local Evaluation and Calibration Report

**Files:**
- Create: `src/attest/benchmark/live.py`
- Modify: `scripts/benchmark.py`
- Create: `tests/benchmark/test_live.py`
- Create on an authorized successful run: `docs/acceptance/real-data-evaluation.md`
- Modify on paid runs: `DEVSPEND.md`
- Modify: `DECISIONS.md`

**Interfaces:**
- Produces: CLI mode `live-local --allow-paid-api`, atomic run checkpoints, idempotent cost settlement, `--resume RUN_ID`, and calibration recommendations that never mutate production constants.

- [ ] **Step 1: Write opt-in/preflight RED tests**

Reject live mode without `--allow-paid-api`, missing key, non-immutable manifest, insufficient development-cap headroom, or an unfrozen preregistration hash. Verify key presence by boolean/length/prefix only.

- [ ] **Step 2: Implement fail-closed live preflight**

Default commands remain offline even when a key exists. Live-local invokes the real `ApiProvider` but no GitHub mutation. Reserve the full selected-case budget before the first call.

- [ ] **Step 3: Write checkpoint/resume RED tests**

Interrupt after provider completion, after artifact persistence, and before report settlement. Resume must never repeat a completed model call, must verify artifact hashes, and must append each provider/run cost exactly once.

- [ ] **Step 4: Implement atomic state machine**

Use states `reserved -> provider_complete -> artifacts_complete -> settled -> reported`. Unknown cost or corrupt state fails closed and retains evidence.

- [ ] **Step 5: Write calibration-report RED tests**

Report channel-conditioned empirical outcomes, differential V fidelity, precision/recall/FPR/abstention, Wilson intervals, strata, latency/cost, exclusions, and sample sufficiency. Below 500 globally labeled findings, output `recommendation_only` and prohibit a constants patch.

- [ ] **Step 6: Implement report and decision record**

Add a decision documenting corpus provenance, counterfactual direction, differential oracle, frozen holdout, and reversal conditions. The report must state whether results are replay or live and must not claim accuracy from replay.

- [ ] **Step 7: Run fake-backed GREEN and full local gates**

```bash
.venv/bin/pytest tests/benchmark -q
.venv/bin/pytest --cov=src/attest --cov-report=term-missing
.venv/bin/pytest -q tests/test_allocation.py tests/test_betting.py tests/test_engine_default.py tests/test_exploration.py tests/test_monitor.py tests/test_regression_pins.py tests/test_tables.py --cov=attest.core --cov-report=term-missing --cov-fail-under=99
.venv/bin/ruff check .
.venv/bin/mypy src/attest
.venv/bin/mypy scripts/benchmark.py
```

- [ ] **Step 8: Stop-check, then run live-local when credentials exist**

The current controller has no model API key. Leave the tested implementation and frozen corpus intact. When a key is available and paid execution is explicitly authorized, run a small preregistered pilot first; immediately report spend and results, then expand only within the remaining $10 cap.

- [ ] **Step 9: Commit local implementation; commit live evidence separately**

```bash
git add src/attest/benchmark scripts/benchmark.py tests/benchmark DECISIONS.md
git commit -m "feat: automate real-data evaluation"
```

After an authorized successful live run only:

```bash
git add docs/acceptance/real-data-evaluation.md DEVSPEND.md
git commit -m "docs: record real-data evaluation"
```

---

## Plan Self-Review

- **Spec coverage:** real developer bug/fix provenance, paired controls, reproducible oracle, blind truth, product-path reuse, differential V validation, accuracy/abstention/latency/cost metrics, uncertainty, artifacts, replay/live separation, checkpointing, budget, and calibration limits each map to a task.
- **Placeholder scan:** no deferred implementation placeholder appears; every task names files, interfaces, RED/GREEN commands, and commit boundaries.
- **Type consistency:** `BenchmarkCase` feeds corpus materialization and `BenchmarkRunner`; `RunRecord` joins product ledger/candidate data; `MatchResult` feeds `aggregate`; `BenchmarkReport` feeds JSON/Markdown rendering; live checkpoints key every paid call by benchmark run/case/repeat identity.
- **Evidence honesty:** BugsInPy contains real defects and developer fixes, but reversed fixes are counterfactual review diffs. Reports must separate this from future naturally occurring bug-introducing PRs and from replay cassettes.
