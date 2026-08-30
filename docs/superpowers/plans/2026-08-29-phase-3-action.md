# Phase 3 GitHub Action and Auto-Verification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a locally verified composite GitHub Action that posts a status-only sticky comment, automatically runs focused Python reproduction tests, and publishes at most three findings only after the existing wealth gate clears.

**Architecture:** Extract the existing CLI orchestration into a reusable review service, persist typed candidates by review task, and keep the frozen S/T/V betting logic in `review.gate`. A best-effort sandboxed Python executor produces ternary evidence (`reproduced`, `not_reproduced`, `deferred`); only the first two buy V evidence. A standard-library GitHub client and a CI coordinator own two-stage comments, while `action.yml` remains a thin installer/launcher and uploads the runner ledger as an artifact.

**Tech Stack:** Python 3.11+, pathlib, dataclasses, urllib, subprocess, pytest, composite GitHub Actions, setup-uv, GitHub CLI for acceptance.

## Global Constraints

- Follow `/Users/franz/Documents/Codex/2026-08-29/https-github-com-icantfind-a-username/Attest/AGENTS.md` exactly; settled decisions in `DECISIONS.md` are not re-opened.
- No AI-assistant or vendor-agent names in commit messages, branch names, code, or comments.
- Do not change factory alpha, channel caps, LR schedules, or any architecture red line.
- Only the continuous wealth threshold decides speech; the top-three cap controls placement, never suppression.
- A generated reproduction test is strong evidence and a surface brake, never an unconditional pass.
- Fork pull requests never execute head code in a privileged context.
- Every model call is budget-reserved before execution; development API spend remains below $10 and every call is logged in `DEVSPEND.md`.
- Python production changes use strict RED -> GREEN -> REFACTOR; each focused test is run once while failing and again while passing.
- Phase gate: all pytest tests pass, total `src/attest` coverage is at least 90%, `attest.core` coverage is at least 99%, ruff is clean, and mypy is clean.
- Remote creation, pushes, secrets, and live API calls require the controller to honor AGENTS.md's stop conditions before performing them.

---

### Task 1: Enforce the Coverage Floor

**Files:**
- Modify: `pyproject.toml`

**Interfaces:**
- Consumes: pytest-cov's existing `[tool.coverage.report]` configuration.
- Produces: an enforced total coverage floor of exactly 90 percent.

- [ ] **Step 1: Add the configured gate**

Add the following value under `[tool.coverage.report]` without changing `show_missing`:

```toml
fail_under = 90
```

- [ ] **Step 2: Run the behavior that consumes the configuration**

Run:

```bash
.venv/bin/pytest --cov=src/attest --cov-report=term-missing
```

Expected: 128 baseline tests pass and coverage exits successfully above 90 percent. This configuration-only change is verified through the consuming coverage command rather than a source-text assertion.

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "chore: enforce coverage floor"
```

---

### Task 2: Extract the Review Service and Typed Candidate Store

**Files:**
- Create: `src/attest/review/candidates.py`
- Create: `src/attest/review/run.py`
- Create: `tests/test_candidates.py`
- Create: `tests/test_review_run.py`
- Modify: `src/attest/review/gate.py`
- Modify: `src/attest/cli/main.py`
- Modify: `tests/test_gate.py`
- Modify: `tests/test_cli_e2e.py`

**Interfaces:**
- Consumes: `Finding`, `GateResult`, `GateOutcome`, `propose`, `collect_signals`, `Budget`, and `Ledger`.
- Produces: `StoredCandidate`, `CandidateStore`, `ReviewRun`, `run_review`, and `apply_verification` for the executor and CI coordinator.

Use these exact public shapes:

```python
@dataclass(frozen=True)
class StoredCandidate:
    task_id: str
    finding: Finding
    wealth: float
    action: str
    alpha: float

class CandidateStore:
    def __init__(self, repo: Path): ...
    def append(self, task_id: str, alpha: float, results: list[GateResult]) -> None: ...
    def load(self, task_id: str | None = None) -> list[StoredCandidate]: ...
    def latest(self, finding_id: str, task_id: str | None = None) -> StoredCandidate | None: ...

@dataclass
class ReviewRun:
    task_id: str
    alpha: float
    budget: Budget
    results: list[GateResult]
    outcome: GateOutcome
    notes: list[str]
    deferred_reason: str | None
    elapsed_s: float

