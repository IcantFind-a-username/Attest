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
* task state is separate from finding outcomes: defer/failure never erases an
  already-published precision or harm outcome, positive misses remain misses,
  and silent non-completed controls are not inferred to be true negatives; and
* Wilson denominators come from repeat zero only.

Publication of accuracy-flavoured numbers is not decided here: the report
layer withholds them without a manifest-bound validation receipt (D-019,
D-032). Operational accounting -- calls, tokens, spend, wall time,
deterministic-tool cost -- claims no correctness and is always reported.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import stat
import subprocess
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager, suppress
from dataclasses import dataclass, replace
from pathlib import Path
from threading import Lock
from typing import Any

from attest.benchmark.api import (
    ABSENT_BINDING_SHA256,
    EVALUATION_BINDING_SCHEMA_VERSION,
    ProjectEvaluationAuthorityError,
    ProjectEvaluationRequest,
    ProjectTruth,
    build_evaluation_binding,
    current_runtime_identity,
    evaluate_project,
    freeze_evaluation_request,
    manifest_project_truth,
    project_truth_sha256,
    require_manifest_evaluation_request,
)
from attest.benchmark.checkpoints import (
    CALL_ROLE_BENCHMARK_ORACLE,
    CALL_ROLE_PRODUCT,
    CALL_ROLES,
    AmbiguousCostError,
    CheckpointedProvider,
    PaidCallTotals,
    paid_call_totals,
)
from attest.benchmark.corpus import (
    ValidationReceipt,
    ValidationReceiptV2,
    ValidationVerification,
    validation_receipt_binding_bytes,
)
from attest.benchmark.measurement import (
    ARM_ATTEST_PRODUCT,
    AccuracyStatus,
    FindingAuthority,
    MeasurementRecord,
    TaskStatus,
    TruthStatus,
    measurement_summary_payload,
    reduce_measurements,
)
from attest.benchmark.metrics import silence_precision, wilson_interval
from attest.benchmark.outcomes import (
    COMPARISON_FINAL_RECEIPT_PATH,
    COMPARISON_LAUNCH_RECEIPT_PATH,
    COMPARISON_OUTCOME_PROTOCOL,
    CanonicalDocument,
    ComparisonArmOutcome,
    ComparisonOutcomeAuthority,
    ComparisonOutcomeSlot,
    ComparisonPublicationAuthority,
    ComparisonSurfacedFinding,
    VerifiedComparisonOutcomes,
    create_comparison_publication_authority,
    finalize_comparison_outcomes,
    issue_comparison_launch_receipt,
    list_authoritative_directory,
    predeclare_comparison_outcomes,
    read_authoritative_bytes,
    read_canonical_json,
    read_comparison_arm_outcome_if_present,
    read_comparison_final_receipt,
    read_comparison_launch_receipt,
    verify_comparison_outcomes,
    write_canonical_json_once,
    write_comparison_arm_outcome_once,
    write_comparison_final_receipt_once,
    write_comparison_launch_receipt_once,
)
from attest.benchmark.schema import (
    BenchmarkCase,
    BenchmarkManifest,
    TruthDefect,
    is_scored_placement,
    require_manifest_binding,
)
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

ARM_PRODUCT = ARM_ATTEST_PRODUCT
ARM_BARE_PROMPT = "bare_prompt"
ARM_RUFF = "ruff_static"
COMPARISON_CHECKPOINT_SCHEMA_VERSION = "7"
COMPARISON_RECONCILIATION_SCHEMA_VERSION = "2"
_EMPTY_PAID_CALLS_SHA256 = hashlib.sha256(b"[]").hexdigest()
_EVALUATION_BINDING_FIELDS = frozenset(
    {
        "schema_version",
        "repository",
        "base_sha",
        "head_sha",
        "fixed_sha",
        "diff_sha256",
        "truth_sha256",
        "receipt_sha256",
        "policy_sha256",
        "provider_id",
        "model_id",
        "prompt_sha256",
        "schema_sha256",
        "interpreter_id",
        "environment_sha256",
        "code_sha256",
        "budget_usd",
    }
)
_EVALUATION_DIGEST_FIELDS = (
    "diff_sha256",
    "truth_sha256",
    "receipt_sha256",
    "policy_sha256",
    "prompt_sha256",
    "schema_sha256",
    "environment_sha256",
    "code_sha256",
)

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
    finding_id: str = ""


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
    paid_calls: tuple[Mapping[str, object], ...] = ()
    paid_calls_sha256: str = _EMPTY_PAID_CALLS_SHA256
    model_id: str | None = None
    product_measurement: MeasurementRecord | None = None


class ComparisonEvidenceError(ValueError):
    """Persisted comparison call evidence is incomplete or contradictory."""


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
            "total_spend_usd": _number(self.spend_usd + self.oracle_spend_usd),
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
    scoring_semantics: str = "legacy_v1_scoring"
    outcome_accounting: Mapping[str, object] | None = None


@dataclass(frozen=True)
class ComparisonPlan:
    """One case and the repeat-zero product request every arm shares."""

    manifest: BenchmarkManifest
    manifest_sha256: str
    case: BenchmarkCase
    request: ProjectEvaluationRequest


@dataclass(frozen=True)
class ComparisonMeasurements:
    """Everything the three arms measured, before any publication gating."""

    line_slack: int
    budget_ceiling_usd: float
    manifest_sha256: str
    arms: tuple[ArmSummary, ...]
    runs: tuple[ArmRun, ...]
    evaluated_case_ids: tuple[str, ...]
    checkpoint_root: Path | None = None
    outcome_predeclaration_sha256: str | None = None
    outcome_authority_id: str | None = None


@dataclass(frozen=True)
class ComparisonExecution:
    """One measurement payload plus its separate owner publication capability."""

    measurements: ComparisonMeasurements
    publication_authority: ComparisonPublicationAuthority | None

    def __post_init__(self) -> None:
        if type(self.measurements) is not ComparisonMeasurements:
            raise ValueError(
                "comparison execution requires exact ComparisonMeasurements"
            )
        if self.publication_authority is not None and type(
            self.publication_authority
        ) is not ComparisonPublicationAuthority:
            raise ValueError(
                "comparison execution publication authority must be exact or null"
            )

    @property
    def line_slack(self) -> int:
        return self.measurements.line_slack

    @property
    def budget_ceiling_usd(self) -> float:
        return self.measurements.budget_ceiling_usd

    @property
    def manifest_sha256(self) -> str:
        return self.measurements.manifest_sha256

    @property
    def arms(self) -> tuple[ArmSummary, ...]:
        return self.measurements.arms

    @property
    def runs(self) -> tuple[ArmRun, ...]:
        return self.measurements.runs

    @property
    def evaluated_case_ids(self) -> tuple[str, ...]:
        return self.measurements.evaluated_case_ids

    @property
    def checkpoint_root(self) -> Path | None:
        return self.measurements.checkpoint_root


class _MeteredProvider:
    """Counts calls and tokens through any provider without altering them."""

    def __init__(
        self, inner: Provider, *, shared: _MeteredProvider | None = None
    ) -> None:
        self._inner = inner
        self._lock: Lock
        self._counts: list[int]
        if shared is None:
            self._lock = Lock()
            self._counts = [0, 0, 0]
        else:
            self._lock = shared._lock
            self._counts = shared._counts

    @property
    def calls(self) -> int:
        return self._counts[0]

    @property
    def input_tokens(self) -> int:
        return self._counts[1]

    @property
    def output_tokens(self) -> int:
        return self._counts[2]

    def for_role(self, role: str) -> _MeteredProvider:
        scoped = getattr(self._inner, "for_role", None)
        if not callable(scoped):
            raise ComparisonEvidenceError("paid provider cannot create a role scope")
        return _MeteredProvider(scoped(role), shared=self)

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
            self._counts[0] += 1
            self._counts[1] += result.input_tokens
            self._counts[2] += result.output_tokens
        return result


class _LateBoundComparisonProvider:
    """A provider delegate bound only after the durable fresh trial exists."""

    def __init__(self) -> None:
        self._delegate: Provider | None = None

    def bind(self, delegate: Provider) -> None:
        if self._delegate is not None:
            raise ComparisonEvidenceError(
                "comparison paid provider delegate was already bound"
            )
        self._delegate = delegate

    def sample(
        self,
        system: str,
        prompt: str,
        schema: dict[str, Any],
        max_tokens: int,
        *,
        timeout_s: float | None = None,
    ) -> ProviderResult:
        if self._delegate is None:
            raise ComparisonEvidenceError(
                "comparison paid provider delegate is not bound"
            )
        return self._delegate.sample(
            system, prompt, schema, max_tokens, timeout_s=timeout_s
        )


_DirectoryIdentity = tuple[int, int, int]


def _directory_identity(descriptor: int) -> _DirectoryIdentity:
    opened = os.fstat(descriptor)
    if not stat.S_ISDIR(opened.st_mode):
        raise OSError("paid checkpoint component is not a directory")
    return opened.st_dev, opened.st_ino, opened.st_mode


def _open_absolute_directory(path: Path) -> int:
    """Open *path* one component at a time without following symlinks."""
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW
    absolute = Path(os.path.abspath(path))
    descriptor = os.open(absolute.anchor, flags)
    try:
        for component in absolute.parts[1:]:
            child = os.open(component, flags, dir_fd=descriptor)
            previous, descriptor = descriptor, child
            os.close(previous)
    except BaseException:
        with suppress(OSError):
            os.close(descriptor)
        raise
    return descriptor


def _open_paid_checkpoint_directory_chain(
    checkpoint_root: Path, *, arm: str, case_id: str
) -> tuple[tuple[int, ...], tuple[_DirectoryIdentity, ...]]:
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW
    descriptors: list[int] = []
    try:
        descriptors.append(_open_absolute_directory(checkpoint_root))
        for component in (arm, case_id):
            descriptors.append(os.open(component, flags, dir_fd=descriptors[-1]))
        case_descriptor = descriptors[-1]
        for component in ("calls", "artifacts"):
            descriptors.append(os.open(component, flags, dir_fd=case_descriptor))
        identities = tuple(_directory_identity(item) for item in descriptors)
    except BaseException:
        for descriptor in reversed(descriptors):
            with suppress(OSError):
                os.close(descriptor)
        raise
    return tuple(descriptors), identities


class _PaidCheckpointDirectoryLease:
    """Hold and later re-resolve the exact paid checkpoint directory chain."""

    def __init__(self, checkpoint_root: Path, *, arm: str, case_id: str) -> None:
        self._checkpoint_root = checkpoint_root
        self._arm = arm
        self._case_id = case_id
        self._descriptors, self._identities = _open_paid_checkpoint_directory_chain(
            checkpoint_root, arm=arm, case_id=case_id
        )

    def is_unchanged(self) -> bool:
        reopened: tuple[int, ...] = ()
        try:
            held_identities = tuple(
                _directory_identity(item) for item in self._descriptors
            )
            reopened, path_identities = _open_paid_checkpoint_directory_chain(
                self._checkpoint_root,
                arm=self._arm,
                case_id=self._case_id,
            )
            return held_identities == self._identities == path_identities
        except OSError:
            return False
        finally:
            for descriptor in reversed(reopened):
                with suppress(OSError):
                    os.close(descriptor)

    def close(self) -> None:
        descriptors, self._descriptors = self._descriptors, ()
        for descriptor in reversed(descriptors):
            with suppress(OSError):
                os.close(descriptor)


