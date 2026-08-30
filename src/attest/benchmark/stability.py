"""Ten-repeat stability measurement for one preregistered benchmark case.

The study asks one question: given identical diff bytes and identical
configuration, how much does the product's behaviour vary run to run? Exactly
:data:`STABILITY_REPEATS` independent provider runs are executed through the
real product path (D-025), cross-run findings are grouped by canonical file
and preregistered location cluster -- never by claim prose -- and every failed
or missing run is carried as a DEFER instead of being dropped.

Receipt discipline (D-019/D-032): every number this module emits is
**operational**. Stability measures agreement between runs, spend, latency,
and wealth dispersion; none of it claims the tool was right or wrong about the
case. The clustering consumes only the product-visible ``changed_locations``
metadata, never the hidden truth, so no validation receipt is required and no
accuracy figure can appear here. Repeats are variability observations: they
never enter an accuracy numerator or denominator anywhere (``metrics.aggregate``
scores repeat zero only), and this report carries that limitation explicitly.

Resumption: each completed repeat is persisted atomically to its own state
file before the next one starts, so an interruption never duplicates a paid
provider call. The study predeclares its case, repeat count, and provider
configuration in ``study.json``; resuming under a drifted configuration fails
closed rather than silently mixing incomparable runs.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from attest.benchmark.api import (
    ProjectEvaluationRequest,
    build_evaluation_binding,
    current_runtime_identity,
    evaluate_project,
    freeze_evaluation_request,
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
from attest.benchmark.metrics import dispersion, mean_pairwise_jaccard
from attest.benchmark.schema import ChangedLocation, is_scored_placement
from attest.review.proposer import Provider, ProviderResult

#: The preregistered repeat count. Ten is part of the study design, not a knob.
STABILITY_REPEATS = 10
STABILITY_PREDECLARATION_SCHEMA_VERSION = "5"
STABILITY_REPORT_SCHEMA_VERSION = "4"
_OBSERVATION_SCHEMA_VERSION = "3"

_OUTCOME_SURFACED = "surfaced"
_OUTCOME_SILENT = "silent"
_OUTCOME_DEFERRED = "deferred"
_DECISION_ABSENT = "absent"
_DECISION_DEFERRED = "deferred"


@dataclass(frozen=True)
class SurfacedAnchor:
    """One author-visible finding, reduced to what stability may compare on."""

    file: str
    line: int
    placement: str
    action: str
    evidence_class: str
    wealth_final: float | None

    def to_json_dict(self) -> dict[str, object]:
        return {
            "file": self.file,
            "line": self.line,
            "placement": self.placement,
            "action": self.action,
            "evidence_class": self.evidence_class,
            "wealth_final": self.wealth_final,
        }


@dataclass(frozen=True)
class StabilityObservation:
    """Everything one repeat produced, persisted before the next repeat runs."""

    repeat: int
    run_id: str
    status: str
    abstain_reason: str | None
    surfaced: tuple[SurfacedAnchor, ...]
    candidate_count: int
    latency_s: float
    product_spend_usd: float
    oracle_spend_usd: float
    total_spend_usd: float
    delivery_at_s: float | None
    call_count: int = 0
    call_evidence_sha256: str = hashlib.sha256(b"[]").hexdigest()

    @property
    def outcome(self) -> str:
        if self.status == "deferred":
            return _OUTCOME_DEFERRED
        return _OUTCOME_SURFACED if self.surfaced else _OUTCOME_SILENT

    def to_json_dict(self) -> dict[str, object]:
        return {
            "schema_version": _OBSERVATION_SCHEMA_VERSION,
            "repeat": self.repeat,
            "run_id": self.run_id,
            "status": self.status,
            "abstain_reason": self.abstain_reason,
            "surfaced": [anchor.to_json_dict() for anchor in self.surfaced],
            "candidate_count": self.candidate_count,
            "latency_s": self.latency_s,
            "product_spend_usd": self.product_spend_usd,
            "oracle_spend_usd": self.oracle_spend_usd,
            "total_spend_usd": self.total_spend_usd,
            "delivery_at_s": self.delivery_at_s,
            "call_count": self.call_count,
            "call_evidence_sha256": self.call_evidence_sha256,
        }

    @classmethod
    def from_json_dict(cls, raw: object) -> StabilityObservation:
        if not isinstance(raw, dict):
            raise ValueError("observation must be an object")
        version = raw.get("schema_version")
        if version != _OBSERVATION_SCHEMA_VERSION:
            raise ValueError(
                f"unsupported observation schema version {version!r}; supported version "
                f"is {_OBSERVATION_SCHEMA_VERSION}"
            )
        repeat = raw.get("repeat")
        if not isinstance(repeat, int) or isinstance(repeat, bool) or repeat < 0:
            raise ValueError("observation repeat must be a non-negative integer")
        run_id = raw.get("run_id")
        status = raw.get("status")
        if not isinstance(run_id, str) or not run_id:
            raise ValueError("observation run_id must be a non-empty string")
        if status not in ("completed", "deferred"):
            raise ValueError("observation status must be completed or deferred")
        reason = raw.get("abstain_reason")
        if reason is not None and not isinstance(reason, str):
            raise ValueError("observation abstain_reason must be a string or null")
        surfaced_raw = raw.get("surfaced")
        if not isinstance(surfaced_raw, list):
            raise ValueError("observation surfaced must be a list")
        surfaced = tuple(_anchor_from_json(entry) for entry in surfaced_raw)
        candidate_count = raw.get("candidate_count")
        if (
            not isinstance(candidate_count, int)
            or isinstance(candidate_count, bool)
            or candidate_count < 0
        ):
            raise ValueError("observation candidate_count must be a non-negative integer")
        call_count = raw.get("call_count")
        call_evidence_sha256 = raw.get("call_evidence_sha256")
        if (
            not isinstance(call_count, int)
            or isinstance(call_count, bool)
            or call_count < 0
        ):
            raise ValueError("observation call_count must be a non-negative integer")
        if (
            not isinstance(call_evidence_sha256, str)
            or len(call_evidence_sha256) != 64
            or any(character not in "0123456789abcdef" for character in call_evidence_sha256)
        ):
            raise ValueError("observation call_evidence_sha256 must be a SHA-256 digest")
        return cls(
            repeat=repeat,
            run_id=run_id,
            status=status,
            abstain_reason=reason,
            surfaced=surfaced,
            candidate_count=candidate_count,
            latency_s=_finite_number(raw.get("latency_s"), "latency_s"),
            product_spend_usd=_finite_number(
                raw.get("product_spend_usd"), "product_spend_usd"
            ),
            oracle_spend_usd=_finite_number(
                raw.get("oracle_spend_usd"), "oracle_spend_usd"
            ),
            total_spend_usd=_finite_number(
                raw.get("total_spend_usd"), "total_spend_usd"
            ),
            delivery_at_s=(
                None
                if raw.get("delivery_at_s") is None
                else _finite_number(raw.get("delivery_at_s"), "delivery_at_s")
            ),
            call_count=call_count,
            call_evidence_sha256=call_evidence_sha256,
        )


def _anchor_from_json(raw: object) -> SurfacedAnchor:
    if not isinstance(raw, dict):
        raise ValueError("surfaced anchor must be an object")
    file = raw.get("file")
    line = raw.get("line")
    if not isinstance(file, str) or not file:
        raise ValueError("surfaced anchor file must be a non-empty string")
    if not isinstance(line, int) or isinstance(line, bool) or line < 1:
        raise ValueError("surfaced anchor line must be a positive integer")
    placement = raw.get("placement")
    action = raw.get("action")
    evidence_class = raw.get("evidence_class")
    if (
        not isinstance(placement, str)
        or not isinstance(action, str)
        or not isinstance(evidence_class, str)
    ):
        raise ValueError("surfaced anchor decisions must be strings")
    wealth = raw.get("wealth_final")
    if wealth is not None and not isinstance(wealth, (int, float)):
        raise ValueError("surfaced anchor wealth_final must be a number or null")
    return SurfacedAnchor(
        file=file,
        line=line,
        placement=placement,
        action=action,
        evidence_class=evidence_class,
        wealth_final=None if wealth is None else float(wealth),
    )


def _finite_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"observation {label} must be a number")
    return float(value)


@dataclass(frozen=True)
class DeferredRun:
    """One repeat the product could not decide, with its recorded reason."""

    repeat: int
    reason: str

    def to_json_dict(self) -> dict[str, object]:
        return {"repeat": self.repeat, "reason": self.reason}


@dataclass(frozen=True)
class ClusterStability:
    """Cross-run agreement for one canonical file and location cluster."""

    cluster_id: str
    file: str
    start_line: int
    end_line: int
    decisions: tuple[str, ...]
    modal_decision: str
    modal_share: float
    runs_present: int
    wealth_mean: float | None
    wealth_variance: float | None
    wealth_range: float | None

    def to_json_dict(self) -> dict[str, object]:
        return {
            "cluster_id": self.cluster_id,
            "file": self.file,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "decisions": list(self.decisions),
            "modal_decision": self.modal_decision,
            "modal_share": _rounded(self.modal_share),
            "runs_present": self.runs_present,
            "wealth_mean": _rounded(self.wealth_mean),
            "wealth_variance": _rounded(self.wealth_variance),
            "wealth_range": _rounded(self.wealth_range),
        }


@dataclass(frozen=True)
class StabilityReport:
    """Operational variability of one case under ten identical-input runs."""

    schema_version: str
    case_id: str
    manifest_sha256: str
    provider_label: str
    repeats: int
    run_ids: tuple[str, ...]
    outcomes: tuple[str, ...]
    modal_outcome: str
    run_outcome_stability: float
    deferred_runs: tuple[DeferredRun, ...]
    clusters: tuple[ClusterStability, ...]
    mean_pairwise_jaccard: float | None
    jaccard_pairs: int
    candidate_counts: tuple[int, ...]
    candidate_count_mean: float | None
    candidate_count_variance: float | None
    latency_mean_s: float | None
    latency_min_s: float | None
    latency_max_s: float | None
    product_spend_per_run_usd: tuple[float, ...]
    oracle_spend_per_run_usd: tuple[float, ...]
    total_spend_per_run_usd: tuple[float, ...]
    paid_call_counts: tuple[int, ...]
    paid_call_reconciliation_sha256: tuple[str, ...]
    product_spend_total_usd: float
    oracle_spend_total_usd: float
    total_spend_total_usd: float
    total_spend_mean_usd: float
    wealth_mean: float | None
    wealth_variance: float | None
    wealth_range: float | None
    limitations: tuple[str, ...]
    digest: str = ""

    @property
    def spend_total_usd(self) -> float:
        """Compatibility alias for callers that need the all-role total."""
        return self.total_spend_total_usd

    def to_json_dict(self) -> dict[str, object]:
        payload = self._payload()
        payload["digest"] = self.digest
        return payload

    def _payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "case_id": self.case_id,
            "manifest_sha256": self.manifest_sha256,
            "provider_label": self.provider_label,
            "repeats": self.repeats,
            "run_ids": list(self.run_ids),
            "outcomes": list(self.outcomes),
            "modal_outcome": self.modal_outcome,
            "run_outcome_stability": _rounded(self.run_outcome_stability),
            "deferred_runs": [row.to_json_dict() for row in self.deferred_runs],
            "clusters": [cluster.to_json_dict() for cluster in self.clusters],
            "mean_pairwise_jaccard": _rounded(self.mean_pairwise_jaccard),
            "jaccard_pairs": self.jaccard_pairs,
            "candidate_counts": list(self.candidate_counts),
            "candidate_count_mean": _rounded(self.candidate_count_mean),
            "candidate_count_variance": _rounded(self.candidate_count_variance),
            "latency_mean_s": _rounded(self.latency_mean_s),
            "latency_min_s": _rounded(self.latency_min_s),
            "latency_max_s": _rounded(self.latency_max_s),
            "product_spend_per_run_usd": [
                _rounded(value) for value in self.product_spend_per_run_usd
            ],
            "oracle_spend_per_run_usd": [
                _rounded(value) for value in self.oracle_spend_per_run_usd
            ],
            "total_spend_per_run_usd": [
                _rounded(value) for value in self.total_spend_per_run_usd
            ],
            "paid_call_counts": list(self.paid_call_counts),
            "paid_call_reconciliation_sha256": list(
                self.paid_call_reconciliation_sha256
            ),
            "product_spend_total_usd": _rounded(self.product_spend_total_usd),
            "oracle_spend_total_usd": _rounded(self.oracle_spend_total_usd),
            "total_spend_total_usd": _rounded(self.total_spend_total_usd),
            "total_spend_mean_usd": _rounded(self.total_spend_mean_usd),
            "wealth_mean": _rounded(self.wealth_mean),
            "wealth_variance": _rounded(self.wealth_variance),
            "wealth_range": _rounded(self.wealth_range),
            "limitations": list(self.limitations),
        }


@dataclass(frozen=True)
class StabilityStudyResult:
    """The finished report plus this invocation's execute/resume accounting.

    The split stays out of the report on purpose: whether a repeat was
    executed now or resumed from state is a fact about the invocation, and a
    resumed study must produce a byte-identical report.
    """

    report: StabilityReport
    executed_repeats: int
    resumed_repeats: int


def summarize_stability(
    *,
    case_id: str,
    manifest_sha256: str,
    observations: tuple[StabilityObservation, ...],
    locations: tuple[ChangedLocation, ...],
    line_slack: int = 0,
    provider_label: str = "unspecified",
) -> StabilityReport:
    """Reduce exactly ten persisted observations to one operational report."""
    if line_slack < 0:
        raise ValueError("line_slack must not be negative")
    if len(observations) != STABILITY_REPEATS:
        raise ValueError(
            f"a stability study requires exactly ten observations, got {len(observations)}"
        )
    ordered = tuple(sorted(observations, key=lambda observation: observation.repeat))
    if [observation.repeat for observation in ordered] != list(range(STABILITY_REPEATS)):
        raise ValueError("observations must cover repeat 0 through 9 exactly once")
    if any(
        not _same_cost(
            observation.total_spend_usd,
            observation.product_spend_usd + observation.oracle_spend_usd,
        )
        for observation in ordered
    ):
        raise ValueError("observation total spend must equal product plus oracle spend")
    if any(
        isinstance(observation.call_count, bool)
        or not isinstance(observation.call_count, int)
        or observation.call_count < 0
        or not isinstance(observation.call_evidence_sha256, str)
        or len(observation.call_evidence_sha256) != 64
        or any(
            character not in "0123456789abcdef"
            for character in observation.call_evidence_sha256
        )
        for observation in ordered
    ):
        raise ValueError("observation paid-call reconciliation binding is invalid")

    outcomes = tuple(observation.outcome for observation in ordered)
    modal_outcome, modal_count = _modal(outcomes)
    deferred = tuple(
        DeferredRun(observation.repeat, observation.abstain_reason or "unspecified")
        for observation in ordered
        if observation.outcome == _OUTCOME_DEFERRED
    )
    completed = tuple(
        observation for observation in ordered if observation.outcome != _OUTCOME_DEFERRED
    )

    cluster_keys: dict[str, tuple[str, int, int]] = {}
    anchors_by_run: list[dict[str, SurfacedAnchor]] = []
    for observation in ordered:
        present: dict[str, SurfacedAnchor] = {}
        for anchor in observation.surfaced:
            cluster_id, span = _cluster(anchor, locations, line_slack)
            cluster_keys.setdefault(cluster_id, span)
            present.setdefault(cluster_id, anchor)
        anchors_by_run.append(present)

    clusters = tuple(
        _cluster_stability(cluster_id, cluster_keys[cluster_id], ordered, anchors_by_run)
        for cluster_id in sorted(cluster_keys)
    )

    surface_sets = [
        frozenset(anchors_by_run[observation.repeat])
        for observation in completed
    ]
    jaccard = mean_pairwise_jaccard(surface_sets)
    jaccard_pairs = len(surface_sets) * (len(surface_sets) - 1) // 2

    candidate_counts = tuple(observation.candidate_count for observation in ordered)
    candidate_spread = dispersion(
        [float(observation.candidate_count) for observation in completed]
    )
    latency_spread = dispersion([observation.latency_s for observation in completed])
    latencies = [observation.latency_s for observation in completed]
    product_spend_per_run = tuple(
        observation.product_spend_usd for observation in ordered
    )
    oracle_spend_per_run = tuple(
        observation.oracle_spend_usd for observation in ordered
    )
    total_spend_per_run = tuple(
        observation.total_spend_usd for observation in ordered
    )
    wealth_values = [
        anchor.wealth_final
        for observation in ordered
        for anchor in observation.surfaced
        if anchor.wealth_final is not None
    ]
    wealth_spread = dispersion(wealth_values)

    report = StabilityReport(
        schema_version=STABILITY_REPORT_SCHEMA_VERSION,
        case_id=case_id,
        manifest_sha256=manifest_sha256,
        provider_label=provider_label,
        repeats=STABILITY_REPEATS,
        run_ids=tuple(observation.run_id for observation in ordered),
        outcomes=outcomes,
        modal_outcome=modal_outcome,
        run_outcome_stability=modal_count / STABILITY_REPEATS,
        deferred_runs=deferred,
        clusters=clusters,
        mean_pairwise_jaccard=jaccard,
        jaccard_pairs=jaccard_pairs,
        candidate_counts=candidate_counts,
        candidate_count_mean=None if candidate_spread is None else candidate_spread.mean,
        candidate_count_variance=(
            None if candidate_spread is None else candidate_spread.variance
        ),
        latency_mean_s=None if latency_spread is None else latency_spread.mean,
        latency_min_s=min(latencies) if latencies else None,
        latency_max_s=max(latencies) if latencies else None,
        product_spend_per_run_usd=product_spend_per_run,
        oracle_spend_per_run_usd=oracle_spend_per_run,
        total_spend_per_run_usd=total_spend_per_run,
        paid_call_counts=tuple(observation.call_count for observation in ordered),
        paid_call_reconciliation_sha256=tuple(
            observation.call_evidence_sha256 for observation in ordered
        ),
        product_spend_total_usd=sum(product_spend_per_run),
        oracle_spend_total_usd=sum(oracle_spend_per_run),
        total_spend_total_usd=sum(total_spend_per_run),
        total_spend_mean_usd=sum(total_spend_per_run) / STABILITY_REPEATS,
        wealth_mean=None if wealth_spread is None else wealth_spread.mean,
        wealth_variance=None if wealth_spread is None else wealth_spread.variance,
        wealth_range=None if wealth_spread is None else wealth_spread.value_range,
        limitations=_limitations(deferred),
        digest="",
    )
    return _with_digest(report)


def run_stability_study(
    request: ProjectEvaluationRequest,
    *,
    provider_factory: Callable[[int], Provider],
    state_dir: Path,
    locations: tuple[ChangedLocation, ...],
    manifest_sha256: str,
    line_slack: int = 0,
    provider_label: str = "injected",
    clock: Callable[[], float] = time.monotonic,
    on_call_transition: Callable[[int, str, str], None] | None = None,
) -> StabilityStudyResult:
    """Execute or resume the ten-repeat study, one atomic state file per repeat.

    A repeat whose state file already exists is loaded, never re-executed: the
    file is written only after the repeat finished, so resuming cannot
    duplicate a paid provider call. A corrupt state file fails the study
    closed -- guessing would either lose a paid observation or buy it twice.
    """
    if request.truth is not None:
        raise ValueError(
            "stability is an operational study: it consumes no hidden truth and "
            "must not be given any"
        )
    runtime = current_runtime_identity()
    binding = build_evaluation_binding(
        request,
        provider_id=provider_label,
        interpreter_id=runtime.interpreter_id,
        environment_sha256=runtime.environment_sha256,
        code_sha256=runtime.code_sha256,
    )
    request = freeze_evaluation_request(request, binding)
    predeclaration = _predeclaration(
        request, manifest_sha256, line_slack, provider_label, binding.to_json_dict()
    )
    call_binding_sha256 = hashlib.sha256(
        json.dumps(predeclaration, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()
    state_dir.mkdir(parents=True, exist_ok=True)
    study_path = state_dir / "study.json"
    if study_path.exists():
        try:
            stored = json.loads(study_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("stability study predeclaration is unreadable") from exc
        if (
            not isinstance(stored, dict)
            or stored.get("schema_version")
            != STABILITY_PREDECLARATION_SCHEMA_VERSION
        ):
            version = stored.get("schema_version") if isinstance(stored, dict) else None
            raise ValueError(
                f"unsupported stability predeclaration schema version {version!r}; "
                f"supported version is {STABILITY_PREDECLARATION_SCHEMA_VERSION}. Use "
                "the compatible reader and retain all paid-call state; never coerce "
                "old rows."
            )
        if stored != predeclaration:
            raise ValueError(
                "stability study predeclaration does not match this configuration; "
                "refusing to mix incomparable runs"
            )
    else:
        _atomic_write_json(study_path, predeclaration)

    observations: list[StabilityObservation] = []
    executed = resumed = 0
    for repeat in range(STABILITY_REPEATS):
        path = state_dir / f"repeat-{repeat}.json"
        if path.exists():
            observation = _load_observation(path, repeat)
            checkpointed = CheckpointedProvider(
                _NoDispatchProvider(),
                root=state_dir / f"repeat-{repeat}-calls",
                trial_id=f"{request.case_id}:repeat-{repeat}",
                model_id=request.config.model,
                binding_sha256=call_binding_sha256,
                role=CALL_ROLE_PRODUCT,
            )
            records = checkpointed.reconciliation_records()
            totals = paid_call_totals(records)
            call_count, call_evidence_sha256 = _call_evidence_binding(records)
            if (
                observation.call_count != call_count
                or observation.call_evidence_sha256 != call_evidence_sha256
            ):
                raise ValueError(
                    f"stability repeat {repeat} paid-call evidence binding does not match "
                    "its persisted observation"
                )
            _require_observation_costs(repeat, observation, totals)
            resumed += 1
        else:
            provider = provider_factory(repeat)
            transition: Callable[[str, str], None] | None = None
            if on_call_transition is not None:

                def notify_transition(
                    call_id: str, state: str, current: int = repeat
                ) -> None:
                    on_call_transition(current, call_id, state)

                transition = notify_transition

            checkpointed = CheckpointedProvider(
                provider,
                root=state_dir / f"repeat-{repeat}-calls",
                trial_id=f"{request.case_id}:repeat-{repeat}",
                model_id=request.config.model,
                binding_sha256=call_binding_sha256,
                role=CALL_ROLE_PRODUCT,
                on_transition=transition,
            )
            observation = _observe(request, repeat, checkpointed, clock)
            records = checkpointed.reconciliation_records()
            totals = paid_call_totals(records)
            call_count, call_evidence_sha256 = _call_evidence_binding(records)
            observation = replace(
                observation,
                product_spend_usd=totals.product_usd,
                oracle_spend_usd=totals.oracle_usd,
                total_spend_usd=totals.total_usd,
                call_count=call_count,
                call_evidence_sha256=call_evidence_sha256,
            )
            _atomic_write_json(path, observation.to_json_dict())
            executed += 1
        observations.append(observation)

    report = summarize_stability(
        case_id=request.case_id,
        manifest_sha256=manifest_sha256,
        observations=tuple(observations),
        locations=locations,
        line_slack=line_slack,
        provider_label=provider_label,
    )
    return StabilityStudyResult(
        report=report, executed_repeats=executed, resumed_repeats=resumed
    )


class _NoDispatchProvider:
    """Verify resumed call evidence without constructing a remote provider."""

    def sample(
        self,
        system: str,
        prompt: str,
        schema: dict[str, Any],
        max_tokens: int,
        *,
        timeout_s: float | None = None,
    ) -> ProviderResult:
        raise AssertionError("completed stability evidence must never dispatch")


def _call_evidence_binding(
    records: tuple[dict[str, object], ...],
) -> tuple[int, str]:
    payload = json.dumps(records, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return len(records), hashlib.sha256(payload).hexdigest()


def _require_observation_costs(
    repeat: int, observation: StabilityObservation, totals: PaidCallTotals
) -> None:
    if (
        not _same_cost(observation.product_spend_usd, totals.product_usd)
        or not _same_cost(observation.oracle_spend_usd, totals.oracle_usd)
        or not _same_cost(observation.total_spend_usd, totals.total_usd)
    ):
        raise ValueError(
            f"stability repeat {repeat} spend does not match authoritative role evidence"
        )


def _same_cost(left: float, right: float) -> bool:
    return abs(left - right) <= 1e-12


def _observe(
    request: ProjectEvaluationRequest,
    repeat: int,
    provider: Provider,
    clock: Callable[[], float],
) -> StabilityObservation:
    prepared = replace(
        request,
        repeat=repeat,
        workspace_root=request.workspace_root / f"repeat-{repeat}",
    )
    try:
        assert isinstance(provider, CheckpointedProvider)
        result = evaluate_project(
            prepared,
            provider=provider,
            oracle_provider=provider.for_role(CALL_ROLE_BENCHMARK_ORACLE),
            clock=clock,
        )
    except AmbiguousCostError:
        raise
    except Exception as exc:  # noqa: BLE001 - a failed run is a DEFER, never dropped
        return StabilityObservation(
            repeat=repeat,
            run_id=f"{request.case_id}-repeat-{repeat}-deferred",
            status="deferred",
            abstain_reason=f"{type(exc).__name__}: {exc}",
            surfaced=(),
            candidate_count=0,
            latency_s=0.0,
            product_spend_usd=0.0,
            oracle_spend_usd=0.0,
            total_spend_usd=0.0,
            delivery_at_s=None,
        )
    wealth_by_finding: dict[str, float] = {}
    for decision in result.final_decisions:
        finding_id = decision.get("finding_id")
        wealth = decision.get("wealth_final")
        if isinstance(finding_id, str) and isinstance(wealth, (int, float)):
            wealth_by_finding[finding_id] = float(wealth)
    deferred = result.abstain_reason is not None
    surfaced = (
        ()
        if deferred
        else tuple(
            SurfacedAnchor(
                file=prediction.file,
                line=prediction.line,
                placement=prediction.placement.value,
                action=prediction.action,
                evidence_class=prediction.evidence_class,
                wealth_final=wealth_by_finding.get(prediction.finding_id),
            )
            for prediction in result.predictions
            if is_scored_placement(prediction.placement)
        )
    )
    return StabilityObservation(
        repeat=repeat,
        run_id=result.run.run_id,
        status="deferred" if deferred else "completed",
        abstain_reason=result.abstain_reason,
        surfaced=surfaced,
        candidate_count=len(result.final_decisions),
        latency_s=result.latency_s,
        product_spend_usd=0.0,
        oracle_spend_usd=0.0,
        total_spend_usd=0.0,
        delivery_at_s=result.run.delivery_at_s,
    )


def _load_observation(path: Path, repeat: int) -> StabilityObservation:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        observation = StabilityObservation.from_json_dict(raw)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError(
            f"stability state {path.name} is corrupt; refusing to guess whether the "
            "run was paid for"
        ) from exc
    if observation.repeat != repeat:
        raise ValueError(
            f"stability state {path.name} records repeat {observation.repeat}"
        )
    return observation


def _predeclaration(
    request: ProjectEvaluationRequest,
    manifest_sha256: str,
    line_slack: int,
    provider_label: str,
    binding: Mapping[str, object],
) -> dict[str, object]:
    """Machine-independent binding of the study design before any run.

    Deliberately excludes local filesystem paths so a study can resume from a
    different working checkout of the same immutable inputs.
    """
    config = request.config
    return {
        "schema_version": STABILITY_PREDECLARATION_SCHEMA_VERSION,
        "paid_call_roles": sorted(CALL_ROLES),
        "case_id": request.case_id,
        "manifest_sha256": manifest_sha256,
        "repeats": STABILITY_REPEATS,
        "base_ref": request.base_ref,
        "head_ref": request.head_ref,
        "line_slack": line_slack,
        "provider_label": provider_label,
        "evaluation_binding": dict(binding),
        "seeds": None,
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


def _cluster(
    anchor: SurfacedAnchor,
    locations: tuple[ChangedLocation, ...],
    line_slack: int,
) -> tuple[str, tuple[str, int, int]]:
    """Cluster key for one anchor: nearest preregistered location, else itself."""
    file = _normal_path(anchor.file)
    best: ChangedLocation | None = None
    best_distance = line_slack + 1
    for location in locations:
        if _normal_path(location.path) != file:
            continue
        distance = _distance(anchor.line, location.start_line, location.end_line)
        if distance <= line_slack and distance < best_distance:
            best = location
            best_distance = distance
    if best is not None:
        return (
            f"{file}:{best.start_line}-{best.end_line}",
            (file, best.start_line, best.end_line),
        )
    return f"{file}:{anchor.line}", (file, anchor.line, anchor.line)


def _cluster_stability(
    cluster_id: str,
    span: tuple[str, int, int],
    ordered: tuple[StabilityObservation, ...],
    anchors_by_run: list[dict[str, SurfacedAnchor]],
) -> ClusterStability:
    decisions: list[str] = []
    wealth_values: list[float] = []
    present = 0
    for observation in ordered:
        if observation.outcome == _OUTCOME_DEFERRED:
            decisions.append(_DECISION_DEFERRED)
            continue
        anchor = anchors_by_run[observation.repeat].get(cluster_id)
        if anchor is None:
            decisions.append(_DECISION_ABSENT)
            continue
        present += 1
        decisions.append(anchor.placement)
        if anchor.wealth_final is not None:
            wealth_values.append(anchor.wealth_final)
    modal_decision, modal_count = _modal(tuple(decisions))
    wealth_spread = dispersion(wealth_values)
    file, start_line, end_line = span
    return ClusterStability(
        cluster_id=cluster_id,
        file=file,
        start_line=start_line,
        end_line=end_line,
        decisions=tuple(decisions),
        modal_decision=modal_decision,
        modal_share=modal_count / STABILITY_REPEATS,
        runs_present=present,
        wealth_mean=None if wealth_spread is None else wealth_spread.mean,
        wealth_variance=None if wealth_spread is None else wealth_spread.variance,
        wealth_range=None if wealth_spread is None else wealth_spread.value_range,
    )


def _modal(values: tuple[str, ...]) -> tuple[str, int]:
    counts = Counter(values)
    top = max(counts.values())
    winner = min(value for value, count in counts.items() if count == top)
    return winner, top


def _limitations(deferred: tuple[DeferredRun, ...]) -> tuple[str, ...]:
    notes = [
        "operational_only: every number here measures run-to-run variability of the "
        "product under one fixed configuration. None is an accuracy claim, no hidden "
        "truth was consulted, and therefore no validation receipt is required or "
        "checked (D-019/D-032).",
        "repeats: the ten runs are variability observations of one case. They never "
        "enter any accuracy numerator or denominator -- scoring elsewhere uses repeat "
        "zero only -- and stability shares must not be combined with detection or "
        "precision figures.",
        "clusters: cross-run findings are grouped by canonical file and preregistered "
        "changed-location cluster, never by claim prose. A stable cluster is a "
        "consistent behaviour, not a correct one.",
        "seeds: the provider interface exposes no sampling seed, so repeats are "
        "independent samples under an identical configuration rather than seeded "
        "replicas.",
    ]
    if deferred:
        notes.append(
            f"defers: {len(deferred)} run(s) failed or could not decide and are carried "
            "as DEFER with their reasons. They stay in every stability denominator and "
            "are never dropped or scored as silence."
        )
    return tuple(notes)


def _distance(line: int, start_line: int, end_line: int) -> int:
    if start_line <= line <= end_line:
        return 0
    return min(abs(line - start_line), abs(line - end_line))


def _normal_path(path: str) -> str:
    return path.replace("\\", "/")


def _rounded(value: float | None) -> float | None:
    return None if value is None else round(float(value), 6)


def _with_digest(report: StabilityReport) -> StabilityReport:
    encoded = json.dumps(report._payload(), sort_keys=True, separators=(",", ":"))
    return replace(report, digest=hashlib.sha256(encoded.encode("utf-8")).hexdigest())


def _atomic_write_json(path: Path, payload: Mapping[str, object]) -> None:
    encoded = (
        json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(encoded)
    os.replace(temporary, path)
