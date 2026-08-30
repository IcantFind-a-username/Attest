"""Resumable live-local evaluation with fail-closed paid-call accounting.

Live-local is the only benchmark mode that is allowed to spend money, and it
treats that permission as a liability to be minimised:

* **nothing runs without the explicit opt-in.** The paid flag is checked before
  any file is read and long before any provider client could be constructed;
  a present credential is never taken as consent.
* **the full selected-case budget is reserved before the first call.** The run
  predeclaration is written atomically and doubles as the reservation record;
  a run that cannot fit inside the remaining development-cap headroom is
  refused with a distinct reason.
* **every paid call sits inside an atomic checkpoint state machine**
  (``reserved -> provider_complete -> artifacts_complete -> settled ->
  reported``). Resuming never repeats a completed model call, verifies the
  persisted evidence hashes, and appends each cost exactly once. An unknown
  cost or a corrupt state fails the run closed while retaining the evidence.
* **the calibration report recommends and never patches.** Below 500 globally
  labeled findings every output is ``recommendation_only`` and a constants
  patch is prohibited; accuracy follows the D-032 receipt gate and is never
  claimed from replay provenance.

The provider key is verified by presence and length only. Its value is never
stored, compared against artifacts, or written into any message or file.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import time
from collections.abc import (
    Callable,
    Iterable,
    Iterator,
    Mapping,
    MutableMapping,
    Sequence,
)
from contextlib import contextmanager
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

from attest.benchmark.api import (
    ProjectEvaluationBinding,
    ProjectEvaluationRequest,
    ProjectEvaluationResult,
    build_evaluation_binding,
    current_runtime_identity,
    evaluate_project,
    freeze_evaluation_request,
)
from attest.benchmark.checkpoints import CheckpointedProvider
from attest.benchmark.corpus import ValidationReceipt
from attest.benchmark.matcher import match_findings
from attest.benchmark.metrics import wilson_interval
from attest.benchmark.report import (
    LIVE_MODE,
    REPLAY_MODE,
    BenchmarkRunReport,
    ReportAbstention,
    ReportExclusion,
    build_report,
)
from attest.benchmark.schema import (
    BenchmarkManifest,
    Placement,
    Prediction,
    RunRecord,
    TruthDefect,
    is_scored_placement,
)
from attest.review.proposer import Provider, ProviderResult

LIVE_SCHEMA_VERSION = "3"
CALIBRATION_SCHEMA_VERSION = "2"
CALIBRATION_JSON_NAME = "calibration.json"
CALIBRATION_MARKDOWN_NAME = "calibration.md"

#: The checkpoint state machine, in order. A state only ever moves rightward.
STATE_RESERVED = "reserved"
STATE_PROVIDER_COMPLETE = "provider_complete"
STATE_ARTIFACTS_COMPLETE = "artifacts_complete"
STATE_SETTLED = "settled"
STATE_REPORTED = "reported"
CASE_STATES = (
    STATE_RESERVED,
    STATE_PROVIDER_COMPLETE,
    STATE_ARTIFACTS_COMPLETE,
    STATE_SETTLED,
    STATE_REPORTED,
)

#: Preflight refusal reasons. Each names a missing authorisation distinctly.
REASON_PAID_API_NOT_ALLOWED = "paid_api_not_allowed"
REASON_API_KEY_UNAVAILABLE = "api_key_unavailable"
REASON_PREREGISTRATION_NOT_FROZEN = "preregistration_not_frozen"
REASON_MANIFEST_NOT_IMMUTABLE = "manifest_not_immutable"
REASON_INSUFFICIENT_HEADROOM = "insufficient_development_cap_headroom"

#: Why a calibration report may refuse to publish accuracy figures.
ACCURACY_WITHHELD_REPLAY = "replay_provenance_cannot_claim_accuracy"

#: Below this many globally labeled findings, calibration output is
#: ``recommendation_only`` and a constants patch is prohibited (red line 5).
MINIMUM_GLOBAL_LABELS = 500

#: The environment variable the product executor reads for the reviewed
#: project's own interpreter (D-037: the first pilot failed without it).
PROJECT_PYTHON_ENV = "ATTEST_PROJECT_PYTHON"

_KEY_ENV = "ANTHROPIC_API_KEY"
_MINIMUM_KEY_LENGTH = 16
_CONFIRMED_STATUS = "buggy_fail_fixed_pass"
_RUN_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
_DIGEST_PATTERN = re.compile(r"[0-9a-f]{64}")
_DEVSPEND_TOTAL_PATTERN = re.compile(
    r"\*\*Total API spend: \$([0-9]+(?:\.[0-9]+)?) of \$([0-9]+(?:\.[0-9]+)?)\.\*\*"
)


class LivePreflightError(ValueError):
    """A live run was refused before any provider client could be constructed."""

    def __init__(self, reason: str, message: str) -> None:
        self.reason = reason
        super().__init__(f"{reason}: {message}")


@dataclass(frozen=True)
class LivePreflight:
    """The authorisations a live run holds. Never carries key material."""

    manifest_sha256: str
    preregistration_sha256: str
    selected_cases: int
    reserved_total_usd: float
    devspend_total_usd: float
    devspend_cap_usd: float
    headroom_usd: float

    def to_json_dict(self) -> dict[str, object]:
        return {
            "manifest_sha256": self.manifest_sha256,
            "preregistration_sha256": self.preregistration_sha256,
            "selected_cases": self.selected_cases,
            "reserved_total_usd": _rounded(self.reserved_total_usd),
            "devspend_total_usd": _rounded(self.devspend_total_usd),
            "devspend_cap_usd": _rounded(self.devspend_cap_usd),
            "headroom_usd": _rounded(self.headroom_usd),
        }


def read_devspend(path: Path) -> tuple[float, float]:
    """Return ``(total_usd, cap_usd)`` from the development spend ledger.

    A ledger that cannot be read or parsed fails closed: without a trustworthy
    total there is no headroom to reserve paid budget against.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(
            f"development spend ledger {path} could not be read; refusing to "
            "reserve paid budget without a trustworthy total"
        ) from exc
    matches = _DEVSPEND_TOTAL_PATTERN.findall(text)
    if len(matches) != 1:
        raise ValueError(
            f"development spend ledger {path} must contain exactly one "
            "'**Total API spend: $X of $Y.**' line; refusing to reserve paid "
            "budget without a trustworthy total"
        )
    total, cap = matches[0]
    return float(total), float(cap)