def run_review(
    repo: Path,
    base: str | None,
    config: ReviewConfig,
    provider: Provider,
    *,
    clock: Callable[[], float] = time.monotonic,
) -> ReviewRun: ...

def apply_verification(result: GateResult, alpha: float, reproduced: bool) -> GateResult: ...
```

`CandidateStore` keeps the existing JSONL keys for compatibility and reconstructs `Finding` including votes. Invalid JSON and malformed rows are skipped. `run_review` owns proposal, tier-0 signals, S/T evaluation, task-scoped candidate persistence, review/review_run ledger rows, and budget deferral. `cmd_review` becomes parameter adaptation plus `render()`. `cmd_verify` resolves a stored candidate, calls `apply_verification`, and records the same human-visible result as before.

- [ ] **Step 1: Write failing candidate-store tests**

Add tests that append two tasks sharing one finding id, assert task-filtered `latest`, assert all finding fields round-trip, and assert corrupt JSONL lines are ignored. Name the mutation caught by each test: losing `task_id`, losing a finding field, or aborting on one corrupt row.

- [ ] **Step 2: Verify candidate-store RED**

Run:

```bash
.venv/bin/pytest tests/test_candidates.py -q
```

Expected: collection fails because `attest.review.candidates` does not exist.

- [ ] **Step 3: Implement the minimal candidate store and verify GREEN**

Implement only the interfaces above, then rerun the same command. Expected: all candidate tests pass.

- [ ] **Step 4: Write failing verification-helper tests**

Add literal assertions showing `wealth=2.639...` becomes a surface after reproduced V evidence, becomes drawer after failed reproduction, purchases exactly one V channel, and does not mutate the input `GateResult`.

- [ ] **Step 5: Verify gate-helper RED, implement, and verify GREEN**

Run the exact focused tests before and after implementation:

```bash
.venv/bin/pytest tests/test_gate.py -q
```

The RED failure must be a missing `apply_verification`; GREEN must preserve all existing gate tests.

- [ ] **Step 6: Write failing review-service parity tests**

Use a real temporary git repository and `MockProvider`. Assert `run_review` returns one drawer candidate, writes only that task's candidate and ledger rows, records a deterministic elapsed time through the injected clock, and turns `BudgetExceeded` into an explicit defer without a model call.

- [ ] **Step 7: Verify review-service RED, implement, and verify GREEN**

Run:

```bash
.venv/bin/pytest tests/test_review_run.py tests/test_cli_e2e.py -q
```

Expected RED: missing `run_review`; expected GREEN: the service tests and all existing CLI behavior pass.

- [ ] **Step 8: Commit**

```bash
git add src/attest/review/candidates.py src/attest/review/run.py src/attest/review/gate.py src/attest/cli/main.py tests/test_candidates.py tests/test_review_run.py tests/test_gate.py tests/test_cli_e2e.py
git commit -m "refactor: expose review workflow services"
```

---

### Task 3: Build the Budgeted Python Evidence Executor

**Files:**
- Create: `src/attest/review/executor.py`
- Create: `tests/test_executor.py`
- Modify: `src/attest/review/ledger.py`
- Modify: `tests/test_budget_ledger.py`

**Interfaces:**
- Consumes: `StoredCandidate`, `Provider`, `Budget`, and `apply_verification`.
- Produces: validated generated repro specs, ternary execution results, and auditable verification rows.

Use these exact public shapes:

```python
class ExecutionOutcome(str, Enum):
    REPRODUCED = "reproduced"
    NOT_REPRODUCED = "not_reproduced"
    DEFERRED = "deferred"

@dataclass(frozen=True)
class ExecutorLimits:
    wall_timeout_s: float = 60.0
    cpu_timeout_s: int = 30
    memory_mb: int = 1024
    output_bytes: int = 16_384

@dataclass(frozen=True)
class ReproSpec:
    test_body: str

@dataclass(frozen=True)
class ExecutionResult:
    outcome: ExecutionOutcome
    reason: str
    exit_code: int | None
    stdout: str
    stderr: str
    elapsed_s: float
    network_blocked: bool

def generate_repro(
    repo: Path,
    candidate: StoredCandidate,
    provider: Provider,
    budget: Budget,
) -> ReproSpec: ...

