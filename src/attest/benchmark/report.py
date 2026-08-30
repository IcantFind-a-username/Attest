"""Deterministic benchmark reports that state what they cannot claim.

Every report carries its own limitations. The five that are easiest to get
wrong, and are therefore always emitted:

* **replay is not observation.** A replayed run measures whether the product
  path still behaves as it did against frozen model responses. It says nothing
  about live model behaviour, and the two are never presented as the same
  measurement.
* **an unevaluated case is an exclusion.** Cases that were not run appear by
  identifier with a reason and never enter any denominator as a negative.
* **an undecided run is an abstention.** A case the tool deferred on -- budget
  exhausted, deadline exceeded, infrastructure failure -- is reported with its
  reason and excluded from every accuracy numerator and denominator. "I could
  not evaluate this" is not "I correctly stayed silent".
* **accuracy needs authorisation.** Precision, recall, and specificity are
  published only when a validation receipt bound to this exact manifest digest
  authorises scoring (D-019). Operational measurements claim no correctness and
  are reported either way.
* **evidence classes are not all failures.** A ``new_code_candidate`` is
  unpriced by design (D-022); lumping it in with unfaithful or unreproduced
  evidence would misrepresent the tool.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path

from attest.benchmark.baselines import (
    ArmRun,
    ComparisonMeasurements,
    validate_comparison_measurements,
)
from attest.benchmark.corpus import ValidationReceipt, require_validated_pair
from attest.benchmark.metrics import (
    ORACLE_INCONCLUSIVE_REASON,
    BenchmarkReport,
    aggregate,
)
from attest.benchmark.schema import BenchmarkCase, BenchmarkManifest, RunRecord
from attest.benchmark.stability import StabilityReport

REPLAY_MODE = "replay"
LIVE_MODE = "live"
REPORT_SCHEMA_VERSION = "2"
JSON_NAME = "report.json"
MARKDOWN_NAME = "report.md"
COMPARISON_SCHEMA_VERSION = "3"
COMPARISON_JSON_NAME = "comparison.json"
COMPARISON_MARKDOWN_NAME = "comparison.md"
STABILITY_JSON_NAME = "stability.json"
STABILITY_MARKDOWN_NAME = "stability.md"
#: Why accuracy metrics were withheld. Each value names a missing authorisation,
#: never a property of the product under evaluation.
RECEIPT_MISSING = "validation_receipt_missing"
RECEIPT_MANIFEST_MISMATCH = "validation_receipt_manifest_mismatch"
RECEIPT_EXCLUDES_PAIR = "validation_receipt_excludes_a_scored_pair"


@dataclass(frozen=True)
class ReportExclusion:
    """One case that was not evaluated, retained for denominator auditing."""

    case_id: str
    reason: str

    def to_json_dict(self) -> dict[str, object]:
        return {"case_id": self.case_id, "reason": self.reason}


@dataclass(frozen=True)
class ReportAbstention:
    """One case the tool could not decide, retained for denominator auditing."""

    case_id: str
    reason: str

    def to_json_dict(self) -> dict[str, object]:
        return {"case_id": self.case_id, "reason": self.reason}


@dataclass(frozen=True)
class BenchmarkRunReport:
    """A scored benchmark run together with the limits of what it shows.

    ``measurements`` is everything the run measured. ``metrics`` is the subset
    this report is allowed to publish as accuracy: it is ``None`` unless a
    manifest-bound validation receipt authorised scoring, and
    ``metrics_withheld_reason`` then says which authorisation was missing.
    """

    schema_version: str
    protocol_version: str
    corpus_commit: str
    manifest_sha256: str
    mode: str
    repeats: int
    differential_repeats: int
    line_slack: int
    evaluated_cases: int
    scored_runs: int
    excluded_cases: tuple[ReportExclusion, ...]
    abstained_cases: tuple[ReportAbstention, ...]
    measurements: BenchmarkReport | None
    metrics_withheld_reason: str | None
    evidence_class_counts: Mapping[str, int]
    limitations: tuple[str, ...]
    digest: str = ""

    @property
    def metrics(self) -> BenchmarkReport | None:
        """Accuracy metrics, or ``None`` while scoring is unauthorised."""
        return None if self.metrics_withheld_reason is not None else self.measurements

    def to_json_dict(self) -> dict[str, object]:
        """Canonical, deterministic payload including its own digest."""
        payload = self._payload()
        payload["digest"] = self.digest
        return payload

    def _payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "protocol_version": self.protocol_version,
            "corpus_commit": self.corpus_commit,
            "manifest_sha256": self.manifest_sha256,
            "mode": self.mode,
            "repeats": self.repeats,
            "differential_repeats": self.differential_repeats,
            "line_slack": self.line_slack,
            "evaluated_cases": self.evaluated_cases,
            "scored_runs": self.scored_runs,
            "excluded_cases": [exclusion.to_json_dict() for exclusion in self.excluded_cases],
            "abstained_cases": [
                abstention.to_json_dict() for abstention in self.abstained_cases
            ],
            "evidence_class_counts": dict(sorted(self.evidence_class_counts.items())),
            "metrics": _metrics_payload(self.metrics),
            "metrics_withheld_reason": self.metrics_withheld_reason,
            "operational": _operational_payload(
                self.measurements, self.abstained_cases, self.excluded_cases
            ),
            "limitations": list(self.limitations),
        }


def build_report(
    manifest: BenchmarkManifest,
    runs: Iterable[RunRecord],
    *,
    mode: str,
    manifest_sha256: str,
    exclusions: Iterable[ReportExclusion] = (),
    abstentions: Iterable[ReportAbstention] = (),
    differential_repeats: int = 0,
    line_slack: int = 0,
    validation_receipt: ValidationReceipt | None = None,
) -> BenchmarkRunReport:
    """Aggregate the evaluated subset and attach its provenance limitations.

    Accuracy is withheld unless ``validation_receipt`` is bound to
    ``manifest_sha256`` and covers every scored pair; the default is refusal,
    because a report that scores without a receipt claims a number it has not
    earned (D-019). Cases the caller lists in ``abstentions`` are reported with
    their reasons and are never handed to :func:`aggregate`, so an undecided run
    can enter no denominator.
    """
    if mode not in (REPLAY_MODE, LIVE_MODE):
        raise ValueError("mode must be replay or live")
    records = tuple(runs)
    abstained = tuple(
        sorted(abstentions, key=lambda abstention: (abstention.case_id, abstention.reason))
    )
    abstained_ids = {abstention.case_id for abstention in abstained}
    if abstained_ids & {run.case_id for run in records}:
        raise ValueError("an abstained case must not also be scored")
    evaluated_ids = {run.case_id for run in records}
    cases = tuple(case for case in manifest.cases if case.case_id in evaluated_ids)
    truths = tuple(
        truth for truth in manifest.truth_defects if truth.case_id in evaluated_ids
    )
    repeats = len({run.repeat for run in records})
    measurements = (
        aggregate(cases, truths, records, line_slack=line_slack) if cases else None
    )
    excluded = tuple(
        sorted(
            (
                *exclusions,
                *(
                    ReportExclusion(exclusion.case_id, exclusion.reason)
                    for exclusion in (
                        () if measurements is None else measurements.excluded_cases
                    )
                ),
            ),
            key=lambda exclusion: (exclusion.case_id, exclusion.reason),
        )
    )
    withheld = (
        None
        if measurements is None
        else _scoring_refusal(validation_receipt, manifest_sha256, cases)
    )
    counts: dict[str, int] = {}
    for run in records:
        if run.repeat != 0:
            continue
        for prediction in run.predictions:
            counts[prediction.evidence_class] = counts.get(prediction.evidence_class, 0) + 1
    report = BenchmarkRunReport(
        schema_version=REPORT_SCHEMA_VERSION,
        protocol_version=manifest.protocol_version,
        corpus_commit=manifest.corpus_commit,
        manifest_sha256=manifest_sha256,
        mode=mode,
        repeats=repeats,
        differential_repeats=differential_repeats,
        line_slack=line_slack,
        evaluated_cases=len(cases),
        scored_runs=sum(1 for run in records if run.repeat == 0),
        excluded_cases=excluded,
        abstained_cases=abstained,
        measurements=measurements,
        metrics_withheld_reason=withheld,
        evidence_class_counts=counts,
        limitations=_limitations(
            manifest,
            mode,
            excluded,
            abstained,
            repeats,
            differential_repeats,
            measurements,
            withheld,
        ),
    )
    return _with_digest(report)


def _scoring_refusal(
    receipt: ValidationReceipt | None,
    manifest_sha256: str,
    cases: tuple[BenchmarkCase, ...],
) -> str | None:
    """Name the missing authorisation, or ``None`` when scoring is authorised.

    The receipt is the corpus validator's own artifact: it exists only after a
    real isolation probe, it is bound to one manifest digest, and it names the
    pairs that probe validated. Nothing here re-derives that judgement.
    """
    if receipt is None:
        return RECEIPT_MISSING
    if receipt.manifest_sha256 != manifest_sha256:
        return RECEIPT_MANIFEST_MISMATCH
    for case in cases:
        try:
            require_validated_pair(receipt, case.pair_id)
        except ValueError:
            return RECEIPT_EXCLUDES_PAIR
    return None


def _with_digest(report: BenchmarkRunReport) -> BenchmarkRunReport:
    encoded = json.dumps(report._payload(), sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    return replace(report, digest=digest)


def _limitations(
    manifest: BenchmarkManifest,
    mode: str,
    excluded: tuple[ReportExclusion, ...],
    abstained: tuple[ReportAbstention, ...],
    repeats: int,
    differential_repeats: int,
    metrics: BenchmarkReport | None,
    withheld: str | None,
) -> tuple[str, ...]:
    provenance = manifest.provenance
    license_status = provenance.license_status if provenance is not None else "UNSPECIFIED"
    notes = [
        f"provenance: corpus metadata comes from commit {manifest.corpus_commit} with "
        f"license status {license_status}; no third-party source is copied into this "
        "repository and no result here is a claim about the upstream projects.",
        "role_labelling: replay cases are inverse developer fixes, recorded honestly as "
        "historical_bug_replay. They are not naturally occurring bug-introducing pull "
        "requests, and detection on them is not evidence about such pull requests.",
    ]
    if mode == REPLAY_MODE:
        notes.append(
            "replay regression: model responses were served from recorded cassettes, so "
            "these numbers show whether the product path still behaves as recorded. They "
            "are not an observation of model behaviour and must never be reported as one."
        )
    else:
        notes.append(
            "live observation: model responses were sampled from a provider during this "
            "run. The result is one observation under one configuration, not a replayable "
            "regression."
        )
    notes.append(
        "evidence_class: results are broken down by differential evidence class. A "
        "new_code_candidate is recorded signal that is unpriced by design (D-022): it "
        "purchases no evidence and must not be reported as a failure alongside "
        "unfaithful or not_reproduced runs."
    )
    notes.append(
        f"repeats: {repeats} run repeat(s) were recorded; only repeat zero is scored. "
        "Repeats are variability observations and never enlarge a Wilson denominator. "
        f"Each differential verification ran {differential_repeats} time(s) per side."
    )
    if excluded:
        note = (
            f"exclusions: {len(excluded)} case(s) were not scored and are listed by "
            "identifier with a reason. None was scored as a silent negative."
        )
        undecided = sum(
            1
            for exclusion in excluded
            if exclusion.reason == ORACLE_INCONCLUSIVE_REASON
        )
        if undecided:
            note += (
                f" {undecided} of them are oracle_inconclusive: the differential "
                "oracle itself could not decide the case, so it has no usable ground "
                "truth and is charged to nobody rather than counted as a false "
                "positive and a false negative at once."
            )
        notes.append(note)
    if abstained:
        notes.append(
            f"abstentions: {len(abstained)} case(s) were deferred by the tool and are "
            "listed by identifier with a reason. An abstention means the tool could "
            "not evaluate the case, so it enters no accuracy numerator and no accuracy "
            "denominator; it is never counted as correct silence."
        )
    if withheld is not None:
        notes.append(
            f"scoring_withheld ({withheld}): accuracy metrics are not reported because "
            "no validation receipt bound to this manifest digest authorised scoring "
            "(D-019). The receipt is issued only after a real isolation probe and names "
            "the pairs it validated. Operational measurements claim no correctness and "
            "are reported."
        )
    if metrics is None:
        notes.append(
            "no_metrics: no case was evaluated, so no rate is reported. An empty run is "
            "not a perfect run."
        )
    return tuple(notes)


def _metrics_payload(metrics: BenchmarkReport | None) -> dict[str, object] | None:
    """Only the fields that claim the product was right or wrong about a case."""
    if metrics is None:
        return None
    return {
        "true_positives": metrics.true_positives,
        "false_positives": metrics.false_positives,
        "false_negatives": metrics.false_negatives,
        "true_negatives": metrics.true_negatives,
        "finding_true_positives": metrics.finding_true_positives,
        "finding_false_positives": metrics.finding_false_positives,
        "clean_false_positive_rate": _number(metrics.clean_false_positive_rate),
        "specificity": _number(metrics.specificity),
        "all_positive_detection": _number(metrics.all_positive_detection),
        "finding_precision": _number(metrics.finding_precision),
        "conditional_recall": _number(metrics.conditional_recall),
        "all_positive_detection_interval": _interval(metrics.all_positive_detection_interval),
        "finding_precision_interval": _interval(metrics.finding_precision_interval),
        "clean_false_positive_rate_interval": _interval(
            metrics.clean_false_positive_rate_interval
        ),
    }


def _operational_payload(
    measurements: BenchmarkReport | None,
    abstained: tuple[ReportAbstention, ...],
    excluded: tuple[ReportExclusion, ...],
) -> dict[str, object]:
    """Counts and timings, which describe the run rather than its correctness.

    These are reported whether or not a receipt authorised scoring: none of
    them asserts that the tool was right about anything.
    """
    return {
        "decided_cases": 0 if measurements is None else measurements.decided_cases,
        "abstained_cases": len(abstained),
        "excluded_cases": len(excluded),
        "duplicate_surfaces": (
            0 if measurements is None else measurements.duplicate_surfaces
        ),
        "silent_run_rate": (
            None if measurements is None else _number(measurements.abstention_rate)
        ),
        "delivery_rate": None if measurements is None else _number(measurements.delivery_rate),
        "delivery_p50_s": (
            None if measurements is None else _number(measurements.delivery_p50_s)
        ),
        "delivery_p95_s": (
            None if measurements is None else _number(measurements.delivery_p95_s)
        ),
        "deadline_censored": 0 if measurements is None else measurements.deadline_censored,
    }


def _number(value: float | None) -> float | None:
    return None if value is None else round(float(value), 6)


def _interval(value: tuple[float, float] | None) -> list[float] | None:
    return None if value is None else [round(value[0], 6), round(value[1], 6)]


def render_markdown(report: BenchmarkRunReport) -> str:
    """Render the same content as the JSON payload, in the same order."""
    lines = [
        "# Attest benchmark report",
        "",
        f"- protocol version: `{report.protocol_version}`",
        f"- mode: `{report.mode}`",
        f"- corpus commit: `{report.corpus_commit}`",
        f"- manifest SHA-256: `{report.manifest_sha256}`",
        f"- evaluated cases: {report.evaluated_cases}",
        f"- scored runs (repeat zero): {report.scored_runs}",
        f"- run repeats recorded: {report.repeats}",
        f"- differential repeats per side: {report.differential_repeats}",
        f"- line slack: {report.line_slack}",
        f"- report digest: `{report.digest}`",
        "",
        "## Limitations",
        "",
    ]
    lines.extend(f"- {note}" for note in report.limitations)
    lines.extend(["", "## Metrics", ""])
    metrics = report.metrics
    if metrics is not None:
        lines.extend(_value_table("metric", _metrics_payload(metrics)))
    elif report.metrics_withheld_reason is not None:
        lines.append(
            f"withheld ({report.metrics_withheld_reason}): no validation receipt bound "
            "to this manifest digest authorised scoring (D-019), so no accuracy metric "
            "is reported. The operational measurements below claim no correctness."
        )
    else:
        lines.append(
            "no case was evaluated, so no rate is reported; an empty run is not a "
            "perfect run."
        )
    lines.extend(
        [
            "",
            "## Operational",
            "",
            "counts and timings only; `silent_run_rate` is the share of decided runs "
            "that surfaced nothing, which is not an abstention.",
            "",
        ]
    )
    lines.extend(
        _value_table(
            "measurement",
            _operational_payload(
                report.measurements, report.abstained_cases, report.excluded_cases
            ),
        )
    )
    lines.extend(["", "## Evidence classes", "", "| class | count |", "| --- | --- |"])
    if report.evidence_class_counts:
        lines.extend(
            f"| {name} | {count} |"
            for name, count in sorted(report.evidence_class_counts.items())
        )
    else:
        lines.append("| (none) | 0 |")
    lines.extend(["", "## Abstentions", "", "| case | reason |", "| --- | --- |"])
    if report.abstained_cases:
        lines.extend(
            f"| `{abstention.case_id}` | {abstention.reason} |"
            for abstention in report.abstained_cases
        )
    else:
        lines.append("| (none) | (none) |")
    lines.extend(["", "## Exclusions", "", "| case | reason |", "| --- | --- |"])
    if report.excluded_cases:
        lines.extend(
            f"| `{exclusion.case_id}` | {exclusion.reason} |"
            for exclusion in report.excluded_cases
        )
    else:
        lines.append("| (none) | (none) |")
    return "\n".join(lines) + "\n"


def _value_table(label: str, payload: Mapping[str, object] | None) -> list[str]:
    assert payload is not None
    rows = [f"| {label} | value |", "| --- | --- |"]
    for name in sorted(payload):
        rows.append(f"| {name} | {_cell(payload[name])} |")
    return rows


def _cell(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, list):
        return "[" + ", ".join(f"{item:.6f}" for item in value) + "]"
    if isinstance(value, float):
        return f"{value:.6f}"
    return str(value)


def write_report(report: BenchmarkRunReport, output_dir: Path) -> tuple[Path, Path]:
    """Write deterministic JSON and Markdown reports via atomic replace."""
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / JSON_NAME
    markdown_path = output_dir / MARKDOWN_NAME
    _atomic_write(
        json_path,
        (
            json.dumps(report.to_json_dict(), sort_keys=True, separators=(",", ":"))
            + "\n"
        ).encode("utf-8"),
    )
    _atomic_write(markdown_path, render_markdown(report).encode("utf-8"))
    return json_path, markdown_path


@dataclass(frozen=True)
class ComparisonRunReport:
    """The three-arm comparison plus the limits of what it may publish.

    ``measurements`` always carries everything the arms measured. Accuracy is
    published only under a manifest-bound validation receipt (D-019/D-032);
    ``metrics_withheld_reason`` otherwise names the missing authorisation, and
    the payload then omits every per-arm accuracy block and every
    finding-to-truth match. Operational accounting -- calls, tokens, spend,
    wall time, deterministic-tool cost -- claims no correctness and is always
    published, as are losing arms and failed or deferred runs.
    """

    schema_version: str
    protocol_version: str
    corpus_commit: str
    manifest_sha256: str
    mode: str
    line_slack: int
    budget_ceiling_usd: float
    measurements: ComparisonMeasurements
    excluded_cases: tuple[ReportExclusion, ...]
    metrics_withheld_reason: str | None
    limitations: tuple[str, ...]
    digest: str = ""

    def to_json_dict(self) -> dict[str, object]:
        payload = self._payload()
        payload["digest"] = self.digest
        return payload

    def _payload(self) -> dict[str, object]:
        authorized = self.metrics_withheld_reason is None
        return {
            "schema_version": self.schema_version,
            "protocol_version": self.protocol_version,
            "corpus_commit": self.corpus_commit,
            "manifest_sha256": self.manifest_sha256,
            "mode": self.mode,
            "line_slack": self.line_slack,
            "budget_ceiling_usd": round(self.budget_ceiling_usd, 6),
            "evaluated_cases": len(self.measurements.evaluated_case_ids),
            "arms": [
                {
                    "arm": summary.arm,
                    "description": summary.description,
                    "evidence_class_counts": dict(
                        sorted(summary.evidence_class_counts.items())
                    ),
                    "abstentions": [row.to_json_dict() for row in summary.abstentions],
                    "operational": summary.operational.to_json_dict(),
                    "accuracy": summary.accuracy.to_json_dict() if authorized else None,
                }
                for summary in self.measurements.arms
            ],
            "runs": [_arm_run_payload(run, authorized) for run in self.measurements.runs],
            "excluded_cases": [row.to_json_dict() for row in self.excluded_cases],
            "metrics_withheld_reason": self.metrics_withheld_reason,
            "limitations": list(self.limitations),
        }


def _arm_run_payload(run: ArmRun, authorized: bool) -> dict[str, object]:
    findings: list[dict[str, object]] = []
    for index, finding in enumerate(run.findings):
        row: dict[str, object] = {
            "file": finding.file,
            "line": finding.line,
            "evidence_class": finding.evidence_class,
        }
        if authorized:
            matched = (
                run.matched_defect_ids[index]
                if index < len(run.matched_defect_ids)
                else None
            )
            row["matched_defect_id"] = matched
        findings.append(row)
    return {
        "arm": run.arm,
        "case_id": run.case_id,
        "role": run.role,
        "status": run.status,
        "abstain_reason": run.abstain_reason,
        "findings": findings,
        "model_calls": run.model_calls,
        "input_tokens": run.input_tokens,
        "output_tokens": run.output_tokens,
        "spend_usd": _number(run.spend_usd),
        "oracle_spend_usd": _number(run.oracle_spend_usd),
        "total_spend_usd": _number(run.spend_usd + run.oracle_spend_usd),
        "wall_time_s": _number(run.wall_time_s),
        "tool_cost_s": _number(run.tool_cost_s),
        "paid_calls": [dict(record) for record in run.paid_calls],
        "paid_calls_sha256": run.paid_calls_sha256,
        "model_id": run.model_id,
    }


def build_comparison_report(
    manifest: BenchmarkManifest,
    measurements: ComparisonMeasurements,
    *,
    manifest_sha256: str,
    mode: str = REPLAY_MODE,
    exclusions: Iterable[ReportExclusion] = (),
    validation_receipt: ValidationReceipt | None = None,
) -> ComparisonRunReport:
    """Attach provenance limitations and apply the receipt gate to a comparison.

    The gate is the same one the replay report uses: accuracy defaults to
    refusal, and only a receipt bound to this exact manifest digest that covers
    every evaluated pair lifts it.
    """
    if mode not in (REPLAY_MODE, LIVE_MODE):
        raise ValueError("mode must be replay or live")
    validate_comparison_measurements(measurements)
    evaluated_ids = set(measurements.evaluated_case_ids)
    cases = tuple(case for case in manifest.cases if case.case_id in evaluated_ids)
    withheld = (
        None if not cases else _scoring_refusal(validation_receipt, manifest_sha256, cases)
    )
    excluded = tuple(
        sorted(exclusions, key=lambda exclusion: (exclusion.case_id, exclusion.reason))
    )
    report = ComparisonRunReport(
        schema_version=COMPARISON_SCHEMA_VERSION,
        protocol_version=manifest.protocol_version,
        corpus_commit=manifest.corpus_commit,
        manifest_sha256=manifest_sha256,
        mode=mode,
        line_slack=measurements.line_slack,
        budget_ceiling_usd=measurements.budget_ceiling_usd,
        measurements=measurements,
        excluded_cases=excluded,
        metrics_withheld_reason=withheld,
        limitations=_comparison_limitations(mode, measurements, excluded, withheld),
    )
    encoded = json.dumps(report._payload(), sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    return replace(report, digest=digest)


def _comparison_limitations(
    mode: str,
    measurements: ComparisonMeasurements,
    excluded: tuple[ReportExclusion, ...],
    withheld: str | None,
) -> tuple[str, ...]:
    deferred_runs = sum(1 for run in measurements.runs if run.status != "completed")
    notes = [
        (
            "replay regression: model responses were served from recorded cassettes, "
            "so these numbers show whether each arm still behaves as recorded. They "
            "are not an observation of live model behaviour."
            if mode == REPLAY_MODE
            else "live observation: model responses were sampled from a provider "
            "during this run; the result is one observation under one configuration."
        ),
        "losing_arms: every arm's results are reported, including losing arms and "
        f"the {deferred_runs} failed or deferred run(s); no selective omission.",
        "static_arm: the ruff_static arm is a deterministic static analyzer. It is "
        "not an AI reviewer, and its numbers must never be presented as evidence "
        "about one.",
        "verification: only the product arm can purchase differential verification. "
        "Matching uses preregistered location truth alone, and every finding "
        "records its evidence class, so an unverified claim is never presented as "
        "a verified one.",
        "intervals: every accuracy denominator and Wilson interval uses repeat zero "
        "only; repeats never enlarge them.",
        "abstentions: a run an arm could not decide -- tool unavailable, invalid "
        "response, budget refusal, crash -- is a DEFER carried with its reason. It "
        "enters no accuracy numerator or denominator and is never inferred to be a "
        "negative label.",
        "product_accounting: the product arm's call and token totals include the "
        "benchmark oracle's independent re-verification; that oracle spend is "
        "disclosed separately as oracle_spend_usd and is not product cost.",
    ]
    if excluded:
        notes.append(
            f"exclusions: {len(excluded)} case(s) were not evaluated by any arm and "
            "are listed by identifier with a reason; none is a silent negative."
        )
    if withheld is not None:
        notes.append(
            f"scoring_withheld ({withheld}): accuracy-flavoured metrics are not "
            "reported because no validation receipt bound to this manifest digest "
            "authorised scoring (D-019). Operational accounting claims no "
            "correctness and is reported."
        )
    return tuple(notes)


def render_comparison_markdown(report: ComparisonRunReport) -> str:
    """Render the same content as the comparison JSON payload, arm by arm."""
    payload = report._payload()
    lines = [
        "# Attest three-arm comparison",
        "",
        f"- protocol version: `{report.protocol_version}`",
        f"- mode: `{report.mode}`",
        f"- corpus commit: `{report.corpus_commit}`",
        f"- manifest SHA-256: `{report.manifest_sha256}`",
        f"- per-case USD ceiling: {report.budget_ceiling_usd:.6f}",
        f"- line slack: {report.line_slack}",
        f"- evaluated cases: {len(report.measurements.evaluated_case_ids)}",
        f"- report digest: `{report.digest}`",
        "",
        "## Limitations",
        "",
    ]
    lines.extend(f"- {note}" for note in report.limitations)
    arms = payload["arms"]
    assert isinstance(arms, list)
    for arm in arms:
        assert isinstance(arm, dict)
        lines.extend(["", f"## Arm `{arm['arm']}`", "", str(arm["description"]), ""])
        lines.extend(["### Operational", ""])
        operational = arm["operational"]
        assert isinstance(operational, dict)
        lines.extend(_value_table("measurement", operational))
        lines.extend(["", "### Accuracy", ""])
        accuracy = arm["accuracy"]
        if accuracy is None:
            lines.append(
                "withheld: no validation receipt bound to this manifest digest "
                "authorised scoring (D-019)."
            )
        else:
            assert isinstance(accuracy, dict)
            lines.extend(_value_table("metric", accuracy))
        lines.extend(["", "### Evidence classes", "", "| class | count |", "| --- | --- |"])
        counts = arm["evidence_class_counts"]
        assert isinstance(counts, dict)
        if counts:
            lines.extend(f"| {name} | {count} |" for name, count in sorted(counts.items()))
        else:
            lines.append("| (none) | 0 |")
        lines.extend(["", "### Abstentions", "", "| case | reason |", "| --- | --- |"])
        abstentions = arm["abstentions"]
        assert isinstance(abstentions, list)
        if abstentions:
            lines.extend(
                f"| `{row['case_id']}` | {row['reason']} |"
                for row in abstentions
                if isinstance(row, dict)
            )
        else:
            lines.append("| (none) | (none) |")
    lines.extend(["", "## Exclusions", "", "| case | reason |", "| --- | --- |"])
    if report.excluded_cases:
        lines.extend(
            f"| `{row.case_id}` | {row.reason} |" for row in report.excluded_cases
        )
    else:
        lines.append("| (none) | (none) |")
    return "\n".join(lines) + "\n"


def write_comparison_report(
    report: ComparisonRunReport, output_dir: Path
) -> tuple[Path, Path]:
    """Write deterministic comparison JSON and Markdown via atomic replace."""
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / COMPARISON_JSON_NAME
    markdown_path = output_dir / COMPARISON_MARKDOWN_NAME
    _atomic_write(
        json_path,
        (
            json.dumps(report.to_json_dict(), sort_keys=True, separators=(",", ":"))
            + "\n"
        ).encode("utf-8"),
    )
    _atomic_write(markdown_path, render_comparison_markdown(report).encode("utf-8"))
    return json_path, markdown_path


def render_stability_markdown(report: StabilityReport) -> str:
    """Render the stability report; every number here is operational."""
    payload = report.to_json_dict()
    lines = [
        "# Attest repeat-stability report",
        "",
        f"- case: `{report.case_id}`",
        f"- manifest SHA-256: `{report.manifest_sha256}`",
        f"- provider: `{report.provider_label}`",
        f"- repeats: {report.repeats}",
        f"- report digest: `{report.digest}`",
        "",
        "## Limitations",
        "",
    ]
    lines.extend(f"- {note}" for note in report.limitations)
    lines.extend(
        [
            "",
            "## Run outcomes",
            "",
            "| repeat | run id | outcome | candidates | product spend (USD) | "
            "oracle spend (USD) | total spend (USD) |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for repeat in range(report.repeats):
        lines.append(
            f"| {repeat} | `{report.run_ids[repeat]}` | {report.outcomes[repeat]} | "
            f"{report.candidate_counts[repeat]} | "
            f"{report.product_spend_per_run_usd[repeat]:.6f} | "
            f"{report.oracle_spend_per_run_usd[repeat]:.6f} | "
            f"{report.total_spend_per_run_usd[repeat]:.6f} |"
        )
    lines.extend(
        [
            "",
            f"modal outcome: `{report.modal_outcome}` "
            f"(stability {report.run_outcome_stability:.6f})",
            "",
            "## Clusters",
            "",
            "| cluster | modal decision | modal share | present | wealth mean | "
            "wealth variance | wealth range |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    if report.clusters:
        for cluster in report.clusters:
            lines.append(
                f"| `{cluster.cluster_id}` | {cluster.modal_decision} | "
                f"{cluster.modal_share:.6f} | {cluster.runs_present} | "
                f"{_cell(cluster.wealth_mean)} | {_cell(cluster.wealth_variance)} | "
                f"{_cell(cluster.wealth_range)} |"
            )
    else:
        lines.append("| (none) | (none) | (none) | 0 | null | null | null |")
    dispersion_payload = {
        key: payload[key]
        for key in (
            "mean_pairwise_jaccard",
            "jaccard_pairs",
            "candidate_count_mean",
            "candidate_count_variance",
            "latency_mean_s",
            "latency_min_s",
            "latency_max_s",
            "product_spend_total_usd",
            "oracle_spend_total_usd",
            "total_spend_total_usd",
            "total_spend_mean_usd",
            "wealth_mean",
            "wealth_variance",
            "wealth_range",
        )
    }
    lines.extend(["", "## Dispersion", ""])
    lines.extend(_value_table("measurement", dispersion_payload))
    lines.extend(["", "## Defers", "", "| repeat | reason |", "| --- | --- |"])
    if report.deferred_runs:
        lines.extend(f"| {row.repeat} | {row.reason} |" for row in report.deferred_runs)
    else:
        lines.append("| (none) | (none) |")
    return "\n".join(lines) + "\n"


def write_stability_report(
    report: StabilityReport, output_dir: Path
) -> tuple[Path, Path]:
    """Write deterministic stability JSON and Markdown via atomic replace."""
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / STABILITY_JSON_NAME
    markdown_path = output_dir / STABILITY_MARKDOWN_NAME
    _atomic_write(
        json_path,
        (
            json.dumps(report.to_json_dict(), sort_keys=True, separators=(",", ":"))
            + "\n"
        ).encode("utf-8"),
    )
    _atomic_write(markdown_path, render_stability_markdown(report).encode("utf-8"))
    return json_path, markdown_path


def _atomic_write(path: Path, payload: bytes) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(payload)
    os.replace(temporary, path)