def preflight_live(
    *,
    allow_paid_api: bool,
    manifest_path: Path,
    devspend_path: Path,
    case_budgets_usd: Sequence[float],
    env: Mapping[str, str],
) -> LivePreflight:
    """Fail closed unless every live authorisation is explicitly present.

    Checks run in a fixed order and each refusal carries its own distinct
    reason: the paid opt-in first (before anything is read), then key
    presence/length, then the frozen preregistration, then manifest
    immutability against that freeze, then development-cap headroom for the
    full selected-case reservation.
    """
    if not allow_paid_api:
        raise LivePreflightError(
            REASON_PAID_API_NOT_ALLOWED,
            "live-local is a paid mode; pass --allow-paid-api explicitly. "
            "Refused before any provider client is constructed.",
        )
    key = env.get(_KEY_ENV, "")
    if not isinstance(key, str) or len(key) < _MINIMUM_KEY_LENGTH:
        raise LivePreflightError(
            REASON_API_KEY_UNAVAILABLE,
            f"{_KEY_ENV} is missing or below the minimum plausible length; the "
            "key is verified by presence and length only and its value is "
            "never logged",
        )
    frozen_digest = _frozen_preregistration_digest(manifest_path)
    try:
        manifest_bytes = manifest_path.read_bytes()
        protocol_bytes = (manifest_path.parent / "protocol.md").read_bytes()
    except OSError as exc:
        raise LivePreflightError(
            REASON_MANIFEST_NOT_IMMUTABLE,
            "the manifest and protocol bytes under preregistration could not "
            "be read",
        ) from exc
    recomputed = hashlib.sha256(protocol_bytes + b"\x00" + manifest_bytes).hexdigest()
    if recomputed != frozen_digest:
        raise LivePreflightError(
            REASON_MANIFEST_NOT_IMMUTABLE,
            "the manifest or protocol bytes no longer match the frozen "
            "preregistration digest; a mutable corpus buys nothing",
        )
    reserved_total = 0.0
    for budget in case_budgets_usd:
        if not math.isfinite(budget) or budget < 0:
            raise ValueError("every case budget must be a finite non-negative amount")
        reserved_total += budget
    total, cap = read_devspend(devspend_path)
    headroom = cap - total - reserved_total
    if headroom < 0:
        raise LivePreflightError(
            REASON_INSUFFICIENT_HEADROOM,
            f"reserving {reserved_total:.4f} USD for {len(case_budgets_usd)} "
            f"case(s) would exceed the {cap:.2f} USD development cap "
            f"({total:.4f} USD already spent)",
        )
    return LivePreflight(
        manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
        preregistration_sha256=frozen_digest,
        selected_cases=len(case_budgets_usd),
        reserved_total_usd=reserved_total,
        devspend_total_usd=total,
        devspend_cap_usd=cap,
        headroom_usd=headroom,
    )


def _frozen_preregistration_digest(manifest_path: Path) -> str:
    path = manifest_path.parent / "preregistration.sha256"
    try:
        first_field = path.read_text(encoding="utf-8").split()[0]
    except (OSError, IndexError) as exc:
        raise LivePreflightError(
            REASON_PREREGISTRATION_NOT_FROZEN,
            f"no readable preregistration digest at {path}; freeze the "
            "protocol and manifest before observing live results",
        ) from exc
    if _DIGEST_PATTERN.fullmatch(first_field) is None:
        raise LivePreflightError(
            REASON_PREREGISTRATION_NOT_FROZEN,
            f"{path} does not start with a lowercase SHA-256 digest",
        )
    return first_field


@dataclass(frozen=True)
class LiveCase:
    """One selected case: its evaluation request plus its opaque source."""

    request: ProjectEvaluationRequest
    source_id: str
    binding: ProjectEvaluationBinding | None = None


def reserved_case_budget_usd(request: ProjectEvaluationRequest) -> float:
    """The pre-call reservation for one case: product budget, doubled when a
    truth reference means the independent benchmark oracle will also spend."""
    budget = request.config.budget_usd
    return budget * 2.0 if request.truth is not None else budget


def case_payload(result: ProjectEvaluationResult) -> dict[str, object]:
    """The persisted per-case evidence: the frozen result plus its run identity."""
    payload = result.to_json_dict()
    payload["run_id"] = result.run.run_id
    return payload


@dataclass(frozen=True)
class _Checkpoint:
    """One case's atomic on-disk state. ``payload`` is the paid evidence."""

    case_id: str
    state: str
    reserved_usd: float
    payload: dict[str, object] | None
    payload_sha256: str | None

    def to_json_dict(self) -> dict[str, object]:
        return {
            "schema_version": LIVE_SCHEMA_VERSION,
            "case_id": self.case_id,
            "state": self.state,
            "reserved_usd": self.reserved_usd,
            "payload": self.payload,
            "payload_sha256": self.payload_sha256,
        }


def _corrupt(path: Path, exc: Exception | None = None) -> ValueError:
    error = ValueError(
        f"live case state {path.name} is corrupt; refusing to guess whether "
        "the paid call happened. The evidence is retained for inspection."
    )
    if exc is not None:
        error.__cause__ = exc
    return error


def _load_checkpoint(path: Path, case_id: str) -> _Checkpoint:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise _corrupt(path, exc) from exc
    if not isinstance(raw, dict):
        raise _corrupt(path)
    version = raw.get("schema_version")
    if version != LIVE_SCHEMA_VERSION:
        raise ValueError(
            f"unsupported live checkpoint schema version {version!r}; supported version "
            f"is {LIVE_SCHEMA_VERSION}. Use the compatible reader and retain the paid "
            "evidence; never coerce or replay it."
        )
    if raw.get("case_id") != case_id or raw.get("state") not in CASE_STATES:
        raise _corrupt(path)
    reserved = raw.get("reserved_usd")
    if isinstance(reserved, bool) or not isinstance(reserved, (int, float)):
        raise _corrupt(path)
    payload = raw.get("payload")
    payload_sha256 = raw.get("payload_sha256")
    state = str(raw.get("state"))
    if state == STATE_RESERVED:
        if payload is not None or payload_sha256 is not None:
            raise _corrupt(path)
        return _Checkpoint(case_id, state, float(reserved), None, None)
    if (
        not isinstance(payload, dict)
        or not isinstance(payload_sha256, str)
        or hashlib.sha256(_canonical_bytes(payload)).hexdigest() != payload_sha256
    ):
        raise _corrupt(path)
    return _Checkpoint(case_id, state, float(reserved), payload, payload_sha256)


@dataclass(frozen=True)
class LiveRunResult:
    """What one invocation executed, resumed, settled, and reported."""

    run_id: str
    report: CalibrationReport
    report_path: Path
    markdown_path: Path
    executed_cases: int
    resumed_cases: int
    reserved_total_usd: float
    settled_spend_usd: float
    settled_oracle_spend_usd: float
    case_states: Mapping[str, str]