def execute_repro(
    repo: Path,
    candidate: StoredCandidate,
    spec: ReproSpec,
    limits: ExecutorLimits,
) -> ExecutionResult: ...
```

The generation schema has one required string property, `test_body`, with `additionalProperties: false`. The generator receives claim, failure scenario, falsification plan, anchor, and at most 200 lines centered on the anchor. It reserves a call labeled `verify-<finding_id>` before provider use and settles or cancels it exactly once.

The executor supports `.py` anchors only. It writes `.attest/repro/<task_id>/<finding_id>/test_repro.py`, runs `[sys.executable, "-m", "pytest", "-q", generated_path, "--junitxml", junit_path]`, disables pytest plugin autoload, prepends a generated `sitecustomize.py` to `PYTHONPATH` to reject Python socket connections, and uses wall timeout everywhere plus CPU/address-space limits on POSIX. Exit code 1 is `REPRODUCED` only when JUnit reports at least one failure and zero errors. Exit code 0 is `NOT_REPRODUCED`. Timeout, unsupported language, malformed generator output, collection/import/syntax errors, missing JUnit, and executor failure are `DEFERRED` and buy no V evidence. Captured output is truncated to the last `output_bytes` bytes.

Add this ledger method:

```python
def record_verification(
    self,
    *,
    task_id: str,
    finding_id: str,
    outcome: str,
    reason: str,
    elapsed_s: float,
    network_blocked: bool,
    evidence: str,
) -> None: ...
```

- [ ] **Step 1: Write failing generation tests**

Cover literal schema validation, narrow anchor context, pre-charge before provider invocation, reservation cancellation on provider error, and task-scoped output paths. Use a recording provider fake that returns complete `ProviderResult` values; assert on budget state and returned behavior, not on mock existence.

- [ ] **Step 2: Verify generation RED, implement, and verify GREEN**

Run before and after:

```bash
.venv/bin/pytest tests/test_executor.py -q -k generate
```

- [ ] **Step 3: Write failing execution tests**

Use real subprocesses for: a focused assertion failure (`REPRODUCED`), a passing test (`NOT_REPRODUCED`), import error (`DEFERRED`), syntax error (`DEFERRED`), timeout (`DEFERRED`), unsupported non-Python anchor (`DEFERRED`), output truncation, and a socket attempt blocked by `sitecustomize`.

- [ ] **Step 4: Verify execution RED, implement, and verify GREEN**

Run before and after:

```bash
.venv/bin/pytest tests/test_executor.py -q -k execute
```

- [ ] **Step 5: Write failing ledger tests, implement, and verify GREEN**

Assert that reproduced, not-reproduced, and deferred events preserve exact task/finding identity and evidence without changing existing review bookkeeping. Run before and after:

```bash
.venv/bin/pytest tests/test_budget_ledger.py -q
```

- [ ] **Step 6: Commit**

```bash
git add src/attest/review/executor.py src/attest/review/ledger.py tests/test_executor.py tests/test_budget_ledger.py
git commit -m "feat: add constrained evidence executor"
```

---

### Task 4: Add the GitHub Context and Comment Adapter

**Files:**
- Create: `src/attest/github/__init__.py`
- Create: `src/attest/github/client.py`
- Create: `src/attest/github/context.py`
- Create: `src/attest/github/presentation.py`
- Create: `tests/test_github_client.py`
- Create: `tests/test_github_presentation.py`

**Interfaces:**
- Consumes: GitHub pull-request event JSON and verified `GateResult` values.
- Produces: fork-safe context detection, sticky issue-comment upserts, batched inline reviews, and text that never leaks drawer findings.

Use these exact public shapes:

```python
@dataclass(frozen=True)
class PullRequestContext:
    repository: str
    number: int
    base_sha: str
    head_sha: str
    is_fork: bool

def load_pull_request_context(event_path: Path) -> PullRequestContext: ...

class GitHubClient:
    def __init__(self, token: str, api_url: str = "https://api.github.com"): ...
    def upsert_issue_comment(self, repository: str, number: int, marker: str, body: str) -> dict: ...
    def create_review(self, repository: str, number: int, commit_id: str, comments: list[dict[str, object]]) -> dict: ...

STATUS_MARKER = "<!-- attest:status -->"

