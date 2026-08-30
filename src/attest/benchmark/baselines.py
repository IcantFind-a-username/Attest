"""Three-arm baseline comparison over identical blinded diff bytes and truth.

Arm A is the real product: the full propose/corroborate/verify/gate path,
driven through :func:`attest.benchmark.api.evaluate_project` (D-025). Arm B is
one direct schema-constrained call through the same configured provider --
no corroboration, no verification, no gate -- surfacing every valid returned
finding. Arm C is a local deterministic static analyzer
(``ruff check --output-format=json --select=F,E9``) keeping only diagnostics
anchored inside the diff. Arm C is **not an AI reviewer** and is never
described as one.

Fairness rules the module enforces rather than promises:

* every arm sees the same diff bytes, produced by the product's own
  ``git_diff`` over a worktree at the reviewed head;
* the same per-case USD ceiling applies -- the bare-prompt arm reserves
  against it before its one call is made, exactly as the product does;
* the matcher uses preregistered location truth only. It never pretends the
  bare-prompt or static arm purchased verification: every finding records its
  evidence class, and only the product arm can carry a verification class;
* a run an arm could not decide (tool unavailable, invalid response, budget
  refusal, crash) is a DEFER with a reason. It enters no accuracy numerator or
  denominator and is never turned into a negative label; and
* Wilson denominators come from repeat zero only.

Publication of accuracy-flavoured numbers is not decided here: the report
layer withholds them without a manifest-bound validation receipt (D-019,
D-032). Operational accounting -- calls, tokens, spend, wall time,
deterministic-tool cost -- claims no correctness and is always reported.
"""

from __future__ import annotations

import json
import subprocess
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager, suppress
from dataclasses import dataclass, replace
from pathlib import Path
from threading import Lock
from typing import Any

from attest.benchmark.api import ProjectEvaluationRequest, evaluate_project
from attest.benchmark.metrics import silence_precision, wilson_interval
from attest.benchmark.schema import BenchmarkCase, TruthDefect, is_scored_placement
from attest.review.budget import Budget, BudgetExceeded
from attest.review.config import ReviewConfig
from attest.review.diffs import DiffInfo, git_diff, norm_path
from attest.review.proposer import (
    PROPOSER_MAX_OUTPUT_TOKENS,
    SYSTEM_PROMPT,
    Provider,
    ProviderResult,
    build_prompt,
)
from attest.review.schema import PROPOSAL_SCHEMA, validate_finding

ARM_PRODUCT = "attest_product"
ARM_BARE_PROMPT = "bare_prompt"
ARM_RUFF = "ruff_static"

ARM_DESCRIPTIONS: Mapping[str, str] = {
    ARM_PRODUCT: (
        "the full product path: schema-constrained proposals, static "
        "corroboration, differential verification, and the betting gate"
    ),
    ARM_BARE_PROMPT: (
        "one direct schema-constrained model call over the same diff bytes; no "
        "corroboration, no verification, no gate; every valid returned finding "
        "is surfaced"
    ),
    ARM_RUFF: (
        "local deterministic static analyzer (ruff check --output-format=json "
        "--select=F,E9) keeping only diff-anchored diagnostics; not an AI reviewer"
    ),
}

EVIDENCE_UNVERIFIED_CLAIM = "unverified_model_claim"
EVIDENCE_STATIC_DIAGNOSTIC = "static_diagnostic"

_GIT_TIMEOUT_S = 60.0
_ROLE_POSITIVE = "historical_bug_replay"
_ROLE_CONTROL = "developer_fix_control"


@dataclass(frozen=True)
class BaselineFinding:
    """One surfaced anchor and the class of evidence actually purchased."""

    file: str
    line: int
    evidence_class: str


@dataclass(frozen=True)
class ArmRun:
    """One case evaluated under one arm, with full fairness accounting."""

    arm: str
    case_id: str
    role: str
    status: str
    abstain_reason: str | None
    findings: tuple[BaselineFinding, ...]
    matched_defect_ids: tuple[str | None, ...]
    model_calls: int
    input_tokens: int
    output_tokens: int
    spend_usd: float
    oracle_spend_usd: float
    wall_time_s: float
    tool_cost_s: float | None