def run_live_local(
    cases: Sequence[LiveCase],
    *,
    run_id: str,
    state_dir: Path,
    output_dir: Path,
    manifest: BenchmarkManifest,
    manifest_sha256: str,
    preregistration_sha256: str,
    provider_factory: Callable[[ProjectEvaluationRequest], Provider],
    resume: bool = False,
    interpreters: Mapping[str, str] | None = None,
    exclusions: Iterable[ReportExclusion] = (),
    validation_receipt: ValidationReceipt | None = None,
    line_slack: int = 0,
    globally_labeled_findings: int | None = None,
    evaluate: (
        Callable[[ProjectEvaluationRequest, Provider], ProjectEvaluationResult] | None
    ) = None,
    env: MutableMapping[str, str] | None = None,
    on_transition: Callable[[str, str], None] | None = None,
    on_call_transition: Callable[[str, str, str], None] | None = None,
    provider_id: str = "anthropic-api-v1",
    clock: Callable[[], float] = time.monotonic,
) -> LiveRunResult:
    """Execute or resume one live run under the atomic checkpoint state machine.

    The run predeclaration is written atomically before the first provider
    call and IS the budget reservation. Each case then advances through
    ``reserved -> provider_complete -> artifacts_complete -> settled ->
    reported``, committing every transition to its own state file before the
    next step runs, so an interruption anywhere never duplicates a paid call
    and never loses paid evidence. Resuming re-verifies every persisted
    artifact hash and refuses -- retaining the evidence -- on any state whose
    cost cannot be known.
    """
    if not cases:
        raise ValueError("a live run needs at least one selected case")
    if _RUN_ID_PATTERN.fullmatch(run_id) is None:
        raise ValueError("run_id must be a short, path-safe identifier")
    case_ids = [case.request.case_id for case in cases]
    if len(set(case_ids)) != len(case_ids):
        raise ValueError("selected cases must be unique")
    environment: MutableMapping[str, str] = os.environ if env is None else env
    evaluator = evaluate or (
        lambda request, provider: evaluate_project(request, provider=provider, clock=clock)
    )
    interpreter_by_source = dict(interpreters or {})
    runtime = current_runtime_identity()
    receipt_sha256 = (
        None
        if validation_receipt is None
        else hashlib.sha256(_canonical_bytes(asdict(validation_receipt))).hexdigest()
    )
    bindings: dict[str, ProjectEvaluationBinding] = {}
    for live_case in cases:
        if live_case.binding is not None:
            if evaluate is None:
                raise ValueError(
                    "prebuilt evaluation bindings are accepted only with an injected evaluator"
                )
            bindings[live_case.request.case_id] = live_case.binding
            continue
        interpreter = interpreter_by_source.get(live_case.source_id)
        interpreter_id = runtime.interpreter_id
        if interpreter is not None:
            interpreter_id = _interpreter_identity(interpreter)
        environment_sha256 = hashlib.sha256(
            _canonical_bytes(
                {
                    "controller_environment_sha256": runtime.environment_sha256,
                    "source_id": live_case.source_id,
                    "project_interpreter": interpreter_id,
                }
            )
        ).hexdigest()
        bindings[live_case.request.case_id] = build_evaluation_binding(
            live_case.request,
            provider_id=provider_id,
            interpreter_id=interpreter_id,
            environment_sha256=environment_sha256,
            code_sha256=runtime.code_sha256,
            receipt_sha256=receipt_sha256,
        )
    cases = tuple(
        replace(
            live_case,
            request=freeze_evaluation_request(
                live_case.request, bindings[live_case.request.case_id]
            ),
        )
        for live_case in cases
    )
    predeclaration = _predeclaration(
        cases,
        run_id,
        manifest_sha256,
        preregistration_sha256,
        line_slack,
        bindings,
    )
    call_binding_sha256 = hashlib.sha256(
        _canonical_bytes(predeclaration)
    ).hexdigest()
    run_dir = state_dir / run_id
    run_path = run_dir / "run.json"
    if resume:
        if not run_path.exists():
            raise ValueError(
                f"no predeclaration found for run {run_id}; a resume needs the "
                "original reservation"
            )
        try:
            stored = json.loads(run_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"run {run_id} predeclaration is unreadable") from exc
        if not isinstance(stored, dict) or stored.get("schema_version") != LIVE_SCHEMA_VERSION:
            version = stored.get("schema_version") if isinstance(stored, dict) else None
            raise ValueError(
                f"unsupported live predeclaration schema version {version!r}; supported "
                f"version is {LIVE_SCHEMA_VERSION}. Use the compatible reader; never "
                "reinterpret an existing reservation."
            )
        if stored != predeclaration:
            raise ValueError(
                f"run {run_id} predeclaration does not match this configuration; "
                "refusing to mix incomparable paid runs"
            )
    else:
        if run_path.exists():
            raise ValueError(
                f"run {run_id} already has recorded state; pass resume=True "
                f"(--resume {run_id}) to continue it instead of re-reserving"
            )
        # The reservation: committed atomically before any provider call.
        (run_dir / "cases").mkdir(parents=True, exist_ok=True)
        _atomic_write(run_path, _canonical_bytes(predeclaration))
    (run_dir / "artifacts").mkdir(parents=True, exist_ok=True)
    costs_path = run_dir / "costs.jsonl"

    executed = resumed = 0
    checkpoints: dict[str, _Checkpoint] = {}
    for live_case in cases:
        checkpoint, ran = _advance_case(
            live_case,
            run_dir=run_dir,
            costs_path=costs_path,
            provider_factory=provider_factory,
            evaluator=evaluator,
            environment=environment,
            interpreter=interpreter_by_source.get(live_case.source_id),
            call_binding_sha256=call_binding_sha256,
            on_transition=on_transition,
            on_call_transition=on_call_transition,
        )
        checkpoints[checkpoint.case_id] = checkpoint
        if ran:
            executed += 1
        else:
            resumed += 1

    payloads = [_required_payload(checkpoints[case_id]) for case_id in case_ids]
    reserved_total = float(predeclaration["reserved_total_usd"])  # type: ignore[arg-type]
    report = build_calibration_report(
        manifest,
        payloads,
        run_id=run_id,
        mode=LIVE_MODE,
        manifest_sha256=manifest_sha256,
        preregistration_sha256=preregistration_sha256,
        exclusions=exclusions,
        validation_receipt=validation_receipt,
        differential_repeats=cases[0].request.repeats,
        line_slack=line_slack,
        globally_labeled_findings=globally_labeled_findings,
        reserved_total_usd=reserved_total,
    )
    report_path, markdown_path = write_calibration_report(report, output_dir)
    for case_id in case_ids:
        checkpoint = checkpoints[case_id]
        if checkpoint.state == STATE_SETTLED:
            checkpoint = replace(checkpoint, state=STATE_REPORTED)
            _commit(run_dir, checkpoint, on_transition)
            checkpoints[case_id] = checkpoint
    spend, oracle_spend = _settled_totals(costs_path)
    return LiveRunResult(
        run_id=run_id,
        report=report,
        report_path=report_path,
        markdown_path=markdown_path,
        executed_cases=executed,
        resumed_cases=resumed,
        reserved_total_usd=reserved_total,
        settled_spend_usd=spend,
        settled_oracle_spend_usd=oracle_spend,
        case_states={
            case_id: checkpoints[case_id].state for case_id in sorted(case_ids)
        },
    )


