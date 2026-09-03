"""E-04 prospective natural-PR shadow (mainline §2 step 15, `G-SHADOW-001`).

The collector observes the product on traffic that arrives *after* the protocol is
frozen, with no author-visible side effect: every trial runs the local review path
(``attest.review.run.run_review``), which owns no GitHub client, and records what the
CI path would have published -- the same ``run_verification_stage`` decides both, so
shadow on/off publication identity is a property of the code, checked by a fixture.

Fail-closed preflight (the work order's RED): no authorization, an unfrozen
preregistration, a sample recorded after an outcome, a zero or missing silent-audit
inclusion probability, a missing paid opt-in, or insufficient development-cap headroom
each refuse with their own reason before any provider client exists. The report never
treats unknown truth as clean: eligible detection is ``INSUFFICIENT`` until every audited
unit has a product-blind resolved label and the preregistered minimum is met.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from attest.benchmark.live import read_devspend

STUDY_SCHEMA_VERSION = "attest.e04-prospective.v1"
PROTOCOL_FILES = ("protocol.md", "preregistration.json", "authorization.json")
FREEZE_FILE = "preregistration.sha256"
SAMPLE_FILE = "sample.jsonl"
TRIALS_FILE = "trials.jsonl"
ADJUDICATION_FILE = "adjudication.jsonl"
MINIMUM_CONFIRMED_OPPORTUNITIES = 100  # G-SHADOW-001 primary analysis
MINIMUM_ADJUDICATED_FINDINGS = 100

REASON_PAID_API_NOT_ALLOWED = "paid_api_not_allowed"
REASON_AUTHORIZATION_MISSING = "authorization_missing"
REASON_PREREGISTRATION_NOT_FROZEN = "preregistration_not_frozen"
REASON_PREREGISTRATION_INVALID = "preregistration_invalid"
REASON_SAMPLE_AFTER_OUTCOMES = "sample_recorded_after_outcomes"
REASON_INCLUSION_PROBABILITY_INVALID = "silent_inclusion_probability_invalid"
REASON_INSUFFICIENT_HEADROOM = "insufficient_development_cap_headroom"

_KEY_ENV = "ANTHROPIC_API_KEY"
_MINIMUM_KEY_LENGTH = 16


class ProspectivePreflightError(ValueError):
    def __init__(self, reason: str, message: str) -> None:
        self.reason = reason
        super().__init__(f"{reason}: {message}")


def _utc(value: object) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError("timestamp must be an ISO-8601 string")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must carry a timezone")
    return parsed.astimezone(UTC)


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must hold a JSON object")
    return value


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            if isinstance(row, dict):
                rows.append(row)
    return rows


def _append_jsonl(path: Path, row: Mapping[str, object]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")


def protocol_digest(study_dir: Path) -> str:
    """SHA-256 over the protocol, preregistration and authorization bytes, in order."""
    digest = hashlib.sha256()
    for name in PROTOCOL_FILES:
        digest.update((study_dir / name).read_bytes())
        digest.update(b"\x00")
    return digest.hexdigest()


def freeze(study_dir: Path) -> str:
    """Write the freeze digest; after this the protocol files are immutable."""
    digest = protocol_digest(study_dir)
    (study_dir / FREEZE_FILE).write_text(f"{digest}  protocol+preregistration+authorization\n")
    return digest


@dataclass(frozen=True)
class Preregistration:
    freeze_at: str
    population: tuple[str, ...]  # repository names the authorization grants
    per_pr_budget_usd: float
    k_samples: int
    silent_audit_inclusion_probability: float
    silent_audit_seed: int
    cost_cap_usd: float
    safety_stop_wrong_findings: int
    # A stratum whose units already existed when the protocol was frozen is not
    # prospective, and saying so is the point: `G-SHADOW-001` asks for units the
    # product could not have seen. A stratum must declare `prospective: false`
    # explicitly to record such units; the default stays the strong reading, and
    # every sample row and report carries the flag so no reader can lose it.
    prospective: bool = True

    @classmethod
    def from_json(cls, raw: Mapping[str, Any]) -> Preregistration:
        try:
            value = cls(
                freeze_at=str(raw["freeze_at"]),
                population=tuple(str(item) for item in raw["population"]),
                per_pr_budget_usd=float(raw["per_pr_budget_usd"]),
                k_samples=int(raw["k_samples"]),
                silent_audit_inclusion_probability=float(raw["silent_audit_inclusion_probability"]),
                silent_audit_seed=int(raw["silent_audit_seed"]),
                cost_cap_usd=float(raw["cost_cap_usd"]),
                safety_stop_wrong_findings=int(raw["safety_stop_wrong_findings"]),
                prospective=bool(raw.get("prospective", True)),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ProspectivePreflightError(
                REASON_PREREGISTRATION_INVALID, f"preregistration.json: {exc}"
            ) from exc
        _utc(value.freeze_at)
        if not value.population:
            raise ProspectivePreflightError(
                REASON_PREREGISTRATION_INVALID, "population must name a repository"
            )
        for amount in (value.per_pr_budget_usd, value.cost_cap_usd):
            if not math.isfinite(amount) or amount <= 0:
                raise ProspectivePreflightError(
                    REASON_PREREGISTRATION_INVALID, "budgets must be finite and positive"
                )
        if value.k_samples < 1 or value.safety_stop_wrong_findings < 1:
            raise ProspectivePreflightError(
                REASON_PREREGISTRATION_INVALID, "k_samples and the safety stop must be >= 1"
            )
        probability = value.silent_audit_inclusion_probability
        if not math.isfinite(probability) or not 0 < probability <= 1:
            raise ProspectivePreflightError(
                REASON_INCLUSION_PROBABILITY_INVALID,
                "the silent-audit inclusion probability must lie in (0, 1]: a silent unit "
                "with no chance of adjudication cannot enter a design-weighted estimate",
            )
        return value


@dataclass(frozen=True)
class ProspectivePreflight:
    protocol_sha256: str
    freeze_at: str
    population: tuple[str, ...]
    sampled_units: int
    trials_recorded: int
    reserved_usd: float
    headroom_usd: float

    def to_json_dict(self) -> dict[str, object]:
        return asdict(self)


def load_preregistration(study_dir: Path) -> Preregistration:
    return Preregistration.from_json(_read_json(study_dir / "preregistration.json"))


def preflight_prospective(
    study_dir: Path,
    *,
    devspend_path: Path,
    env: Mapping[str, str],
    allow_paid_api: bool,
    reserve_usd: float = 0.0,
) -> ProspectivePreflight:
    """Every authorization the study needs, checked in a fixed order, each with its
    own refusal reason; nothing paid can be constructed before this returns."""
    if not allow_paid_api:
        raise ProspectivePreflightError(
            REASON_PAID_API_NOT_ALLOWED,
            "the prospective shadow is a paid study; pass --allow-paid-api explicitly",
        )
    key = env.get(_KEY_ENV, "")
    if len(key) < _MINIMUM_KEY_LENGTH:
        raise ProspectivePreflightError(
            REASON_PAID_API_NOT_ALLOWED, f"{_KEY_ENV} is missing or implausibly short"
        )
    authorization_path = study_dir / "authorization.json"
    if not authorization_path.is_file():
        raise ProspectivePreflightError(
            REASON_AUTHORIZATION_MISSING, "authorization.json is absent: no traffic is authorized"
        )
    authorization = _read_json(authorization_path)
    for key_name in ("authorized_by", "granted_at", "population", "scope"):
        if not authorization.get(key_name):
            raise ProspectivePreflightError(
                REASON_AUTHORIZATION_MISSING, f"authorization.json lacks {key_name}"
            )
    freeze_path = study_dir / FREEZE_FILE
    try:
        frozen = freeze_path.read_text(encoding="utf-8").split()[0]
    except (OSError, IndexError) as exc:
        raise ProspectivePreflightError(
            REASON_PREREGISTRATION_NOT_FROZEN,
            f"no freeze digest at {freeze_path}; freeze the protocol before sampling",
        ) from exc
    try:
        current = protocol_digest(study_dir)
    except OSError as exc:
        raise ProspectivePreflightError(
            REASON_PREREGISTRATION_NOT_FROZEN, "a protocol file is missing"
        ) from exc
    if current != frozen:
        raise ProspectivePreflightError(
            REASON_PREREGISTRATION_NOT_FROZEN,
            "protocol, preregistration or authorization bytes differ from the freeze digest",
        )
    preregistration = load_preregistration(study_dir)
    authorized = {str(item) for item in authorization["population"]}
    if not set(preregistration.population) <= authorized:
        raise ProspectivePreflightError(
            REASON_AUTHORIZATION_MISSING,
            "the preregistered population names a repository the authorization does not",
        )
    if _utc(authorization["granted_at"]) > _utc(preregistration.freeze_at):
        raise ProspectivePreflightError(
            REASON_AUTHORIZATION_MISSING, "authorization was granted after the freeze"
        )
    freeze_at = _utc(preregistration.freeze_at)
    samples = _read_jsonl(study_dir / SAMPLE_FILE)
    trials = _read_jsonl(study_dir / TRIALS_FILE)
    recorded_by_unit: dict[object, datetime] = {}
    for row in samples:
        try:
            recorded_at = _utc(row.get("recorded_at"))
        except ValueError as exc:
            raise ProspectivePreflightError(
                REASON_SAMPLE_AFTER_OUTCOMES,
                f"sampled unit {row.get('unit_id')} has no valid recorded_at timestamp",
            ) from exc
        probability = row.get("silent_audit_inclusion_probability")
        if (
            not isinstance(probability, int | float)
            or isinstance(probability, bool)
            or not 0 < float(probability) <= 1
        ):
            raise ProspectivePreflightError(
                REASON_INCLUSION_PROBABILITY_INVALID,
                f"sampled unit {row.get('unit_id')} has no valid inclusion probability",
            )
        if recorded_at < freeze_at:
            raise ProspectivePreflightError(
                REASON_SAMPLE_AFTER_OUTCOMES,
                f"unit {row.get('unit_id')} was recorded before the freeze: not prospective",
            )
        recorded_by_unit.setdefault(row.get("unit_id"), recorded_at)
    # selection precedes its own outcome: every trial's unit was recorded, with its
    # inclusion probability, before that trial ran (traffic arriving after earlier
    # outcomes is recorded as it arrives; nothing is chosen by outcome)
    for trial in trials:
        unit_id = trial.get("unit_id")
        try:
            trial_at = _utc(trial.get("recorded_at"))
        except ValueError as exc:
            raise ProspectivePreflightError(
                REASON_SAMPLE_AFTER_OUTCOMES, f"trial for {unit_id} has no valid timestamp"
            ) from exc
        selected_at = recorded_by_unit.get(unit_id)
        if selected_at is None or selected_at > trial_at:
            raise ProspectivePreflightError(
                REASON_SAMPLE_AFTER_OUTCOMES,
                f"unit {unit_id} has an outcome recorded before its selection; "
                "selection must precede its own outcome",
            )
    total, cap = read_devspend(devspend_path)
    headroom = cap - total - reserve_usd
    if reserve_usd < 0 or not math.isfinite(headroom) or headroom < 0:
        raise ProspectivePreflightError(
            REASON_INSUFFICIENT_HEADROOM,
            f"reserving {reserve_usd:.4f} USD would exceed the {cap:.2f} USD cap "
            f"({total:.4f} USD spent)",
        )
    return ProspectivePreflight(
        protocol_sha256=current,
        freeze_at=preregistration.freeze_at,
        population=preregistration.population,
        sampled_units=len(samples),
        trials_recorded=len(trials),
        reserved_usd=reserve_usd,
        headroom_usd=headroom,
    )


@dataclass(frozen=True)
class TrafficUnit:
    """One natural change: a commit reviewed as head, its parent as base."""

    unit_id: str  # "<repository>@<sha>"
    repository: str
    head_sha: str
    base_sha: str
    subject: str
    stratum: str  # docs | refactor | feature | fix | other
    changed_files: int
    pushed_at: str  # ISO-8601; must be after the freeze


def classify_subject(subject: str) -> str:
    head = subject.lower().split(":")[0]
    if "fix" in head or "bug" in head or "revert" in head:
        return "fix"
    if head.startswith(("docs", "doc")):
        return "docs"
    if head.startswith(("refactor", "chore", "style", "test", "tests", "build", "ci", "perf")):
        return "refactor"
    if head.startswith(("feat", "add")):
        return "feature"
    return "other"


def record_sample(
    study_dir: Path, units: list[TrafficUnit], *, recorded_at: str
) -> list[dict[str, object]]:
    """Record the units, their strata and the silent-audit draw BEFORE any outcome.
    The draw is seeded by the preregistration and the unit id, so it is
    reproducible and independent of what the product later does."""
    preregistration = load_preregistration(study_dir)
    freeze_at = _utc(preregistration.freeze_at)
    known = {row.get("unit_id") for row in _read_jsonl(study_dir / SAMPLE_FILE)}
    rows: list[dict[str, object]] = []
    for unit in units:
        if unit.unit_id in known:
            continue
        if preregistration.prospective and _utc(unit.pushed_at) < freeze_at:
            raise ValueError(f"{unit.unit_id} predates the freeze; it is not prospective")
        draw = random.Random(f"{preregistration.silent_audit_seed}:{unit.unit_id}").random()
        row: dict[str, object] = {
            **asdict(unit),
            "recorded_at": recorded_at,
            "prospective": preregistration.prospective,
            "silent_audit_inclusion_probability": (
                preregistration.silent_audit_inclusion_probability
            ),
            "selected_for_silent_audit": draw < preregistration.silent_audit_inclusion_probability,
        }
        _append_jsonl(study_dir / SAMPLE_FILE, row)
        rows.append(row)
        known.add(unit.unit_id)
    return rows


@dataclass(frozen=True)
class ShadowTrial:
    unit_id: str
    task_id: str
    recorded_at: str
    candidates: int
    eligible: int
    attempted: int
    certified: int
    would_publish: tuple[str, ...]  # candidate ids CI would have shown the author
    behavior_changes_verified: int
    behavior_changes_intent_unknown: int
    failure_categories: dict[str, int] = field(default_factory=dict)
    deferred_reason: str | None = None
    spend_usd: float = 0.0
    elapsed_s: float = 0.0
    executor_profile: str = ""

    def to_json_dict(self) -> dict[str, object]:
        return asdict(self)


def trial_from_ledger(
    rows: list[Mapping[str, Any]],
    *,
    unit_id: str,
    task_id: str,
    recorded_at: str,
    would_publish: tuple[str, ...],
    deferred_reason: str | None,
    spend_usd: float,
    elapsed_s: float,
) -> ShadowTrial:
    """The trial record from the ledger rows of one task: counts only, never a
    candidate's claim, file or line (the study bundle is not a publication)."""
    from attest.review.status import status_from_rows

    status = status_from_rows(rows, task_id)
    mine = [row for row in rows if row.get("task_id") == task_id]
    intent_unknown = sum(
        1
        for row in mine
        if row.get("kind") == "verification"
        and row.get("evidence_class") == "behavior_change"
        and row.get("outcome") != "reproduced"
    )
    profile = next(
        (str(row.get("profile")) for row in mine if row.get("kind") == "executor_backend"), ""
    )
    return ShadowTrial(
        unit_id=unit_id,
        task_id=task_id,
        recorded_at=recorded_at,
        candidates=status.candidates,
        eligible=status.eligible,
        attempted=status.attempts,
        certified=status.certified,
        would_publish=would_publish,
        behavior_changes_verified=status.behavior_changes,
        behavior_changes_intent_unknown=intent_unknown,
        failure_categories=dict(status.counts),
        deferred_reason=deferred_reason,
        spend_usd=round(spend_usd, 6),
        elapsed_s=round(elapsed_s, 3),
        executor_profile=profile,
    )