class _FailClosedCheckpointProvider:
    """Do not let an arm translate checkpoint-integrity failure into DEFER."""

    def __init__(
        self,
        inner: CheckpointedProvider,
        *,
        maximum_calls: int | None = None,
        shared: _FailClosedCheckpointProvider | None = None,
    ) -> None:
        self._inner = inner
        self._maximum_calls = maximum_calls
        self._calls: list[int]
        self._lock: Lock
        if shared is None:
            self._calls = [0]
            self._lock = Lock()
        else:
            self._calls = shared._calls
            self._lock = shared._lock

    def for_role(self, role: str) -> _FailClosedCheckpointProvider:
        return _FailClosedCheckpointProvider(
            self._inner.for_role(role),
            maximum_calls=self._maximum_calls,
            shared=self,
        )

    def sample(
        self,
        system: str,
        prompt: str,
        schema: dict[str, Any],
        max_tokens: int,
        *,
        timeout_s: float | None = None,
    ) -> ProviderResult:
        with self._lock:
            ordinal = self._calls[0]
            if self._maximum_calls is not None and ordinal >= self._maximum_calls:
                raise ComparisonEvidenceError(
                    "settled comparison replay requested a new paid-call ordinal"
                )
            self._calls[0] += 1
        try:
            return self._inner.sample(
                system, prompt, schema, max_tokens, timeout_s=timeout_s
            )
        except ValueError as exc:
            raise ComparisonEvidenceError(
                "comparison paid-call checkpoint reconciliation failed"
            ) from exc


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
                        finding_id=finding.finding_id,
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
                        finding_id=_baseline_finding_id(
                            ARM_RUFF,
                            case_id,
                            len(findings),
                            anchor[0],
                            anchor[1],
                            EVIDENCE_STATIC_DIAGNOSTIC,
                        ),
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


def _manifest_truth(
    manifest: BenchmarkManifest, case_id: str
) -> ProjectTruth | None:
    return manifest_project_truth(manifest, case_id)


def _comparison_manifest_contract(
    plans: Sequence[ComparisonPlan],
    empty_manifest: BenchmarkManifest | None,
    empty_manifest_sha256: str | None,
) -> tuple[BenchmarkManifest, str]:
    if plans:
        manifest = require_manifest_binding(
            plans[0].manifest, plans[0].manifest_sha256
        )
        manifest_sha256 = plans[0].manifest_sha256
        if empty_manifest is not None:
            if empty_manifest_sha256 is None:
                raise ValueError("explicit comparison manifest requires its digest")
            explicit_manifest = require_manifest_binding(
                empty_manifest, empty_manifest_sha256
            )
            if (
                explicit_manifest != manifest
                or empty_manifest_sha256 != manifest_sha256
            ):
                raise ValueError(
                    "explicit comparison manifest differs from planned manifest"
                )
    else:
        if empty_manifest is None or empty_manifest_sha256 is None:
            raise ValueError("an empty comparison still requires an exact bound manifest")
        manifest = require_manifest_binding(empty_manifest, empty_manifest_sha256)
        manifest_sha256 = empty_manifest_sha256
    cases = {case.case_id: case for case in manifest.cases}
    seen: set[str] = set()
    for plan in plans:
        plan_manifest = require_manifest_binding(
            plan.manifest, plan.manifest_sha256
        )
        if plan.manifest_sha256 != manifest_sha256 or plan_manifest != manifest:
            raise ValueError("comparison plans do not share one exact bound manifest")
        exact_case = cases.get(plan.case.case_id)
        if (
            type(plan.case) is not BenchmarkCase
            or exact_case is None
            or plan.case != exact_case
        ):
            raise ValueError("comparison plan case does not match the bound manifest")
        if plan.case.case_id in seen:
            raise ValueError("comparison plan repeats a manifest case")
        seen.add(plan.case.case_id)
        request = plan.request
        if request.case_id != exact_case.case_id:
            raise ValueError("plan case and request must name the same manifest case")
        require_manifest_evaluation_request(
            manifest, request, source_id=exact_case.source_id
        )
    return manifest, manifest_sha256


def compare_arms(
    plans: Sequence[ComparisonPlan],
    *,
    provider_factory: Callable[[ProjectEvaluationRequest], Provider],
    bare_provider_factory: Callable[[str], Provider],
    ruff_executable: str | None,
    line_slack: int = 0,
    clock: Callable[[], float] = time.monotonic,
    checkpoint_root: Path | None = None,
    authority_root: Path | None = None,
    run_identity: str | None = None,
    provider_id: str = "comparison-provider-v1",
    validation_receipt: (
        ValidationReceipt | ValidationReceiptV2 | ValidationVerification | None
    ) = None,
    manifest: BenchmarkManifest | None = None,
    manifest_sha256: str | None = None,
) -> ComparisonExecution:
    """Run all three arms over every planned case and aggregate per arm.

    Only a safely classified terminal arm outcome may become that arm's DEFER.
    Authority, evidence, baseline-materialization, and post-publication boundary
    exceptions propagate and prevent any final receipt; they never become DEFER.
    """
    if type(line_slack) is not int or line_slack < 0:
        raise ValueError("line_slack must be an exact non-negative integer")
    if isinstance(validation_receipt, (ValidationReceiptV2, ValidationVerification)):
        raise ValueError(
            "symmetric current validation authority cannot authorize comparison "
            "execution; wait for X-01/V-03 or a public-key protocol"
        )
    if validation_receipt is not None and type(validation_receipt) is not ValidationReceipt:
        raise ValueError("comparison execution accepts only a historical V1 receipt")
    if checkpoint_root is not None and plans:
        if not isinstance(authority_root, Path):
            raise ValueError(
                "comparison execution requires an explicit external authority_root"
            )
        if type(run_identity) is not str or not _is_sha256(run_identity):
            raise ValueError(
                "comparison execution requires an explicit unique SHA-256 run_identity"
            )
    elif authority_root is not None or run_identity is not None:
        raise ValueError(
            "comparison authority_root/run_identity require a non-empty checkpointed run"
        )
    receipt_sha256 = (
        ABSENT_BINDING_SHA256
        if validation_receipt is None
        else hashlib.sha256(
            validation_receipt_binding_bytes(validation_receipt)
        ).hexdigest()
    )
    bound_manifest, bound_manifest_sha256 = _comparison_manifest_contract(
        plans, manifest, manifest_sha256
    )
    for plan in plans:
        if type(plan.request.line_slack) is not int or plan.request.line_slack != line_slack:
            raise ValueError(
                "every comparison request line_slack must exactly match the study line_slack"
            )
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
    comparison_binding_sha256: str | None = None
    outcome_authority: ComparisonOutcomeAuthority | None = None
    launch_receipt = None
    comparison_document: CanonicalDocument | None = None
    publication_authority: ComparisonPublicationAuthority | None = None
    if checkpoint_root is not None:
        checkpoint_had_evidence = _comparison_checkpoint_has_evidence(checkpoint_root)
        comparison_path = checkpoint_root / "comparison.json"
        if comparison_path.exists():
            try:
                stored_comparison = read_canonical_json(
                    checkpoint_root, "comparison.json"
                ).value
            except ValueError as exc:
                raise ValueError(
                    "comparison predeclaration is unreadable before resume"
                ) from exc
            stored_version = (
                stored_comparison.get("schema_version")
                if type(stored_comparison) is dict
                else None
            )
            if stored_version != COMPARISON_CHECKPOINT_SCHEMA_VERSION:
                raise ValueError(
                    f"unsupported comparison checkpoint schema version "
                    f"{stored_version!r}; supported version is "
                    f"{COMPARISON_CHECKPOINT_SCHEMA_VERSION}. Retain old state and "
                    "use its historical reader; never replay it as current."
                )
        runtime = current_runtime_identity()
        bindings = [
            build_evaluation_binding(
                plan.request,
                provider_id=provider_id,
                interpreter_id=runtime.interpreter_id,
                environment_sha256=runtime.environment_sha256,
                code_sha256=runtime.code_sha256,
                receipt_sha256=(
                    None if validation_receipt is None else receipt_sha256
                ),
            )
            for plan in plans
        ]
        predeclaration_basis = {
            "schema_version": COMPARISON_CHECKPOINT_SCHEMA_VERSION,
            "run_identity": (
                run_identity if plans else ABSENT_BINDING_SHA256
            ),
            "manifest_sha256": bound_manifest_sha256,
            "receipt_sha256": receipt_sha256,
            "line_slack": line_slack,
            "provider_id": provider_id,
            "paid_call_roles": sorted(CALL_ROLES),
            "ruff_sha256": _executable_digest(ruff_executable),
            "bindings": [
                {
                    "case_id": plan.case.case_id,
                    "binding": binding.to_json_dict(),
                }
                for plan, binding in zip(plans, bindings, strict=True)
            ],
            "paid_trials": [
                {
                    "case_id": plan.case.case_id,
                    "arm": arm,
                    "trial_id": f"comparison:{arm}:{plan.case.case_id}",
                    "model_id": binding.model_id,
                    "allowed_roles": (
                        sorted(CALL_ROLES)
                        if arm == ARM_PRODUCT
                        else [CALL_ROLE_PRODUCT]
                    ),
                }
                for plan, binding in zip(plans, bindings, strict=True)
                for arm in (ARM_PRODUCT, ARM_BARE_PROMPT)
            ],
        }
        if plans:
            assert authority_root is not None and run_identity is not None
            outcome_authority_id = _json_mapping_sha256(
                {
                    "authority_protocol": COMPARISON_OUTCOME_PROTOCOL,
                    "comparison": predeclaration_basis,
                }
            )
            outcome_root = checkpoint_root / "authoritative-outcomes"
            _require_separate_outcome_root(outcome_root, plans)
            _require_separate_authority_root(
                authority_root,
                checkpoint_root=checkpoint_root,
                outcome_root=outcome_root,
                plans=plans,
            )
            if checkpoint_had_evidence and not (
                authority_root / COMPARISON_LAUNCH_RECEIPT_PATH
            ).is_file():
                raise ComparisonEvidenceError(
                    "existing comparison evidence has no original external launch receipt"
                )
            try:
                outcome_authority = predeclare_comparison_outcomes(
                    outcome_root,
                    authority_id=outcome_authority_id,
                    manifest_sha256=bound_manifest_sha256,
                    case_bindings={
                        plan.case.case_id: _json_mapping_sha256(
                            binding.to_json_dict()
                        )
                        for plan, binding in zip(plans, bindings, strict=True)
                    },
                    repeats=1,
                )
            except ValueError as exc:
                raise ValueError(
                    "comparison outcome predeclaration drift is refused before "
                    "provider execution"
                ) from exc
        predeclaration = {
            **predeclaration_basis,
            "outcome_authority": (
                None
                if outcome_authority is None
                else {
                    "protocol": COMPARISON_OUTCOME_PROTOCOL,
                    "root": "authoritative-outcomes",
                    "authority_id": outcome_authority.authority_id,
                    "predeclaration_sha256": outcome_authority.predeclaration_sha256,
                }
            ),
        }
        comparison_document = _require_comparison_predeclaration(
            checkpoint_root, predeclaration
        )
        comparison_binding_sha256 = _json_mapping_sha256(predeclaration)
        if outcome_authority is not None:
            assert authority_root is not None and run_identity is not None
            expected_launch = issue_comparison_launch_receipt(
                outcome_authority,
                checkpoint_root=checkpoint_root,
                authority_root=authority_root,
                run_identity=run_identity,
                comparison_sha256=comparison_document.sha256,
            )
            if (authority_root / COMPARISON_LAUNCH_RECEIPT_PATH).is_file():
                launch_receipt = read_comparison_launch_receipt(authority_root)
                if launch_receipt != expected_launch:
                    raise ComparisonEvidenceError(
                        "external comparison launch receipt differs from frozen state"
                    )
            else:
                write_comparison_launch_receipt_once(authority_root, expected_launch)
                launch_receipt = read_comparison_launch_receipt(authority_root)
        plans = tuple(
            replace(
                plan,
                request=freeze_evaluation_request(plan.request, binding),
            )
            for plan, binding in zip(plans, bindings, strict=True)
        )
        if outcome_authority is not None:
            assert (
                authority_root is not None
                and comparison_document is not None
                and comparison_binding_sha256 is not None
            )
            if (authority_root / COMPARISON_FINAL_RECEIPT_PATH).is_file():
                final_receipt = read_comparison_final_receipt(authority_root)
                publication_authority = create_comparison_publication_authority(
                    checkpoint_root=checkpoint_root,
                    outcome_root=outcome_authority.root,
                    authority_root=authority_root,
                    final_receipt=final_receipt,
                )
                verified = verify_comparison_outcomes(
                    outcome_authority.root,
                    expected_final_receipt=final_receipt,
                    expected_comparison_sha256=comparison_document.sha256,
                )
                paid_trials = _paid_trials_from_plans(plans)
                _require_exact_comparison_paid_evidence(
                    checkpoint_root, paid_trials
                )
                measurements = _comparison_measurements_from_verified(
                    verified,
                    checkpoint_root=checkpoint_root,
                    paid_trials=paid_trials,
                    binding_sha256=comparison_binding_sha256,
                    manifest=bound_manifest,
                    line_slack=line_slack,
                    budget_ceiling_usd=(
                        next(iter(ceilings)) if ceilings else 0.0
                    ),
                    manifest_sha256=bound_manifest_sha256,
                )
                return ComparisonExecution(
                    measurements=measurements,
                    publication_authority=publication_authority,
                )
    runs: list[ArmRun] = []
    for plan in plans:
        defects = () if plan.request.truth is None else plan.request.truth.defects
        product_run = _product_arm(
            plan,
            provider_factory,
            clock,
            checkpoint_root,
            comparison_binding_sha256,
            outcome_authority,
            bound_manifest,
            line_slack,
        )
        if product_run.product_measurement is None:  # pragma: no cover - arm contract
            raise ComparisonEvidenceError("product run has no authoritative measurement")
        runs.append(
            replace(
                product_run,
                matched_defect_ids=_product_measurement_matches(
                    product_run.findings, product_run.product_measurement
                ),
            )
        )
        bare_run, ruff_run = _baseline_arms(
            plan,
            bare_provider_factory,
            ruff_executable,
            clock,
            checkpoint_root,
            comparison_binding_sha256,
            outcome_authority,
            bound_manifest,
            line_slack,
        )
        runs.append(_with_matches(bare_run, defects, line_slack))
        runs.append(_with_matches(ruff_run, defects, line_slack))

    if outcome_authority is not None:
        assert (
            launch_receipt is not None
            and authority_root is not None
            and comparison_document is not None
            and comparison_binding_sha256 is not None
            and checkpoint_root is not None
        )
        paid_trials = _paid_trials_from_plans(plans)
        _require_exact_comparison_paid_evidence(checkpoint_root, paid_trials)
        final_receipt = finalize_comparison_outcomes(
            outcome_authority,
            launch_receipt,
            checkpoint_root=checkpoint_root,
            authority_root=authority_root,
        )
        verified = verify_comparison_outcomes(
            outcome_authority.root,
            expected_final_receipt=final_receipt,
            expected_comparison_sha256=comparison_document.sha256,
        )
        _comparison_measurements_from_verified(
            verified,
            checkpoint_root=checkpoint_root,
            paid_trials=paid_trials,
            binding_sha256=comparison_binding_sha256,
            manifest=bound_manifest,
            line_slack=line_slack,
            budget_ceiling_usd=(next(iter(ceilings)) if ceilings else 0.0),
            manifest_sha256=bound_manifest_sha256,
        )
        write_comparison_final_receipt_once(
            authority_root,
            final_receipt,
            checkpoint_root=checkpoint_root,
            outcome_root=outcome_authority.root,
        )
        final_receipt = read_comparison_final_receipt(authority_root)
        publication_authority = create_comparison_publication_authority(
            checkpoint_root=checkpoint_root,
            outcome_root=outcome_authority.root,
            authority_root=authority_root,
            final_receipt=final_receipt,
        )
        verified = verify_comparison_outcomes(
            outcome_authority.root,
            expected_final_receipt=final_receipt,
            expected_comparison_sha256=comparison_document.sha256,
        )
        measurements = _comparison_measurements_from_verified(
            verified,
            checkpoint_root=checkpoint_root,
            paid_trials=paid_trials,
            binding_sha256=comparison_binding_sha256,
            manifest=bound_manifest,
            line_slack=line_slack,
            budget_ceiling_usd=(next(iter(ceilings)) if ceilings else 0.0),
            manifest_sha256=bound_manifest_sha256,
        )
    else:
        arms = tuple(
            _summarize_arm(arm, tuple(run for run in runs if run.arm == arm))
            for arm in (ARM_PRODUCT, ARM_BARE_PROMPT, ARM_RUFF)
        )
        evaluated = tuple(sorted({run.case_id for run in runs}))
        measurements = ComparisonMeasurements(
            line_slack=line_slack,
            budget_ceiling_usd=next(iter(ceilings)) if ceilings else 0.0,
            manifest_sha256=bound_manifest_sha256,
            arms=arms,
            runs=tuple(runs),
            evaluated_case_ids=evaluated,
            checkpoint_root=checkpoint_root,
        )
    return ComparisonExecution(
        measurements=measurements,
        publication_authority=publication_authority,
    )