def _advance_case(
    live_case: LiveCase,
    *,
    run_dir: Path,
    costs_path: Path,
    provider_factory: Callable[[ProjectEvaluationRequest], Provider],
    evaluator: Callable[[ProjectEvaluationRequest, Provider], ProjectEvaluationResult],
    environment: MutableMapping[str, str],
    interpreter: str | None,
    call_binding_sha256: str,
    on_transition: Callable[[str, str], None] | None,
    on_call_transition: Callable[[str, str, str], None] | None,
) -> tuple[_Checkpoint, bool]:
    request = live_case.request
    case_id = request.case_id
    path = run_dir / "cases" / f"{case_id}.json"
    ran = False
    if path.exists():
        checkpoint = _load_checkpoint(path, case_id)
    else:
        checkpoint = _Checkpoint(
            case_id, STATE_RESERVED, reserved_case_budget_usd(request), None, None
        )
        _commit(run_dir, checkpoint, on_transition)
    if checkpoint.state == STATE_RESERVED:
        provider = provider_factory(request)
        checkpointed = CheckpointedProvider(
            provider,
            root=run_dir / "calls" / case_id,
            trial_id=f"{run_dir.name}:{case_id}",
            model_id=request.config.model,
            binding_sha256=call_binding_sha256,
            on_transition=(
                None
                if on_call_transition is None
                else lambda call_id, state: on_call_transition(case_id, call_id, state)
            ),
        )
        with _project_interpreter(environment, interpreter):
            result = evaluator(request, checkpointed)
        paid_calls = _live_paid_call_records(
            case_id, checkpointed.reconciliation_records()
        )
        payload = case_payload(result)
        payload["paid_calls"] = paid_calls
        checkpoint = replace(
            checkpoint,
            state=STATE_PROVIDER_COMPLETE,
            payload=payload,
            payload_sha256=hashlib.sha256(_canonical_bytes(payload)).hexdigest(),
        )
        _commit(run_dir, checkpoint, on_transition)
        ran = True
    artifact_path = run_dir / "artifacts" / f"{case_id}.json"
    payload = _required_payload(checkpoint)
    if checkpoint.state == STATE_PROVIDER_COMPLETE:
        _atomic_write(artifact_path, _canonical_bytes(payload))
        checkpoint = replace(checkpoint, state=STATE_ARTIFACTS_COMPLETE)
        _commit(run_dir, checkpoint, on_transition)
    _verify_artifact(artifact_path, checkpoint.payload_sha256)
    if checkpoint.state == STATE_ARTIFACTS_COMPLETE:
        spend, oracle_spend = _known_cost(case_id, payload)
        _settle_once(
            costs_path,
            case_id,
            spend,
            oracle_spend,
            _required_paid_calls(
                run_dir,
                case_id,
                payload,
                request.config.model,
                call_binding_sha256,
            ),
        )
        checkpoint = replace(checkpoint, state=STATE_SETTLED)
        _commit(run_dir, checkpoint, on_transition)
    if checkpoint.state in {STATE_SETTLED, STATE_REPORTED}:
        spend, oracle_spend = _known_cost(case_id, payload)
        _verify_case_settlement(
            costs_path,
            case_id,
            spend,
            oracle_spend,
            _required_paid_calls(
                run_dir,
                case_id,
                payload,
                request.config.model,
                call_binding_sha256,
            ),
        )
    return checkpoint, ran


def _required_payload(checkpoint: _Checkpoint) -> dict[str, object]:
    payload = checkpoint.payload
    assert payload is not None  # states past reserved always carry the evidence
    return payload


@contextmanager
def _project_interpreter(
    environment: MutableMapping[str, str], interpreter: str | None
) -> Iterator[None]:
    """Expose the case's project interpreter to the product executor (D-037).

    The executor reads :data:`PROJECT_PYTHON_ENV` from its process environment
    at reproduction time, so the mapping is applied there for exactly the
    duration of the case's evaluation and always restored.
    """
    if interpreter is None:
        yield
        return
    previous = environment.get(PROJECT_PYTHON_ENV)
    environment[PROJECT_PYTHON_ENV] = interpreter
    try:
        yield
    finally:
        if previous is None:
            environment.pop(PROJECT_PYTHON_ENV, None)
        else:
            environment[PROJECT_PYTHON_ENV] = previous


def _known_cost(case_id: str, payload: Mapping[str, object]) -> tuple[float, float]:
    """The case's settled cost, or a closed failure that retains the evidence."""
    values: list[float] = []
    for key in ("spend_usd", "oracle_spend_usd"):
        value = payload.get(key)
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or float(value) < 0
        ):
            raise ValueError(
                f"case {case_id} has an unknown {key} cost; refusing to settle. "
                "The paid evidence is retained in its checkpoint."
            )
        values.append(float(value))
    return values[0], values[1]


def _live_paid_call_records(
    case_id: str, records: Sequence[Mapping[str, object]]
) -> list[dict[str, object]]:
    prefix = f"calls/{case_id}/"
    joined: list[dict[str, object]] = []
    for record in records:
        artifact_path = record.get("artifact_path")
        if not isinstance(artifact_path, str):
            raise ValueError(f"case {case_id} paid-call artifact path is invalid")
        joined.append(
            {
                **dict(record),
                "artifact_path": prefix + artifact_path,
                "spend_path": prefix + "costs.jsonl",
            }
        )
    return joined


def _required_paid_calls(
    run_dir: Path,
    case_id: str,
    payload: Mapping[str, object],
    model_id: str,
    binding_sha256: str,
) -> tuple[dict[str, object], ...]:
    raw = payload.get("paid_calls")
    if not isinstance(raw, list):
        raise ValueError(f"case {case_id} payload has no paid-call reconciliation list")
    records: list[dict[str, object]] = []
    seen: set[str] = set()
    by_spend_path: dict[str, list[dict[str, object]]] = {}
    for value in raw:
        if not isinstance(value, dict):
            raise ValueError(f"case {case_id} has an invalid paid-call reconciliation row")
        record = dict(value)
        call_id = record.get("call_id")
        trial_id = record.get("trial_id")
        artifact_path = record.get("artifact_path")
        spend_path = record.get("spend_path")
        if (
            not isinstance(call_id, str)
            or not isinstance(trial_id, str)
            or not call_id.startswith(trial_id + ":")
            or not isinstance(artifact_path, str)
            or not artifact_path.startswith(f"calls/{case_id}/artifacts/")
            or not isinstance(spend_path, str)
            or spend_path != f"calls/{case_id}/costs.jsonl"
        ):
            raise ValueError(f"case {case_id} paid-call trial/artifact binding is invalid")
        if call_id in seen:
            raise ValueError(f"case {case_id} repeats paid call {call_id}")
        seen.add(call_id)
        artifact = run_dir / artifact_path
        try:
            artifact_payload = json.loads(artifact.read_text(encoding="utf-8"))
            digest = hashlib.sha256(
                json.dumps(
                    artifact_payload, sort_keys=True, separators=(",", ":")
                ).encode("utf-8")
            ).hexdigest()
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(
                f"case {case_id} paid-call artifact {artifact_path} is missing or corrupt"
            ) from exc
        if digest != record.get("artifact_sha256"):
            raise ValueError(
                f"case {case_id} paid-call artifact {artifact_path} hash binding is invalid"
            )
        records.append(record)
        by_spend_path.setdefault(spend_path, []).append(record)
    for spend_path, expected_records in by_spend_path.items():
        authoritative = _json_rows(run_dir / spend_path, "paid-call spend rows")
        normalized = []
        prefix = f"calls/{case_id}/"
        for record in expected_records:
            normalized.append(
                {
                    key: value
                    for key, value in record.items()
                    if key != "spend_path"
                }
            )
            normalized[-1]["artifact_path"] = str(record["artifact_path"])[len(prefix) :]
        authoritative.sort(key=lambda row: str(row.get("call_id")))
        normalized.sort(key=lambda row: str(row.get("call_id")))
        if authoritative != normalized:
            raise ValueError(
                f"case {case_id} paid-call spend rows are missing, duplicated, or mismatched"
            )
    checkpointed = CheckpointedProvider(
        _VerificationOnlyProvider(),
        root=run_dir / "calls" / case_id,
        trial_id=f"{run_dir.name}:{case_id}",
        model_id=model_id,
        binding_sha256=binding_sha256,
    )
    authoritative_calls = tuple(
        _live_paid_call_records(case_id, checkpointed.reconciliation_records())
    )
    if tuple(records) != authoritative_calls:
        raise ValueError(
            f"case {case_id} paid-call payload does not match its call checkpoints"
        )
    return tuple(records)


