"""Deterministic benchmark reports that state what they cannot claim.

Every report carries its own limitations. The three that are easiest to get
wrong, and are therefore always emitted:

* **replay is not observation.** A replayed run measures whether the product
  path still behaves as it did against frozen model responses. It says nothing
  about live model behaviour, and the two are never presented as the same
  measurement.
* **an unevaluated case is an exclusion.** Cases that were not run appear by
  identifier with a reason and never enter any denominator as a negative.
* **evidence classes are not all failures.** A ``new_code_candidate`` is
  unpriced by design (D-022); lumping it in with unfaithful or unreproduced
  evidence would misrepresent the tool.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from attest.benchmark.metrics import BenchmarkReport, aggregate
from attest.benchmark.schema import BenchmarkManifest, RunRecord

REPLAY_MODE = "replay"
LIVE_MODE = "live"
REPORT_SCHEMA_VERSION = "1"
JSON_NAME = "report.json"
MARKDOWN_NAME = "report.md"


@dataclass(frozen=True)
class ReportExclusion:
    """One case that was not evaluated, retained for denominator auditing."""

    case_id: str
    reason: str

    def to_json_dict(self) -> dict[str, object]:
        return {"case_id": self.case_id, "reason": self.reason}


@dataclass(frozen=True)
class BenchmarkRunReport:
    """A scored benchmark run together with the limits of what it shows."""

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
    metrics: BenchmarkReport | None
    evidence_class_counts: Mapping[str, int]
    limitations: tuple[str, ...]
    digest: str = ""

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
            "evidence_class_counts": dict(sorted(self.evidence_class_counts.items())),
            "metrics": _metrics_payload(self.metrics),
            "limitations": list(self.limitations),
        }


def build_report(
    manifest: BenchmarkManifest,
    runs: Iterable[RunRecord],
    *,
    mode: str,
    manifest_sha256: str,
    exclusions: Iterable[ReportExclusion] = (),
    differential_repeats: int = 0,
    line_slack: int = 0,
) -> BenchmarkRunReport:
    """Aggregate the evaluated subset and attach its provenance limitations."""
    if mode not in (REPLAY_MODE, LIVE_MODE):
        raise ValueError("mode must be replay or live")
    records = tuple(runs)
    evaluated_ids = {run.case_id for run in records}
    cases = tuple(case for case in manifest.cases if case.case_id in evaluated_ids)
    truths = tuple(
        truth for truth in manifest.truth_defects if truth.case_id in evaluated_ids
    )
    excluded = tuple(
        sorted(exclusions, key=lambda exclusion: (exclusion.case_id, exclusion.reason))
    )
    repeats = len({run.repeat for run in records})
    metrics = aggregate(cases, truths, records, line_slack=line_slack) if cases else None
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
        metrics=metrics,
        evidence_class_counts=counts,
        limitations=_limitations(
            manifest, mode, excluded, repeats, differential_repeats, metrics
        ),
    )
    return _with_digest(report)


def _with_digest(report: BenchmarkRunReport) -> BenchmarkRunReport:
    encoded = json.dumps(report._payload(), sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    return BenchmarkRunReport(
        schema_version=report.schema_version,
        protocol_version=report.protocol_version,
        corpus_commit=report.corpus_commit,
        manifest_sha256=report.manifest_sha256,
        mode=report.mode,
        repeats=report.repeats,
        differential_repeats=report.differential_repeats,
        line_slack=report.line_slack,
        evaluated_cases=report.evaluated_cases,
        scored_runs=report.scored_runs,
        excluded_cases=report.excluded_cases,
        metrics=report.metrics,
        evidence_class_counts=report.evidence_class_counts,
        limitations=report.limitations,
        digest=digest,
    )


def _limitations(
    manifest: BenchmarkManifest,
    mode: str,
    excluded: tuple[ReportExclusion, ...],
    repeats: int,
    differential_repeats: int,
    metrics: BenchmarkReport | None,
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
        notes.append(
            f"exclusions: {len(excluded)} case(s) were not evaluated and are listed by "
            "identifier with a reason. None was scored as a silent negative."
        )
    if metrics is None:
        notes.append(
            "no_metrics: no case was evaluated, so no rate is reported. An empty run is "
            "not a perfect run."
        )
    return tuple(notes)


def _metrics_payload(metrics: BenchmarkReport | None) -> dict[str, object] | None:
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
        "abstention_rate": _number(metrics.abstention_rate),
        "duplicate_surfaces": metrics.duplicate_surfaces,
        "delivery_rate": _number(metrics.delivery_rate),
        "delivery_p50_s": _number(metrics.delivery_p50_s),
        "delivery_p95_s": _number(metrics.delivery_p95_s),
        "deadline_censored": metrics.deadline_censored,
        "all_positive_detection_interval": _interval(metrics.all_positive_detection_interval),
        "finding_precision_interval": _interval(metrics.finding_precision_interval),
        "clean_false_positive_rate_interval": _interval(
            metrics.clean_false_positive_rate_interval
        ),
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
    if report.metrics is None:
        lines.append(
            "no case was evaluated, so no rate is reported; an empty run is not a "
            "perfect run."
        )
    else:
        lines.extend(_metrics_table(report.metrics))
    lines.extend(["", "## Evidence classes", "", "| class | count |", "| --- | --- |"])
    if report.evidence_class_counts:
        lines.extend(
            f"| {name} | {count} |"
            for name, count in sorted(report.evidence_class_counts.items())
        )
    else:
        lines.append("| (none) | 0 |")
    lines.extend(["", "## Exclusions", "", "| case | reason |", "| --- | --- |"])
    if report.excluded_cases:
        lines.extend(
            f"| `{exclusion.case_id}` | {exclusion.reason} |"
            for exclusion in report.excluded_cases
        )
    else:
        lines.append("| (none) | (none) |")
    return "\n".join(lines) + "\n"


def _metrics_table(metrics: BenchmarkReport) -> list[str]:
    payload = _metrics_payload(metrics)
    assert payload is not None
    rows = ["| metric | value |", "| --- | --- |"]
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


def _atomic_write(path: Path, payload: bytes) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(payload)
    os.replace(temporary, path)