@dataclass(frozen=True)
class ArmAbstention:
    """One case an arm could not decide, kept with its reason."""

    case_id: str
    reason: str

    def to_json_dict(self) -> dict[str, object]:
        return {"case_id": self.case_id, "reason": self.reason}


@dataclass(frozen=True)
class ArmAccuracy:
    """Accuracy-flavoured measurements; publication requires a receipt."""

    finding_true_positives: int
    finding_false_positives: int
    finding_precision: float | None
    finding_precision_interval: tuple[float, float] | None
    detected_positive_cases: int
    decided_positive_cases: int
    detection_rate: float | None
    detection_rate_interval: tuple[float, float] | None
    flagged_control_cases: int
    decided_control_cases: int
    clean_false_positive_rate: float | None
    clean_false_positive_rate_interval: tuple[float, float] | None
    silent_control_cases: int
    silent_positive_cases: int
    silence_precision: float | None
    silence_precision_interval: tuple[float, float] | None

    def to_json_dict(self) -> dict[str, object]:
        return {
            "finding_true_positives": self.finding_true_positives,
            "finding_false_positives": self.finding_false_positives,
            "finding_precision": _number(self.finding_precision),
            "finding_precision_interval": _interval(self.finding_precision_interval),
            "detected_positive_cases": self.detected_positive_cases,
            "decided_positive_cases": self.decided_positive_cases,
            "detection_rate": _number(self.detection_rate),
            "detection_rate_interval": _interval(self.detection_rate_interval),
            "flagged_control_cases": self.flagged_control_cases,
            "decided_control_cases": self.decided_control_cases,
            "clean_false_positive_rate": _number(self.clean_false_positive_rate),
            "clean_false_positive_rate_interval": _interval(
                self.clean_false_positive_rate_interval
            ),
            "silent_control_cases": self.silent_control_cases,
            "silent_positive_cases": self.silent_positive_cases,
            "silence_precision": _number(self.silence_precision),
            "silence_precision_interval": _interval(self.silence_precision_interval),
        }


@dataclass(frozen=True)
class ArmOperational:
    """Counts, spend, and timings; these claim no correctness."""

    evaluated_cases: int
    deferred_cases: int
    surfaced_findings: int
    silent_cases: int
    silence_rate: float | None
    model_calls: int
    input_tokens: int
    output_tokens: int
    spend_usd: float
    oracle_spend_usd: float
    wall_time_s: float
    tool_cost_s: float | None

    def to_json_dict(self) -> dict[str, object]:
        return {
            "evaluated_cases": self.evaluated_cases,
            "deferred_cases": self.deferred_cases,
            "surfaced_findings": self.surfaced_findings,
            "silent_cases": self.silent_cases,
            "silence_rate": _number(self.silence_rate),
            "model_calls": self.model_calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "spend_usd": _number(self.spend_usd),
            "oracle_spend_usd": _number(self.oracle_spend_usd),
            "wall_time_s": _number(self.wall_time_s),
            "tool_cost_s": _number(self.tool_cost_s),
        }


@dataclass(frozen=True)
class ArmSummary:
    """One arm's aggregated outcome over the shared case set."""

    arm: str
    description: str
    accuracy: ArmAccuracy
    operational: ArmOperational
    abstentions: tuple[ArmAbstention, ...]
    evidence_class_counts: Mapping[str, int]


@dataclass(frozen=True)
class ComparisonPlan:
    """One case and the repeat-zero product request every arm shares."""

    case: BenchmarkCase
    request: ProjectEvaluationRequest


@dataclass(frozen=True)
class ComparisonMeasurements:
    """Everything the three arms measured, before any publication gating."""

    line_slack: int
    budget_ceiling_usd: float
    arms: tuple[ArmSummary, ...]
    runs: tuple[ArmRun, ...]
    evaluated_case_ids: tuple[str, ...]