class _VerificationOnlyProvider:
    """A verifier must never turn absent checkpoint evidence into a new call."""

    def sample(
        self,
        system: str,
        prompt: str,
        schema: dict[str, Any],
        max_tokens: int,
        *,
        timeout_s: float | None = None,
    ) -> ProviderResult:  # pragma: no cover - reconciliation never dispatches
        raise AssertionError("paid-call reconciliation must not dispatch a provider call")


def _case_cost_row(
    case_id: str,
    spend: float,
    oracle: float,
    paid_calls: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    return {
        "kind": "case_summary",
        "case_id": case_id,
        "spend_usd": _rounded(spend),
        "oracle_spend_usd": _rounded(oracle),
        "paid_calls": [dict(record) for record in paid_calls],
    }


def _settle_once(
    costs_path: Path,
    case_id: str,
    spend: float,
    oracle: float,
    paid_calls: Sequence[Mapping[str, object]],
) -> None:
    """Append this case's cost exactly once, whatever happened before."""
    rows = _cost_rows(costs_path)
    mine = [row for row in rows if row.get("case_id") == case_id]
    if len(mine) > 1:
        raise ValueError(
            f"case {case_id} appears more than once in the cost ledger; the "
            "ledger is corrupt and settlement is refused"
        )
    if mine:
        if mine[0] != _case_cost_row(case_id, spend, oracle, paid_calls):
            raise ValueError(
                f"case {case_id} cost settlement does not match its paid-call artifacts"
            )
        return
    rows.append(_case_cost_row(case_id, spend, oracle, paid_calls))
    _atomic_write(costs_path, b"".join(_canonical_bytes(row) for row in rows))


def _verify_case_settlement(
    costs_path: Path,
    case_id: str,
    spend: float,
    oracle: float,
    paid_calls: Sequence[Mapping[str, object]],
) -> None:
    rows = _cost_rows(costs_path)
    mine = [row for row in rows if row.get("case_id") == case_id]
    if not mine:
        raise ValueError(f"case {case_id} has no cost settlement row")
    if len(mine) > 1:
        raise ValueError(f"case {case_id} has duplicate cost settlement rows")
    if mine[0] != _case_cost_row(case_id, spend, oracle, paid_calls):
        raise ValueError(
            f"case {case_id} cost settlement paid-call binding is invalid"
        )


def _cost_rows(costs_path: Path) -> list[dict[str, object]]:
    rows = _json_rows(costs_path, "the cost ledger")
    for row in rows:
        if (
            row.get("kind") != "case_summary"
            or not isinstance(row.get("case_id"), str)
        ):
            raise ValueError("the cost ledger is corrupt; settlement is refused")
    return rows


def _json_rows(path: Path, label: str) -> list[dict[str, object]]:
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ValueError(f"{label} could not be read") from exc
    rows: list[dict[str, object]] = []
    for line in lines:
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{label} is corrupt") from exc
        if not isinstance(row, dict):
            raise ValueError(f"{label} must contain JSON objects")
        rows.append(row)
    return rows


def _settled_totals(costs_path: Path) -> tuple[float, float]:
    spend = oracle = 0.0
    for row in _cost_rows(costs_path):
        value = row.get("spend_usd")
        oracle_value = row.get("oracle_spend_usd")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            spend += float(value)
        if isinstance(oracle_value, (int, float)) and not isinstance(oracle_value, bool):
            oracle += float(oracle_value)
    return spend, oracle


def _verify_artifact(path: Path, payload_sha256: str | None) -> None:
    try:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise ValueError(
            f"artifact {path.name} is missing or unreadable; its recorded hash "
            "cannot be verified and the run fails closed"
        ) from exc
    if digest != payload_sha256:
        raise ValueError(
            f"artifact {path.name} hash mismatch: the persisted evidence does "
            "not match its checkpoint; failing closed and retaining both"
        )


def _commit(
    run_dir: Path,
    checkpoint: _Checkpoint,
    on_transition: Callable[[str, str], None] | None,
) -> None:
    path = run_dir / "cases" / f"{checkpoint.case_id}.json"
    _atomic_write(path, _canonical_bytes(checkpoint.to_json_dict()))
    if on_transition is not None:
        on_transition(checkpoint.case_id, checkpoint.state)


def _predeclaration(
    cases: Sequence[LiveCase],
    run_id: str,
    manifest_sha256: str,
    preregistration_sha256: str,
    line_slack: int,
    bindings: Mapping[str, ProjectEvaluationBinding],
) -> dict[str, object]:
    """Machine-independent binding of the run design, written before any call.

    Deliberately excludes local filesystem paths so a run can resume from a
    different working checkout of the same immutable inputs.
    """
    reserved_total = 0.0
    rows: list[dict[str, object]] = []
    for live_case in cases:
        request = live_case.request
        reserved = reserved_case_budget_usd(request)
        reserved_total += reserved
        rows.append(
            {
                "case_id": request.case_id,
                "source_id": live_case.source_id,
                "base_ref": request.base_ref,
                "head_ref": request.head_ref,
                "reserved_usd": _rounded(reserved),
                "has_truth": request.truth is not None,
                "evaluation_binding": bindings[request.case_id].to_json_dict(),
            }
        )
    config = cases[0].request.config
    request = cases[0].request
    return {
        "schema_version": LIVE_SCHEMA_VERSION,
        "mode": "live_local",
        "run_id": run_id,
        "manifest_sha256": manifest_sha256,
        "preregistration_sha256": preregistration_sha256,
        "line_slack": line_slack,
        "cases": rows,
        "reserved_total_usd": _rounded(reserved_total),
        "configuration": {
            "alpha": config.alpha,
            "budget_usd": config.budget_usd,
            "model": config.model,
            "k_samples": config.k_samples,
            "max_findings": config.max_findings,
            "auto_tighten_alpha": config.auto_tighten_alpha,
            "tier0_commands": list(config.tier0_commands),
            "differential_repeats": request.repeats,
            "deadline_s": request.deadline_s,
            "verification_timeout_s": request.verification_timeout_s,
            "wall_timeout_s": request.limits.wall_timeout_s,
        },
    }


def _interpreter_identity(interpreter: str) -> str:
    path = Path(interpreter)
    try:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise ValueError(
            f"project interpreter {interpreter!r} is unreadable; drift cannot be bound"
        ) from exc
    return f"{path.resolve()}@sha256:{digest}"


@dataclass
class _Channel:
    predictions: int = 0
    surfaced: int = 0
    withheld: int = 0
    matched: int = 0


@dataclass
class _Stratum:
    cases: int = 0
    surfaced_cases: int = 0
    abstained: int = 0


@dataclass(frozen=True)
class CalibrationReport:
    """Channel-conditioned live calibration evidence, and its own limits.

    ``underlying`` carries the D-032-gated benchmark report this calibration is
    built over. ``accuracy_withheld_reason`` may be stricter than the
    underlying gate: replay provenance withholds accuracy even under a valid
    receipt, because a replayed cassette observes the harness, not the model.
    The report recommends only; it can prohibit a constants patch and it can
    never perform one.
    """

    schema_version: str
    run_id: str
    mode: str
    manifest_sha256: str
    preregistration_sha256: str
    underlying: BenchmarkRunReport
    accuracy_withheld_reason: str | None
    channel_outcomes: Mapping[str, Mapping[str, object]]
    differential_v: Mapping[str, object]
    strata: tuple[Mapping[str, object], ...]
    latency: Mapping[str, object]
    cost: Mapping[str, object]
    paid_calls: tuple[Mapping[str, object], ...]
    sample_sufficiency: Mapping[str, object]
    limitations: tuple[str, ...]
    digest: str = ""

    def to_json_dict(self) -> dict[str, object]:
        payload = self._payload()
        payload["digest"] = self.digest
        return payload

    def _payload(self) -> dict[str, object]:
        underlying = self.underlying.to_json_dict()
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "mode": self.mode,
            "manifest_sha256": self.manifest_sha256,
            "preregistration_sha256": self.preregistration_sha256,
            "protocol_version": underlying["protocol_version"],
            "corpus_commit": underlying["corpus_commit"],
            "evaluated_cases": underlying["evaluated_cases"],
            "scored_runs": underlying["scored_runs"],
            "abstained_cases": underlying["abstained_cases"],
            "excluded_cases": underlying["excluded_cases"],
            "evidence_class_counts": underlying["evidence_class_counts"],
            "accuracy": (
                None if self.accuracy_withheld_reason is not None else underlying["metrics"]
            ),
            "accuracy_withheld_reason": self.accuracy_withheld_reason,
            "operational": underlying["operational"],
            "channel_outcomes": {
                name: dict(entry) for name, entry in sorted(self.channel_outcomes.items())
            },
            "differential_v": dict(self.differential_v),
            "strata": [dict(row) for row in self.strata],
            "latency": dict(self.latency),
            "cost": dict(self.cost),
            "paid_calls": [dict(row) for row in self.paid_calls],
            "sample_sufficiency": dict(self.sample_sufficiency),
            "limitations": list(self.limitations),
        }