def _require_comparison_predeclaration(
    root: Path, expected: Mapping[str, object]
) -> CanonicalDocument:
    try:
        document = write_canonical_json_once(root, "comparison.json", dict(expected))
    except ValueError as exc:
        path = root / "comparison.json"
        if not path.exists():
            raise
        try:
            stored = read_canonical_json(root, "comparison.json")
        except ValueError as read_exc:
            raise ValueError("comparison predeclaration is unreadable") from read_exc
        value = stored.value
        version = value.get("schema_version") if isinstance(value, dict) else None
        if version != COMPARISON_CHECKPOINT_SCHEMA_VERSION:
            raise ValueError(
                f"unsupported comparison checkpoint schema version {version!r}; supported "
                f"version is {COMPARISON_CHECKPOINT_SCHEMA_VERSION}. Use the compatible "
                "reader and retain call state; never coerce old rows."
            ) from exc
        if value != dict(expected):
            raise ValueError(
                "comparison predeclaration does not match this configuration; drift is "
                "refused before provider execution"
            ) from exc
        document = stored
    if document.value != dict(expected):
        raise ValueError("comparison predeclaration canonical bytes differ")
    return document


def _require_separate_outcome_root(
    outcome_root: Path, plans: Sequence[ComparisonPlan]
) -> None:
    try:
        outcome = outcome_root.resolve(strict=False)
        forbidden = tuple(
            path.resolve(strict=False)
            for plan in plans
            for path in (plan.request.repo, plan.request.workspace_root)
        )
    except OSError as exc:
        raise ValueError("comparison outcome root identity is unreadable") from exc
    if any(
        outcome == path
        or outcome.is_relative_to(path)
        or path.is_relative_to(outcome)
        for path in forbidden
    ):
        raise ValueError(
            "comparison outcome root must be separate from repositories and worktrees"
        )


def _require_separate_authority_root(
    authority_root: Path,
    *,
    checkpoint_root: Path,
    outcome_root: Path,
    plans: Sequence[ComparisonPlan],
) -> None:
    try:
        authority = authority_root.resolve(strict=False)
        forbidden = (
            checkpoint_root.resolve(strict=False),
            outcome_root.resolve(strict=False),
            *(
                path.resolve(strict=False)
                for plan in plans
                for path in (plan.request.repo, plan.request.workspace_root)
            ),
        )
    except OSError as exc:
        raise ValueError("comparison authority root identity is unreadable") from exc
    if any(
        authority == path
        or authority.is_relative_to(path)
        or path.is_relative_to(authority)
        for path in forbidden
    ):
        raise ValueError(
            "comparison authority root must be external to checkpoint, outcome, "
            "repository, and worktree roots"
        )


def _comparison_checkpoint_has_evidence(root: Path) -> bool:
    try:
        return root.exists() and any(root.iterdir())
    except OSError as exc:
        raise ValueError("comparison checkpoint root is unreadable") from exc


def _require_no_symlink_paid_checkpoint_tree(
    checkpoint_root: Path, *, arm: str, case_id: str
) -> None:
    """Reject paid evidence reached through aliases before legacy Path readers run."""

    def existing_lstat(path: Path) -> os.stat_result | None:
        try:
            return path.lstat()
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise ComparisonEvidenceError(
                "comparison paid-call checkpoint path is unreadable"
            ) from exc

    absolute_root = Path(os.path.abspath(checkpoint_root))
    current = Path(absolute_root.anchor)
    for part in absolute_root.parts[1:]:
        current /= part
        status = existing_lstat(current)
        if status is None:
            break
        if stat.S_ISLNK(status.st_mode):
            raise ComparisonEvidenceError(
                "comparison paid-call checkpoint ancestor is a symlink"
            )
        if not stat.S_ISDIR(status.st_mode):
            raise ComparisonEvidenceError(
                "comparison paid-call checkpoint ancestor is not a directory"
            )

    trial_root = checkpoint_root / arm / case_id
    directories = (
        checkpoint_root / "reconciliation",
        checkpoint_root / "reconciliation" / arm,
        trial_root,
        trial_root / "calls",
        trial_root / "artifacts",
    )
    for directory in directories:
        status = existing_lstat(directory)
        if status is None:
            continue
        if stat.S_ISLNK(status.st_mode) or not stat.S_ISDIR(status.st_mode):
            raise ComparisonEvidenceError(
                "comparison paid-call checkpoint directory is a symlink or unsafe"
            )

    files = [
        _comparison_reconciliation_path(checkpoint_root, arm, case_id),
        trial_root / "costs.jsonl",
    ]
    for directory in (trial_root / "calls", trial_root / "artifacts"):
        if existing_lstat(directory) is None:
            continue
        try:
            files.extend(directory.iterdir())
        except OSError as exc:
            raise ComparisonEvidenceError(
                "comparison paid-call checkpoint directory is unreadable"
            ) from exc
    if existing_lstat(trial_root) is not None:
        try:
            children = tuple(trial_root.iterdir())
        except OSError as exc:
            raise ComparisonEvidenceError(
                "comparison paid-call checkpoint trial is unreadable"
            ) from exc
        allowed = {"calls", "artifacts", "costs.jsonl"}
        if any(child.name not in allowed for child in children):
            raise ComparisonEvidenceError(
                "comparison paid-call checkpoint trial contains an unsafe entry"
            )
    for path in files:
        status = existing_lstat(path)
        if status is None:
            continue
        if (
            stat.S_ISLNK(status.st_mode)
            or not stat.S_ISREG(status.st_mode)
            or status.st_nlink != 1
        ):
            raise ComparisonEvidenceError(
                "comparison paid-call checkpoint file is a symlink or unsafe"
            )


def _executable_digest(executable: str | None) -> str | None:
    if executable is None:
        return None
    try:
        return hashlib.sha256(Path(executable).read_bytes()).hexdigest()
    except OSError as exc:
        raise ValueError(f"static-tool executable {executable!r} is unreadable") from exc


def _comparison_reconciliation_path(root: Path, arm: str, case_id: str) -> Path:
    return root / "reconciliation" / arm / f"{case_id}.json"


def _call_evidence_exists(root: Path) -> bool:
    try:
        status = root.lstat()
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise ComparisonEvidenceError(
            "comparison paid-call root is unreadable"
        ) from exc
    if stat.S_ISLNK(status.st_mode) or not stat.S_ISDIR(status.st_mode):
        raise ComparisonEvidenceError("comparison paid-call root is unsafe")
    try:
        names = set(list_authoritative_directory(root, ".", maximum_entries=4))
        if names - {"calls", "artifacts", "costs.jsonl"}:
            raise ComparisonEvidenceError(
                "comparison paid-call root contains an unsafe entry"
            )
        call_names = (
            list_authoritative_directory(root, "calls", maximum_entries=100_000)
            if "calls" in names
            else ()
        )
        artifact_names = (
            list_authoritative_directory(
                root, "artifacts", maximum_entries=100_000
            )
            if "artifacts" in names
            else ()
        )
        costs = (
            read_authoritative_bytes(
                root, "costs.jsonl", maximum_bytes=64 * 1024 * 1024
            )
            if "costs.jsonl" in names
            else b""
        )
    except ValueError as exc:
        if isinstance(exc, ComparisonEvidenceError):
            raise
        raise ComparisonEvidenceError(
            "comparison paid-call evidence is unreadable or unsafe"
        ) from exc
    return bool(call_names or artifact_names or costs)


def _prepare_comparison_reconciliation(
    checkpoint_root: Path, arm: str, case_id: str
) -> tuple[Path, dict[str, object], bool]:
    path = _comparison_reconciliation_path(checkpoint_root, arm, case_id)
    if path.exists():
        return path, _read_comparison_reconciliation(path, arm, case_id), False
    call_root = checkpoint_root / arm / case_id
    if _call_evidence_exists(call_root):
        raise ComparisonEvidenceError(
            f"comparison {arm}/{case_id} paid-call reconciliation is missing"
        )
    running: dict[str, object] = {
        "schema_version": COMPARISON_RECONCILIATION_SCHEMA_VERSION,
        "arm": arm,
        "case_id": case_id,
        "trial_id": f"comparison:{arm}:{case_id}",
        "status": "running",
    }
    _atomic_write_json(path, running)
    return path, running, True