class _MeteredProvider:
    """Counts calls and tokens through any provider without altering them."""

    def __init__(self, inner: Provider) -> None:
        self._inner = inner
        self._lock = Lock()
        self.calls = 0
        self.input_tokens = 0
        self.output_tokens = 0

    def sample(
        self,
        system: str,
        prompt: str,
        schema: dict[str, Any],
        max_tokens: int,
        *,
        timeout_s: float | None = None,
    ) -> ProviderResult:
        result = self._inner.sample(
            system, prompt, schema, max_tokens, timeout_s=timeout_s
        )
        with self._lock:
            self.calls += 1
            self.input_tokens += result.input_tokens
            self.output_tokens += result.output_tokens
        return result


class BarePromptBaseline:
    """Arm B: one direct call with ``PROPOSAL_SCHEMA``; no S/T/V, no gate."""

    def __init__(
        self, provider: Provider, *, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self._provider = provider
        self._clock = clock

    def evaluate(
        self,
        *,
        case_id: str,
        role: str,
        diff: DiffInfo,
        config: ReviewConfig,
    ) -> ArmRun:
        started = self._clock()
        budget = Budget(limit_usd=config.budget_usd, model=config.model)
        prompt = build_prompt(diff)
        try:
            reservation = budget.reserve(
                "bare-prompt",
                len(SYSTEM_PROMPT) + len(prompt),
                PROPOSER_MAX_OUTPUT_TOKENS,
            )
        except BudgetExceeded as exc:
            return self._deferred(
                case_id, role, f"budget: {exc.reason}", started, calls=0
            )
        try:
            result = self._provider.sample(
                SYSTEM_PROMPT, prompt, PROPOSAL_SCHEMA, PROPOSER_MAX_OUTPUT_TOKENS
            )
        except Exception as exc:  # noqa: BLE001 - a provider failure is a DEFER
            budget.cancel(reservation)
            return self._deferred(
                case_id,
                role,
                f"provider_error: {type(exc).__name__}",
                started,
                calls=0,
            )
        budget.settle(
            "bare-prompt", reservation, result.input_tokens, result.output_tokens
        )
        raw_findings = _parse_findings(result.text)
        if raw_findings is None:
            return self._deferred(
                case_id,
                role,
                "invalid_model_response",
                started,
                calls=1,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                spend_usd=budget.spent_usd,
            )
        findings: list[BaselineFinding] = []
        for raw in raw_findings:
            if not isinstance(raw, dict):
                continue
            finding, _ = validate_finding(raw, diff)
            if finding is not None:
                findings.append(
                    BaselineFinding(
                        file=finding.file,
                        line=finding.line,
                        evidence_class=EVIDENCE_UNVERIFIED_CLAIM,
                    )
                )
        return ArmRun(
            arm=ARM_BARE_PROMPT,
            case_id=case_id,
            role=role,
            status="completed",
            abstain_reason=None,
            findings=tuple(findings),
            matched_defect_ids=(None,) * len(findings),
            model_calls=1,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            spend_usd=budget.spent_usd,
            oracle_spend_usd=0.0,
            wall_time_s=self._clock() - started,
            tool_cost_s=0.0,
        )

    def _deferred(
        self,
        case_id: str,
        role: str,
        reason: str,
        started: float,
        *,
        calls: int,
        input_tokens: int = 0,
        output_tokens: int = 0,
        spend_usd: float = 0.0,
    ) -> ArmRun:
        return ArmRun(
            arm=ARM_BARE_PROMPT,
            case_id=case_id,
            role=role,
            status="deferred",
            abstain_reason=reason,
            findings=(),
            matched_defect_ids=(),
            model_calls=calls,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            spend_usd=spend_usd,
            oracle_spend_usd=0.0,
            wall_time_s=self._clock() - started,
            tool_cost_s=0.0,
        )


class RuffBaseline:
    """Arm C: the preregistered local static command over diff-anchored lines.

    This arm is a deterministic tool, never an AI reviewer. Missing tool
    support -- no executable, no Python file in the diff, a crash -- defers the
    case; it is never read as the tool judging the code clean.
    """

    def __init__(
        self,
        executable: str | None,
        *,
        timeout_s: float = 120.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._executable = executable
        self._timeout_s = timeout_s
        self._clock = clock

    def evaluate(
        self,
        *,
        case_id: str,
        role: str,
        diff: DiffInfo,
        worktree: Path,
    ) -> ArmRun:
        started = self._clock()
        if self._executable is None or not Path(self._executable).is_file():
            return self._deferred(case_id, role, "static_tool_unavailable", started)
        py_files = [
            path
            for path in diff.files
            if path.endswith(".py") and (worktree / path).is_file()
        ]
        if not py_files:
            return self._deferred(case_id, role, "diff_contains_no_python_files", started)
        try:
            completed = subprocess.run(
                [
                    self._executable,
                    "check",
                    "--output-format=json",
                    "--select=F,E9",
                    *py_files,
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=worktree,
                timeout=self._timeout_s,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return self._deferred(case_id, role, "static_tool_failed", started)
        if completed.returncode not in (0, 1):
            return self._deferred(case_id, role, "static_tool_failed", started)
        try:
            diagnostics = json.loads(completed.stdout or "[]")
        except json.JSONDecodeError:
            return self._deferred(case_id, role, "static_tool_output_unreadable", started)
        if not isinstance(diagnostics, list):
            return self._deferred(case_id, role, "static_tool_output_unreadable", started)
        findings: list[BaselineFinding] = []
        for diagnostic in diagnostics:
            anchor = _diagnostic_anchor(diagnostic, worktree, diff)
            if anchor is not None:
                findings.append(
                    BaselineFinding(
                        file=anchor[0],
                        line=anchor[1],
                        evidence_class=EVIDENCE_STATIC_DIAGNOSTIC,
                    )
                )
        elapsed = self._clock() - started
        return ArmRun(
            arm=ARM_RUFF,
            case_id=case_id,
            role=role,
            status="completed",
            abstain_reason=None,
            findings=tuple(findings),
            matched_defect_ids=(None,) * len(findings),
            model_calls=0,
            input_tokens=0,
            output_tokens=0,
            spend_usd=0.0,
            oracle_spend_usd=0.0,
            wall_time_s=elapsed,
            tool_cost_s=elapsed,
        )

    def _deferred(self, case_id: str, role: str, reason: str, started: float) -> ArmRun:
        return ArmRun(
            arm=ARM_RUFF,
            case_id=case_id,
            role=role,
            status="deferred",
            abstain_reason=reason,
            findings=(),
            matched_defect_ids=(),
            model_calls=0,
            input_tokens=0,
            output_tokens=0,
            spend_usd=0.0,
            oracle_spend_usd=0.0,
            wall_time_s=self._clock() - started,
            tool_cost_s=None,
        )


def compare_arms(
    plans: Sequence[ComparisonPlan],
    *,
    provider_factory: Callable[[ProjectEvaluationRequest], Provider],
    bare_provider_factory: Callable[[str], Provider],
    ruff_executable: str | None,
    line_slack: int = 0,
    clock: Callable[[], float] = time.monotonic,
) -> ComparisonMeasurements:
    """Run all three arms over every planned case and aggregate per arm.

    One case's failure under one arm becomes that run's DEFER; it never aborts
    the comparison and never hides the runs that completed.
    """
    if line_slack < 0:
        raise ValueError("line_slack must not be negative")
    for plan in plans:
        if plan.request.repeat != 0:
            raise ValueError(
                "comparison accuracy uses repeat zero only; every planned request "
                "must carry repeat 0"
            )
        if plan.case.case_id != plan.request.case_id:
            raise ValueError("plan case and request must name the same case")
    ceilings = {plan.request.config.budget_usd for plan in plans}
    if len(ceilings) > 1:
        raise ValueError(
            "the primary comparison requires one identical per-case USD ceiling"
        )
    runs: list[ArmRun] = []
    for plan in plans:
        defects = () if plan.request.truth is None else plan.request.truth.defects
        product_run = _product_arm(plan, provider_factory, clock)
        runs.append(_with_matches(product_run, defects, line_slack))
        bare_run, ruff_run = _baseline_arms(
            plan, bare_provider_factory, ruff_executable, clock
        )
        runs.append(_with_matches(bare_run, defects, line_slack))
        runs.append(_with_matches(ruff_run, defects, line_slack))

    arms = tuple(
        _summarize_arm(arm, tuple(run for run in runs if run.arm == arm))
        for arm in (ARM_PRODUCT, ARM_BARE_PROMPT, ARM_RUFF)
    )
    evaluated = tuple(
        sorted({run.case_id for run in runs if run.status == "completed"})
    )
    return ComparisonMeasurements(
        line_slack=line_slack,
        budget_ceiling_usd=next(iter(ceilings)) if ceilings else 0.0,
        arms=arms,
        runs=tuple(runs),
        evaluated_case_ids=evaluated,
    )


def _product_arm(
    plan: ComparisonPlan,
    provider_factory: Callable[[ProjectEvaluationRequest], Provider],
    clock: Callable[[], float],
) -> ArmRun:
    request = plan.request
    meter = _MeteredProvider(provider_factory(request))
    started = clock()
    try:
        result = evaluate_project(request, provider=meter, clock=clock)
    except Exception as exc:  # noqa: BLE001 - a failed product run is a DEFER
        return ArmRun(
            arm=ARM_PRODUCT,
            case_id=request.case_id,
            role=plan.case.role,
            status="deferred",
            abstain_reason=f"{type(exc).__name__}: {exc}",
            findings=(),
            matched_defect_ids=(),
            model_calls=meter.calls,
            input_tokens=meter.input_tokens,
            output_tokens=meter.output_tokens,
            spend_usd=0.0,
            oracle_spend_usd=0.0,
            wall_time_s=clock() - started,
            tool_cost_s=None,
        )
    deferred = result.abstain_reason is not None
    findings = (
        ()
        if deferred
        else tuple(
            BaselineFinding(
                file=prediction.file,
                line=prediction.line,
                evidence_class=prediction.evidence_class,
            )
            for prediction in result.predictions
            if is_scored_placement(prediction.placement)
        )
    )
    return ArmRun(
        arm=ARM_PRODUCT,
        case_id=request.case_id,
        role=plan.case.role,
        status="deferred" if deferred else "completed",
        abstain_reason=result.abstain_reason,
        findings=findings,
        matched_defect_ids=(None,) * len(findings),
        model_calls=meter.calls,
        input_tokens=meter.input_tokens,
        output_tokens=meter.output_tokens,
        spend_usd=result.spend_usd,
        oracle_spend_usd=result.oracle_spend_usd,
        wall_time_s=result.latency_s,
        tool_cost_s=None,
    )


def _baseline_arms(
    plan: ComparisonPlan,
    bare_provider_factory: Callable[[str], Provider],
    ruff_executable: str | None,
    clock: Callable[[], float],
) -> tuple[ArmRun, ArmRun]:
    request = plan.request
    role = plan.case.role
    try:
        with _materialized_diff(request) as (worktree, diff):
            bare = BarePromptBaseline(
                bare_provider_factory(request.case_id), clock=clock
            ).evaluate(
                case_id=request.case_id,
                role=role,
                diff=diff,
                config=request.config,
            )
            ruff = RuffBaseline(ruff_executable, clock=clock).evaluate(
                case_id=request.case_id,
                role=role,
                diff=diff,
                worktree=worktree,
            )
        return bare, ruff
    except Exception as exc:  # noqa: BLE001 - an unpreparable case is a DEFER
        reason = f"diff_unavailable: {type(exc).__name__}"
        return (
            _shared_defer(ARM_BARE_PROMPT, request.case_id, role, reason),
            _shared_defer(ARM_RUFF, request.case_id, role, reason),
        )


def _shared_defer(arm: str, case_id: str, role: str, reason: str) -> ArmRun:
    return ArmRun(
        arm=arm,
        case_id=case_id,
        role=role,
        status="deferred",
        abstain_reason=reason,
        findings=(),
        matched_defect_ids=(),
        model_calls=0,
        input_tokens=0,
        output_tokens=0,
        spend_usd=0.0,
        oracle_spend_usd=0.0,
        wall_time_s=0.0,
        tool_cost_s=None,
    )


@contextmanager
def _materialized_diff(
    request: ProjectEvaluationRequest,
) -> Iterator[tuple[Path, DiffInfo]]:
    """The identical diff bytes the product sees: its own ``git_diff`` over a
    worktree at the reviewed head against the resolved base."""
    base_sha = _resolve_commit(request.repo, request.base_ref)
    destination = request.workspace_root / f"{request.case_id}-baseline-arms"
    if destination.exists():
        raise ValueError(f"baseline worktree {destination} already exists")
    destination.parent.mkdir(parents=True, exist_ok=True)
    added = subprocess.run(
        [
            "git",
            "-C",
            str(request.repo),
            "worktree",
            "add",
            "--detach",
            str(destination),
            request.head_ref,
        ],
        capture_output=True,
        text=True,
        timeout=_GIT_TIMEOUT_S,
        check=False,
    )
    if added.returncode != 0:
        raise ValueError("could not materialize a baseline worktree at head")
    try:
        yield destination, git_diff(destination, base_sha)
    finally:
        with suppress(OSError, subprocess.SubprocessError):
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(request.repo),
                    "worktree",
                    "remove",
                    "--force",
                    str(destination),
                ],
                capture_output=True,
                timeout=_GIT_TIMEOUT_S,
                check=False,
            )
            subprocess.run(
                ["git", "-C", str(request.repo), "worktree", "prune"],
                capture_output=True,
                timeout=_GIT_TIMEOUT_S,
                check=False,
            )


def _resolve_commit(repo: Path, ref: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"],
        capture_output=True,
        text=True,
        timeout=_GIT_TIMEOUT_S,
        check=False,
    )
    resolved = completed.stdout.strip()
    if completed.returncode != 0 or not resolved:
        raise ValueError(f"{ref} does not resolve to an immutable commit")
    return resolved


def _parse_findings(text: str) -> list[object] | None:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    findings = payload.get("findings")
    if not isinstance(findings, list):
        return None
    return findings


def _diagnostic_anchor(
    diagnostic: object, worktree: Path, diff: DiffInfo
) -> tuple[str, int] | None:
    if not isinstance(diagnostic, dict):
        return None
    filename = diagnostic.get("filename")
    location = diagnostic.get("location")
    if not isinstance(filename, str) or not isinstance(location, dict):
        return None
    row = location.get("row")
    if not isinstance(row, int) or isinstance(row, bool) or row < 1:
        return None
    path = Path(filename)
    if path.is_absolute():
        try:
            path = path.resolve().relative_to(worktree.resolve())
        except (OSError, ValueError):
            return None
    relative = norm_path(path.as_posix())
    canonical = diff.canonical_anchor(relative, row)
    if canonical is None:
        return None
    return canonical, row


def _with_matches(
    run: ArmRun, defects: tuple[TruthDefect, ...], line_slack: int
) -> ArmRun:
    if run.status != "completed" or not run.findings:
        return run
    matched = _match_locations(defects, run.findings, line_slack)
    return replace(run, matched_defect_ids=matched)


def _match_locations(
    defects: tuple[TruthDefect, ...],
    findings: tuple[BaselineFinding, ...],
    line_slack: int,
) -> tuple[str | None, ...]:
    """Deterministic one-to-one location matching against preregistered truth.

    Maximum matches first, then minimum total anchor distance, then a stable
    lexicographic tie-break. No repro status is consulted: this matcher must
    treat an unverified claim and a verified one identically, because two of
    the arms cannot purchase verification at all.
    """
    edges: list[list[tuple[int, int]]] = []
    for finding in findings:
        candidates: list[tuple[int, int]] = []
        for index, defect in enumerate(defects):
            if norm_path(finding.file) != norm_path(defect.file):
                continue
            distance = _distance(finding.line, defect.start_line, defect.end_line)
            if distance <= line_slack:
                candidates.append((index, distance))
        edges.append(candidates)

    best: dict[int, int] = {}
    best_key: tuple[object, ...] | None = None

    def consider(candidate: dict[int, int]) -> None:
        nonlocal best, best_key
        detail = tuple(
            sorted(
                (
                    _distance(
                        findings[finding_index].line,
                        defects[defect_index].start_line,
                        defects[defect_index].end_line,
                    ),
                    defects[defect_index].defect_id,
                    finding_index,
                )
                for finding_index, defect_index in candidate.items()
            )
        )
        key: tuple[object, ...] = (
            -len(candidate),
            sum(distance for distance, _, _ in detail),
            detail,
        )
        if best_key is None or key < best_key:
            best = dict(candidate)
            best_key = key

    def search(index: int, taken: set[int], candidate: dict[int, int]) -> None:
        if index == len(findings):
            consider(candidate)
            return
        search(index + 1, taken, candidate)
        for defect_index, _ in edges[index]:
            if defect_index in taken:
                continue
            taken.add(defect_index)
            candidate[index] = defect_index
            search(index + 1, taken, candidate)
            del candidate[index]
            taken.remove(defect_index)

    search(0, set(), {})
    return tuple(
        defects[best[index]].defect_id if index in best else None
        for index in range(len(findings))
    )


def _distance(line: int, start_line: int, end_line: int) -> int:
    if start_line <= line <= end_line:
        return 0
    return min(abs(line - start_line), abs(line - end_line))


def _summarize_arm(arm: str, runs: tuple[ArmRun, ...]) -> ArmSummary:
    completed = tuple(run for run in runs if run.status == "completed")
    deferred = tuple(run for run in runs if run.status != "completed")
    finding_true_positives = sum(
        1 for run in completed for match in run.matched_defect_ids if match is not None
    )
    finding_total = sum(len(run.findings) for run in completed)
    finding_false_positives = finding_total - finding_true_positives

    positives = tuple(run for run in completed if run.role == _ROLE_POSITIVE)
    controls = tuple(run for run in completed if run.role == _ROLE_CONTROL)
    detected = sum(
        1
        for run in positives
        if any(match is not None for match in run.matched_defect_ids)
    )
    flagged = sum(1 for run in controls if run.findings)
    silent_controls = sum(1 for run in controls if not run.findings)
    silent_positives = sum(1 for run in positives if not run.findings)
    silent_cases = sum(1 for run in completed if not run.findings)

    counts: dict[str, int] = {}
    for run in completed:
        for finding in run.findings:
            counts[finding.evidence_class] = counts.get(finding.evidence_class, 0) + 1

    tool_costs = [run.tool_cost_s for run in runs if run.tool_cost_s is not None]
    accuracy = ArmAccuracy(
        finding_true_positives=finding_true_positives,
        finding_false_positives=finding_false_positives,
        finding_precision=_ratio(finding_true_positives, finding_total),
        finding_precision_interval=wilson_interval(finding_true_positives, finding_total),
        detected_positive_cases=detected,
        decided_positive_cases=len(positives),
        detection_rate=_ratio(detected, len(positives)),
        detection_rate_interval=wilson_interval(detected, len(positives)),
        flagged_control_cases=flagged,
        decided_control_cases=len(controls),
        clean_false_positive_rate=_ratio(flagged, len(controls)),
        clean_false_positive_rate_interval=wilson_interval(flagged, len(controls)),
        silent_control_cases=silent_controls,
        silent_positive_cases=silent_positives,
        silence_precision=silence_precision(silent_controls, silent_positives),
        silence_precision_interval=wilson_interval(
            silent_controls, silent_controls + silent_positives
        ),
    )
    operational = ArmOperational(
        evaluated_cases=len(completed),
        deferred_cases=len(deferred),
        surfaced_findings=finding_total,
        silent_cases=silent_cases,
        silence_rate=_ratio(silent_cases, len(completed)),
        model_calls=sum(run.model_calls for run in runs),
        input_tokens=sum(run.input_tokens for run in runs),
        output_tokens=sum(run.output_tokens for run in runs),
        spend_usd=sum(run.spend_usd for run in runs),
        oracle_spend_usd=sum(run.oracle_spend_usd for run in runs),
        wall_time_s=sum(run.wall_time_s for run in runs),
        tool_cost_s=sum(tool_costs) if tool_costs else None,
    )
    return ArmSummary(
        arm=arm,
        description=ARM_DESCRIPTIONS[arm],
        accuracy=accuracy,
        operational=operational,
        abstentions=tuple(
            ArmAbstention(run.case_id, run.abstain_reason or "unspecified")
            for run in deferred
        ),
        evidence_class_counts=dict(sorted(counts.items())),
    )


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _number(value: float | None) -> float | None:
    return None if value is None else round(float(value), 6)


def _interval(value: tuple[float, float] | None) -> list[float] | None:
    return None if value is None else [round(value[0], 6), round(value[1], 6)]