def render_running(candidate_count: int | None = None) -> str: ...
def render_deferred(reason: str) -> str: ...
def render_complete(results: list[GateResult], spend_usd: float, elapsed_s: float) -> str: ...
def inline_comments(results: list[GateResult]) -> list[dict[str, object]]: ...
```

`GitHubClient` uses `urllib.request` with JSON and GitHub API headers, follows pagination for issue comments, updates the first bot-authored marker comment or creates one, and raises a sanitized `GitHubApiError` that never includes the token. `inline_comments` accepts only surfaced gate results, sorts by wealth, puts the top three in the formal batch, and keeps surfaced overflow visible in the final sticky summary. Each inline object uses `path`, `line`, `side: "RIGHT"`, and a body containing claim, failure scenario, falsification plan, wealth, and evidence purchases.

- [ ] **Step 1: Write failing context and presentation tests**

Use literal event fixtures for same-repository and fork PRs. Assert running text contains no claim, file, line, scenario, or plan; deferred text contains only the reason; complete text names only surfaced results; inline comments reject drawer results and preserve right-side anchors.

- [ ] **Step 2: Verify presentation RED, implement, and verify GREEN**

Run before and after:

```bash
.venv/bin/pytest tests/test_github_presentation.py -q
```

- [ ] **Step 3: Write failing HTTP behavior tests**

Run a local `ThreadingHTTPServer` fake rather than asserting on a mock transport. Cover create sticky, update existing sticky, pagination, batched review payload, HTTP error sanitization, and token non-disclosure.

- [ ] **Step 4: Verify client RED, implement, and verify GREEN**

Run before and after:

```bash
.venv/bin/pytest tests/test_github_client.py -q
```

- [ ] **Step 5: Commit**

```bash
git add src/attest/github tests/test_github_client.py tests/test_github_presentation.py
git commit -m "feat: add pull request reporting adapter"
```

---

### Task 5: Orchestrate the Two-Stage CI Review

**Files:**
- Create: `src/attest/review/ci.py`
- Create: `tests/test_ci_flow.py`
- Modify: `src/attest/cli/main.py`
- Modify: `tests/test_cli_e2e.py`

**Interfaces:**
- Consumes: `run_review`, `CandidateStore`, executor interfaces, `PullRequestContext`, `GitHubClient`, and the existing gate.
- Produces: `attest ci` with immediate status, task-scoped verification, threshold-only speech, explicit fork/defer behavior, and ledger rows for every event.

Use this coordinator result:

```python
@dataclass
class CiRun:
    task_id: str | None
    candidate_count: int
    surfaced_count: int
    deferred_reason: str | None
    spend_usd: float
    elapsed_s: float