def _read_comparison_reconciliation(
    path: Path, arm: str, case_id: str
) -> dict[str, object]:
    checkpoint_root = path.parents[2]
    try:
        raw = read_canonical_json(
            checkpoint_root, path.relative_to(checkpoint_root)
        ).value
    except ValueError as exc:
        raise ComparisonEvidenceError(
            f"comparison {arm}/{case_id} reconciliation is unreadable"
        ) from exc
    if (
        not isinstance(raw, dict)
        or raw.get("schema_version") != COMPARISON_RECONCILIATION_SCHEMA_VERSION
        or raw.get("arm") != arm
        or raw.get("case_id") != case_id
        or raw.get("trial_id") != f"comparison:{arm}:{case_id}"
        or raw.get("status") not in {"running", "settled"}
    ):
        raise ComparisonEvidenceError(
            f"comparison {arm}/{case_id} reconciliation identity is invalid"
        )
    return dict(raw)


def _paid_call_binding(
    records: Sequence[Mapping[str, object]],
) -> tuple[tuple[dict[str, object], ...], str, PaidCallTotals]:
    normalized = tuple(dict(record) for record in records)
    encoded = json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    try:
        totals = paid_call_totals(normalized)
    except ValueError as exc:
        raise ComparisonEvidenceError(
            "comparison paid-call reconciliation has invalid role or settled spend"
        ) from exc
    return normalized, hashlib.sha256(encoded).hexdigest(), totals


def _settled_reconciliation_payload(
    arm: str,
    case_id: str,
    records: Sequence[Mapping[str, object]],
    digest: str,
) -> dict[str, object]:
    totals = paid_call_totals(records)
    return {
        "schema_version": COMPARISON_RECONCILIATION_SCHEMA_VERSION,
        "arm": arm,
        "case_id": case_id,
        "trial_id": f"comparison:{arm}:{case_id}",
        "status": "settled",
        "call_count": len(records),
        "paid_calls": [dict(record) for record in records],
        "paid_calls_sha256": digest,
        "product_spend_usd": totals.product_usd,
        "oracle_spend_usd": totals.oracle_usd,
        "total_spend_usd": totals.total_usd,
    }


def _verified_checkpoint_records(
    checkpointed: CheckpointedProvider,
) -> tuple[tuple[dict[str, object], ...], str, PaidCallTotals]:
    records, digest, totals, _, _ = _verified_checkpoint_snapshot(checkpointed)
    return records, digest, totals


def _verified_checkpoint_snapshot(
    checkpointed: CheckpointedProvider,
) -> tuple[tuple[dict[str, object], ...], str, PaidCallTotals, int, int]:
    try:
        snapshot = checkpointed.reconciliation_snapshot()
        records, digest, totals = _paid_call_binding(snapshot.records)
        return (
            records,
            digest,
            totals,
            snapshot.input_tokens,
            snapshot.output_tokens,
        )
    except AmbiguousCostError:
        raise
    except ValueError as exc:
        raise ComparisonEvidenceError(
            "comparison paid-call checkpoint reconciliation failed"
        ) from exc


def _verify_existing_reconciliation(
    stored: Mapping[str, object],
    *,
    fresh: bool,
    checkpointed: CheckpointedProvider,
) -> None:
    if fresh:
        return
    records, digest, _ = _verified_checkpoint_records(checkpointed)
    if stored.get("status") == "running":
        if not records:
            raise ComparisonEvidenceError(
                "comparison reconciliation was interrupted before durable call evidence; "
                "automatic dispatch is refused"
            )
        return
    expected = _settled_reconciliation_payload(
        str(stored["arm"]), str(stored["case_id"]), records, digest
    )
    if dict(stored) != expected:
        raise ComparisonEvidenceError(
            "comparison reconciliation rows or digest do not match paid-call evidence"
        )


def _checkpointed_comparison_provider(
    inner: Provider,
    *,
    checkpoint_root: Path,
    arm: str,
    case_id: str,
    model_id: str,
    binding_sha256: str,
    prepared_reconciliation: tuple[Path, dict[str, object], bool] | None = None,
) -> tuple[CheckpointedProvider, Path, dict[str, object]]:
    path, stored, fresh = (
        _prepare_comparison_reconciliation(checkpoint_root, arm, case_id)
        if prepared_reconciliation is None
        else prepared_reconciliation
    )
    try:
        checkpointed = CheckpointedProvider(
            inner,
            root=checkpoint_root / arm / case_id,
            trial_id=f"comparison:{arm}:{case_id}",
            model_id=model_id,
            binding_sha256=binding_sha256,
            role=CALL_ROLE_PRODUCT,
        )
    except ValueError as exc:
        raise ComparisonEvidenceError(
            "comparison paid-call checkpoint reconciliation failed"
        ) from exc
    _verify_existing_reconciliation(
        stored, fresh=fresh, checkpointed=checkpointed
    )
    return checkpointed, path, stored


def _fresh_checkpointed_comparison_provider(
    factory: Callable[[], Provider],
    *,
    checkpoint_root: Path,
    arm: str,
    case_id: str,
    model_id: str,
    binding_sha256: str,
) -> tuple[CheckpointedProvider, Path, dict[str, object]]:
    """Persist and revalidate a fresh trial marker around provider construction."""
    prepared = _prepare_comparison_reconciliation(checkpoint_root, arm, case_id)
    path, stored, fresh = prepared
    if not fresh:
        raise ComparisonEvidenceError(
            f"comparison {arm}/{case_id} reconciliation marker appeared before "
            "provider factory"
        )
    try:
        before = read_canonical_json(
            checkpoint_root, path.relative_to(checkpoint_root)
        )
    except ValueError as exc:
        raise ComparisonEvidenceError(
            f"comparison {arm}/{case_id} reconciliation marker is unreadable "
            "before provider factory"
        ) from exc
    if before.value != stored:
        raise ComparisonEvidenceError(
            f"comparison {arm}/{case_id} reconciliation marker identity is invalid "
            "before provider factory"
        )

    holder = _LateBoundComparisonProvider()
    reconciliation = _checkpointed_comparison_provider(
        holder,
        checkpoint_root=checkpoint_root,
        arm=arm,
        case_id=case_id,
        model_id=model_id,
        binding_sha256=binding_sha256,
        prepared_reconciliation=prepared,
    )
    try:
        directory_lease = _PaidCheckpointDirectoryLease(
            checkpoint_root, arm=arm, case_id=case_id
        )
    except OSError as exc:
        raise ComparisonEvidenceError(
            f"comparison {arm}/{case_id} paid checkpoint directory is unsafe "
            "before provider factory"
        ) from exc

    marker_flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
    try:
        marker_descriptor = os.open(path, marker_flags)
    except OSError as exc:
        directory_lease.close()
        raise ComparisonEvidenceError(
            f"comparison {arm}/{case_id} reconciliation marker is unsafe before "
            "provider factory"
        ) from exc
    try:
        marker_status = os.fstat(marker_descriptor)
    except OSError as exc:
        with suppress(OSError):
            os.close(marker_descriptor)
        directory_lease.close()
        raise ComparisonEvidenceError(
            f"comparison {arm}/{case_id} reconciliation marker is unsafe before "
            "provider factory"
        ) from exc
    if (
        not stat.S_ISREG(marker_status.st_mode)
        or marker_status.st_nlink != 1
        or marker_status.st_size != before.size
    ):
        with suppress(OSError):
            os.close(marker_descriptor)
        directory_lease.close()
        raise ComparisonEvidenceError(
            f"comparison {arm}/{case_id} reconciliation marker is unsafe before "
            "provider factory"
        )
    marker_identity = (
        marker_status.st_dev,
        marker_status.st_ino,
        marker_status.st_mode,
        marker_status.st_nlink,
        marker_status.st_size,
        marker_status.st_mtime_ns,
        marker_status.st_ctime_ns,
    )

    def marker_is_unchanged() -> bool:
        try:
            document = read_canonical_json(
                checkpoint_root, path.relative_to(checkpoint_root)
            )
            current_descriptor = os.open(path, marker_flags)
            try:
                original_status = os.fstat(marker_descriptor)
                current_status = os.fstat(current_descriptor)
            finally:
                os.close(current_descriptor)
        except (OSError, ValueError):
            return False
        original_identity = (
            original_status.st_dev,
            original_status.st_ino,
            original_status.st_mode,
            original_status.st_nlink,
            original_status.st_size,
            original_status.st_mtime_ns,
            original_status.st_ctime_ns,
        )
        current_identity = (
            current_status.st_dev,
            current_status.st_ino,
            current_status.st_mode,
            current_status.st_nlink,
            current_status.st_size,
            current_status.st_mtime_ns,
            current_status.st_ctime_ns,
        )
        return (
            original_identity == marker_identity
            and current_identity == marker_identity
            and document.data == before.data
            and document.value == before.value
        )

    try:
        try:
            inner = factory()
        except BaseException as exc:
            if not marker_is_unchanged():
                raise ComparisonEvidenceError(
                    f"comparison {arm}/{case_id} reconciliation marker changed during "
                    "failed provider factory"
                ) from exc
            if not directory_lease.is_unchanged():
                raise ComparisonEvidenceError(
                    f"comparison {arm}/{case_id} paid checkpoint directory changed "
                    "during failed provider factory"
                ) from exc
            raise

        if not marker_is_unchanged():
            raise ComparisonEvidenceError(
                f"comparison {arm}/{case_id} reconciliation marker changed during "
                "provider factory"
            )
        if not directory_lease.is_unchanged():
            raise ComparisonEvidenceError(
                f"comparison {arm}/{case_id} paid checkpoint directory changed during "
                "provider factory"
            )
        if _call_evidence_exists(checkpoint_root / arm / case_id):
            raise ComparisonEvidenceError(
                f"comparison {arm}/{case_id} paid evidence appeared during provider "
                "factory"
            )
        holder.bind(inner)
    finally:
        with suppress(OSError):
            os.close(marker_descriptor)
        directory_lease.close()
    return reconciliation


def _settled_checkpoint_recovery(
    *,
    checkpoint_root: Path,
    arm: str,
    case_id: str,
    model_id: str,
    binding_sha256: str,
) -> tuple[CheckpointedProvider, Path, dict[str, object]] | None:
    """Return a verification-only replay when paid state predates its outcome slot."""
    _require_no_symlink_paid_checkpoint_tree(
        checkpoint_root, arm=arm, case_id=case_id
    )
    path = _comparison_reconciliation_path(checkpoint_root, arm, case_id)
    call_root = checkpoint_root / arm / case_id
    has_marker = path.exists()
    try:
        root_status = call_root.lstat()
    except FileNotFoundError:
        has_root = False
    except OSError as exc:
        raise ComparisonEvidenceError(
            f"comparison {arm}/{case_id} paid case root is unreadable"
        ) from exc
    else:
        if stat.S_ISLNK(root_status.st_mode) or not stat.S_ISDIR(
            root_status.st_mode
        ):
            raise ComparisonEvidenceError(
                f"comparison {arm}/{case_id} paid case root is unsafe"
            )
        has_root = True
    if has_marker and not has_root:
        raise ComparisonEvidenceError(
            f"comparison {arm}/{case_id} paid case root is missing for its "
            "reconciliation marker"
        )
    if has_root and not has_marker:
        raise ComparisonEvidenceError(
            f"comparison {arm}/{case_id} paid evidence has no reconciliation marker"
        )
    if not has_marker:
        return None
    stored = _read_comparison_reconciliation(path, arm, case_id)
    if stored.get("status") != "settled":
        raise ComparisonEvidenceError(
            f"comparison {arm}/{case_id} interrupted reconciliation is not "
            "safe for factory-less resume"
        )
    return _checkpointed_comparison_provider(
        _VerificationOnlyComparisonProvider(),
        checkpoint_root=checkpoint_root,
        arm=arm,
        case_id=case_id,
        model_id=model_id,
        binding_sha256=binding_sha256,
    )


