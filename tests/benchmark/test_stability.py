"""Ten-repeat stability: preregistered, resumable, and operational-only."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from attest.benchmark.api import (
    ProjectEvaluationRequest,
    ProjectTruth,
    build_evaluation_binding,
    current_runtime_identity,
)
from attest.benchmark.artifacts import canonical_json_bytes
from attest.benchmark.checkpoints import (
    CALL_ROLE_BENCHMARK_ORACLE,
    CALL_ROLE_PRODUCT,
    STATE_AMBIGUOUS_COST,
    STATE_DISPATCHED,
    STATE_RESPONSE_PERSISTED,
    AmbiguousCostError,
)
from attest.benchmark.measurement import ARM_ATTEST_PRODUCT, TaskStatus
from attest.benchmark.runner import Cassette, ReplayProvider
from attest.benchmark.schema import ChangedLocation, TruthDefect, load_manifest
from attest.benchmark.stability import (
    STABILITY_REPEATS,
    StabilityObservation,
    SurfacedAnchor,
    run_stability_study,
    summarize_stability,
)
from attest.review.config import ReviewConfig
from attest.review.executor import ExecutorLimits
from attest.review.proposer import Provider

from .test_baselines import _finding, _measurement_record
from .test_corpus import _oracle_fixture

_SCRIPT = Path(__file__).parents[2] / "scripts" / "benchmark.py"

_FINDING_PROPOSAL = json.dumps(
    {
        "findings": [
            {
                "claim": "value() returns 0 instead of the documented 1.",
                "anchor": {"file": "calc.py", "line": 2},
                "failure_scenario": "value() returns 0 and callers divide by it",
                "falsification_plan": "call value() and require the documented 1",
            }
        ]
    }
)
_REPRO = json.dumps(
    {
        "test_body": "import runpy\n\n"
        "def test_value_is_one():\n"
        "    assert runpy.run_path('calc.py')['value']() == 1\n"
    }
)
_EMPTY_PROPOSAL = json.dumps({"findings": []})

_LOCATIONS = (ChangedLocation(path="calc.py", start_line=2, end_line=2, side="old"),)


def _surfaced(wealth: float, finding_id: str = "finding-1") -> SurfacedAnchor:
    return SurfacedAnchor(
        finding_id=finding_id,
        file="calc.py",
        line=2,
        placement="inline",
        action="surface",
        evidence_class="regression_reproduced",
        wealth_final=wealth,
    )


def _observation(
    repeat: int,
    *,
    surfaced: tuple[SurfacedAnchor, ...] = (),
    deferred: str | None = None,
    candidate_count: int = 0,
    latency_s: float = 1.0,
    spend_usd: float = 0.01,
) -> StabilityObservation:
    findings = tuple(
        _finding(
            anchor.finding_id,
            accuracy="unadjudicated",
            defect_id=None,
        )
        for anchor in surfaced
    )
    findings += tuple(
        _finding(
            f"unresolved-{repeat}-{index}",
            status="unresolved",
            accuracy="unadjudicated",
            defect_id=None,
        )
        for index in range(candidate_count - len(findings))
    )
    stop = "candidate_defer" if deferred is not None and surfaced else (
        "task_defer" if deferred is not None else "none"
    )
    measurement = replace(
        _measurement_record(
            stop=stop,
            findings=findings,
            repeat=repeat,
            eligible_defect_ids=(),
            truth_status="unadjudicated",
        ),
        case_id="case-333333333333",
        arm=ARM_ATTEST_PRODUCT,
    )
    return StabilityObservation(
        repeat=repeat,
        run_id=f"run-{repeat}",
        status=measurement.task_status.value,
        abstain_reason=deferred,
        surfaced=surfaced,
        candidate_count=measurement.candidate_count,
        measurement=measurement,
        latency_s=latency_s,
        product_spend_usd=spend_usd,
        oracle_spend_usd=0.0,
        total_spend_usd=spend_usd,
        delivery_at_s=None if deferred is not None else latency_s,
    )


def _sealed_observation_payload(
    observation: StabilityObservation,
) -> dict[str, object]:
    digest = hashlib.sha256(canonical_json_bytes(observation._payload())).hexdigest()
    return replace(observation, digest=digest).to_json_dict()


def _synthetic_observations() -> tuple[StabilityObservation, ...]:
    """Three surfacing runs, six silent runs, one deferred run."""
    wealthy = (10.0, 12.0, 8.0)
    observations = [
        _observation(repeat, surfaced=(_surfaced(wealthy[repeat]),), candidate_count=1)
        for repeat in range(3)
    ]
    observations.extend(_observation(repeat) for repeat in range(3, 9))
    observations.append(_observation(9, deferred="provider_error"))
    return tuple(observations)


def test_summarize_stability_reports_exact_agreement_and_dispersion() -> None:
    """Modal shares, Jaccard, and wealth dispersion must be exact, with the
    deferred run counted as a DEFER in every stability denominator."""
    report = summarize_stability(
        case_id="case-333333333333",
        manifest_sha256="ab" * 32,
        observations=_synthetic_observations(),
        locations=_LOCATIONS,
    )

    assert report.repeats == STABILITY_REPEATS == 10
    assert report.schema_version == "5"
    assert report.semantic_n == 1
    assert report.operational_repeats == 10
    assert report.task_status_counts == {
        "completed": 9,
        "partially_deferred": 0,
        "fully_deferred": 1,
        "failed": 0,
    }
    assert len(report.run_ids) == 10
    assert report.outcomes == (
        "surfaced",
        "surfaced",
        "surfaced",
        "silent",
        "silent",
        "silent",
        "silent",
        "silent",
        "silent",
        "deferred",
    )
    assert report.modal_outcome == "silent"
    assert report.run_outcome_stability == pytest.approx(0.6)
    assert [(row.repeat, row.reason) for row in report.deferred_runs] == [(9, "provider_error")]

    assert len(report.clusters) == 1
    cluster = report.clusters[0]
    assert cluster.cluster_id == "calc.py:2-2"
    assert cluster.decisions == ("inline",) * 3 + ("absent",) * 6 + ("deferred",)
    assert cluster.modal_decision == "absent"
    assert cluster.modal_share == pytest.approx(0.6)
    assert cluster.wealth_mean == pytest.approx(10.0)
    assert cluster.wealth_variance == pytest.approx(8.0 / 3.0)
    assert cluster.wealth_range == pytest.approx(4.0)

    # Nine completed runs: 3 identical surfaced sets, 6 identical empty sets.
    assert report.jaccard_pairs == 36
    assert report.mean_pairwise_jaccard == pytest.approx((3 + 15) / 36)

    assert report.candidate_counts == (1, 1, 1, 0, 0, 0, 0, 0, 0, 0)
    assert report.candidate_count_mean == pytest.approx(1 / 3)
    assert report.candidate_count_variance == pytest.approx(2 / 9)
    assert report.spend_total_usd == pytest.approx(0.1)
    assert report.latency_mean_s == pytest.approx(1.0)
    assert report.wealth_mean == pytest.approx(10.0)
    assert report.wealth_range == pytest.approx(4.0)
    assert report.digest


def test_stability_partial_defer_retains_author_visible_surface() -> None:
    observations = (
        *(_observation(repeat) for repeat in range(9)),
        _observation(
            9,
            deferred="candidate evidence remained unresolved",
            surfaced=(_surfaced(12.0),),
            candidate_count=2,
        ),
    )

    report = summarize_stability(
        case_id="case-333333333333",
        manifest_sha256="ab" * 32,
        observations=observations,
        locations=_LOCATIONS,
    )

    assert report.outcomes[-1] == "surfaced_deferred"
    assert [(row.repeat, row.reason) for row in report.deferred_runs] == [
        (9, "candidate evidence remained unresolved")
    ]
    assert report.clusters[0].decisions[-1] == "inline"
    assert report.clusters[0].runs_present == 1


def test_stability_report_digest_binds_each_repeat_reconciliation() -> None:
    observations = _synthetic_observations()
    original = summarize_stability(
        case_id="case-333333333333",
        manifest_sha256="ab" * 32,
        observations=observations,
        locations=_LOCATIONS,
    )
    changed = summarize_stability(
        case_id="case-333333333333",
        manifest_sha256="ab" * 32,
        observations=(
            replace(observations[0], call_evidence_sha256="b" * 64),
            *observations[1:],
        ),
        locations=_LOCATIONS,
    )

    assert changed.digest != original.digest
    assert changed.paid_call_reconciliation_sha256[0] == "b" * 64


def test_summarize_stability_gives_off_location_anchors_singleton_clusters() -> None:
    """An anchor outside every preregistered location clusters by its own
    canonical file and line, never by claim prose."""
    stray = SurfacedAnchor(
        finding_id="finding-stray",
        file="calc.py",
        line=40,
        placement="overflow",
        action="surface",
        evidence_class="not_reproduced",
        wealth_final=None,
    )
    observations = (
        _observation(0, surfaced=(_surfaced(10.0), stray), candidate_count=2),
        *(_observation(repeat) for repeat in range(1, 10)),
    )

    report = summarize_stability(
        case_id="case-333333333333",
        manifest_sha256="ab" * 32,
        observations=observations,
        locations=_LOCATIONS,
    )

    assert {cluster.cluster_id for cluster in report.clusters} == {"calc.py:2-2", "calc.py:40"}
    stray_cluster = next(c for c in report.clusters if c.cluster_id == "calc.py:40")
    assert stray_cluster.decisions[0] == "overflow"
    assert stray_cluster.modal_decision == "absent"
    assert stray_cluster.wealth_mean is None


def test_summarize_stability_requires_exactly_ten_distinct_repeats() -> None:
    """Nine runs are not a stability study, and a duplicated repeat could hide
    a dropped one."""
    observations = _synthetic_observations()

    with pytest.raises(ValueError, match="ten"):
        summarize_stability(
            case_id="case-333333333333",
            manifest_sha256="ab" * 32,
            observations=observations[:9],
            locations=_LOCATIONS,
        )
    duplicated = (*observations[:9], _observation(8))
    with pytest.raises(ValueError, match="repeat"):
        summarize_stability(
            case_id="case-333333333333",
            manifest_sha256="ab" * 32,
            observations=duplicated,
            locations=_LOCATIONS,
        )


def test_stability_observation_rejects_status_and_surface_authority_drift() -> None:
    observation = _observation(0, surfaced=(_surfaced(10.0),), candidate_count=1)

    with pytest.raises(ValueError, match="status.*measurement"):
        replace(observation, status=TaskStatus.FAILED.value)
    with pytest.raises(ValueError, match="published finding"):
        replace(
            observation,
            surfaced=(replace(observation.surfaced[0], finding_id="injected"),),
        )


@pytest.mark.parametrize("mutation", ["extra-field", "non-finite-wealth"])
def test_stability_observation_rejects_unsealed_anchor_data(mutation: str) -> None:
    payload = _sealed_observation_payload(
        _observation(0, surfaced=(_surfaced(10.0),), candidate_count=1)
    )
    surfaced = payload["surfaced"]
    assert isinstance(surfaced, list)
    anchor = surfaced[0]
    assert isinstance(anchor, dict)
    if mutation == "extra-field":
        anchor["unsigned_extra"] = "injected"
    else:
        anchor["wealth_final"] = float("nan")
        unsealed = dict(payload)
        unsealed.pop("digest")
        payload["digest"] = hashlib.sha256(
            canonical_json_bytes(unsealed)
        ).hexdigest()

    with pytest.raises(ValueError, match="field set|finite"):
        StabilityObservation.from_json_dict(payload)


def test_retained_stability_v4_observation_is_not_reinterpreted() -> None:
    payload = _observation(0).to_json_dict()
    payload["schema_version"] = "4"

    with pytest.raises(ValueError, match="unsupported observation schema version '4'"):
        StabilityObservation.from_json_dict(payload)


def test_stability_report_is_operational_only() -> None:
    """Stability never claims accuracy: no precision, recall, detection, or
    Wilson interval may appear, and the limitations must say why no validation
    receipt is needed."""
    report = summarize_stability(
        case_id="case-333333333333",
        manifest_sha256="ab" * 32,
        observations=_synthetic_observations(),
        locations=_LOCATIONS,
    )

    document = report.to_json_dict()
    document.pop("limitations")  # the prose names the metrics precisely to forbid them
    payload = json.dumps(document, sort_keys=True)
    for forbidden in (
        "precision",
        "recall",
        "true_positive",
        "false_positive",
        "detection",
        "interval",
        "wilson",
        "specificity",
    ):
        assert forbidden not in payload.lower()
    text = " ".join(report.limitations)
    assert "operational" in text
    assert "accuracy" in text
    assert "denominator" in text


def _study_request(tmp_path: Path) -> ProjectEvaluationRequest:
    manifest_path, root, _ = _oracle_fixture(tmp_path)
    manifest = load_manifest(manifest_path)
    case = next(c for c in manifest.cases if c.role == "historical_bug_replay")
    runtime = next(r for r in manifest.runtime if r.case_id == case.case_id)
    return ProjectEvaluationRequest(
        case_id=case.case_id,
        repo=root / runtime.cwd,
        base_ref=case.fixed_commit,
        head_ref=case.buggy_commit,
        workspace_root=tmp_path / "workspace",
        config=ReviewConfig(
            alpha=0.1, k_samples=1, tier0_commands=[], auto_tighten_alpha=False
        ),
        limits=ExecutorLimits(wall_timeout_s=60.0),
        verification_timeout_s=120.0,
        repeats=1,
        deadline_s=60.0,
        truth=None,
    )


def test_run_stability_study_executes_ten_runs_and_records_defers(tmp_path: Path) -> None:
    """Ten independent provider runs over identical bytes and configuration;
    a run whose proposal is unusable becomes a DEFER, never a dropped run."""
    request = _study_request(tmp_path)
    built: list[int] = []

    def factory(repeat: int) -> Provider:
        built.append(repeat)
        if repeat >= 8:
            return ReplayProvider(Cassette(proposal="not-json-at-all", repro=""))
        proposal = _FINDING_PROPOSAL if repeat < 2 else _EMPTY_PROPOSAL
        return ReplayProvider(
            Cassette(proposal=proposal, repro=_REPRO, input_tokens=800, output_tokens=200)
        )

    result = run_stability_study(
        request,
        provider_factory=factory,
        state_dir=tmp_path / "state",
        locations=_LOCATIONS,
        manifest_sha256="cd" * 32,
        provider_label="injected_fake",
    )

    assert built == list(range(10))
    assert result.executed_repeats == 10
    assert result.resumed_repeats == 0
    report = result.report
    assert report.repeats == 10
    assert len(report.run_ids) == 10
    assert len(set(report.run_ids)) == 10
    assert report.outcomes[:2] == ("surfaced", "surfaced")
    assert report.outcomes[8:] == ("deferred", "deferred")
    assert {row.repeat for row in report.deferred_runs} == {8, 9}
    assert all(row.reason for row in report.deferred_runs)
    cluster = next(c for c in report.clusters if c.cluster_id == "calc.py:2-2")
    assert cluster.decisions[0] == "inline"
    assert cluster.decisions[2] == "absent"
    assert cluster.decisions[9] == "deferred"
    assert report.spend_total_usd > 0
    assert (tmp_path / "state" / "repeat-9.json").is_file()


def test_run_stability_study_resumes_without_repeating_a_paid_run(tmp_path: Path) -> None:
    """Interruption after five persisted repeats must never re-execute them:
    a duplicated repeat is a duplicated paid provider call."""
    request = _study_request(tmp_path)
    state_dir = tmp_path / "state"

    def interrupted(repeat: int) -> Provider:
        if repeat == 5:
            raise KeyboardInterrupt
        return ReplayProvider(
            Cassette(proposal=_EMPTY_PROPOSAL, repro="", input_tokens=10, output_tokens=10)
        )

    with pytest.raises(KeyboardInterrupt):
        run_stability_study(
            request,
            provider_factory=interrupted,
            state_dir=state_dir,
            locations=_LOCATIONS,
            manifest_sha256="cd" * 32,
            provider_label="injected_fake",
        )
    persisted = sorted(path.name for path in state_dir.glob("repeat-*.json"))
    assert persisted == [f"repeat-{i}.json" for i in range(5)]
    first_run_ids = [
        json.loads((state_dir / f"repeat-{i}.json").read_text())["run_id"] for i in range(5)
    ]

    resumed_calls: list[int] = []

    def resumed(repeat: int) -> Provider:
        resumed_calls.append(repeat)
        return ReplayProvider(
            Cassette(proposal=_EMPTY_PROPOSAL, repro="", input_tokens=10, output_tokens=10)
        )

    result = run_stability_study(
        request,
        provider_factory=resumed,
        state_dir=state_dir,
        locations=_LOCATIONS,
        manifest_sha256="cd" * 32,
        provider_label="injected_fake",
    )

    assert resumed_calls == [5, 6, 7, 8, 9]
    assert result.executed_repeats == 5
    assert result.resumed_repeats == 5
    assert list(result.report.run_ids[:5]) == first_run_ids


def test_stability_resume_replays_durable_subcall_response_without_redispatch(
    tmp_path: Path,
) -> None:
    request = _study_request(tmp_path)
    state_dir = tmp_path / "state"
    first = ReplayProvider(
        Cassette(proposal=_EMPTY_PROPOSAL, repro="", input_tokens=10, output_tokens=10)
    )
    crashed = False

    def interrupt(repeat: int, _call_id: str, state: str) -> None:
        nonlocal crashed
        if repeat == 0 and state == STATE_RESPONSE_PERSISTED and not crashed:
            crashed = True
            raise KeyboardInterrupt(state)

    with pytest.raises(KeyboardInterrupt, match=STATE_RESPONSE_PERSISTED):
        run_stability_study(
            request,
            provider_factory=lambda _repeat: first,
            state_dir=state_dir,
            locations=_LOCATIONS,
            manifest_sha256="cd" * 32,
            provider_label="injected_fake",
            on_call_transition=interrupt,
        )
    assert first.proposal_calls == 1
    assert not (state_dir / "repeat-0.json").exists()

    resumed = ReplayProvider(
        Cassette(proposal=_EMPTY_PROPOSAL, repro="", input_tokens=10, output_tokens=10)
    )
    result = run_stability_study(
        request,
        provider_factory=lambda _repeat: resumed,
        state_dir=state_dir,
        locations=_LOCATIONS,
        manifest_sha256="cd" * 32,
        provider_label="injected_fake",
    )

    assert result.report.repeats == STABILITY_REPEATS
    assert resumed.proposal_calls == STABILITY_REPEATS - 1


@pytest.mark.parametrize(
    ("settled_role", "expected_product", "expected_oracle"),
    (
        (CALL_ROLE_PRODUCT, True, False),
        (CALL_ROLE_BENCHMARK_ORACLE, False, True),
    ),
)
def test_post_settlement_exception_preserves_authoritative_role_spend(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    settled_role: str,
    expected_product: bool,
    expected_oracle: bool,
) -> None:
    request = _study_request(tmp_path)
    state_dir = tmp_path / "state"

    def settle_then_fail(
        prepared: ProjectEvaluationRequest,
        *,
        provider: Provider,
        oracle_provider: Provider,
        clock: object,
    ) -> object:
        selected = provider if settled_role == CALL_ROLE_PRODUCT else oracle_provider
        selected.sample("system", "prompt", {"type": "object"}, 20)
        raise RuntimeError("evaluation failed after settlement")

    monkeypatch.setattr(
        "attest.benchmark.stability.evaluate_project", settle_then_fail
    )
    with pytest.raises(RuntimeError, match="evaluation failed after settlement"):
        run_stability_study(
            request,
            provider_factory=lambda _repeat: ReplayProvider(
                Cassette(proposal="{}", repro="{}", input_tokens=100, output_tokens=20)
            ),
            state_dir=state_dir,
            locations=_LOCATIONS,
            manifest_sha256="cd" * 32,
            provider_label="injected_fake",
        )

    assert not (state_dir / "repeat-0.json").exists()
    cost_rows = [
        json.loads(line)
        for line in (state_dir / "repeat-0-calls" / "costs.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert len(cost_rows) == 1
    assert cost_rows[0]["role"] == settled_role
    assert cost_rows[0]["cost_usd"] > 0
    assert (settled_role == CALL_ROLE_PRODUCT) is expected_product
    assert (settled_role == CALL_ROLE_BENCHMARK_ORACLE) is expected_oracle


def test_stability_resume_rejects_observation_spend_tampering(
    tmp_path: Path,
) -> None:
    request = _study_request(tmp_path)
    state_dir = tmp_path / "state"
    run_stability_study(
        request,
        provider_factory=lambda _repeat: ReplayProvider(
            Cassette(proposal=_EMPTY_PROPOSAL, repro="", input_tokens=10, output_tokens=10)
        ),
        state_dir=state_dir,
        locations=_LOCATIONS,
        manifest_sha256="cd" * 32,
        provider_label="injected_fake",
    )
    path = state_dir / "repeat-0.json"
    observation = json.loads(path.read_text(encoding="utf-8"))
    observation["product_spend_usd"] += 1.0
    observation["total_spend_usd"] += 1.0
    unsealed = dict(observation)
    unsealed.pop("digest")
    observation["digest"] = hashlib.sha256(canonical_json_bytes(unsealed)).hexdigest()
    path.write_bytes(canonical_json_bytes(observation))

    with pytest.raises(ValueError, match="spend|evidence binding|authoritative"):
        run_stability_study(
            request,
            provider_factory=lambda _repeat: pytest.fail("tamper path dispatched"),
            state_dir=state_dir,
            locations=_LOCATIONS,
            manifest_sha256="cd" * 32,
            provider_label="injected_fake",
        )


def test_stability_resume_rejects_canonical_observation_latency_tampering(
    tmp_path: Path,
) -> None:
    request = _study_request(tmp_path)
    state_dir = tmp_path / "state"
    run_stability_study(
        request,
        provider_factory=lambda _repeat: ReplayProvider(
            Cassette(proposal=_EMPTY_PROPOSAL, repro="", input_tokens=10, output_tokens=10)
        ),
        state_dir=state_dir,
        locations=_LOCATIONS,
        manifest_sha256="cd" * 32,
        provider_label="injected_fake",
    )
    path = state_dir / "repeat-0.json"
    observation = json.loads(path.read_bytes())
    observation["latency_s"] += 1.0
    path.write_bytes(canonical_json_bytes(observation))

    with pytest.raises(ValueError, match="repeat-0.*corrupt"):
        run_stability_study(
            request,
            provider_factory=lambda _repeat: pytest.fail("tamper path dispatched"),
            state_dir=state_dir,
            locations=_LOCATIONS,
            manifest_sha256="cd" * 32,
            provider_label="injected_fake",
        )


def test_stability_dispatched_without_response_withholds_report_and_blocks_retry(
    tmp_path: Path,
) -> None:
    request = _study_request(tmp_path)
    state_dir = tmp_path / "state"
    first = ReplayProvider(Cassette(proposal=_EMPTY_PROPOSAL, repro=""))

    def interrupt(repeat: int, _call_id: str, state: str) -> None:
        if repeat == 0 and state == STATE_DISPATCHED:
            raise KeyboardInterrupt(state)

    with pytest.raises(KeyboardInterrupt, match=STATE_DISPATCHED):
        run_stability_study(
            request,
            provider_factory=lambda _repeat: first,
            state_dir=state_dir,
            locations=_LOCATIONS,
            manifest_sha256="cd" * 32,
            provider_label="injected_fake",
            on_call_transition=interrupt,
        )
    assert first.proposal_calls == 0

    resumed = ReplayProvider(Cassette(proposal=_EMPTY_PROPOSAL, repro=""))
    with pytest.raises(AmbiguousCostError, match=STATE_AMBIGUOUS_COST):
        run_stability_study(
            request,
            provider_factory=lambda _repeat: resumed,
            state_dir=state_dir,
            locations=_LOCATIONS,
            manifest_sha256="cd" * 32,
            provider_label="injected_fake",
        )
    assert resumed.proposal_calls == 0
    assert not (state_dir / "repeat-0.json").exists()


@pytest.mark.parametrize("missing", ["spend", "artifact", "directory"])
def test_stability_resume_reconciles_completed_repeat_paid_call_evidence(
    tmp_path: Path, missing: str
) -> None:
    request = _study_request(tmp_path)
    state_dir = tmp_path / "state"
    run_stability_study(
        request,
        provider_factory=lambda _repeat: ReplayProvider(
            Cassette(proposal=_EMPTY_PROPOSAL, repro="", input_tokens=10, output_tokens=10)
        ),
        state_dir=state_dir,
        locations=_LOCATIONS,
        manifest_sha256="cd" * 32,
        provider_label="injected_fake",
    )
    call_root = state_dir / "repeat-0-calls"
    if missing == "spend":
        (call_root / "costs.jsonl").write_text("", encoding="utf-8")
    elif missing == "artifact":
        next((call_root / "artifacts").glob("*.json")).unlink()
    else:
        shutil.rmtree(call_root)
    resumed = ReplayProvider(Cassette(proposal=_EMPTY_PROPOSAL, repro=""))

    with pytest.raises(ValueError, match="spend row|artifact.*missing|evidence binding"):
        run_stability_study(
            request,
            provider_factory=lambda _repeat: resumed,
            state_dir=state_dir,
            locations=_LOCATIONS,
            manifest_sha256="cd" * 32,
            provider_label="injected_fake",
        )

    assert resumed.proposal_calls == 0


def test_run_stability_study_fails_closed_on_drift_truth_or_corrupt_state(
    tmp_path: Path,
) -> None:
    """The predeclaration binds configuration; hidden truth is refused because
    stability is operational; corrupt state must never silently re-buy a run."""
    request = _study_request(tmp_path)
    state_dir = tmp_path / "state"

    def factory(repeat: int) -> Provider:
        return ReplayProvider(
            Cassette(proposal=_EMPTY_PROPOSAL, repro="", input_tokens=10, output_tokens=10)
        )

    run_stability_study(
        request,
        provider_factory=factory,
        state_dir=state_dir,
        locations=_LOCATIONS,
        manifest_sha256="cd" * 32,
        provider_label="injected_fake",
    )

    drifted = replace(
        request,
        config=ReviewConfig(
            alpha=0.05, k_samples=1, tier0_commands=[], auto_tighten_alpha=False
        ),
    )
    with pytest.raises(ValueError, match="predeclar"):
        run_stability_study(
            drifted,
            provider_factory=factory,
            state_dir=state_dir,
            locations=_LOCATIONS,
            manifest_sha256="cd" * 32,
            provider_label="injected_fake",
        )

    with_truth = ProjectEvaluationRequest(
        case_id=request.case_id,
        repo=request.repo,
        base_ref=request.base_ref,
        head_ref=request.head_ref,
        workspace_root=request.workspace_root,
        config=request.config,
        limits=request.limits,
        truth=ProjectTruth(
            defects=(
                TruthDefect(
                    defect_id="truth_1",
                    case_id=request.case_id,
                    file="calc.py",
                    start_line=2,
                    end_line=2,
                ),
            ),
            fixed_ref=request.base_ref,
        ),
    )
    with pytest.raises(ValueError, match="operational"):
        run_stability_study(
            with_truth,
            provider_factory=factory,
            state_dir=tmp_path / "state-truth",
            locations=_LOCATIONS,
            manifest_sha256="cd" * 32,
            provider_label="injected_fake",
        )

    (state_dir / "repeat-3.json").write_text("{corrupt", encoding="utf-8")
    with pytest.raises(ValueError, match="repeat-3"):
        run_stability_study(
            request,
            provider_factory=factory,
            state_dir=state_dir,
            locations=_LOCATIONS,
            manifest_sha256="cd" * 32,
            provider_label="injected_fake",
        )


def test_old_study_predeclaration_reports_supported_version(tmp_path: Path) -> None:
    request = _study_request(tmp_path)
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    (state_dir / "study.json").write_text(
        json.dumps({"schema_version": "0"}), encoding="utf-8"
    )

    with pytest.raises(ValueError, match="unsupported.*schema version.*0.*supported"):
        run_stability_study(
            request,
            provider_factory=lambda _repeat: ReplayProvider(
                Cassette(proposal=_EMPTY_PROPOSAL, repro="")
            ),
            state_dir=state_dir,
            locations=_LOCATIONS,
            manifest_sha256="cd" * 32,
            provider_label="injected_fake",
        )


def test_retained_stability_v4_predeclaration_is_not_reinterpreted(
    tmp_path: Path,
) -> None:
    """The former v4 study shape fails as a version, before paid-state mutation."""
    request = _study_request(tmp_path)
    runtime = current_runtime_identity()
    binding_v1 = build_evaluation_binding(
        request,
        provider_id="injected_fake",
        interpreter_id=runtime.interpreter_id,
        environment_sha256=runtime.environment_sha256,
        code_sha256=runtime.code_sha256,
    ).to_json_dict()
    binding_v1["schema_version"] = "1"
    config = request.config
    old_v4 = {
        "schema_version": "4",
        "paid_call_roles": ["benchmark_oracle", "product"],
        "case_id": request.case_id,
        "manifest_sha256": "cd" * 32,
        "repeats": 10,
        "base_ref": request.base_ref,
        "head_ref": request.head_ref,
        "line_slack": 0,
        "provider_label": "injected_fake",
        "evaluation_binding": binding_v1,
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
    state_dir = tmp_path / "retained-v4-state"
    state_dir.mkdir()
    (state_dir / "study.json").write_text(
        json.dumps(old_v4, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    (state_dir / "retained-paid-state.bin").write_bytes(b"old-v4-paid-state")
    before = {
        path.name: path.read_bytes() for path in state_dir.iterdir() if path.is_file()
    }
    provider_calls: list[int] = []

    with pytest.raises(
        ValueError,
        match=(
            "unsupported stability predeclaration schema version '4'.*"
            "supported version is 5"
        ),
    ):
        run_stability_study(
            request,
            provider_factory=lambda repeat: (
                provider_calls.append(repeat)
                or ReplayProvider(Cassette(proposal=_EMPTY_PROPOSAL, repro=""))
            ),
            state_dir=state_dir,
            locations=_LOCATIONS,
            manifest_sha256="cd" * 32,
            provider_label="injected_fake",
        )
    after = {
        path.name: path.read_bytes() for path in state_dir.iterdir() if path.is_file()
    }
    assert after == before
    assert provider_calls == []


def _run_cli(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(_SCRIPT), *args],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )


def test_stability_cli_runs_ten_offline_repeats_and_resumes_idempotently(
    tmp_path: Path,
) -> None:
    """The CLI mode is offline by construction (recorded cassette only) and a
    second invocation resumes every persisted repeat instead of re-buying it."""
    manifest_path, root, _ = _oracle_fixture(tmp_path)
    manifest = load_manifest(manifest_path)
    case = next(c for c in manifest.cases if c.role == "developer_fix_control")
    cassettes = tmp_path / "cassettes"
    cassettes.mkdir()
    (cassettes / f"{case.case_id}.json").write_text(
        json.dumps(
            {
                "proposal": _EMPTY_PROPOSAL,
                "repro": json.dumps({"test_body": ""}),
                "input_tokens": 800,
                "output_tokens": 200,
            }
        ),
        encoding="utf-8",
    )
    environment = dict(os.environ)
    environment["ANTHROPIC_API_KEY"] = "must-not-be-used"
    output = tmp_path / "out"

    first = _run_cli(
        "stability",
        "--manifest",
        str(manifest_path),
        "--case",
        case.case_id,
        "--cassette-root",
        str(cassettes),
        "--root",
        str(root),
        "--output",
        str(output),
        "--k-samples",
        "1",
        "--differential-repeats",
        "1",
        env=environment,
    )

    assert first.returncode == 0, first.stderr
    summary = json.loads(first.stdout)
    assert summary["status"] == "ok"
    assert summary["offline"] is True
    assert summary["repeats"] == 10
    assert summary["executed_repeats"] == 10
    assert summary["resumed_repeats"] == 0
    assert summary["deferred_repeats"] == 0
    report = json.loads((output / "stability.json").read_text(encoding="utf-8"))
    assert report["case_id"] == case.case_id
    assert report["modal_outcome"] == "silent"
    assert report["run_outcome_stability"] == 1.0
    assert report["mean_pairwise_jaccard"] == 1.0
    assert len(report["run_ids"]) == 10
    assert "operational" in " ".join(report["limitations"])
    assert (output / "stability.md").is_file()
    assert len(list((output / "state").glob("repeat-*.json"))) == 10

    second = _run_cli(
        "stability",
        "--manifest",
        str(manifest_path),
        "--case",
        case.case_id,
        "--cassette-root",
        str(cassettes),
        "--root",
        str(root),
        "--output",
        str(output),
        "--k-samples",
        "1",
        "--differential-repeats",
        "1",
        env=environment,
    )

    assert second.returncode == 0, second.stderr
    resumed = json.loads(second.stdout)
    assert resumed["executed_repeats"] == 0
    assert resumed["resumed_repeats"] == 10
    assert resumed["digest"] == summary["digest"]


def test_stability_cli_without_prepared_environment_is_not_executed(tmp_path: Path) -> None:
    """A missing checkout or cassette is a refusal to run, never a measurement."""
    manifest_path, _, _ = _oracle_fixture(tmp_path)
    manifest = load_manifest(manifest_path)
    case = manifest.cases[0]

    completed = _run_cli(
        "stability",
        "--manifest",
        str(manifest_path),
        "--case",
        case.case_id,
        "--cassette-root",
        str(tmp_path / "missing-cassettes"),
        "--output",
        str(tmp_path / "out"),
    )

    assert completed.returncode == 3
    summary = json.loads(completed.stdout)
    assert summary["status"] == "not_executed"
    assert summary["reason"] == "cassette_missing"
    assert not (tmp_path / "out" / "stability.json").exists()