def record_trial(study_dir: Path, trial: ShadowTrial) -> None:
    _append_jsonl(study_dir / TRIALS_FILE, trial.to_json_dict())


def _percentile(values: list[float], share: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(share * len(ordered)) - 1))
    return ordered[index]


def report(study_dir: Path) -> dict[str, object]:
    """Metrics from the study files alone. Truth is product-blind adjudication in
    ``adjudication.jsonl`` (unit_id, finding_id or "", label in
    {defect, not_defect, unresolved}); anything else leaves detection INSUFFICIENT."""
    preregistration = load_preregistration(study_dir)
    samples = _read_jsonl(study_dir / SAMPLE_FILE)
    trials = _read_jsonl(study_dir / TRIALS_FILE)
    adjudications = _read_jsonl(study_dir / ADJUDICATION_FILE)
    by_unit = {row.get("unit_id"): row for row in trials}
    strata: dict[str, int] = {}
    for row in samples:
        strata[str(row.get("stratum"))] = strata.get(str(row.get("stratum")), 0) + 1
    shadow_findings = [
        (row["unit_id"], finding_id)
        for row in trials
        for finding_id in row.get("would_publish", [])
    ]
    labels = {
        (row.get("unit_id"), row.get("finding_id") or ""): str(row.get("label"))
        for row in adjudications
    }
    wrong = sum(1 for key in shadow_findings if labels.get(key) == "not_defect")
    unadjudicated = [
        key for key in shadow_findings if labels.get(key) not in {"defect", "not_defect"}
    ]
    silent_audit = [
        row["unit_id"]
        for row in samples
        if row.get("selected_for_silent_audit")
        and not by_unit.get(row["unit_id"], {}).get("would_publish")
    ]
    unresolved_silent = [
        unit for unit in silent_audit if labels.get((unit, "")) not in {"defect", "not_defect"}
    ]
    confirmed_opportunities = sum(
        1 for (unit, finding), label in labels.items() if label == "defect"
    )
    spends = [float(row.get("spend_usd", 0.0)) for row in trials]
    latencies = [float(row.get("elapsed_s", 0.0)) for row in trials]
    units_with_finding = {unit for unit, _finding in shadow_findings}
    detection_status = (
        "INSUFFICIENT"
        if unresolved_silent
        or unadjudicated
        or confirmed_opportunities < MINIMUM_CONFIRMED_OPPORTUNITIES
        else "estimable"
    )
    safety_status = "INSUFFICIENT" if unadjudicated else "adjudicated"
    stop = wrong >= preregistration.safety_stop_wrong_findings
    return {
        "schema_version": STUDY_SCHEMA_VERSION,
        "freeze_at": preregistration.freeze_at,
        # a stratum whose units predate its freeze cannot support a prospective
        # claim, and the report says so rather than leaving it to the reader
        "prospective": preregistration.prospective,
        "population": list(preregistration.population),
        "units_sampled": len(samples),
        "units_run": len(trials),
        "strata": strata,
        "shadow_findings": len(shadow_findings),
        "units_with_shadow_finding": len(units_with_finding),
        "pr_any_shadow_finding_rate": (len(units_with_finding) / len(trials) if trials else None),
        "wrong_shadow_findings": wrong,
        "unadjudicated_shadow_findings": len(unadjudicated),
        "behavior_changes_verified": sum(
            int(row.get("behavior_changes_verified", 0)) for row in trials
        ),
        "behavior_changes_intent_unknown": sum(
            int(row.get("behavior_changes_intent_unknown", 0)) for row in trials
        ),
        "deferred_units": sum(1 for row in trials if row.get("deferred_reason")),
        "silent_audit_selected": len(silent_audit),
        "silent_audit_unresolved": len(unresolved_silent),
        "confirmed_eligible_opportunities": confirmed_opportunities,
        "eligible_detection": detection_status,
        "semantic_precision": safety_status,
        "safety_stop_reached": stop,
        "cost_usd_total": round(sum(spends), 6),
        "cost_usd_p50": _percentile(spends, 0.5),
        "cost_usd_p95": _percentile(spends, 0.95),
        "latency_s_p50": _percentile(latencies, 0.5),
        "latency_s_p95": _percentile(latencies, 0.95),
        "permitted_claim": (
            "prospective shadow observation on the authorized population; no utility or "
            "precision claim until every shadow finding and every sampled silent unit is "
            "adjudicated product-blind and the preregistered minimum is met"
        ),
    }