def build_calibration_report(
    manifest: BenchmarkManifest,
    payloads: Sequence[Mapping[str, object]],
    *,
    run_id: str,
    mode: str,
    manifest_sha256: str,
    preregistration_sha256: str,
    exclusions: Iterable[ReportExclusion] = (),
    validation_receipt: ValidationReceipt | None = None,
    differential_repeats: int = 0,
    line_slack: int = 0,
    globally_labeled_findings: int | None = None,
    reserved_total_usd: float | None = None,
) -> CalibrationReport:
    """Reduce persisted case payloads to one deterministic calibration report.

    Accuracy passes through the D-032 receipt gate, and replay provenance
    withholds it outright: a replayed run may never be presented as a live
    observation of the model. Every channel-conditioned figure is an empirical
    count, never a likelihood ratio, and below 500 globally labeled findings
    the whole report is ``recommendation_only`` with a constants patch
    prohibited.
    """
    if mode not in (REPLAY_MODE, LIVE_MODE):
        raise ValueError("mode must be replay or live")
    scored: list[Mapping[str, object]] = []
    abstentions: list[ReportAbstention] = []
    excluded: list[ReportExclusion] = list(exclusions)
    for payload in payloads:
        case_id = str(payload.get("case_id"))
        reason = payload.get("abstain_reason")
        if payload.get("task_id") is None:
            excluded.append(ReportExclusion(case_id, str(reason or "not_executed")))
        elif reason is not None:
            abstentions.append(ReportAbstention(case_id, str(reason)))
        else:
            scored.append(payload)
    records = tuple(_run_record(payload) for payload in scored)
    underlying = build_report(
        manifest,
        records,
        mode=mode,
        manifest_sha256=manifest_sha256,
        exclusions=excluded,
        abstentions=abstentions,
        differential_repeats=differential_repeats,
        line_slack=line_slack,
        validation_receipt=validation_receipt,
    )
    accuracy_withheld = (
        ACCURACY_WITHHELD_REPLAY if mode == REPLAY_MODE else underlying.metrics_withheld_reason
    )
    authorized = accuracy_withheld is None and underlying.measurements is not None
    channel_outcomes = _channel_outcomes(
        manifest, scored, authorized=authorized, line_slack=line_slack
    )
    labels = (
        globally_labeled_findings
        if globally_labeled_findings is not None
        else _labeled_findings(underlying, authorized)
    )
    sufficiency = {
        "globally_labeled_findings": labels,
        "minimum_required": MINIMUM_GLOBAL_LABELS,
        "status": "recommendation_only" if labels < MINIMUM_GLOBAL_LABELS else "sufficient",
        "constants_patch": (
            "prohibited" if labels < MINIMUM_GLOBAL_LABELS else "owner_decision_required"
        ),
    }
    report = CalibrationReport(
        schema_version=CALIBRATION_SCHEMA_VERSION,
        run_id=run_id,
        mode=mode,
        manifest_sha256=manifest_sha256,
        preregistration_sha256=preregistration_sha256,
        underlying=underlying,
        accuracy_withheld_reason=accuracy_withheld,
        channel_outcomes=channel_outcomes,
        differential_v=_differential_v(scored),
        strata=_strata(manifest, scored, abstentions),
        latency=_latency(scored),
        cost=_cost(payloads, reserved_total_usd),
        paid_calls=_report_paid_calls(payloads),
        sample_sufficiency=sufficiency,
        limitations=_calibration_limitations(
            mode, labels, accuracy_withheld, len(abstentions)
        ),
    )
    encoded = json.dumps(report._payload(), sort_keys=True, separators=(",", ":"))
    return replace(report, digest=hashlib.sha256(encoded.encode("utf-8")).hexdigest())


def _labeled_findings(underlying: BenchmarkRunReport, authorized: bool) -> int:
    measurements = underlying.measurements
    if not authorized or measurements is None:
        return 0
    return measurements.finding_true_positives + measurements.finding_false_positives