def _attach_comparison_reconciliation(
    run: ArmRun,
    checkpointed: CheckpointedProvider,
    path: Path,
    stored: Mapping[str, object],
) -> ArmRun:
    records, digest, totals = _verified_checkpoint_records(checkpointed)
    settled = _settled_reconciliation_payload(run.arm, run.case_id, records, digest)
    if stored.get("status") == "settled":
        if dict(stored) != settled:
            raise ComparisonEvidenceError(
                "comparison reconciliation rows or digest changed during replay"
            )
    else:
        _atomic_write_json(path, settled)
    return replace(
        run,
        spend_usd=totals.product_usd,
        oracle_spend_usd=totals.oracle_usd,
        paid_calls=records,
        paid_calls_sha256=digest,
    )


def _settled_replay_limit(stored: Mapping[str, object]) -> int | None:
    if stored.get("status") != "settled":
        return None
    count = stored.get("call_count")
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise ComparisonEvidenceError(
            "settled comparison reconciliation has an invalid call count"
        )
    return count


def validate_arm_run_reconciliation(run: ArmRun) -> None:
    """Fail report publication closed on missing, duplicate, or mismatched joins."""
    records, digest, totals = _paid_call_binding(run.paid_calls)
    if digest != run.paid_calls_sha256:
        raise ComparisonEvidenceError(
            f"comparison {run.arm}/{run.case_id} paid-call reconciliation digest mismatch"
        )
    if run.arm == ARM_RUFF and (
        records
        or run.model_calls != 0
        or run.input_tokens != 0
        or run.output_tokens != 0
        or run.model_id is not None
        or not math.isclose(run.spend_usd, 0.0, rel_tol=0.0, abs_tol=1e-12)
        or not math.isclose(run.oracle_spend_usd, 0.0, rel_tol=0.0, abs_tol=1e-12)
    ):
        raise ComparisonEvidenceError(
            f"comparison {run.arm}/{run.case_id} is a local-tool arm and cannot contain "
            "provider calls, model tokens, or paid-call spend"
        )
    if run.model_calls != len(records):
        raise ComparisonEvidenceError(
            f"comparison {run.arm}/{run.case_id} has missing reconciliation rows"
        )
    call_ids: set[str] = set()
    trial_id = f"comparison:{run.arm}:{run.case_id}"
    for ordinal, record in enumerate(records):
        call_id = record.get("call_id")
        if (
            record.get("trial_id") != trial_id
            or record.get("ordinal") != ordinal
            or call_id != f"{trial_id}:{ordinal}"
            or not isinstance(call_id, str)
            or call_id in call_ids
        ):
            raise ComparisonEvidenceError(
                f"comparison {run.arm}/{run.case_id} paid-call trial binding mismatch"
            )
        call_ids.add(call_id)
        if run.arm == ARM_BARE_PROMPT and record.get("role") != CALL_ROLE_PRODUCT:
            raise ComparisonEvidenceError(
                f"comparison {run.arm}/{run.case_id} contains an oracle-role call"
            )
    if not math.isclose(
        run.spend_usd, totals.product_usd, rel_tol=0.0, abs_tol=1e-12
    ) or not math.isclose(
        run.oracle_spend_usd, totals.oracle_usd, rel_tol=0.0, abs_tol=1e-12
    ):
        raise ComparisonEvidenceError(
            f"comparison {run.arm}/{run.case_id} product/oracle spend does not match "
            "reconciliation rows"
        )


class _VerificationOnlyComparisonProvider:
    def sample(
        self,
        system: str,
        prompt: str,
        schema: dict[str, Any],
        max_tokens: int,
        *,
        timeout_s: float | None = None,
    ) -> ProviderResult:  # pragma: no cover - publication never dispatches
        raise AssertionError("comparison report verification must never dispatch")


def validate_comparison_measurements(
    measurements: ComparisonMeasurements,
    receipt_sha256: str,
    manifest: BenchmarkManifest,
    manifest_sha256: str,
    publication_authority: ComparisonPublicationAuthority | None,
) -> tuple[str, ComparisonMeasurements]:
    """Re-read authoritative call/spend/artifact joins immediately before publication."""
    manifest = require_manifest_binding(manifest, manifest_sha256)
    if type(publication_authority) is not ComparisonPublicationAuthority:
        raise ComparisonEvidenceError(
            "comparison publication requires an exact external final authority; "
            "an empty run is only a not-executed diagnostic"
        )
    try:
        fresh_publication_authority = create_comparison_publication_authority(
            checkpoint_root=publication_authority.checkpoint_root,
            outcome_root=publication_authority.outcome_root,
            authority_root=publication_authority.authority_root,
            final_receipt=publication_authority.final_receipt,
        )
    except ValueError as exc:
        raise ComparisonEvidenceError(
            "comparison external publication authority is not fresh or exact"
        ) from exc
    if fresh_publication_authority != publication_authority:
        raise ComparisonEvidenceError("comparison publication authority was mutated")
    if (
        type(measurements.manifest_sha256) is not str
        or measurements.manifest_sha256 != manifest_sha256
    ):
        raise ComparisonEvidenceError(
            "comparison measurements do not match the bound manifest digest"
        )
    paid_runs = tuple(run for run in measurements.runs if run.arm != ARM_RUFF)
    if (
        measurements.checkpoint_root is None
        or measurements.checkpoint_root != publication_authority.checkpoint_root
    ):
        raise ComparisonEvidenceError(
            "comparison report does not match its external checkpoint authority"
        )
    (
        paid_trials,
        declared_line_slack,
        declared_budget,
        binding_sha256,
        declared_receipt_sha256,
        declared_manifest_sha256,
        frozen_bindings,
        outcome_anchor,
        declared_run_identity,
    ) = _comparison_predeclared_paid_trials(publication_authority.checkpoint_root)
    if (
        declared_run_identity
        != publication_authority.final_receipt.launch.run_identity
    ):
        raise ComparisonEvidenceError(
            "comparison run identity differs from its external launch receipt"
        )
    if declared_manifest_sha256 != manifest_sha256:
        raise ComparisonEvidenceError(
            "comparison predeclaration does not match the report manifest digest"
        )
    if declared_receipt_sha256 != receipt_sha256:
        raise ComparisonEvidenceError(
            "comparison validation receipt binding does not match its predeclaration"
        )
    if measurements.line_slack != declared_line_slack or not math.isclose(
        measurements.budget_ceiling_usd,
        declared_budget,
        rel_tol=0.0,
        abs_tol=1e-12,
    ):
        raise ComparisonEvidenceError(
            "comparison measurement policy does not match its frozen predeclaration"
        )
    paid_run_keys = tuple((run.case_id, run.arm) for run in paid_runs)
    if len(set(paid_run_keys)) != len(paid_run_keys) or set(paid_trials) != set(
        paid_run_keys
    ):
        raise ComparisonEvidenceError(
            "comparison predeclared paid trials do not match report runs"
        )
    case_ids = {case_id for case_id, _ in paid_trials}
    manifest_cases = {case.case_id: case for case in manifest.cases}
    if set(frozen_bindings) != case_ids:
        raise ComparisonEvidenceError(
            "comparison frozen bindings do not match predeclared cases"
        )
    for case_id, binding in frozen_bindings.items():
        case = manifest_cases.get(case_id)
        if case is None:
            raise ComparisonEvidenceError(
                "comparison frozen binding case is absent from the bound manifest"
            )
        expected_truth = _manifest_truth(manifest, case_id)
        expected_base = (
            case.fixed_commit if case.role == _ROLE_POSITIVE else case.buggy_commit
        )
        expected_head = (
            case.buggy_commit if case.role == _ROLE_POSITIVE else case.fixed_commit
        )
        if (
            binding.get("base_sha") != expected_base
            or binding.get("head_sha") != expected_head
            or binding.get("fixed_sha")
            != (
                None
                if expected_truth is None or not expected_truth.defects
                else case.fixed_commit
            )
            or binding.get("truth_sha256")
            != project_truth_sha256(expected_truth)
        ):
            raise ComparisonEvidenceError(
                "comparison frozen commit/truth binding does not match the manifest"
            )
    expected_run_keys = {
        (case_id, arm)
        for case_id in case_ids
        for arm in (ARM_PRODUCT, ARM_BARE_PROMPT, ARM_RUFF)
    }
    run_keys = tuple((run.case_id, run.arm) for run in measurements.runs)
    if len(set(run_keys)) != len(run_keys) or set(run_keys) != expected_run_keys:
        raise ComparisonEvidenceError(
            "comparison report does not contain exactly one run for every declared arm"
        )
    expected_evaluated = tuple(sorted({run.case_id for run in measurements.runs}))
    if measurements.evaluated_case_ids != expected_evaluated:
        raise ComparisonEvidenceError(
            "comparison evaluated case IDs do not match completed runs"
        )
    truths_by_case: dict[str, tuple[TruthDefect, ...]] = {}
    for case_id in case_ids:
        truth = _manifest_truth(manifest, case_id)
        truths_by_case[case_id] = () if truth is None else truth.defects
    for run in measurements.runs:
        case = manifest_cases.get(run.case_id)
        if case is None or type(run.role) is not str or run.role != case.role:
            raise ComparisonEvidenceError(
                "comparison run role/case does not match the bound manifest"
            )
        if run.arm == ARM_PRODUCT:
            if run.product_measurement is None:
                raise ComparisonEvidenceError(
                    "product comparison run has no authoritative measurement"
                )
            expected_matches = _product_measurement_matches(
                run.findings, run.product_measurement
            )
        else:
            expected_matches = _match_locations(
                truths_by_case[run.case_id], run.findings, measurements.line_slack
            )
        if run.matched_defect_ids != expected_matches:
            raise ComparisonEvidenceError(
                "comparison run matches do not reproduce from bound manifest truth"
            )
    expected_summaries = tuple(
        _summarize_arm(
            arm, tuple(run for run in measurements.runs if run.arm == arm)
        )
        for arm in (ARM_PRODUCT, ARM_BARE_PROMPT, ARM_RUFF)
    )
    if measurements.arms != expected_summaries:
        raise ComparisonEvidenceError(
            "comparison arm summaries do not match their authoritative runs"
        )
    _require_exact_comparison_paid_evidence(
        measurements.checkpoint_root, paid_trials
    )
    for run in measurements.runs:
        validate_arm_run_reconciliation(run)
        if run.arm == ARM_RUFF:
            continue
        _require_no_symlink_paid_checkpoint_tree(
            publication_authority.checkpoint_root,
            arm=run.arm,
            case_id=run.case_id,
        )
        expected_trial, expected_model = paid_trials[(run.case_id, run.arm)]
        if run.model_id != expected_model or not isinstance(expected_model, str):
            raise ComparisonEvidenceError(
                f"comparison {run.arm}/{run.case_id} model does not match its frozen "
                "predeclaration binding"
            )
        path = _comparison_reconciliation_path(
            publication_authority.checkpoint_root, run.arm, run.case_id
        )
        stored = _read_comparison_reconciliation(path, run.arm, run.case_id)
        if stored.get("status") != "settled":
            raise ComparisonEvidenceError(
                f"comparison {run.arm}/{run.case_id} reconciliation is not settled"
            )
        try:
            checkpointed = CheckpointedProvider(
                _VerificationOnlyComparisonProvider(),
                root=publication_authority.checkpoint_root / run.arm / run.case_id,
                trial_id=expected_trial,
                model_id=expected_model,
                binding_sha256=binding_sha256,
                role=CALL_ROLE_PRODUCT,
            )
        except ValueError as exc:
            raise ComparisonEvidenceError(
                "comparison report authority reconciliation failed"
            ) from exc
        records, digest, totals = _verified_checkpoint_records(checkpointed)
        expected = _settled_reconciliation_payload(
            run.arm, run.case_id, records, digest
        )
        if (
            dict(stored) != expected
            or records != tuple(dict(record) for record in run.paid_calls)
            or digest != run.paid_calls_sha256
            or not math.isclose(
                run.spend_usd, totals.product_usd, rel_tol=0.0, abs_tol=1e-12
            )
            or not math.isclose(
                run.oracle_spend_usd,
                totals.oracle_usd,
                rel_tol=0.0,
                abs_tol=1e-12,
            )
        ):
            raise ComparisonEvidenceError(
                f"comparison {run.arm}/{run.case_id} report evidence is not authoritative"
            )
    if outcome_anchor is None:
        raise ComparisonEvidenceError(
            "comparison report has no authoritative outcome artifact anchor"
        )
    outcome_root_name, outcome_authority_id, outcome_predeclaration_sha256 = (
        outcome_anchor
    )
    launch = publication_authority.final_receipt.launch
    try:
        comparison_document = read_canonical_json(
            publication_authority.checkpoint_root, "comparison.json"
        )
    except ValueError as exc:
        raise ComparisonEvidenceError(
            "comparison predeclaration is not a fresh canonical artifact"
        ) from exc
    if (
        outcome_root_name != "authoritative-outcomes"
        or publication_authority.outcome_root
        != publication_authority.checkpoint_root / outcome_root_name
        or outcome_authority_id != launch.authority_id
        or outcome_predeclaration_sha256 != launch.predeclaration_sha256
        or launch.manifest_sha256 != manifest_sha256
        or comparison_document.sha256 != launch.comparison_sha256
    ):
        raise ComparisonEvidenceError(
            "comparison external final receipt differs from frozen comparison state"
        )
    verified_outcomes = verify_comparison_outcomes(
        publication_authority.outcome_root,
        expected_final_receipt=publication_authority.final_receipt,
        expected_comparison_sha256=comparison_document.sha256,
    )
    fresh_runs = _rebuild_runs_from_verified_comparison_outcomes(
        verified_outcomes,
        checkpoint_root=publication_authority.checkpoint_root,
        paid_trials=paid_trials,
        binding_sha256=binding_sha256,
        manifest=manifest,
        line_slack=declared_line_slack,
    )
    fresh_arms = tuple(
        _summarize_arm(
            arm, tuple(run for run in fresh_runs if run.arm == arm)
        )
        for arm in (ARM_PRODUCT, ARM_BARE_PROMPT, ARM_RUFF)
    )
    fresh_evaluated = tuple(sorted({run.case_id for run in fresh_runs}))
    fresh_measurements = replace(
        measurements,
        runs=fresh_runs,
        arms=fresh_arms,
        evaluated_case_ids=fresh_evaluated,
        outcome_predeclaration_sha256=outcome_predeclaration_sha256,
        outcome_authority_id=outcome_authority_id,
    )
    if (
        measurements.runs != fresh_runs
        or measurements.arms != fresh_arms
        or measurements.evaluated_case_ids != fresh_evaluated
        or measurements.outcome_predeclaration_sha256
        != outcome_predeclaration_sha256
        or measurements.outcome_authority_id != outcome_authority_id
    ):
        raise ComparisonEvidenceError(
            "comparison caller values differ from authoritative outcome artifacts"
        )
    return binding_sha256, fresh_measurements