def run_ci(
    repo: Path,
    context: PullRequestContext,
    client: GitHubClient,
    config: ReviewConfig,
    provider: Provider,
    *,
    verification_timeout_s: float = 600.0,
    limits: ExecutorLimits | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> CiRun: ...
```

The exact event order is: reject fork before provider or subprocess use; upsert an immediate status-only running summary; call `run_review` against `context.base_sha`; update the same status-only summary with candidate count; generate/execute repros only for this `task_id`; map only conclusive results through `apply_verification`; write `verification` and `github_comment` ledger events; call `apply_gate` on updated results; publish one batched review only when surfaced results exist; update the sticky summary to complete or DEFER. Verification stops when the shared 600-second deadline expires; remaining candidates receive deferred ledger events and no V purchase. A GitHub comment failure is explicit and does not trigger a second model call.

The CLI subcommand is:

```text
attest ci --event-path PATH [--verification-timeout SECONDS] [--mock PAYLOAD ...]
```

It reads `GITHUB_TOKEN` and optional `GITHUB_API_URL`, applies normal config/CLI budget/model/sample overrides, rejects missing token or malformed event with exit code 2, and prints one JSON object matching `CiRun` for the action log. `--mock` is the offline integration-test seam and keeps the existing never-fall-through `nargs='+'` behavior.

- [ ] **Step 1: Write the failing planted-bug CI flow test**

Use a real temp git repo, real failing generated pytest, recording local HTTP GitHub server, and canned proposer/generator payloads. Assert the first comment timestamp precedes provider use, the intermediate comment contains a count but no finding text, V changes wealth, one inline finding appears only afterward, and all review/verification/comment ledger rows share one `task_id`.

- [ ] **Step 2: Verify planted-bug RED, implement minimal flow, and verify GREEN**

Run before and after:

```bash
.venv/bin/pytest tests/test_ci_flow.py -q -k planted
```

- [ ] **Step 3: Write remaining failing CI flow tests**

Cover clean negative control with zero inline comments, fork skip before provider/executor, review budget defer, executor timeout defer, verification deadline with unprocessed candidates, GitHub failure, and overflow visibility without suppression.

- [ ] **Step 4: Verify CI RED, complete implementation, and verify GREEN**

Run before and after:

```bash
.venv/bin/pytest tests/test_ci_flow.py -q
```

- [ ] **Step 5: Write failing CLI adaptation tests and verify RED**

Add tests for missing token, malformed event, mock provider routing, JSON output, and zero-file `--mock` rejection. Run:

```bash
.venv/bin/pytest tests/test_cli_e2e.py -q
```

- [ ] **Step 6: Implement CLI adaptation and verify GREEN**

Rerun the same command and then:

```bash
.venv/bin/pytest tests/test_ci_flow.py tests/test_cli_e2e.py -q
```

- [ ] **Step 7: Commit**

```bash
git add src/attest/review/ci.py src/attest/cli/main.py tests/test_ci_flow.py tests/test_cli_e2e.py
git commit -m "feat: orchestrate verified pull request reviews"
```

---

### Task 6: Add the Composite Action, Workflow Example, and Safety Documentation

**Files:**
- Create: `action.yml`
- Create: `examples/pull-request.yml`
- Create: `docs/github-action.md`
- Create: `scripts/action-entrypoint.sh`
- Create: `tests/test_action_entrypoint.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: `attest ci`, GitHub event environment, the action's own checkout, and setup-uv.
- Produces: a consumable root composite action, a workflow with exact permissions/concurrency, fork-safe behavior, and uploaded ledger evidence.

The action inputs are `github-token` (required), `model-api-key` (required for trusted PRs), `budget-usd` (default `0.25`), `samples` (default `5`), and `verification-timeout` (default `600`). The composite steps use `astral-sh/setup-uv`, create a venv below `$RUNNER_TEMP`, run `uv pip install --python <venv-python> "${{ github.action_path }}"`, and call `scripts/action-entrypoint.sh`. The entrypoint checks the event before testing head code, exports neither secret to logs, and invokes the venv's `attest ci` with base/event/budget/sample/timebox values.

The example workflow uses:

```yaml
permissions:
  contents: read
  pull-requests: write
concurrency:
  group: attest-${{ github.event.pull_request.number }}
  cancel-in-progress: true
```

It checks out with `fetch-depth: 0`, invokes the action, and uploads `.attest/ledger.jsonl` with `if: always()` and a PR/run-specific artifact name. Documentation states: fork PRs are skipped before secrets or head execution; Python socket blocking is best-effort rather than global network isolation; trusted head code can mutate its ephemeral runner; generated-test errors/timeouts defer rather than refute; and a later unprivileged-job plus `workflow_run` design is required for forks.

- [ ] **Step 1: Write failing entrypoint behavior tests**

Execute the real shell script with temporary fake `attest` and event files. Assert a fork event exits before the fake executable is invoked, a trusted event forwards exact non-secret arguments, missing required paths fail explicitly, and no supplied secret appears in stdout/stderr.

- [ ] **Step 2: Verify entrypoint RED, implement, and verify GREEN**

Run before and after:

```bash
.venv/bin/pytest tests/test_action_entrypoint.py -q
```

- [ ] **Step 3: Add action/workflow/docs and validate consumed behavior**

Add the configuration and documentation exactly as specified. Run the entrypoint tests and parse both YAML documents with Ruby's standard YAML parser:

```bash
ruby -e 'require "yaml"; YAML.load_file("action.yml", aliases: true); YAML.load_file("examples/pull-request.yml", aliases: true)'
```

Expected: exit code 0. Do not add source-text grep tests for human documentation.

- [ ] **Step 4: Commit**

```bash
git add action.yml examples/pull-request.yml docs/github-action.md scripts/action-entrypoint.sh tests/test_action_entrypoint.py README.md
git commit -m "feat: add composite pull request action"
```

---

### Task 7: Automate Phase 3 Scratch-Repository Acceptance

**Files:**
- Create: `scripts/acceptance/phase3.py`
- Create: `tests/test_phase3_acceptance.py`
- Create on success: `docs/acceptance/phase-3.md`
- Modify on live runs: `DEVSPEND.md`
- Modify: `DECISIONS.md`

**Interfaces:**
- Consumes: authenticated `gh`, the pushed Phase 3 ref, a model API key supplied without printing, GitHub run/job/comment/review/artifact APIs, and the action artifact from Task 6.
- Produces: a private retained scratch repository, two driven PRs, machine assertions for every acceptance criterion, an acceptance report with URLs/timings/spend, and decision D-017.

Use a library-first script with these public functions:

```python
@dataclass(frozen=True)
class AcceptanceResult:
    repository_url: str
    bug_pr_url: str
    control_pr_url: str
    bug_sticky_seconds: float
    control_sticky_seconds: float
    queue_seconds: dict[int, float]
    spend_usd: float

def preflight() -> None: ...
def run_acceptance(action_ref: str, *, keep_repo: bool = True) -> AcceptanceResult: ...
def render_report(result: AcceptanceResult) -> str: ...
```

`preflight` runs `gh auth status`, verifies repo/workflow scope, and checks model-key presence by boolean/length/prefix only. `run_acceptance` creates a uniquely named private repo under the authenticated owner, seeds a small Python package, installs a workflow that checks out `IcantFind-a-username/Attest` at `action_ref` into a subdirectory and uses it locally, pipes the model key into `gh secret set`, and creates PR 1 with a deterministic empty-input crash plus PR 2 with a clean refactor. It watches each workflow, obtains job `started_at`, issue comments, review comments, and ledger artifact through `gh api`/`gh run download`, and asserts: first sticky comment minus job start is at most 60 seconds; PR 1 has at least one verified inline finding; PR 2 has zero finding comments; every review/comment/verification event has ledger rows; and cumulative development spend remains below $10. Failed assertions retain the private repo and return a nonzero exit. Success writes the report and appends actual spend without duplicating an existing run id.

- [ ] **Step 1: Write failing preflight and parser tests**

Inject a subprocess runner and filesystem boundary. Cover missing `gh`, unauthenticated CLI, missing model key, private-repo command construction, timestamp math excluding queue time, comment classification, artifact ledger parsing, spend-cap rejection, idempotent spend insertion, and report URLs.

- [ ] **Step 2: Verify acceptance RED, implement dry-run logic, and verify GREEN**

Run before and after:

```bash
.venv/bin/pytest tests/test_phase3_acceptance.py -q
```

- [ ] **Step 3: Record the design decision**

Append D-017 describing the service/adapter/executor split, ternary verification semantics, best-effort Python network guard, artifact ledger persistence, and the conditions under which each choice can be reversed.

- [ ] **Step 4: Commit local acceptance automation**

```bash
git add scripts/acceptance/phase3.py tests/test_phase3_acceptance.py DECISIONS.md
git commit -m "test: automate phase three acceptance"
```

- [ ] **Step 5: Run the complete local phase gate**

Run in parallel where safe:

```bash
.venv/bin/pytest --cov=src/attest --cov-report=term-missing
.venv/bin/ruff check .
.venv/bin/mypy
```

Expected: all tests pass, total coverage is at least 90%, core is at least 99%, ruff is clean, and mypy is clean.

- [ ] **Step 6: Obtain required remote authority and credentials**

Before any push, scratch-repository creation, secret mutation, or paid live call, the controller checks the current owner instruction against AGENTS.md ground rule 8. If explicit authority or the model key is absent, stop with the exact missing condition and leave the fully tested local branch intact.

- [ ] **Step 7: Execute live acceptance and iterate**

After the stop conditions are satisfied, push the Phase 3 feature ref, run:

```bash
.venv/bin/python scripts/acceptance/phase3.py --action-ref feature/phase-3-action
```

On failure, write a failing regression test, observe RED, implement the minimal fix, observe GREEN, rerun the relevant local gate, and rerun acceptance. On success, commit `docs/acceptance/phase-3.md` and the exact `DEVSPEND.md` row with:

```bash
git add docs/acceptance/phase-3.md DEVSPEND.md
git commit -m "docs: record phase three acceptance"
```

---

## Plan Self-Review

- Spec coverage: coverage enforcement, thin root Action, self-install through setup-uv, permissions/concurrency, two-stage status and inline comments, Python executor, resource/time/network limits, fork safety, local mocked API, artifact ledger, live scratch matrix, timings, spend, acceptance report, decisions, and phase gate each map to a task above.
- Placeholder scan: the plan contains no deferred implementation markers; every code task names exact files, interfaces, RED command, GREEN command, and commit.
- Type consistency: `ReviewRun.task_id` feeds `StoredCandidate.task_id`; `ExecutionResult.outcome` controls whether `apply_verification` is called; surfaced `GateResult` values feed `inline_comments`; `CiRun` feeds the action log; `AcceptanceResult` feeds the report.