def _channel_outcomes(
    manifest: BenchmarkManifest,
    scored: Sequence[Mapping[str, object]],
    *,
    authorized: bool,
    line_slack: int,
) -> dict[str, dict[str, object]]:
    truths: dict[str, tuple[TruthDefect, ...]] = {}
    for truth in manifest.truth_defects:
        truths[truth.case_id] = truths.get(truth.case_id, ()) + (truth,)
    channels: dict[str, _Channel] = {}
    for payload in scored:
        case_id = str(payload.get("case_id"))
        predictions = _payload_predictions(payload)
        matched_ids: set[str] = set()
        if authorized:
            matches = match_findings(
                truths.get(case_id, ()), predictions, line_slack=line_slack
            )
            matched_ids = {match.finding_id for match in matches if match.matched}
        for prediction in predictions:
            channel = channels.setdefault(prediction.evidence_class, _Channel())
            channel.predictions += 1
            if is_scored_placement(prediction.placement):
                channel.surfaced += 1
                if prediction.finding_id in matched_ids:
                    channel.matched += 1
            else:
                channel.withheld += 1
    return {
        name: {
            "predictions": channel.predictions,
            "surfaced": channel.surfaced,
            "withheld": channel.withheld,
            "matched": channel.matched if authorized else None,
        }
        for name, channel in sorted(channels.items())
    }


def _differential_v(scored: Sequence[Mapping[str, object]]) -> dict[str, object]:
    """Empirical fidelity of the independent differential oracle re-runs."""
    receipts: list[Mapping[str, object]] = []
    for payload in scored:
        rows = payload.get("oracle_receipts")
        if isinstance(rows, list):
            receipts.extend(row for row in rows if isinstance(row, dict))
    statuses = [str(row.get("repro_status")) for row in receipts]
    confirmed = sum(1 for status in statuses if status == _CONFIRMED_STATUS)
    counts: dict[str, int] = {}
    for status in statuses:
        counts[status] = counts.get(status, 0) + 1
    interval = wilson_interval(confirmed, len(receipts))
    return {
        "oracle_receipts": len(receipts),
        "confirmed": confirmed,
        "confirmed_share": (
            None if not receipts else _rounded(confirmed / len(receipts))
        ),
        "confirmed_interval": (
            None if interval is None else [_rounded(interval[0]), _rounded(interval[1])]
        ),
        "status_counts": dict(sorted(counts.items())),
    }


def _strata(
    manifest: BenchmarkManifest,
    scored: Sequence[Mapping[str, object]],
    abstentions: Sequence[ReportAbstention],
) -> tuple[dict[str, object], ...]:
    case_by_id = {case.case_id: case for case in manifest.cases}
    strata: dict[tuple[str, str], _Stratum] = {}

    def stratum_for(case_id: str) -> _Stratum | None:
        case = case_by_id.get(case_id)
        if case is None:
            return None
        return strata.setdefault((case.source_id, case.role), _Stratum())

    for payload in scored:
        stratum = stratum_for(str(payload.get("case_id")))
        if stratum is None:
            continue
        stratum.cases += 1
        if any(
            is_scored_placement(prediction.placement)
            for prediction in _payload_predictions(payload)
        ):
            stratum.surfaced_cases += 1
    for abstention in abstentions:
        stratum = stratum_for(abstention.case_id)
        if stratum is not None:
            stratum.abstained += 1
    return tuple(
        {
            "source_id": source_id,
            "role": role,
            "cases": stratum.cases,
            "surfaced_cases": stratum.surfaced_cases,
            "abstained": stratum.abstained,
        }
        for (source_id, role), stratum in sorted(strata.items())
    )


def _latency(scored: Sequence[Mapping[str, object]]) -> dict[str, object]:
    values = sorted(
        float(value)
        for payload in scored
        if isinstance(value := payload.get("latency_s"), (int, float))
        and not isinstance(value, bool)
    )
    if not values:
        return {"p50_s": None, "p95_s": None, "mean_s": None, "max_s": None}
    return {
        "p50_s": _rounded(values[math.ceil(0.5 * len(values)) - 1]),
        "p95_s": _rounded(values[math.ceil(0.95 * len(values)) - 1]),
        "mean_s": _rounded(sum(values) / len(values)),
        "max_s": _rounded(values[-1]),
    }


def _cost(
    payloads: Sequence[Mapping[str, object]], reserved_total_usd: float | None
) -> dict[str, object]:
    per_case: dict[str, float] = {}
    spend_total = oracle_total = 0.0
    for payload in payloads:
        case_id = str(payload.get("case_id"))
        spend = payload.get("spend_usd")
        oracle = payload.get("oracle_spend_usd")
        if isinstance(spend, (int, float)) and not isinstance(spend, bool):
            per_case[case_id] = float(spend)
            spend_total += float(spend)
        if isinstance(oracle, (int, float)) and not isinstance(oracle, bool):
            oracle_total += float(oracle)
    return {
        "reserved_total_usd": (
            None if reserved_total_usd is None else _rounded(reserved_total_usd)
        ),
        "spend_total_usd": _rounded(spend_total),
        "oracle_spend_total_usd": _rounded(oracle_total),
        "per_case_spend_usd": {
            case_id: _rounded(value) for case_id, value in sorted(per_case.items())
        },
    }


def _report_paid_calls(
    payloads: Sequence[Mapping[str, object]],
) -> tuple[dict[str, object], ...]:
    rows: list[dict[str, object]] = []
    seen: set[str] = set()
    for payload in payloads:
        case_id = str(payload.get("case_id"))
        raw = payload.get("paid_calls", [])
        if not isinstance(raw, list):
            raise ValueError(f"case {case_id} paid-call report binding is invalid")
        for value in raw:
            if not isinstance(value, dict) or not isinstance(value.get("call_id"), str):
                raise ValueError(f"case {case_id} paid-call report row is invalid")
            call_id = str(value["call_id"])
            if call_id in seen:
                raise ValueError(f"paid call {call_id} appears more than once in the report")
            seen.add(call_id)
            rows.append({"case_id": case_id, **value})
    return tuple(sorted(rows, key=lambda row: str(row["call_id"])))


def _calibration_limitations(
    mode: str, labels: int, accuracy_withheld: str | None, abstained: int
) -> tuple[str, ...]:
    notes = [
        (
            "live observation: model responses were sampled from a provider during "
            "this run; every figure is one observation under one configuration, not "
            "a replayable regression."
            if mode == LIVE_MODE
            else "replay provenance: model responses came from recorded cassettes. A "
            "replayed run is a regression check of the harness and product path; "
            "accuracy is never claimed from replay."
        ),
        "calibration_scope: this report recommends and never mutates production "
        "behaviour. Alpha, the S/T/V likelihood ratios, correlation schedules, "
        "channel caps, and every other factory statistical constant are untouched "
        "by construction; adopting any recommendation is a separate owner decision.",
        "channel_outcomes: figures conditioned on differential evidence class are "
        "empirical counts, not likelihood ratios; they price nothing and must not "
        "be read as a channel schedule.",
    ]
    if labels < MINIMUM_GLOBAL_LABELS:
        notes.append(
            f"sample_sufficiency: {labels} globally labeled finding(s) are below the "
            f"{MINIMUM_GLOBAL_LABELS} minimum, so every output is recommendation_only "
            "and a constants patch is prohibited (red line 5)."
        )
    if accuracy_withheld is not None:
        notes.append(
            f"accuracy_withheld ({accuracy_withheld}): no accuracy figure is "
            "published in this report; operational measurements claim no correctness."
        )
    if abstained:
        notes.append(
            f"abstentions: {abstained} case(s) were deferred by the tool and enter "
            "no accuracy numerator or denominator; an abstention is never counted "
            "as correct silence."
        )
    return tuple(notes)