def _paid_trials_from_plans(
    plans: Sequence[ComparisonPlan],
) -> dict[tuple[str, str], tuple[str, str]]:
    return {
        (plan.case.case_id, arm): (
            f"comparison:{arm}:{plan.case.case_id}",
            plan.request.config.model,
        )
        for plan in plans
        for arm in (ARM_PRODUCT, ARM_BARE_PROMPT)
    }


def _comparison_measurements_from_verified(
    verified: VerifiedComparisonOutcomes,
    *,
    checkpoint_root: Path,
    paid_trials: Mapping[tuple[str, str], tuple[str, str]],
    binding_sha256: str,
    manifest: BenchmarkManifest,
    line_slack: int,
    budget_ceiling_usd: float,
    manifest_sha256: str,
) -> ComparisonMeasurements:
    runs = _rebuild_runs_from_verified_comparison_outcomes(
        verified,
        checkpoint_root=checkpoint_root,
        paid_trials=paid_trials,
        binding_sha256=binding_sha256,
        manifest=manifest,
        line_slack=line_slack,
    )
    arms = tuple(
        _summarize_arm(arm, tuple(run for run in runs if run.arm == arm))
        for arm in (ARM_PRODUCT, ARM_BARE_PROMPT, ARM_RUFF)
    )
    evaluated = tuple(sorted({run.case_id for run in runs}))
    return ComparisonMeasurements(
        line_slack=line_slack,
        budget_ceiling_usd=budget_ceiling_usd,
        manifest_sha256=manifest_sha256,
        arms=arms,
        runs=runs,
        evaluated_case_ids=evaluated,
        checkpoint_root=checkpoint_root,
        outcome_predeclaration_sha256=verified.predeclaration_sha256,
        outcome_authority_id=verified.authority_id,
    )


def _rebuild_runs_from_verified_comparison_outcomes(
    verified: VerifiedComparisonOutcomes,
    *,
    checkpoint_root: Path,
    paid_trials: Mapping[tuple[str, str], tuple[str, str]],
    binding_sha256: str,
    manifest: BenchmarkManifest,
    line_slack: int,
) -> tuple[ArmRun, ...]:
    manifest_cases = {case.case_id: case for case in manifest.cases}
    runs: list[ArmRun] = []
    for slot, outcome in zip(verified.slots, verified.outcomes, strict=True):
        case = manifest_cases.get(slot.case_id)
        if case is None:
            raise ComparisonEvidenceError(
                "comparison outcome case is absent from the bound manifest"
            )
        runs.append(
            _rebuild_comparison_run_from_outcome(
                slot,
                outcome,
                checkpoint_root=checkpoint_root,
                paid_trials=paid_trials,
                binding_sha256=binding_sha256,
                manifest=manifest,
                line_slack=line_slack,
            )
        )
    return tuple(runs)


def _rebuild_comparison_run_from_outcome(
    slot: ComparisonOutcomeSlot,
    outcome: ComparisonArmOutcome,
    *,
    checkpoint_root: Path,
    paid_trials: Mapping[tuple[str, str], tuple[str, str]],
    binding_sha256: str,
    manifest: BenchmarkManifest,
    line_slack: int,
) -> ArmRun:
    case = next((case for case in manifest.cases if case.case_id == slot.case_id), None)
    if case is None:
        raise ComparisonEvidenceError(
            "comparison outcome case is absent from the bound manifest"
        )
    findings = tuple(
        BaselineFinding(
            file=finding.file,
            line=finding.line,
            evidence_class=finding.evidence_class,
            finding_id=finding.finding_id,
        )
        for finding in outcome.surfaced_findings
    )
    if slot.arm == ARM_RUFF:
        records: tuple[dict[str, object], ...] = ()
        digest = _EMPTY_PAID_CALLS_SHA256
        totals = PaidCallTotals(product_usd=0.0, oracle_usd=0.0)
        model_id = None
        input_tokens = 0
        output_tokens = 0
    else:
        _require_no_symlink_paid_checkpoint_tree(
            checkpoint_root, arm=slot.arm, case_id=slot.case_id
        )
        expected_trial, model_id = paid_trials[(slot.case_id, slot.arm)]
        stored = _read_comparison_reconciliation(
            _comparison_reconciliation_path(
                checkpoint_root, slot.arm, slot.case_id
            ),
            slot.arm,
            slot.case_id,
        )
        if stored.get("status") != "settled":
            raise ComparisonEvidenceError(
                f"comparison {slot.arm}/{slot.case_id} reconciliation is not settled"
            )
        try:
            checkpointed = CheckpointedProvider(
                _VerificationOnlyComparisonProvider(),
                root=checkpoint_root / slot.arm / slot.case_id,
                trial_id=expected_trial,
                model_id=model_id,
                binding_sha256=binding_sha256,
                role=CALL_ROLE_PRODUCT,
            )
        except ValueError as exc:
            raise ComparisonEvidenceError(
                "comparison outcome paid evidence reconciliation failed"
            ) from exc
        (
            records,
            digest,
            totals,
            input_tokens,
            output_tokens,
        ) = _verified_checkpoint_snapshot(checkpointed)
        if dict(stored) != _settled_reconciliation_payload(
            slot.arm, slot.case_id, records, digest
        ):
            raise ComparisonEvidenceError(
                "comparison outcome paid reconciliation marker differs"
            )
    if digest != outcome.paid_calls_sha256:
        raise ComparisonEvidenceError(
            f"comparison {slot.arm}/{slot.case_id} paid evidence digest differs "
            "from its authoritative outcome"
        )
    run = ArmRun(
        arm=slot.arm,
        case_id=slot.case_id,
        role=case.role,
        status=outcome.task_status.value,
        abstain_reason=outcome.abstain_reason,
        findings=findings,
        matched_defect_ids=(),
        model_calls=len(records),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        spend_usd=totals.product_usd,
        oracle_spend_usd=totals.oracle_usd,
        wall_time_s=outcome.wall_time_s,
        tool_cost_s=outcome.tool_cost_s,
        paid_calls=records,
        paid_calls_sha256=digest,
        model_id=model_id,
        product_measurement=outcome.product_measurement,
    )
    truth = _manifest_truth(manifest, slot.case_id)
    defects = () if truth is None else truth.defects
    if slot.arm == ARM_PRODUCT:
        if outcome.product_measurement is None:
            raise ComparisonEvidenceError(
                "product comparison outcome has no authoritative measurement"
            )
        matched_defect_ids = _product_measurement_matches(
            findings, outcome.product_measurement
        )
    else:
        matched_defect_ids = (
            _match_locations(defects, findings, line_slack) if findings else ()
        )
    return replace(
        run,
        matched_defect_ids=matched_defect_ids,
    )


def _comparison_predeclared_paid_trials(
    root: Path,
) -> tuple[
    dict[tuple[str, str], tuple[str, str]],
    int,
    float,
    str,
    str,
    str,
    dict[str, dict[str, object]],
    tuple[str, str, str] | None,
    str,
]:
    try:
        raw = read_canonical_json(root, "comparison.json").value
    except ValueError as exc:
        raise ComparisonEvidenceError(
            "comparison predeclaration is unreadable at report publication"
        ) from exc
    if type(raw) is not dict:
        raise ComparisonEvidenceError(
            "comparison predeclaration must be an exact JSON object"
        )
    version = raw.get("schema_version")
    trials = raw.get("paid_trials")
    bindings = raw.get("bindings")
    line_slack = raw.get("line_slack")
    provider_id = raw.get("provider_id")
    paid_call_roles = raw.get("paid_call_roles")
    receipt_sha256 = raw.get("receipt_sha256")
    manifest_sha256 = raw.get("manifest_sha256")
    outcome_authority = raw.get("outcome_authority")
    run_identity = raw.get("run_identity")
    if (
        version != COMPARISON_CHECKPOINT_SCHEMA_VERSION
        or not isinstance(trials, list)
        or not isinstance(bindings, list)
        or isinstance(line_slack, bool)
        or not isinstance(line_slack, int)
        or line_slack < 0
        or not isinstance(provider_id, str)
        or not provider_id
        or paid_call_roles != sorted(CALL_ROLES)
        or not _is_sha256(receipt_sha256)
        or not _is_sha256(manifest_sha256)
        or not _is_sha256(run_identity)
        or set(raw) != {
            "schema_version",
            "run_identity",
            "manifest_sha256",
            "receipt_sha256",
            "line_slack",
            "provider_id",
            "paid_call_roles",
            "ruff_sha256",
            "bindings",
            "paid_trials",
            "outcome_authority",
        }
    ):
        raise ComparisonEvidenceError(
            f"comparison predeclaration schema/paid-trial binding is invalid; supported "
            f"version is {COMPARISON_CHECKPOINT_SCHEMA_VERSION}"
        )
    assert isinstance(receipt_sha256, str)
    binding_models: dict[str, str] = {}
    frozen_bindings: dict[str, dict[str, object]] = {}
    budgets: set[float] = set()
    for row in bindings:
        case_id = row.get("case_id") if isinstance(row, dict) else None
        binding = row.get("binding") if isinstance(row, dict) else None
        validated = (
            _validated_frozen_evaluation_binding(binding, provider_id)
            if isinstance(binding, dict)
            else None
        )
        if (
            not isinstance(case_id, str)
            or not case_id
            or case_id in binding_models
            or validated is None
        ):
            raise ComparisonEvidenceError(
                "comparison predeclaration contains an invalid frozen binding"
            )
        assert isinstance(binding, dict)
        binding_model_id, budget, binding_receipt_sha256 = validated
        if binding_receipt_sha256 != receipt_sha256:
            raise ComparisonEvidenceError(
                "comparison frozen receipt digest differs across case bindings"
            )
        binding_models[case_id] = binding_model_id
        frozen_bindings[case_id] = dict(binding)
        budgets.add(budget)
    if len(budgets) > 1:
        raise ComparisonEvidenceError(
            "comparison predeclaration contains inconsistent budget bindings"
        )
    normalized: dict[tuple[str, str], tuple[str, str]] = {}
    for row in trials:
        case_id = row.get("case_id") if isinstance(row, dict) else None
        arm = row.get("arm") if isinstance(row, dict) else None
        trial_id = row.get("trial_id") if isinstance(row, dict) else None
        trial_model_id = row.get("model_id") if isinstance(row, dict) else None
        allowed_roles = row.get("allowed_roles") if isinstance(row, dict) else None
        expected_roles = (
            sorted(CALL_ROLES)
            if arm == ARM_PRODUCT
            else [CALL_ROLE_PRODUCT]
        )
        if (
            not isinstance(case_id, str)
            or not case_id
            or arm not in (ARM_PRODUCT, ARM_BARE_PROMPT)
            or trial_id != f"comparison:{arm}:{case_id}"
            or not isinstance(trial_model_id, str)
            or not trial_model_id
            or binding_models.get(case_id) != trial_model_id
            or allowed_roles != expected_roles
        ):
            raise ComparisonEvidenceError(
                "comparison predeclaration contains an invalid paid-trial binding"
            )
        key = (case_id, arm)
        if key in normalized:
            raise ComparisonEvidenceError(
                "comparison predeclaration contains a duplicate paid-trial binding"
            )
        assert isinstance(arm, str) and isinstance(trial_id, str)
        normalized[key] = (trial_id, trial_model_id)
    expected = {
        (case_id, arm)
        for case_id in binding_models
        for arm in (ARM_PRODUCT, ARM_BARE_PROMPT)
    }
    if set(normalized) != expected:
        raise ComparisonEvidenceError(
            "comparison paid trials do not exactly cover frozen bindings"
        )
    assert isinstance(manifest_sha256, str)
    if binding_models:
        if type(outcome_authority) is not dict or set(outcome_authority) != {
            "protocol",
            "root",
            "authority_id",
            "predeclaration_sha256",
        }:
            raise ComparisonEvidenceError(
                "comparison outcome authority anchor has an invalid field set"
            )
        if (
            outcome_authority["protocol"] != COMPARISON_OUTCOME_PROTOCOL
            or outcome_authority["root"] != "authoritative-outcomes"
            or not _is_sha256(outcome_authority["authority_id"])
            or not _is_sha256(outcome_authority["predeclaration_sha256"])
        ):
            raise ComparisonEvidenceError(
                "comparison outcome authority anchor is invalid"
            )
        outcome_anchor = (
            str(outcome_authority["root"]),
            str(outcome_authority["authority_id"]),
            str(outcome_authority["predeclaration_sha256"]),
        )
    elif outcome_authority is None:
        outcome_anchor = None
    else:
        raise ComparisonEvidenceError(
            "empty comparison cannot claim an outcome authority"
        )
    assert isinstance(run_identity, str)
    return (
        normalized,
        line_slack,
        next(iter(budgets), 0.0),
        _json_mapping_sha256(raw),
        receipt_sha256,
        manifest_sha256,
        frozen_bindings,
        outcome_anchor,
        run_identity,
    )