def _run_record(payload: Mapping[str, object]) -> RunRecord:
    case_id = str(payload.get("case_id"))
    run_id = payload.get("run_id") or payload.get("task_id") or case_id
    repeat = payload.get("repeat", 0)
    deadline = payload.get("deadline_s", 0.0)
    delivery = payload.get("delivery_at_s")
    if isinstance(repeat, bool) or not isinstance(repeat, int):
        raise ValueError(f"case {case_id} payload has an invalid repeat")
    if isinstance(deadline, bool) or not isinstance(deadline, (int, float)):
        raise ValueError(f"case {case_id} payload has an invalid deadline")
    if delivery is not None and (
        isinstance(delivery, bool) or not isinstance(delivery, (int, float))
    ):
        raise ValueError(f"case {case_id} payload has an invalid delivery time")
    return RunRecord(
        run_id=str(run_id),
        case_id=case_id,
        repeat=repeat,
        predictions=_payload_predictions(payload),
        delivery_at_s=None if delivery is None else float(delivery),
        deadline_s=float(deadline),
    )


def _payload_predictions(payload: Mapping[str, object]) -> tuple[Prediction, ...]:
    case_id = str(payload.get("case_id"))
    rows = payload.get("predictions")
    if not isinstance(rows, list):
        raise ValueError(f"case {case_id} payload has no prediction list")
    predictions: list[Prediction] = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError(f"case {case_id} payload has an invalid prediction")
        try:
            predictions.append(
                Prediction(
                    finding_id=str(row["finding_id"]),
                    case_id=case_id,
                    file=str(row["file"]),
                    line=int(row["line"]),
                    placement=Placement(str(row["placement"])),
                    action=str(row["action"]),
                    repro_status=str(row["repro_status"]),
                    evidence_class=str(row.get("evidence_class", "indeterminate")),
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(
                f"case {case_id} payload has an invalid prediction"
            ) from exc
    return tuple(predictions)


def render_calibration_markdown(report: CalibrationReport) -> str:
    """Render the same content as the calibration JSON payload, in order."""
    payload = report.to_json_dict()
    lines = [
        "# Attest live calibration report",
        "",
        f"- run: `{report.run_id}`",
        f"- mode: `{report.mode}`",
        f"- manifest SHA-256: `{report.manifest_sha256}`",
        f"- preregistration SHA-256: `{report.preregistration_sha256}`",
        f"- evaluated cases: {payload['evaluated_cases']}",
        f"- report digest: `{report.digest}`",
        "",
        "## Limitations",
        "",
    ]
    lines.extend(f"- {note}" for note in report.limitations)
    lines.extend(["", "## Accuracy", ""])
    accuracy = payload["accuracy"]
    if accuracy is None:
        reason = payload["accuracy_withheld_reason"]
        lines.append(
            "no accuracy figure is published"
            + (f" ({reason})" if reason else "")
            + "; operational measurements claim no correctness."
        )
    else:
        assert isinstance(accuracy, dict)
        lines.extend(_table("metric", accuracy))
    lines.extend(
        [
            "",
            "## Channel-conditioned outcomes",
            "",
            "| evidence class | predictions | surfaced | withheld | matched |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    channels = payload["channel_outcomes"]
    assert isinstance(channels, dict)
    if channels:
        for name, entry in sorted(channels.items()):
            assert isinstance(entry, dict)
            lines.append(
                f"| {name} | {entry['predictions']} | {entry['surfaced']} | "
                f"{entry['withheld']} | {_cell(entry['matched'])} |"
            )
    else:
        lines.append("| (none) | 0 | 0 | 0 | null |")
    differential = payload["differential_v"]
    assert isinstance(differential, dict)
    lines.extend(["", "## Differential V fidelity", ""])
    lines.extend(_table("measurement", differential))
    lines.extend(
        [
            "",
            "## Strata",
            "",
            "| source | role | cases | surfaced | abstained |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    strata = payload["strata"]
    assert isinstance(strata, list)
    if strata:
        for row in strata:
            assert isinstance(row, dict)
            lines.append(
                f"| `{row['source_id']}` | {row['role']} | {row['cases']} | "
                f"{row['surfaced_cases']} | {row['abstained']} |"
            )
    else:
        lines.append("| (none) | (none) | 0 | 0 | 0 |")
    latency = payload["latency"]
    cost = payload["cost"]
    assert isinstance(latency, dict) and isinstance(cost, dict)
    lines.extend(["", "## Latency and cost", ""])
    lines.extend(_table("measurement", {**latency, **{k: v for k, v in cost.items()}}))
    sufficiency = payload["sample_sufficiency"]
    assert isinstance(sufficiency, dict)
    lines.extend(["", "## Sample sufficiency", ""])
    lines.extend(_table("measurement", sufficiency))
    abstained = payload["abstained_cases"]
    excluded = payload["excluded_cases"]
    assert isinstance(abstained, list) and isinstance(excluded, list)
    lines.extend(["", "## Abstentions", "", "| case | reason |", "| --- | --- |"])
    if abstained:
        lines.extend(
            f"| `{row['case_id']}` | {row['reason']} |"
            for row in abstained
            if isinstance(row, dict)
        )
    else:
        lines.append("| (none) | (none) |")
    lines.extend(["", "## Exclusions", "", "| case | reason |", "| --- | --- |"])
    if excluded:
        lines.extend(
            f"| `{row['case_id']}` | {row['reason']} |"
            for row in excluded
            if isinstance(row, dict)
        )
    else:
        lines.append("| (none) | (none) |")
    return "\n".join(lines) + "\n"


def write_calibration_report(
    report: CalibrationReport, output_dir: Path
) -> tuple[Path, Path]:
    """Write deterministic calibration JSON and Markdown via atomic replace."""
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / CALIBRATION_JSON_NAME
    markdown_path = output_dir / CALIBRATION_MARKDOWN_NAME
    _atomic_write(json_path, _canonical_bytes(report.to_json_dict()))
    _atomic_write(markdown_path, render_calibration_markdown(report).encode("utf-8"))
    return json_path, markdown_path


def _table(label: str, payload: Mapping[str, object]) -> list[str]:
    rows = [f"| {label} | value |", "| --- | --- |"]
    for name in sorted(payload):
        rows.append(f"| {name} | {_cell(payload[name])} |")
    return rows


def _cell(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, list):
        return "[" + ", ".join(str(item) for item in value) + "]"
    if isinstance(value, dict):
        return json.dumps(value, sort_keys=True)
    return str(value)


def _rounded(value: float) -> float:
    return round(float(value), 6)


def _canonical_bytes(value: Mapping[str, object] | dict[str, Any]) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode(
        "utf-8"
    )


def _atomic_write(path: Path, payload: bytes) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(payload)
    os.replace(temporary, path)