def _validated_frozen_evaluation_binding(
    binding: Mapping[str, object], provider_id: str
) -> tuple[str, float, str] | None:
    if (
        set(binding) != _EVALUATION_BINDING_FIELDS
        or binding.get("schema_version") != EVALUATION_BINDING_SCHEMA_VERSION
        or binding.get("provider_id") != provider_id
    ):
        return None
    repository = binding.get("repository")
    model_id = binding.get("model_id")
    interpreter_id = binding.get("interpreter_id")
    if any(
        not isinstance(value, str) or not value.strip()
        for value in (repository, model_id, interpreter_id)
    ):
        return None
    for field in ("base_sha", "head_sha"):
        if not _is_git_object_id(binding.get(field)):
            return None
    fixed_sha = binding.get("fixed_sha")
    if fixed_sha is not None and not _is_git_object_id(fixed_sha):
        return None
    if any(not _is_sha256(binding.get(field)) for field in _EVALUATION_DIGEST_FIELDS):
        return None
    budget = binding.get("budget_usd")
    if (
        isinstance(budget, bool)
        or not isinstance(budget, (int, float))
        or not math.isfinite(float(budget))
        or float(budget) < 0
    ):
        return None
    assert isinstance(model_id, str)
    receipt_sha256 = binding["receipt_sha256"]
    assert isinstance(receipt_sha256, str)
    return model_id, float(budget), receipt_sha256


def _is_git_object_id(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) in (40, 64)
        and all(character in "0123456789abcdef" for character in value)
    )


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _json_mapping_sha256(value: Mapping[str, object]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _comparison_reconciliation_keys(root: Path) -> set[tuple[str, str]]:
    reconciliation_root = root / "reconciliation"
    if not reconciliation_root.exists():
        return set()
    keys: set[tuple[str, str]] = set()
    try:
        arms = list_authoritative_directory(
            root, "reconciliation", maximum_entries=3
        )
        if set(arms) - {ARM_PRODUCT, ARM_BARE_PROMPT}:
            raise ComparisonEvidenceError(
                "comparison reconciliation contains an orphan marker"
            )
        for arm in arms:
            names = list_authoritative_directory(
                root, Path("reconciliation") / arm, maximum_entries=10_000
            )
            for name in names:
                path = Path(name)
                if path.suffix != ".json" or not path.stem:
                    raise ComparisonEvidenceError(
                        "comparison reconciliation contains an orphan marker"
                    )
                key = (path.stem, arm)
                if key in keys:
                    raise ComparisonEvidenceError(
                        "comparison reconciliation contains a duplicate marker"
                    )
                keys.add(key)
    except ValueError as exc:
        if isinstance(exc, ComparisonEvidenceError):
            raise
        raise ComparisonEvidenceError(
            "comparison reconciliation marker path is unsafe"
        ) from exc
    return keys


def _comparison_paid_call_root_keys(root: Path) -> set[tuple[str, str]]:
    allowed = {
        ".outcome-staging",
        "comparison.json",
        "reconciliation",
        "authoritative-outcomes",
        ARM_PRODUCT,
        ARM_BARE_PROMPT,
    }
    try:
        root_names = list_authoritative_directory(
            root, ".", maximum_entries=10_000
        )
    except ValueError as exc:
        raise ComparisonEvidenceError(
            "comparison checkpoint root is unsafe"
        ) from exc
    for name in root_names:
        if name not in allowed:
            raise ComparisonEvidenceError(
                "comparison checkpoint root contains orphan paid-call evidence"
            )
    keys: set[tuple[str, str]] = set()
    for arm in (ARM_PRODUCT, ARM_BARE_PROMPT):
        arm_root = root / arm
        try:
            arm_root.lstat()
        except FileNotFoundError:
            continue
        try:
            case_ids = list_authoritative_directory(
                root, arm, maximum_entries=10_000
            )
        except (OSError, ValueError) as exc:
            raise ComparisonEvidenceError(
                "comparison paid-call arm root is unsafe"
            ) from exc
        for case_id in case_ids:
            if not case_id:
                raise ComparisonEvidenceError(
                    "comparison paid-call arm contains orphan evidence"
                )
            keys.add((case_id, arm))
    return keys


def _require_exact_comparison_paid_evidence(
    root: Path,
    paid_trials: Mapping[tuple[str, str], tuple[str, str]],
) -> None:
    expected = set(paid_trials)
    marker_keys = _comparison_reconciliation_keys(root)
    if marker_keys != expected:
        raise ComparisonEvidenceError(
            "comparison reconciliation markers do not match predeclared paid trials"
        )
    call_root_keys = _comparison_paid_call_root_keys(root)
    if call_root_keys != expected:
        raise ComparisonEvidenceError(
            "comparison paid-call roots do not match predeclared paid trials"
        )


def _atomic_write_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (
        json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(encoded)
    os.replace(temporary, path)


def _product_arm(
    plan: ComparisonPlan,
    provider_factory: Callable[[ProjectEvaluationRequest], Provider],
    clock: Callable[[], float],
    checkpoint_root: Path | None,
    binding_sha256: str | None,
    outcome_authority: ComparisonOutcomeAuthority | None,
    manifest: BenchmarkManifest,
    line_slack: int,
) -> ArmRun:
    request = plan.request
    slot = _comparison_outcome_slot(
        outcome_authority,
        case_id=request.case_id,
        arm=ARM_PRODUCT,
        repeat=request.repeat,
    )
    if outcome_authority is not None and slot is not None:
        existing = read_comparison_arm_outcome_if_present(outcome_authority, slot)
        if existing is not None:
            if checkpoint_root is None or binding_sha256 is None:
                raise ComparisonEvidenceError(
                    "authoritative product outcome lacks paid checkpoint binding"
                )
            return _rebuild_comparison_run_from_outcome(
                slot,
                existing,
                checkpoint_root=checkpoint_root,
                paid_trials=_paid_trials_from_plans((plan,)),
                binding_sha256=binding_sha256,
                manifest=manifest,
                line_slack=line_slack,
            )
    reconciliation: tuple[CheckpointedProvider, Path, dict[str, object]] | None = None
    if checkpoint_root is not None:
        assert binding_sha256 is not None
        reconciliation = _settled_checkpoint_recovery(
            checkpoint_root=checkpoint_root,
            arm=ARM_PRODUCT,
            case_id=request.case_id,
            model_id=request.config.model,
            binding_sha256=binding_sha256,
        )
    if reconciliation is None:
        if checkpoint_root is None:
            inner = provider_factory(request)
        else:
            assert binding_sha256 is not None
            reconciliation = _fresh_checkpointed_comparison_provider(
                lambda: provider_factory(request),
                checkpoint_root=checkpoint_root,
                arm=ARM_PRODUCT,
                case_id=request.case_id,
                model_id=request.config.model,
                binding_sha256=binding_sha256,
            )
            inner = _VerificationOnlyComparisonProvider()
    else:
        inner = _VerificationOnlyComparisonProvider()
    meter = _MeteredProvider(
        inner
        if reconciliation is None
        else _FailClosedCheckpointProvider(
            reconciliation[0],
            maximum_calls=_settled_replay_limit(reconciliation[2]),
        )
    )
    try:
        oracle_meter = (
            meter.for_role(CALL_ROLE_BENCHMARK_ORACLE)
            if reconciliation is not None
            else meter
        )
        result = evaluate_project(
            request,
            provider=meter,
            oracle_provider=oracle_meter,
            clock=clock,
        )
    except (AmbiguousCostError, ComparisonEvidenceError):
        raise
    except ProjectEvaluationAuthorityError:
        raise
    findings = tuple(
        BaselineFinding(
            file=prediction.file,
            line=prediction.line,
            evidence_class=prediction.evidence_class,
            finding_id=prediction.finding_id,
        )
        for prediction in result.predictions
        if is_scored_placement(prediction.placement)
    )
    product_measurement = result.measurement
    if (
        plan.case.role == _ROLE_CONTROL
        and product_measurement.truth_status is not TruthStatus.NULL
    ):
        raise ComparisonEvidenceError(
            "control product measurement was not adjudicated before persistence"
        )
    run = ArmRun(
        arm=ARM_PRODUCT,
        case_id=request.case_id,
        role=plan.case.role,
        status=result.measurement.task_status.value,
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
        product_measurement=product_measurement,
    )
    run = replace(run, model_id=request.config.model)
    if reconciliation is not None:
        run = _attach_comparison_reconciliation(run, *reconciliation)
    _write_comparison_run_outcome(
        outcome_authority,
        run,
        repeat=request.repeat,
        product_measurement=product_measurement,
    )
    return run


def _baseline_arms(
    plan: ComparisonPlan,
    bare_provider_factory: Callable[[str], Provider],
    ruff_executable: str | None,
    clock: Callable[[], float],
    checkpoint_root: Path | None,
    binding_sha256: str | None,
    outcome_authority: ComparisonOutcomeAuthority | None,
    manifest: BenchmarkManifest,
    line_slack: int,
) -> tuple[ArmRun, ArmRun]:
    request = plan.request
    role = plan.case.role
    bare_slot = _comparison_outcome_slot(
        outcome_authority,
        case_id=request.case_id,
        arm=ARM_BARE_PROMPT,
        repeat=request.repeat,
    )
    ruff_slot = _comparison_outcome_slot(
        outcome_authority,
        case_id=request.case_id,
        arm=ARM_RUFF,
        repeat=request.repeat,
    )
    bare_outcome = (
        None
        if outcome_authority is None or bare_slot is None
        else read_comparison_arm_outcome_if_present(outcome_authority, bare_slot)
    )
    ruff_outcome = (
        None
        if outcome_authority is None or ruff_slot is None
        else read_comparison_arm_outcome_if_present(outcome_authority, ruff_slot)
    )
    if ruff_outcome is not None and bare_outcome is None:
        raise ComparisonEvidenceError(
            "comparison Ruff outcome exists before its predeclared bare predecessor"
        )
    paid_trials = _paid_trials_from_plans((plan,))
    bare: ArmRun | None = None
    if bare_outcome is not None:
        if checkpoint_root is None or binding_sha256 is None or bare_slot is None:
            raise ComparisonEvidenceError(
                "authoritative bare outcome lacks paid checkpoint binding"
            )
        bare = _rebuild_comparison_run_from_outcome(
            bare_slot,
            bare_outcome,
            checkpoint_root=checkpoint_root,
            paid_trials=paid_trials,
            binding_sha256=binding_sha256,
            manifest=manifest,
            line_slack=line_slack,
        )
    if ruff_outcome is not None:
        if ruff_slot is None or checkpoint_root is None or binding_sha256 is None:
            raise ComparisonEvidenceError(
                "authoritative Ruff outcome lacks comparison binding"
            )
        ruff = _rebuild_comparison_run_from_outcome(
            ruff_slot,
            ruff_outcome,
            checkpoint_root=checkpoint_root,
            paid_trials=paid_trials,
            binding_sha256=binding_sha256,
            manifest=manifest,
            line_slack=line_slack,
        )
        if bare is not None:
            return bare, ruff
    bare_recovery: tuple[CheckpointedProvider, Path, dict[str, object]] | None = None
    if bare is None and checkpoint_root is not None:
        assert binding_sha256 is not None
        bare_recovery = _settled_checkpoint_recovery(
            checkpoint_root=checkpoint_root,
            arm=ARM_BARE_PROMPT,
            case_id=request.case_id,
            model_id=request.config.model,
            binding_sha256=binding_sha256,
        )
    with _materialized_diff(request) as (worktree, diff):
        if bare is None:
            reconciliation = bare_recovery
            if reconciliation is None:
                if checkpoint_root is None:
                    inner = bare_provider_factory(request.case_id)
                else:
                    assert binding_sha256 is not None
                    reconciliation = _fresh_checkpointed_comparison_provider(
                        lambda: bare_provider_factory(request.case_id),
                        checkpoint_root=checkpoint_root,
                        arm=ARM_BARE_PROMPT,
                        case_id=request.case_id,
                        model_id=request.config.model,
                        binding_sha256=binding_sha256,
                    )
                    inner = _VerificationOnlyComparisonProvider()
            else:
                inner = _VerificationOnlyComparisonProvider()
            bare = BarePromptBaseline(
                inner
                if reconciliation is None
                else _FailClosedCheckpointProvider(
                    reconciliation[0],
                    maximum_calls=_settled_replay_limit(reconciliation[2]),
                ),
                clock=clock,
            ).evaluate(
                case_id=request.case_id,
                role=role,
                diff=diff,
                config=request.config,
            )
            bare = replace(bare, model_id=request.config.model)
            if reconciliation is not None:
                bare = _attach_comparison_reconciliation(bare, *reconciliation)
            _write_comparison_run_outcome(
                outcome_authority,
                bare,
                repeat=request.repeat,
                product_measurement=None,
            )
        ruff = RuffBaseline(ruff_executable, clock=clock).evaluate(
            case_id=request.case_id,
            role=role,
            diff=diff,
            worktree=worktree,
        )
        _write_comparison_run_outcome(
            outcome_authority,
            ruff,
            repeat=request.repeat,
            product_measurement=None,
        )
        return bare, ruff

def _arm_task_status(
    run: ArmRun, product_measurement: MeasurementRecord | None
) -> TaskStatus:
    if product_measurement is not None:
        return product_measurement.task_status
    try:
        return TaskStatus(run.status)
    except ValueError:
        if run.status == "deferred":
            return (
                TaskStatus.PARTIALLY_DEFERRED
                if run.findings
                else TaskStatus.FULLY_DEFERRED
            )
        raise ComparisonEvidenceError(
            f"comparison {run.arm}/{run.case_id} has an unknown task status"
        ) from None


def _comparison_arm_outcome(
    run: ArmRun, *, product_measurement: MeasurementRecord | None
) -> ComparisonArmOutcome:
    task_status = _arm_task_status(run, product_measurement)
    findings: list[ComparisonSurfacedFinding] = []
    for ordinal, finding in enumerate(run.findings):
        if not finding.finding_id:
            raise ComparisonEvidenceError(
                f"comparison {run.arm}/{run.case_id} finding lacks a stable finding_id"
            )
        findings.append(
            ComparisonSurfacedFinding(
                ordinal=ordinal,
                finding_id=finding.finding_id,
                file=finding.file,
                line=finding.line,
                evidence_class=finding.evidence_class,
            )
        )
    return ComparisonArmOutcome(
        task_status=task_status,
        abstain_reason=(
            None
            if task_status is TaskStatus.COMPLETED
            else run.abstain_reason or f"comparison task status was {task_status.value}"
        ),
        surfaced_findings=tuple(findings),
        product_measurement=product_measurement,
        paid_calls_sha256=run.paid_calls_sha256,
        wall_time_s=run.wall_time_s,
        tool_cost_s=run.tool_cost_s,
    )


def _write_comparison_run_outcome(
    authority: ComparisonOutcomeAuthority | None,
    run: ArmRun,
    *,
    repeat: int,
    product_measurement: MeasurementRecord | None,
) -> None:
    if authority is None:
        return
    matching = tuple(
        slot
        for slot in authority.slots
        if slot.case_id == run.case_id and slot.arm == run.arm and slot.repeat == repeat
    )
    if len(matching) != 1:
        raise ComparisonEvidenceError(
            f"comparison {run.arm}/{run.case_id} has no exact authoritative outcome slot"
        )
    write_comparison_arm_outcome_once(
        authority,
        matching[0],
        _comparison_arm_outcome(run, product_measurement=product_measurement),
    )


def _comparison_outcome_slot(
    authority: ComparisonOutcomeAuthority | None,
    *,
    case_id: str,
    arm: str,
    repeat: int,
) -> ComparisonOutcomeSlot | None:
    if authority is None:
        return None
    matching = tuple(
        slot
        for slot in authority.slots
        if slot.case_id == case_id and slot.arm == arm and slot.repeat == repeat
    )
    if len(matching) != 1:
        raise ComparisonEvidenceError(
            f"comparison {arm}/{case_id} has no exact authoritative outcome slot"
        )
    return matching[0]


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


def _parse_findings(text: str | None) -> list[object] | None:
    if text is None:  # no text block in the response: nothing to parse
        return None
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


def _baseline_finding_id(
    arm: str,
    case_id: str,
    ordinal: int,
    file: str,
    line: int,
    evidence_class: str,
) -> str:
    payload = {
        "arm": arm,
        "case_id": case_id,
        "ordinal": ordinal,
        "file": file,
        "line": line,
        "evidence_class": evidence_class,
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return f"{arm}:{digest}"


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
    if not run.findings:
        return run
    matched = _match_locations(defects, run.findings, line_slack)
    return replace(run, matched_defect_ids=matched)


def _product_measurement_matches(
    findings: tuple[BaselineFinding, ...], measurement: MeasurementRecord
) -> tuple[str | None, ...]:
    """Project product run detail from its already-adjudicated measurement."""

    published = tuple(finding for finding in measurement.findings if finding.author_visible)
    if tuple(finding.finding_id for finding in findings) != tuple(
        finding.finding_id for finding in published
    ):
        raise ComparisonEvidenceError(
            "product run and measurement require an exact finding_id join"
        )
    return tuple(
        finding.defect_id
        if finding.authority is FindingAuthority.AUTOMATED
        and finding.accuracy_status is AccuracyStatus.CORRECT
        else None
        for finding in published
    )


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
    if arm == ARM_PRODUCT and runs and all(
        run.product_measurement is not None for run in runs
    ):
        return _summarize_authoritative_product(runs)
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


def _summarize_authoritative_product(runs: tuple[ArmRun, ...]) -> ArmSummary:
    records = tuple(
        run.product_measurement
        for run in runs
        if run.product_measurement is not None
    )
    summary = reduce_measurements(records)
    correct = summary.correct
    wrong = summary.wrong
    detected = summary.detected_positive_pull_requests
    missed = summary.missed_positive_pull_requests
    flagged = summary.pr_false_positive_events
    silent_controls = summary.true_negative_pull_requests
    published = summary.published
    if (
        correct is None
        or wrong is None
        or detected is None
        or missed is None
        or flagged is None
        or silent_controls is None
        or published is None
    ):
        raise ComparisonEvidenceError(
            "authoritative product accuracy is withheld by its measurement record"
        )
    completed_records = tuple(
        record for record in records if record.task_status is TaskStatus.COMPLETED
    )
    silent_positives = sum(
        record.truth_status is TruthStatus.POSITIVE and record.published_count == 0
        for record in completed_records
    )
    finding_total = correct + wrong
    positive_total = summary.positive_pull_requests
    control_total = summary.null_pull_requests
    silent_cases = sum(record.published_count == 0 for record in completed_records)
    counts: dict[str, int] = {}
    for run in runs:
        for finding in run.findings:
            counts[finding.evidence_class] = counts.get(finding.evidence_class, 0) + 1
    tool_costs = [run.tool_cost_s for run in runs if run.tool_cost_s is not None]
    accuracy = ArmAccuracy(
        finding_true_positives=correct,
        finding_false_positives=wrong,
        finding_precision=summary.finding_precision,
        finding_precision_interval=wilson_interval(correct, finding_total),
        detected_positive_cases=detected,
        decided_positive_cases=positive_total,
        detection_rate=_ratio(detected, positive_total),
        detection_rate_interval=wilson_interval(detected, positive_total),
        flagged_control_cases=flagged,
        decided_control_cases=control_total,
        clean_false_positive_rate=summary.pr_false_positive_rate,
        clean_false_positive_rate_interval=wilson_interval(flagged, control_total),
        silent_control_cases=silent_controls,
        silent_positive_cases=silent_positives,
        silence_precision=silence_precision(silent_controls, silent_positives),
        silence_precision_interval=wilson_interval(
            silent_controls, silent_controls + silent_positives
        ),
    )
    operational = ArmOperational(
        evaluated_cases=summary.semantic_n,
        deferred_cases=summary.partially_deferred + summary.fully_deferred,
        surfaced_findings=published,
        silent_cases=silent_cases,
        silence_rate=_ratio(silent_cases, summary.completed),
        model_calls=sum(run.model_calls for run in runs),
        input_tokens=sum(run.input_tokens for run in runs),
        output_tokens=sum(run.output_tokens for run in runs),
        spend_usd=sum(run.spend_usd for run in runs),
        oracle_spend_usd=sum(run.oracle_spend_usd for run in runs),
        wall_time_s=sum(run.wall_time_s for run in runs),
        tool_cost_s=sum(tool_costs) if tool_costs else None,
    )
    return ArmSummary(
        arm=ARM_PRODUCT,
        description=ARM_DESCRIPTIONS[ARM_PRODUCT],
        accuracy=accuracy,
        operational=operational,
        abstentions=tuple(
            ArmAbstention(run.case_id, run.abstain_reason or "unspecified")
            for run in runs
            if run.product_measurement is not None
            and run.product_measurement.task_status
            in {TaskStatus.PARTIALLY_DEFERRED, TaskStatus.FULLY_DEFERRED}
        ),
        evidence_class_counts=dict(sorted(counts.items())),
        scoring_semantics=summary.reducer_semantics,
        outcome_accounting=measurement_summary_payload(summary),
    )


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _number(value: float | None) -> float | None:
    return None if value is None else round(float(value), 6)


def _interval(value: tuple[float, float] | None) -> list[float] | None:
    return None if value is None else [round(value[0], 6), round(value[1], 6)]
