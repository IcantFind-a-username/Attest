"""Live-local evaluation: explicit opt-in, resumable checkpoints, honest calibration.

Every test here is fake-backed: no network, no model client, no credential is
ever used. The live orchestration is exercised with scripted providers and an
injected evaluator; the CLI tests set ``ANTHROPIC_API_KEY=must-not-be-used``
and trap ``git``/``gh``/``curl`` so any escape would be observed.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import sys
from collections.abc import Callable, Mapping
from dataclasses import replace
from pathlib import Path

import pytest

from attest.benchmark.api import (
    ProjectEvaluationRequest,
    ProjectEvaluationResult,
    ProjectTruth,
    _deferred,
    build_evaluation_binding,
    manifest_project_truth,
)
from attest.benchmark.checkpoints import (
    CALL_ROLE_BENCHMARK_ORACLE,
    CALL_ROLE_PRODUCT,
    AmbiguousCostError,
)
from attest.benchmark.checkpoints import (
    STATE_DISPATCHED as CALL_DISPATCHED,
)
from attest.benchmark.checkpoints import (
    STATE_RESPONSE_PERSISTED as CALL_RESPONSE_PERSISTED,
)
from attest.benchmark.corpus import ValidationVerification
from attest.benchmark.live import (
    ACCURACY_WITHHELD_REPLAY,
    CALIBRATION_SCHEMA_VERSION,
    MINIMUM_GLOBAL_LABELS,
    REASON_API_KEY_UNAVAILABLE,
    REASON_INSUFFICIENT_HEADROOM,
    REASON_MANIFEST_NOT_IMMUTABLE,
    REASON_PAID_API_NOT_ALLOWED,
    REASON_PREREGISTRATION_NOT_FROZEN,
    STATE_ARTIFACTS_COMPLETE,
    STATE_PROVIDER_COMPLETE,
    STATE_REPORTED,
    STATE_RESERVED,
    STATE_SETTLED,
    LiveCase,
    LivePreflightError,
    build_calibration_report,
    case_payload,
    preflight_live,
    read_devspend,
    reserved_case_budget_usd,
    run_live_local,
)
from attest.benchmark.measurement import (
    ARM_ATTEST_PRODUCT,
    CURRENT_MEASUREMENT_SCHEMA_VERSION,
    CURRENT_MEASUREMENT_SEMANTICS,
    DELIVERY_TRANSCRIPT_PROTOCOL,
    DELIVERY_TRANSCRIPT_SCHEMA_VERSION,
    AccuracyStatus,
    DeliveryStatus,
    DeliveryTranscriptReceipt,
    FindingAuthority,
    FindingOutcome,
    FindingStatus,
    MeasurementRecord,
    PublicationChannel,
    PublicationEvent,
    PublicationMember,
    PublicationOutcome,
    PublicationPlacement,
    StopKind,
    TaskDeliveryEvent,
    TaskDeliveryTerminalStatus,
    TaskStatus,
    TruthStatus,
    decode_measurement_record,
)
from attest.benchmark.report import LIVE_MODE, REPLAY_MODE
from attest.benchmark.runner import Cassette, ReplayProvider, ReproReceipt
from attest.benchmark.schema import (
    BenchmarkManifest,
    Placement,
    Prediction,
    RunRecord,
    load_manifest,
)
from attest.review.config import ReviewConfig
from attest.review.proposer import Provider

from ._validation_v2 import KEY, KEY_ID, build_validation_v2_bundle, verified_validation_authority
from .test_cli import _run
from .test_corpus import _oracle_fixture


def _current_validation_authority(manifest_path: Path):
    return verified_validation_authority(
        manifest_path.parent / "report-validation-authority", manifest_path
    )


def _freeze(manifest: Path) -> Path:
    """Freeze the preregistration digest over the protocol and manifest bytes."""
    protocol = manifest.parent / "protocol.md"
    if not protocol.exists():
        protocol.write_text("# protocol\n", encoding="utf-8")
    digest = hashlib.sha256(
        protocol.read_bytes() + b"\x00" + manifest.read_bytes()
    ).hexdigest()
    frozen = manifest.parent / "preregistration.sha256"
    frozen.write_text(f"{digest}  protocol.md+manifest.json\n", encoding="utf-8")
    return frozen


def _devspend(tmp_path: Path, total: str = "3.5930", cap: str = "10.00") -> Path:
    path = tmp_path / "DEVSPEND.md"
    path.write_text(
        f"# Development spend ledger\n\n**Total API spend: ${total} of ${cap}.**\n",
        encoding="utf-8",
    )
    return path


def _frozen_manifest(tmp_path: Path) -> Path:
    manifest = tmp_path / "benchmark" / "manifest.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text("{}", encoding="utf-8")
    _freeze(manifest)
    return manifest


_KEY_ENV = {"ANTHROPIC_API_KEY": "k" * 32}


def _preflight(
    tmp_path: Path,
    *,
    allow_paid_api: bool = True,
    manifest: Path | None = None,
    devspend: Path | None = None,
    case_budgets_usd: tuple[float, ...] = (0.25,),
    env: Mapping[str, str] | None = None,
) -> object:
    return preflight_live(
        allow_paid_api=allow_paid_api,
        manifest_path=manifest if manifest is not None else _frozen_manifest(tmp_path),
        devspend_path=devspend if devspend is not None else _devspend(tmp_path),
        case_budgets_usd=case_budgets_usd,
        env=_KEY_ENV if env is None else env,
    )


class TestPreflight:
    def test_rejects_without_explicit_paid_opt_in_before_anything_else(
        self, tmp_path: Path
    ) -> None:
        """The opt-in is checked first: nothing else is read or constructed."""
        with pytest.raises(LivePreflightError) as caught:
            preflight_live(
                allow_paid_api=False,
                manifest_path=tmp_path / "missing-manifest.json",
                devspend_path=tmp_path / "missing-devspend.md",
                case_budgets_usd=(0.25,),
                env={},
            )
        assert caught.value.reason == REASON_PAID_API_NOT_ALLOWED
        assert "--allow-paid-api" in str(caught.value)

    def test_rejects_missing_or_short_key_without_ever_logging_it(
        self, tmp_path: Path
    ) -> None:
        manifest = _frozen_manifest(tmp_path)
        devspend = _devspend(tmp_path)
        for env in ({}, {"ANTHROPIC_API_KEY": ""}, {"ANTHROPIC_API_KEY": "short"}):
            with pytest.raises(LivePreflightError) as caught:
                _preflight(tmp_path, manifest=manifest, devspend=devspend, env=env)
            assert caught.value.reason == REASON_API_KEY_UNAVAILABLE
            key = env.get("ANTHROPIC_API_KEY")
            if key:
                assert key not in str(caught.value)

    def test_rejects_unfrozen_preregistration(self, tmp_path: Path) -> None:
        manifest = tmp_path / "benchmark" / "manifest.json"
        manifest.parent.mkdir(parents=True)
        manifest.write_text("{}", encoding="utf-8")
        devspend = _devspend(tmp_path)

        with pytest.raises(LivePreflightError) as missing:
            _preflight(tmp_path, manifest=manifest, devspend=devspend)
        assert missing.value.reason == REASON_PREREGISTRATION_NOT_FROZEN

        (manifest.parent / "preregistration.sha256").write_text(
            "not-a-digest\n", encoding="utf-8"
        )
        with pytest.raises(LivePreflightError) as malformed:
            _preflight(tmp_path, manifest=manifest, devspend=devspend)
        assert malformed.value.reason == REASON_PREREGISTRATION_NOT_FROZEN

    def test_rejects_manifest_that_drifted_from_its_frozen_digest(
        self, tmp_path: Path
    ) -> None:
        """A manifest edited after freezing is not immutable and buys nothing."""
        manifest = _frozen_manifest(tmp_path)
        manifest.write_text('{"edited": true}', encoding="utf-8")
        with pytest.raises(LivePreflightError) as caught:
            _preflight(tmp_path, manifest=manifest, devspend=_devspend(tmp_path))
        assert caught.value.reason == REASON_MANIFEST_NOT_IMMUTABLE

    def test_rejects_insufficient_development_cap_headroom(self, tmp_path: Path) -> None:
        manifest = _frozen_manifest(tmp_path)
        devspend = _devspend(tmp_path, total="9.90", cap="10.00")
        with pytest.raises(LivePreflightError) as caught:
            _preflight(
                tmp_path,
                manifest=manifest,
                devspend=devspend,
                case_budgets_usd=(0.25, 0.25),
            )
        assert caught.value.reason == REASON_INSUFFICIENT_HEADROOM

    def test_fails_closed_on_unreadable_spend_ledger(self, tmp_path: Path) -> None:
        manifest = _frozen_manifest(tmp_path)
        garbled = tmp_path / "DEVSPEND.md"
        garbled.write_text("no total line here\n", encoding="utf-8")
        with pytest.raises(ValueError, match="spend"):
            _preflight(tmp_path, manifest=manifest, devspend=garbled)
        with pytest.raises(ValueError, match="spend"):
            _preflight(tmp_path, manifest=manifest, devspend=tmp_path / "absent.md")

    def test_passing_preflight_reports_reservation_and_headroom_but_no_key(
        self, tmp_path: Path
    ) -> None:
        manifest = _frozen_manifest(tmp_path)
        devspend = _devspend(tmp_path, total="2.00", cap="10.00")
        result = preflight_live(
            allow_paid_api=True,
            manifest_path=manifest,
            devspend_path=devspend,
            case_budgets_usd=(0.25, 0.50),
            env=_KEY_ENV,
        )
        assert result.reserved_total_usd == pytest.approx(0.75)
        assert result.devspend_total_usd == pytest.approx(2.00)
        assert result.devspend_cap_usd == pytest.approx(10.00)
        assert result.headroom_usd == pytest.approx(10.00 - 2.00 - 0.75)
        assert result.manifest_sha256 == hashlib.sha256(manifest.read_bytes()).hexdigest()
        assert "k" * 32 not in json.dumps(result.to_json_dict())

    def test_read_devspend_parses_the_ledger_total_line(self, tmp_path: Path) -> None:
        total, cap = read_devspend(_devspend(tmp_path, total="3.5930", cap="10.00"))
        assert total == pytest.approx(3.5930)
        assert cap == pytest.approx(10.00)

    def test_read_devspend_rejects_a_decimal_cap_that_overflows_float(
        self, tmp_path: Path
    ) -> None:
        """An unbounded decimal cannot turn the hard development cap into infinity."""
        ledger = _devspend(tmp_path, total="0", cap="9" * 1_000)

        with pytest.raises(ValueError, match="finite"):
            read_devspend(ledger)

    def test_read_devspend_rejects_overflowed_total_and_cap(
        self, tmp_path: Path
    ) -> None:
        """Infinity minus infinity must not become trusted NaN headroom."""
        huge = "9" * 1_000
        ledger = _devspend(tmp_path, total=huge, cap=huge)

        with pytest.raises(ValueError, match="finite"):
            read_devspend(ledger)

    @pytest.mark.parametrize(
        ("total", "cap"),
        (("0", "0"), ("10.01", "10.00")),
    )
    def test_read_devspend_rejects_an_invalid_hard_cap_range(
        self, tmp_path: Path, total: str, cap: str
    ) -> None:
        """The ledger cannot declare a zero cap or spend beyond its cap."""
        ledger = _devspend(tmp_path, total=total, cap=cap)

        with pytest.raises(ValueError, match="total.*cap"):
            read_devspend(ledger)

    def test_preflight_rejects_a_finite_budget_sequence_whose_sum_overflows(
        self, tmp_path: Path
    ) -> None:
        """Every reserved aggregate must remain finite before live side effects."""
        manifest = _frozen_manifest(tmp_path)
        ledger = _devspend(tmp_path, total="0", cap="10")

        with pytest.raises(ValueError, match="reserved.*finite"):
            _preflight(
                tmp_path,
                manifest=manifest,
                devspend=ledger,
                case_budgets_usd=(1e308, 1e308),
            )

    @pytest.mark.parametrize(
        "budget",
        (False, "0.25", 0, -1, float("nan"), float("inf")),
    )
    def test_preflight_rejects_non_positive_or_non_finite_case_budgets(
        self, tmp_path: Path, budget: object
    ) -> None:
        """A paid reservation accepts only exact positive finite numbers."""
        manifest = _frozen_manifest(tmp_path)
        ledger = _devspend(tmp_path, total="0", cap="10")

        with pytest.raises(ValueError, match="finite positive"):
            _preflight(
                tmp_path,
                manifest=manifest,
                devspend=ledger,
                case_budgets_usd=(budget,),  # type: ignore[arg-type]
            )


def _completed_result(
    case_id: str,
    *,
    spend: float = 0.0,
    oracle: float = 0.0,
    latency: float = 1.5,
    predictions: tuple[Prediction, ...] = (),
    receipts: tuple[ReproReceipt, ...] = (),
    abstain_reason: str | None = None,
) -> ProjectEvaluationResult:
    if abstain_reason is not None and predictions:
        raise ValueError("the fully-deferred fixture cannot publish findings")
    task_id = f"task-{case_id}"
    repository = "fixture/repository"
    pull_request_number = 1
    head_sha = "h" * 40
    members = tuple(
        PublicationMember(
            finding_id=prediction.finding_id,
            placement=PublicationPlacement(prediction.placement.value),
        )
        for prediction in predictions
    )
    publication_events: tuple[PublicationEvent, ...] = ()
    task_delivery_events: tuple[TaskDeliveryEvent, ...] = ()
    if abstain_reason is None:
        attempt_id = hashlib.sha256(f"{task_id}:0:status_summary".encode()).hexdigest()
        body = {
            "members": [member.to_json_dict() for member in members],
            "terminal_status": TaskDeliveryTerminalStatus.COMPLETED.value,
        }
        body_sha256 = hashlib.sha256(
            json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        request = {
            "repository": repository,
            "pull_request_number": pull_request_number,
            "head_sha": head_sha,
            "channel": PublicationChannel.STATUS_SUMMARY.value,
            "body_sha256": body_sha256,
        }
        request_sha256 = hashlib.sha256(
            json.dumps(request, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        if members:
            publication_events = (
                PublicationEvent(
                    event_id=hashlib.sha256(
                        f"{attempt_id}:publication".encode()
                    ).hexdigest(),
                    attempt_id=attempt_id,
                    attempt_ordinal=0,
                    repository=repository,
                    pull_request_number=pull_request_number,
                    head_sha=head_sha,
                    members=members,
                    channel=PublicationChannel.STATUS_SUMMARY,
                    outcome=PublicationOutcome.SUCCEEDED,
                    body_sha256=body_sha256,
                    request_sha256=request_sha256,
                    remote_response_id="1",
                    delivered_at_s=1.0,
                    deadline_s=60.0,
                ),
            )
        task_delivery_events = (
            TaskDeliveryEvent(
                event_id=hashlib.sha256(
                    f"{attempt_id}:task_delivery".encode()
                ).hexdigest(),
                attempt_id=attempt_id,
                attempt_ordinal=0,
                repository=repository,
                pull_request_number=pull_request_number,
                head_sha=head_sha,
                channel=PublicationChannel.STATUS_SUMMARY,
                members=members,
                terminal_status=TaskDeliveryTerminalStatus.COMPLETED,
                outcome=PublicationOutcome.SUCCEEDED,
                body_sha256=body_sha256,
                request_sha256=request_sha256,
                remote_response_id="1",
                delivered_at_s=1.0,
                deadline_s=60.0,
            ),
        )
    attempts = tuple(
        sorted(
            {
                (event.attempt_ordinal, event.attempt_id)
                for event in (*publication_events, *task_delivery_events)
            }
        )
    )
    transcript_payload = {
        "schema_version": DELIVERY_TRANSCRIPT_SCHEMA_VERSION,
        "protocol": DELIVERY_TRANSCRIPT_PROTOCOL,
        "task_id": task_id,
        "expected_attempt_count": len(attempts),
        "last_attempt_ordinal": attempts[-1][0] if attempts else None,
        "attempts": [
            {"attempt_ordinal": ordinal, "attempt_id": attempt}
            for ordinal, attempt in attempts
        ],
    }
    transcript = DeliveryTranscriptReceipt(
        schema_version=DELIVERY_TRANSCRIPT_SCHEMA_VERSION,
        protocol=DELIVERY_TRANSCRIPT_PROTOCOL,
        task_id=task_id,
        expected_attempt_count=len(attempts),
        last_attempt_ordinal=attempts[-1][0] if attempts else None,
        transcript_sha256=hashlib.sha256(
            json.dumps(
                transcript_payload,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest(),
    )
    findings = tuple(
        FindingOutcome(
            finding_id=prediction.finding_id,
            finding_status=FindingStatus.PUBLISHED,
            accuracy_status=AccuracyStatus.UNADJUDICATED,
            defect_id=None,
            publication_event_ids=(publication_events[0].event_id,),
            authority=FindingAuthority.AUTOMATED,
        )
        for prediction in predictions
    )
    measurement = MeasurementRecord(
        schema_version=CURRENT_MEASUREMENT_SCHEMA_VERSION,
        scoring_semantics=CURRENT_MEASUREMENT_SEMANTICS,
        case_id=case_id,
        arm=ARM_ATTEST_PRODUCT,
        repeat=0,
        stop_kind=(
            StopKind.TASK_DEFER if abstain_reason is not None else StopKind.NONE
        ),
        task_status=(
            TaskStatus.FULLY_DEFERRED
            if abstain_reason is not None
            else TaskStatus.COMPLETED
        ),
        findings=findings,
        eligible_defect_ids=(),
        pull_request_number=pull_request_number,
        truth_status=TruthStatus.UNADJUDICATED,
        delivery_status=(
            DeliveryStatus.PUBLISHED_ON_TIME
            if predictions
            else DeliveryStatus.NO_PUBLICATION
        ),
        candidate_count=len(findings),
        published_count=len(findings),
        unresolved_count=0,
        publication_events=publication_events,
        task_delivery_events=task_delivery_events,
        delivery_transcript=transcript,
        metrics_withheld_reason=None,
        delivery_withheld_reason=None,
        task_delivery_withheld_reason=None,
    )
    run = RunRecord(
        run_id=f"run-{case_id}",
        case_id=case_id,
        repeat=0,
        predictions=predictions,
        delivery_at_s=None if abstain_reason else 1.0,
        deadline_s=60.0,
    )
    return ProjectEvaluationResult(
        case_id=case_id,
        status="deferred" if abstain_reason else "completed",
        task_id=task_id,
        base_sha="b" * 40,
        head_sha=head_sha,
        predictions=predictions,
        final_decisions=(),
        abstain_reason=abstain_reason,
        latency_s=latency,
        spend_usd=spend,
        oracle_spend_usd=oracle,
        artifacts=(),
        evidence_class_counts={},
        oracle_receipts=receipts,
        run=run,
        score=None,
        measurement=measurement,
    )


def _fake_case(
    tmp_path: Path, case_id: str, *, budget: float = 0.25, line_slack: int = 0
) -> LiveCase:
    manifest_path = tmp_path / "manifest.json"
    if not manifest_path.exists():
        _oracle_fixture(tmp_path)
    manifest = load_manifest(manifest_path)
    case = next(case for case in manifest.cases if case.case_id == case_id)
    runtime = next(row for row in manifest.runtime if row.case_id == case_id)
    truth = manifest_project_truth(manifest, case_id)
    repo = tmp_path / "cache" / runtime.cwd
    request = ProjectEvaluationRequest(
        case_id=case_id,
        repo=repo,
        base_ref=(
            case.fixed_commit
            if case.role == "historical_bug_replay"
            else case.buggy_commit
        ),
        head_ref=(
            case.buggy_commit
            if case.role == "historical_bug_replay"
            else case.fixed_commit
        ),
        workspace_root=tmp_path / "ws",
        config=ReviewConfig(budget_usd=budget),
        repeats=1,
        line_slack=line_slack,
        truth=truth,
        repository=f"local:{repo.resolve()}",
    )
    return LiveCase(
        request=request,
        source_id="source-111111111111",
        binding=build_evaluation_binding(
            request,
            provider_id="injected-fake-v1",
            interpreter_id="injected-python-v1",
            environment_sha256="e" * 64,
            code_sha256="c" * 64,
        ),
    )


def _manifest_live_case(
    manifest: BenchmarkManifest,
    root: Path,
    source_id: str,
    *,
    role: str = "developer_fix_control",
) -> LiveCase:
    case = next(case for case in manifest.cases if case.role == role)
    runtime = next(row for row in manifest.runtime if row.case_id == case.case_id)
    repo = root / runtime.cwd
    source = next(
        (source for source in manifest.sources if source.source_id == source_id),
        None,
    )
    return LiveCase(
        request=ProjectEvaluationRequest(
            case_id=case.case_id,
            repo=repo,
            base_ref=(
                case.fixed_commit
                if case.role == "historical_bug_replay"
                else case.buggy_commit
            ),
            head_ref=(
                case.buggy_commit
                if case.role == "historical_bug_replay"
                else case.fixed_commit
            ),
            workspace_root=root.parent / "workspace",
            config=ReviewConfig(k_samples=2),
            repeats=1,
            truth=manifest_project_truth(manifest, case.case_id),
            repository=(source.project_url if source is not None else f"local:{repo.resolve()}"),
        ),
        source_id=source_id,
    )


def _run_fake(
    tmp_path: Path,
    cases: list[LiveCase],
    evaluate: Callable[..., ProjectEvaluationResult],
    *,
    run_id: str = "pilot-1",
    resume: bool = False,
    on_transition: Callable[[str, str], None] | None = None,
    interpreters: Mapping[str, str] | None = None,
    env: dict[str, str] | None = None,
    provider_factory: Callable[[ProjectEvaluationRequest], Provider] | None = None,
    on_call_transition: Callable[[str, str, str], None] | None = None,
    validation_receipt: ValidationVerification | None = None,
    line_slack: int = 0,
) -> object:
    manifest = tmp_path / "manifest.json"
    if not manifest.exists():
        manifest, _, _ = _oracle_fixture(tmp_path)
    return run_live_local(
        cases,
        run_id=run_id,
        state_dir=tmp_path / "state",
        output_dir=tmp_path / "out",
        manifest=load_manifest(manifest),
        manifest_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest(),
        preregistration_sha256="f" * 64,
        provider_factory=(
            provider_factory
            if provider_factory is not None
            else lambda request: ReplayProvider(Cassette("{}", "{}"))
        ),
        resume=resume,
        evaluate=evaluate,
        on_transition=on_transition,
        interpreters=dict(interpreters or {}),
        env=env,
        on_call_transition=on_call_transition,
        validation_receipt=validation_receipt,
        line_slack=line_slack,
        provider_id="injected-fake-v1",
    )


class _Interrupt(RuntimeError):
    pass


class TestCheckpoints:
    @pytest.mark.parametrize("line_slack", (-1, True))
    def test_live_rejects_invalid_line_slack_before_side_effects(
        self, tmp_path: Path, line_slack: object
    ) -> None:
        manifest_path, root, source_id = _oracle_fixture(tmp_path)
        manifest = load_manifest(manifest_path)
        case = _manifest_live_case(manifest, root, source_id)
        provider_calls: list[str] = []
        evaluator_calls: list[str] = []
        state = tmp_path / "invalid-slack-state"
        output = tmp_path / "invalid-slack-output"

        with pytest.raises(ValueError, match="line_slack"):
            run_live_local(
                [case],
                run_id="invalid-slack",
                state_dir=state,
                output_dir=output,
                manifest=manifest,
                manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
                preregistration_sha256="f" * 64,
                provider_factory=lambda request: (
                    provider_calls.append(request.case_id)
                    or ReplayProvider(Cassette("{}", "{}"))
                ),
                evaluate=lambda request, provider: (
                    evaluator_calls.append(request.case_id)
                    or _completed_result(request.case_id)
                ),
                line_slack=line_slack,  # type: ignore[arg-type]
            )
        assert provider_calls == []
        assert evaluator_calls == []
        assert not state.exists()
        assert not output.exists()

    def test_live_rejects_request_line_slack_drift_before_side_effects(
        self, tmp_path: Path
    ) -> None:
        manifest_path, root, source_id = _oracle_fixture(tmp_path)
        manifest = load_manifest(manifest_path)
        case = _manifest_live_case(manifest, root, source_id)
        case = replace(case, request=replace(case.request, line_slack=1))
        provider_calls: list[str] = []
        evaluator_calls: list[str] = []
        state = tmp_path / "request-slack-state"
        output = tmp_path / "request-slack-output"

        with pytest.raises(ValueError, match="line_slack"):
            run_live_local(
                [case],
                run_id="request-slack",
                state_dir=state,
                output_dir=output,
                manifest=manifest,
                manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
                preregistration_sha256="f" * 64,
                provider_factory=lambda request: (
                    provider_calls.append(request.case_id)
                    or ReplayProvider(Cassette("{}", "{}"))
                ),
                evaluate=lambda request, provider: (
                    evaluator_calls.append(request.case_id)
                    or _completed_result(request.case_id)
                ),
                line_slack=0,
            )
        assert provider_calls == []
        assert evaluator_calls == []
        assert not state.exists()
        assert not output.exists()

    @pytest.mark.parametrize(
        "drift",
        ("source", "repository", "base", "head", "truth", "case"),
    )
    def test_live_rejects_manifest_case_drift_before_side_effects(
        self, tmp_path: Path, drift: str
    ) -> None:
        manifest_path, root, source_id = _oracle_fixture(tmp_path)
        if drift == "repository":
            document = json.loads(manifest_path.read_text(encoding="utf-8"))
            case = document["cases"][0]
            document["sources"] = [
                {
                    "source_id": source_id,
                    "project_url": "https://example.invalid/original.git",
                    "source_license": "MIT",
                    "license_file": "LICENSE",
                    "license_sha256": "1" * 64,
                    "license_commits_verified": [
                        case["buggy_commit"],
                        case["fixed_commit"],
                    ],
                }
            ]
            manifest_path.write_text(json.dumps(document), encoding="utf-8")
        manifest = load_manifest(manifest_path)
        role = "historical_bug_replay" if drift == "truth" else "developer_fix_control"
        live_case = _manifest_live_case(manifest, root, source_id, role=role)
        request = live_case.request
        if drift == "source":
            live_case = replace(live_case, source_id="source-999999999999")
        elif drift == "repository":
            live_case = replace(
                live_case,
                request=replace(
                    request,
                    repository="https://example.invalid/different.git",
                ),
            )
        elif drift == "base":
            live_case = replace(live_case, request=replace(request, base_ref=request.head_ref))
        elif drift == "head":
            live_case = replace(live_case, request=replace(request, head_ref=request.base_ref))
        elif drift == "truth":
            assert request.truth is not None
            changed = replace(request.truth.defects[0], file="different.py")
            live_case = replace(
                live_case,
                request=replace(
                    request,
                    truth=replace(request.truth, defects=(changed, *request.truth.defects[1:])),
                ),
            )
        else:
            live_case = replace(
                live_case,
                request=replace(request, case_id="case-999999999999", truth=None),
            )
        provider_calls: list[str] = []
        evaluator_calls: list[str] = []
        state = tmp_path / f"{drift}-manifest-state"
        output = tmp_path / f"{drift}-manifest-output"

        with pytest.raises(ValueError, match="manifest|source|repo|commit|truth|case"):
            run_live_local(
                [live_case],
                run_id=f"{drift}-manifest",
                state_dir=state,
                output_dir=output,
                manifest=manifest,
                manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
                preregistration_sha256="f" * 64,
                provider_factory=lambda item: (
                    provider_calls.append(item.case_id)
                    or ReplayProvider(Cassette("{}", "{}"))
                ),
                evaluate=lambda item, provider: (
                    evaluator_calls.append(item.case_id)
                    or _completed_result(item.case_id)
                ),
            )
        assert provider_calls == []
        assert evaluator_calls == []
        assert not state.exists()
        assert not output.exists()

    def test_live_accepts_an_equivalent_checkout_path_for_the_same_bound_inputs(
        self, tmp_path: Path
    ) -> None:
        manifest_path, root, source_id = _oracle_fixture(tmp_path)
        manifest = load_manifest(manifest_path)
        case = _manifest_live_case(manifest, root, source_id)
        alias = tmp_path / "equivalent-checkout"
        alias.symlink_to(case.request.repo, target_is_directory=True)
        case = replace(case, request=replace(case.request, repo=alias))

        result = run_live_local(
            [case],
            run_id="equivalent-checkout",
            state_dir=tmp_path / "equivalent-state",
            output_dir=tmp_path / "equivalent-output",
            manifest=manifest,
            manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            preregistration_sha256="f" * 64,
            provider_factory=lambda item: ReplayProvider(Cassette("{}", "{}")),
            evaluate=lambda item, provider: _completed_result(item.case_id),
        )

        assert result.executed_cases == 1

    @pytest.mark.parametrize(
        "field",
        ("config", "limits", "verification_timeout_s", "repeats", "deadline_s", "line_slack"),
    )
    def test_live_rejects_mixed_study_policy_before_side_effects(
        self, tmp_path: Path, field: str
    ) -> None:
        cases = [
            _fake_case(tmp_path, "case-333333333333"),
            _fake_case(tmp_path, "case-444444444444"),
        ]
        request = cases[1].request
        values: dict[str, object] = {
            "config": replace(request.config, alpha=0.2),
            "limits": replace(request.limits, wall_timeout_s=61.0),
            "verification_timeout_s": request.verification_timeout_s + 1.0,
            "repeats": request.repeats + 1,
            "deadline_s": request.deadline_s + 1.0,
            "line_slack": request.line_slack + 1,
        }
        cases[1] = replace(cases[1], request=replace(request, **{field: values[field]}))
        provider_calls: list[str] = []
        evaluator_calls: list[str] = []

        with pytest.raises(ValueError, match="policy|configuration|line_slack|study"):
            _run_fake(
                tmp_path,
                cases,
                lambda item, provider: (
                    evaluator_calls.append(item.case_id)
                    or _completed_result(item.case_id)
                ),
                provider_factory=lambda item: (
                    provider_calls.append(item.case_id)
                    or ReplayProvider(Cassette("{}", "{}"))
                ),
            )
        assert provider_calls == []
        assert evaluator_calls == []
        assert not (tmp_path / "state").exists()
        assert not (tmp_path / "out").exists()

    def test_live_rejects_nonprimary_request_repeat_before_side_effects(
        self, tmp_path: Path
    ) -> None:
        case = _fake_case(tmp_path, "case-333333333333")
        case = replace(case, request=replace(case.request, repeat=1))
        provider_calls: list[str] = []
        evaluator_calls: list[str] = []

        with pytest.raises(ValueError, match="repeat"):
            _run_fake(
                tmp_path,
                [case],
                lambda item, provider: (
                    evaluator_calls.append(item.case_id)
                    or _completed_result(item.case_id)
                ),
                provider_factory=lambda item: (
                    provider_calls.append(item.case_id)
                    or ReplayProvider(Cassette("{}", "{}"))
                ),
            )
        assert provider_calls == []
        assert evaluator_calls == []
        assert not (tmp_path / "state").exists()
        assert not (tmp_path / "out").exists()

    @pytest.mark.parametrize(
        ("role", "multiplier"),
        (("developer_fix_control", 1.0), ("historical_bug_replay", 2.0)),
    )
    def test_live_reservation_doubles_only_for_positive_oracle_truth(
        self, tmp_path: Path, role: str, multiplier: float
    ) -> None:
        manifest_path, root, source_id = _oracle_fixture(tmp_path)
        case = _manifest_live_case(
            load_manifest(manifest_path), root, source_id, role=role
        )

        assert reserved_case_budget_usd(case.request) == pytest.approx(
            case.request.config.budget_usd * multiplier
        )

    @pytest.mark.parametrize(
        "budget", (float("nan"), float("inf"), float("-inf"), True)
    )
    def test_live_rejects_invalid_mutated_budget_before_side_effects(
        self, tmp_path: Path, budget: object
    ) -> None:
        manifest_path, root, source_id = _oracle_fixture(tmp_path)
        manifest = load_manifest(manifest_path)
        case = _manifest_live_case(manifest, root, source_id)
        case.request.config.budget_usd = budget  # type: ignore[assignment]
        provider_calls: list[str] = []
        evaluator_calls: list[str] = []
        state = tmp_path / "invalid-budget-state"
        output = tmp_path / "invalid-budget-output"

        with pytest.raises(ValueError, match="budget"):
            run_live_local(
                [case],
                run_id="invalid-budget",
                state_dir=state,
                output_dir=output,
                manifest=manifest,
                manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
                preregistration_sha256="f" * 64,
                provider_factory=lambda request: (
                    provider_calls.append(request.case_id)
                    or ReplayProvider(Cassette("{}", "{}"))
                ),
                evaluate=lambda request, provider: (
                    evaluator_calls.append(request.case_id)
                    or _completed_result(request.case_id)
                ),
            )
        assert provider_calls == []
        assert evaluator_calls == []
        assert not state.exists()
        assert not output.exists()

    def test_live_rejects_truth_budget_multiplier_overflow_before_side_effects(
        self, tmp_path: Path
    ) -> None:
        """A finite product budget cannot derive an infinite truth reservation."""
        manifest_path, root, source_id = _oracle_fixture(tmp_path)
        manifest = load_manifest(manifest_path)
        case = _manifest_live_case(
            manifest, root, source_id, role="historical_bug_replay"
        )
        case.request.config.budget_usd = 1e308
        provider_calls: list[str] = []
        evaluator_calls: list[str] = []
        state = tmp_path / "derived-overflow-state"
        output = tmp_path / "derived-overflow-output"

        with pytest.raises(ValueError, match="reservation.*finite"):
            run_live_local(
                [case],
                run_id="derived-overflow",
                state_dir=state,
                output_dir=output,
                manifest=manifest,
                manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
                preregistration_sha256="f" * 64,
                provider_factory=lambda request: (
                    provider_calls.append(request.case_id)
                    or ReplayProvider(Cassette("{}", "{}"))
                ),
                interpreters={source_id: sys.executable},
                evaluate=lambda request, provider: (
                    evaluator_calls.append(request.case_id)
                    or _completed_result(request.case_id)
                ),
            )
        assert provider_calls == []
        assert evaluator_calls == []
        assert not state.exists()
        assert not output.exists()

    def test_live_rejects_finite_case_reservations_whose_sum_overflows(
        self, tmp_path: Path
    ) -> None:
        """The complete public-API reservation is finite before state is created."""
        manifest_path, root, source_id = _oracle_fixture(tmp_path)
        manifest = load_manifest(manifest_path)
        control = _manifest_live_case(manifest, root, source_id)
        replay = _manifest_live_case(
            manifest, root, source_id, role="historical_bug_replay"
        )
        control.request.config.budget_usd = 8e307
        replay.request.config.budget_usd = 8e307
        provider_calls: list[str] = []
        evaluator_calls: list[str] = []
        state = tmp_path / "aggregate-overflow-state"
        output = tmp_path / "aggregate-overflow-output"

        with pytest.raises(ValueError, match="reserved total.*finite"):
            run_live_local(
                [control, replay],
                run_id="aggregate-overflow",
                state_dir=state,
                output_dir=output,
                manifest=manifest,
                manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
                preregistration_sha256="f" * 64,
                provider_factory=lambda request: (
                    provider_calls.append(request.case_id)
                    or ReplayProvider(Cassette("{}", "{}"))
                ),
                interpreters={source_id: sys.executable},
                evaluate=lambda request, provider: (
                    evaluator_calls.append(request.case_id)
                    or _completed_result(request.case_id)
                ),
            )
        assert provider_calls == []
        assert evaluator_calls == []
        assert not state.exists()
        assert not output.exists()

    def test_live_resume_rejects_pull_request_policy_drift(
        self, tmp_path: Path
    ) -> None:
        manifest_path, root, source_id = _oracle_fixture(tmp_path)
        manifest = load_manifest(manifest_path)
        case = _manifest_live_case(manifest, root, source_id)
        common = {
            "run_id": "pr-policy-drift",
            "state_dir": tmp_path / "pr-state",
            "output_dir": tmp_path / "pr-output",
            "manifest": manifest,
            "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            "preregistration_sha256": "f" * 64,
            "evaluate": lambda item, provider: _completed_result(item.case_id),
        }
        run_live_local(
            [case],
            provider_factory=lambda item: ReplayProvider(Cassette("{}", "{}")),
            **common,  # type: ignore[arg-type]
        )
        before = {
            str(path.relative_to(common["state_dir"])): path.read_bytes()  # type: ignore[union-attr]
            for path in sorted((common["state_dir"]).rglob("*"))  # type: ignore[union-attr]
            if path.is_file()
        }
        drifted = replace(
            case, request=replace(case.request, pull_request_number=2)
        )
        provider_calls: list[str] = []

        with pytest.raises(ValueError, match="predeclaration|policy"):
            run_live_local(
                [drifted],
                provider_factory=lambda item: (
                    provider_calls.append(item.case_id)
                    or ReplayProvider(Cassette("{}", "{}"))
                ),
                resume=True,
                **common,  # type: ignore[arg-type]
            )
        assert provider_calls == []
        assert {
            str(path.relative_to(common["state_dir"])): path.read_bytes()  # type: ignore[union-attr]
            for path in sorted((common["state_dir"]).rglob("*"))  # type: ignore[union-attr]
            if path.is_file()
        } == before

    @pytest.mark.parametrize(
        "field", ("base_sha", "head_sha", "fixed_sha", "diff_sha256", "provider_id")
    )
    def test_fresh_live_rejects_prebuilt_binding_identity_drift(
        self, tmp_path: Path, field: str
    ) -> None:
        case = _fake_case(tmp_path, "case-444444444444")
        assert case.binding is not None
        values: dict[str, object] = {
            "base_sha": case.binding.head_sha,
            "head_sha": case.binding.base_sha,
            "fixed_sha": "1" * 40,
            "diff_sha256": "1" * 64,
            "provider_id": "different-provider-v1",
        }
        case = replace(
            case,
            binding=replace(case.binding, **{field: values[field]}),
        )
        provider_calls: list[str] = []
        evaluator_calls: list[str] = []

        with pytest.raises(ValueError, match="binding|provider|commit|diff"):
            _run_fake(
                tmp_path,
                [case],
                lambda item, provider: (
                    evaluator_calls.append(item.case_id)
                    or _completed_result(item.case_id)
                ),
                provider_factory=lambda item: (
                    provider_calls.append(item.case_id)
                    or ReplayProvider(Cassette("{}", "{}"))
                ),
            )
        assert provider_calls == []
        assert evaluator_calls == []
        assert not (tmp_path / "state").exists()
        assert not (tmp_path / "out").exists()

    def test_current_authority_for_same_manifest_fails_before_side_effects(
        self, tmp_path: Path
    ) -> None:
        """Even a valid same-manifest HMAC capability cannot enter live execution."""
        manifest_path, root, source_id = _oracle_fixture(tmp_path)
        manifest = load_manifest(manifest_path)
        authority = _current_validation_authority(manifest_path)
        case = _manifest_live_case(manifest, root, source_id)
        provider_calls: list[str] = []
        evaluator_calls: list[str] = []
        state = tmp_path / "same-current-state"
        output = tmp_path / "same-current-output"

        with pytest.raises(ValueError, match="X-01|public-key|symmetric"):
            run_live_local(
                [case],
                run_id="same-current-refused",
                state_dir=state,
                output_dir=output,
                manifest=manifest,
                manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
                preregistration_sha256="f" * 64,
                provider_factory=lambda request: (
                    provider_calls.append(request.case_id)
                    or ReplayProvider(Cassette("{}", "{}"))
                ),
                evaluate=lambda request, provider: (
                    evaluator_calls.append(request.case_id)
                    or _completed_result(request.case_id)
                ),
                validation_receipt=authority,
            )
        assert provider_calls == []
        assert evaluator_calls == []
        assert not state.exists()
        assert not output.exists()

    def test_raw_v2_receipt_fails_before_live_side_effects(
        self, tmp_path: Path
    ) -> None:
        manifest_path, root, source_id = _oracle_fixture(tmp_path)
        manifest = load_manifest(manifest_path)
        receipt = _current_validation_authority(manifest_path).receipt
        assert receipt is not None
        case = _manifest_live_case(manifest, root, source_id)
        provider_calls: list[str] = []
        evaluator_calls: list[str] = []
        state = tmp_path / "raw-v2-state"
        output = tmp_path / "raw-v2-output"

        with pytest.raises(ValueError, match="X-01|public-key|symmetric"):
            run_live_local(
                [case],
                run_id="raw-v2-refused",
                state_dir=state,
                output_dir=output,
                manifest=manifest,
                manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
                preregistration_sha256="f" * 64,
                provider_factory=lambda request: (
                    provider_calls.append(request.case_id)
                    or ReplayProvider(Cassette("{}", "{}"))
                ),
                evaluate=lambda request, provider: (
                    evaluator_calls.append(request.case_id)
                    or _completed_result(request.case_id)
                ),
                validation_receipt=receipt,
            )
        assert provider_calls == []
        assert evaluator_calls == []
        assert not state.exists()
        assert not output.exists()

    def test_current_authority_for_another_manifest_fails_before_side_effects(
        self, tmp_path: Path
    ) -> None:
        """A same-process HMAC verifier capability never reaches live execution."""
        authority_root = tmp_path / "authority-a"
        authority_root.mkdir()
        manifest_a_path, _, _ = _oracle_fixture(authority_root)
        authority = _current_validation_authority(manifest_a_path)
        manifest_root = tmp_path / "manifest-b"
        manifest_root.mkdir()
        manifest_b_path, root_b, source_id = _oracle_fixture(manifest_root)
        document_b = json.loads(manifest_b_path.read_text(encoding="utf-8"))
        document_b["truth_defects"][0]["file"] = "different.py"
        manifest_b_path.write_text(json.dumps(document_b), encoding="utf-8")
        manifest_b = load_manifest(manifest_b_path)
        case = _manifest_live_case(manifest_b, root_b, source_id)
        provider_calls: list[str] = []
        evaluator_calls: list[str] = []
        state = tmp_path / "current-state"
        output = tmp_path / "current-output"

        with pytest.raises(ValueError, match="X-01|public-key|symmetric"):
            run_live_local(
                [case],
                run_id="current-refused",
                state_dir=state,
                output_dir=output,
                manifest=manifest_b,
                manifest_sha256=hashlib.sha256(manifest_b_path.read_bytes()).hexdigest(),
                preregistration_sha256="f" * 64,
                provider_factory=lambda request: (
                    provider_calls.append(request.case_id)
                    or ReplayProvider(Cassette("{}", "{}"))
                ),
                evaluate=lambda request, provider: (
                    evaluator_calls.append(request.case_id)
                    or _completed_result(request.case_id)
                ),
                validation_receipt=authority,
            )
        assert provider_calls == []
        assert evaluator_calls == []
        assert not state.exists()
        assert not output.exists()

    def test_wrong_manifest_digest_fails_before_live_side_effects(
        self, tmp_path: Path
    ) -> None:
        """Exact manifest bytes are checked before runtime, state, or dispatch."""
        manifest_path, root, source_id = _oracle_fixture(tmp_path)
        manifest = load_manifest(manifest_path)
        case = _manifest_live_case(manifest, root, source_id)
        provider_calls: list[str] = []
        evaluator_calls: list[str] = []
        state = tmp_path / "wrong-digest-state"
        output = tmp_path / "wrong-digest-output"

        with pytest.raises(ValueError, match="manifest.*digest"):
            run_live_local(
                [case],
                run_id="wrong-digest",
                state_dir=state,
                output_dir=output,
                manifest=manifest,
                manifest_sha256="0" * 64,
                preregistration_sha256="f" * 64,
                provider_factory=lambda request: (
                    provider_calls.append(request.case_id)
                    or ReplayProvider(Cassette("{}", "{}"))
                ),
                evaluate=lambda request, provider: (
                    evaluator_calls.append(request.case_id)
                    or _completed_result(request.case_id)
                ),
            )
        assert provider_calls == []
        assert evaluator_calls == []
        assert not state.exists()
        assert not output.exists()

    def test_full_budget_is_reserved_before_the_first_provider_call(
        self, tmp_path: Path
    ) -> None:
        """The run predeclaration (the reservation) must exist before any call."""
        seen: list[dict[str, object]] = []
        run_json = tmp_path / "state" / "pilot-1" / "run.json"

        def evaluate(
            request: ProjectEvaluationRequest, provider: object
        ) -> ProjectEvaluationResult:
            assert run_json.exists(), "reservation must precede the first paid call"
            seen.append(json.loads(run_json.read_text(encoding="utf-8")))
            return _completed_result(request.case_id)

        cases = [
            _fake_case(tmp_path, "case-333333333333"),
            _fake_case(tmp_path, "case-444444444444"),
        ]
        _run_fake(tmp_path, cases, evaluate)
        reserved = seen[0]["reserved_total_usd"]
        assert reserved == pytest.approx(
            sum(reserved_case_budget_usd(case.request) for case in cases)
        )
        assert [row["case_id"] for row in seen[0]["cases"]] == [
            "case-333333333333",
            "case-444444444444",
        ]

    def test_fresh_run_refuses_to_overwrite_an_existing_run(self, tmp_path: Path) -> None:
        cases = [_fake_case(tmp_path, "case-333333333333")]
        _run_fake(tmp_path, cases, lambda request, provider: _completed_result(request.case_id))
        with pytest.raises(ValueError, match="resume"):
            _run_fake(
                tmp_path, cases, lambda request, provider: _completed_result(request.case_id)
            )

    def test_resume_of_an_unknown_run_fails_closed(self, tmp_path: Path) -> None:
        cases = [_fake_case(tmp_path, "case-333333333333")]
        with pytest.raises(ValueError, match="predeclaration"):
            _run_fake(
                tmp_path,
                cases,
                lambda request, provider: _completed_result(request.case_id),
                resume=True,
            )

    def test_resume_under_a_drifted_predeclaration_fails_closed(
        self, tmp_path: Path
    ) -> None:
        _run_fake(
            tmp_path,
            [_fake_case(tmp_path, "case-333333333333")],
            lambda request, provider: _completed_result(request.case_id),
        )
        with pytest.raises(ValueError, match="predeclaration"):
            _run_fake(
                tmp_path,
                [_fake_case(tmp_path, "case-333333333333", budget=0.10)],
                lambda request, provider: _completed_result(request.case_id),
                resume=True,
            )

    def test_resume_rejects_retained_live_v4_predeclaration_before_side_effects(
        self, tmp_path: Path
    ) -> None:
        """The former v4 payload is history, not current configuration drift."""
        case = _fake_case(tmp_path, "case-333333333333")
        assert case.binding is not None
        binding_v1 = case.binding.to_json_dict()
        binding_v1["schema_version"] = "1"
        request = case.request
        config = request.config
        run_dir = tmp_path / "state" / "pilot-1"
        run_dir.mkdir(parents=True)
        old_v4 = {
            "schema_version": "4",
            "mode": "live_local",
            "paid_call_roles": ["benchmark_oracle", "product"],
            "run_id": "pilot-1",
            "manifest_sha256": hashlib.sha256(
                (tmp_path / "manifest.json").read_bytes()
            ).hexdigest(),
            "preregistration_sha256": "f" * 64,
            "line_slack": 0,
            "cases": [
                {
                    "case_id": request.case_id,
                    "source_id": case.source_id,
                    "base_ref": request.base_ref,
                    "head_ref": request.head_ref,
                    "reserved_usd": reserved_case_budget_usd(request),
                    "has_truth": request.truth is not None,
                    "evaluation_binding": binding_v1,
                }
            ],
            "reserved_total_usd": reserved_case_budget_usd(request),
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
        (run_dir / "run.json").write_text(
            json.dumps(old_v4, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        (run_dir / "retained-paid-state.bin").write_bytes(b"old-v4-paid-state")
        before = {
            str(path.relative_to(run_dir)): path.read_bytes()
            for path in sorted(run_dir.rglob("*"))
            if path.is_file()
        }
        provider_calls: list[str] = []
        evaluator_calls: list[str] = []

        with pytest.raises(
            ValueError,
            match=(
                "unsupported live predeclaration schema version '4'.*"
                "supported version is 5"
            ),
        ):
            _run_fake(
                tmp_path,
                [case],
                lambda item, provider: (
                    evaluator_calls.append(item.case_id)
                    or _completed_result(item.case_id)
                ),
                resume=True,
                provider_factory=lambda item: (
                    provider_calls.append(item.case_id)
                    or ReplayProvider(Cassette("{}", "{}"))
                ),
            )
        after = {
            str(path.relative_to(run_dir)): path.read_bytes()
            for path in sorted(run_dir.rglob("*"))
            if path.is_file()
        }
        assert after == before
        assert provider_calls == []
        assert evaluator_calls == []
        assert not (tmp_path / "out").exists()

    def test_fresh_run_rejects_absent_to_current_validation_authority_swap(
        self, tmp_path: Path
    ) -> None:
        """Report authority must equal the receipt frozen before any paid call."""
        manifest_path, _, _ = _oracle_fixture(tmp_path)
        case = _fake_case(tmp_path, "case-333333333333")
        authority = _current_validation_authority(manifest_path)
        provider_calls: list[str] = []
        evaluator_calls: list[str] = []

        def evaluate(
            request: ProjectEvaluationRequest, provider: object
        ) -> ProjectEvaluationResult:
            evaluator_calls.append(request.case_id)
            return _completed_result(request.case_id)

        with pytest.raises(ValueError, match="X-01|public-key|symmetric"):
            _run_fake(
                tmp_path,
                [case],
                evaluate,
                validation_receipt=authority,
                provider_factory=lambda request: (
                    provider_calls.append(request.case_id) or ReplayProvider(Cassette("{}", "{}"))
                ),
            )
        assert provider_calls == []
        assert evaluator_calls == []
        assert not (tmp_path / "state" / "pilot-1" / "run.json").exists()

    def test_live_rejects_receipt_digest_subclass_before_side_effects(
        self, tmp_path: Path
    ) -> None:
        """A prebuilt binding cannot override digest equality at the receipt join."""

        class DeceptiveDigest(str):
            def __eq__(self, other: object) -> bool:
                return True

            def __ne__(self, other: object) -> bool:
                return False

        case = _fake_case(tmp_path, "case-333333333333")
        assert case.binding is not None
        case = replace(
            case,
            binding=replace(
                case.binding,
                receipt_sha256=DeceptiveDigest("1" * 64),
            ),
        )
        provider_calls: list[str] = []
        evaluator_calls: list[str] = []

        with pytest.raises(ValueError, match="receipt.*(exact|binding|digest)"):
            _run_fake(
                tmp_path,
                [case],
                lambda request, provider: (
                    evaluator_calls.append(request.case_id)
                    or _completed_result(request.case_id)
                ),
                provider_factory=lambda request: (
                    provider_calls.append(request.case_id)
                    or ReplayProvider(Cassette("{}", "{}"))
                ),
            )
        assert provider_calls == []
        assert evaluator_calls == []
        assert not (tmp_path / "state").exists()
        assert not (tmp_path / "out").exists()

    @pytest.mark.parametrize(
        "field",
        [
            "repository",
            "base_sha",
            "head_sha",
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
        ],
    )
    def test_resume_rejects_every_binding_drift_before_provider_execution(
        self, tmp_path: Path, field: str
    ) -> None:
        case = _fake_case(tmp_path, "case-333333333333")
        _run_fake(
            tmp_path,
            [case],
            lambda request, provider: _completed_result(request.case_id),
        )
        assert case.binding is not None
        current = getattr(case.binding, field)
        if isinstance(current, float):
            changed: object = current + 0.01
        elif field in {"base_sha", "head_sha"}:
            changed = "1" * 40
        elif field.endswith("sha256"):
            changed = "1" * 64
        else:
            changed = str(current) + "-drift"
        drifted = replace(case, binding=replace(case.binding, **{field: changed}))
        provider_calls: list[str] = []

        def provider_factory(request: ProjectEvaluationRequest) -> ReplayProvider:
            provider_calls.append(request.case_id)
            return ReplayProvider(Cassette("{}", "{}"))

        with pytest.raises(ValueError, match="predeclaration|binding"):
            _run_fake(
                tmp_path,
                [drifted],
                lambda request, provider: _completed_result(request.case_id),
                resume=True,
                provider_factory=provider_factory,
            )
        assert provider_calls == []

    def test_reserved_case_with_no_provider_dispatch_can_resume_safely(
        self, tmp_path: Path
    ) -> None:
        """Only a subcall ``dispatched`` state is ambiguous; reservation alone is free."""

        def crash(request: ProjectEvaluationRequest, provider: object) -> ProjectEvaluationResult:
            raise _Interrupt("crashed mid-call")

        cases = [_fake_case(tmp_path, "case-333333333333")]
        with pytest.raises(_Interrupt):
            _run_fake(tmp_path, cases, crash)
        state = tmp_path / "state" / "pilot-1" / "cases" / "case-333333333333.json"
        assert json.loads(state.read_text(encoding="utf-8"))["state"] == STATE_RESERVED

        calls: list[str] = []

        def complete_after_restart(
            request: ProjectEvaluationRequest, provider: object
        ) -> ProjectEvaluationResult:
            calls.append(request.case_id)
            return _completed_result(request.case_id)

        result = _run_fake(tmp_path, cases, complete_after_restart, resume=True)
        assert calls == ["case-333333333333"]
        assert result.case_states == {"case-333333333333": STATE_REPORTED}
        assert state.exists(), "evidence must be retained"

    def test_durable_provider_subcall_replays_before_case_completion(
        self, tmp_path: Path
    ) -> None:
        case_id = "case-333333333333"
        cases = [_fake_case(tmp_path, case_id)]
        first = ReplayProvider(Cassette(proposal="{}", repro=""))

        def evaluate(
            request: ProjectEvaluationRequest, provider: Provider
        ) -> ProjectEvaluationResult:
            provider.sample("system", "prompt", {"type": "object"}, 20)
            return _completed_result(request.case_id)

        def interrupt(_case_id: str, _call_id: str, state: str) -> None:
            if state == CALL_RESPONSE_PERSISTED:
                raise _Interrupt(state)

        with pytest.raises(_Interrupt, match=CALL_RESPONSE_PERSISTED):
            _run_fake(
                tmp_path,
                cases,
                evaluate,
                provider_factory=lambda _request: first,
                on_call_transition=interrupt,
            )
        assert first.proposal_calls == 1

        resumed = ReplayProvider(Cassette(proposal="{}", repro=""))
        result = _run_fake(
            tmp_path,
            cases,
            evaluate,
            resume=True,
            provider_factory=lambda _request: resumed,
        )
        assert resumed.proposal_calls == 0
        assert result.case_states == {case_id: STATE_REPORTED}

    def test_live_artifact_cost_ledger_and_report_carry_paid_call_join(
        self, tmp_path: Path
    ) -> None:
        case_id = "case-333333333333"
        case = _fake_case(tmp_path, case_id)
        provider = ReplayProvider(Cassette(proposal="{}", repro=""))

        def evaluate(
            request: ProjectEvaluationRequest, paid: Provider
        ) -> ProjectEvaluationResult:
            paid.sample("system", "prompt", {"type": "object"}, 20)
            return _completed_result(request.case_id)

        result = _run_fake(
            tmp_path,
            [case],
            evaluate,
            provider_factory=lambda _request: provider,
        )

        case_artifact = json.loads(
            (
                tmp_path / "state" / "pilot-1" / "artifacts" / f"{case_id}.json"
            ).read_text(encoding="utf-8")
        )
        rows = [
            json.loads(line)
            for line in (
                tmp_path / "state" / "pilot-1" / "costs.jsonl"
            ).read_text(encoding="utf-8").splitlines()
            if line
        ]
        report = json.loads(result.report_path.read_text(encoding="utf-8"))

        assert len(case_artifact["paid_calls"]) == 1
        paid_call = case_artifact["paid_calls"][0]
        assert paid_call["trial_id"] == f"pilot-1:{case_id}"
        assert paid_call["call_id"] == f"pilot-1:{case_id}:0"
        assert rows[0]["kind"] == "case_summary"
        assert rows[0]["case_id"] == case_id
        assert rows[0]["paid_calls"] == [paid_call]
        assert report["paid_calls"] == [
            {"case_id": case_id, **paid_call}
        ]

    def test_live_rejects_result_spend_that_disagrees_with_role_rows(
        self, tmp_path: Path
    ) -> None:
        case_id = "case-333333333333"
        case = _fake_case(tmp_path, case_id)

        def evaluate(
            request: ProjectEvaluationRequest, paid: object
        ) -> ProjectEvaluationResult:
            paid.sample("product", "prompt", {"type": "object"}, 20)
            paid.for_role(CALL_ROLE_BENCHMARK_ORACLE).sample(
                "oracle", "prompt", {"type": "object"}, 20
            )
            return _completed_result(request.case_id, spend=0.01, oracle=0.01)

        with pytest.raises(ValueError, match="spend|role|reconciliation"):
            _run_fake(
                tmp_path,
                [case],
                evaluate,
                provider_factory=lambda _request: ReplayProvider(
                    Cassette("{}", "{}", input_tokens=10, output_tokens=10)
                ),
            )

    def test_completed_live_case_rejects_missing_paid_call_checkpoint(
        self, tmp_path: Path
    ) -> None:
        case_id = "case-333333333333"
        cases = [_fake_case(tmp_path, case_id)]

        def evaluate(
            request: ProjectEvaluationRequest, paid: Provider
        ) -> ProjectEvaluationResult:
            paid.sample("system", "prompt", {"type": "object"}, 20)
            return _completed_result(request.case_id)

        _run_fake(tmp_path, cases, evaluate)
        call = tmp_path / "state" / "pilot-1" / "calls" / case_id / "calls" / "000000.json"
        call.unlink()

        def must_not_run(
            request: ProjectEvaluationRequest, provider: Provider
        ) -> ProjectEvaluationResult:  # pragma: no cover - fail closed first
            raise AssertionError("resume must not evaluate an incomplete paid-call join")

        with pytest.raises(ValueError, match="checkpoint|paid.call|orphan"):
            _run_fake(tmp_path, cases, must_not_run, resume=True)

    def test_dispatched_without_response_is_ambiguous_and_never_retried(
        self, tmp_path: Path
    ) -> None:
        case_id = "case-333333333333"
        cases = [_fake_case(tmp_path, case_id)]
        first = ReplayProvider(Cassette(proposal="{}", repro=""))

        def evaluate(
            request: ProjectEvaluationRequest, provider: Provider
        ) -> ProjectEvaluationResult:
            provider.sample("system", "prompt", {"type": "object"}, 20)
            return _completed_result(request.case_id)

        def interrupt(_case_id: str, _call_id: str, state: str) -> None:
            if state == CALL_DISPATCHED:
                raise _Interrupt(state)

        with pytest.raises(_Interrupt, match=CALL_DISPATCHED):
            _run_fake(
                tmp_path,
                cases,
                evaluate,
                provider_factory=lambda _request: first,
                on_call_transition=interrupt,
            )
        assert first.proposal_calls == 0

        resumed = ReplayProvider(Cassette(proposal="{}", repro=""))
        with pytest.raises(AmbiguousCostError, match="ambiguous_cost"):
            _run_fake(
                tmp_path,
                cases,
                evaluate,
                resume=True,
                provider_factory=lambda _request: resumed,
            )
        assert resumed.proposal_calls == 0

    def test_interruption_after_artifact_persistence_settles_cost_exactly_once(
        self, tmp_path: Path
    ) -> None:
        case_id = "case-333333333333"
        cases = [_fake_case(tmp_path, case_id)]
        costs = tmp_path / "state" / "pilot-1" / "costs.jsonl"

        def interrupt(seen_case: str, state: str) -> None:
            if state == STATE_ARTIFACTS_COMPLETE:
                raise _Interrupt(state)

        with pytest.raises(_Interrupt):
            _run_fake(
                tmp_path,
                cases,
                lambda request, provider: _completed_result(request.case_id),
                on_transition=interrupt,
            )
        assert not costs.exists() or costs.read_text(encoding="utf-8") == ""

        def must_not_run(
            request: ProjectEvaluationRequest, provider: object
        ) -> ProjectEvaluationResult:  # pragma: no cover - defended against
            raise AssertionError("resume must not repeat a completed model call")

        first = _run_fake(tmp_path, cases, must_not_run, resume=True)
        rows = [
            json.loads(line)
            for line in costs.read_text(encoding="utf-8").splitlines()
            if line
        ]
        assert [row["case_id"] for row in rows] == [case_id]
        assert rows[0]["spend_usd"] == pytest.approx(0.0)

        second = _run_fake(tmp_path, cases, must_not_run, resume=True)
        rows_again = [
            json.loads(line)
            for line in costs.read_text(encoding="utf-8").splitlines()
            if line
        ]
        assert [row["case_id"] for row in rows_again] == [case_id]
        assert first.report.digest == second.report.digest

    def test_interruption_before_report_settlement_resumes_to_a_report(
        self, tmp_path: Path
    ) -> None:
        case_id = "case-333333333333"
        cases = [_fake_case(tmp_path, case_id)]

        def interrupt(seen_case: str, state: str) -> None:
            if state == STATE_SETTLED:
                raise _Interrupt(state)

        with pytest.raises(_Interrupt):
            _run_fake(
                tmp_path,
                cases,
                lambda request, provider: _completed_result(request.case_id),
                on_transition=interrupt,
            )
        assert not (tmp_path / "out" / "calibration.json").exists()

        result = _run_fake(
            tmp_path,
            cases,
            lambda request, provider: (_ for _ in ()).throw(AssertionError("re-call")),
            resume=True,
        )
        assert (tmp_path / "out" / "calibration.json").exists()
        assert result.case_states == {case_id: STATE_REPORTED}
        costs = tmp_path / "state" / "pilot-1" / "costs.jsonl"
        rows = [json.loads(line) for line in costs.read_text().splitlines() if line]
        assert len(rows) == 1

    def test_resume_verifies_artifact_hashes_and_fails_closed_on_tampering(
        self, tmp_path: Path
    ) -> None:
        case_id = "case-333333333333"
        cases = [_fake_case(tmp_path, case_id)]
        _run_fake(
            tmp_path, cases, lambda request, provider: _completed_result(request.case_id)
        )
        artifact = tmp_path / "state" / "pilot-1" / "artifacts" / f"{case_id}.json"
        artifact.write_text('{"tampered": true}\n', encoding="utf-8")
        with pytest.raises(ValueError, match="hash"):
            _run_fake(
                tmp_path,
                cases,
                lambda request, provider: _completed_result(request.case_id),
                resume=True,
            )
        assert artifact.exists(), "evidence must be retained"

    def test_corrupt_case_state_fails_closed_and_retains_evidence(
        self, tmp_path: Path
    ) -> None:
        case_id = "case-333333333333"
        cases = [_fake_case(tmp_path, case_id)]
        _run_fake(
            tmp_path, cases, lambda request, provider: _completed_result(request.case_id)
        )
        state = tmp_path / "state" / "pilot-1" / "cases" / f"{case_id}.json"
        state.write_text("{ not json", encoding="utf-8")
        with pytest.raises(ValueError, match="corrupt"):
            _run_fake(
                tmp_path,
                cases,
                lambda request, provider: _completed_result(request.case_id),
                resume=True,
            )
        assert state.exists()

    def test_old_case_checkpoint_reports_supported_version_and_recovery(
        self, tmp_path: Path
    ) -> None:
        case_id = "case-333333333333"
        cases = [_fake_case(tmp_path, case_id)]
        _run_fake(
            tmp_path, cases, lambda request, provider: _completed_result(request.case_id)
        )
        state = tmp_path / "state" / "pilot-1" / "cases" / f"{case_id}.json"
        payload = json.loads(state.read_text(encoding="utf-8"))
        payload["schema_version"] = "0"
        state.write_text(json.dumps(payload), encoding="utf-8")

        with pytest.raises(ValueError, match="unsupported.*schema version.*0.*supported"):
            _run_fake(
                tmp_path,
                cases,
                lambda request, provider: _completed_result(request.case_id),
                resume=True,
            )

    def test_unknown_cost_fails_closed_and_retains_the_paid_evidence(
        self, tmp_path: Path
    ) -> None:
        case_id = "case-333333333333"
        cases = [_fake_case(tmp_path, case_id)]
        with pytest.raises(ValueError, match="cost"):
            _run_fake(
                tmp_path,
                cases,
                lambda request, provider: _completed_result(
                    request.case_id, spend=math.nan
                ),
            )
        state = tmp_path / "state" / "pilot-1" / "cases" / f"{case_id}.json"
        stored = json.loads(state.read_text(encoding="utf-8"))
        assert stored["state"] in (STATE_PROVIDER_COMPLETE, STATE_ARTIFACTS_COMPLETE)
        assert stored["payload"] is not None
        costs = tmp_path / "state" / "pilot-1" / "costs.jsonl"
        assert not costs.exists() or costs.read_text(encoding="utf-8") == ""

    def test_interpreter_mapping_reaches_the_executor_environment_and_is_restored(
        self, tmp_path: Path
    ) -> None:
        """D-037: the orchestration passes ATTEST_PROJECT_PYTHON per source."""
        env = {"ATTEST_PROJECT_PYTHON": "preexisting", "UNRELATED": "kept"}
        observed: dict[str, str | None] = {}

        def evaluate(
            request: ProjectEvaluationRequest, provider: object
        ) -> ProjectEvaluationResult:
            observed[request.case_id] = env.get("ATTEST_PROJECT_PYTHON")
            return _completed_result(request.case_id)

        cases = [
            _fake_case(tmp_path, "case-333333333333"),
            _fake_case(tmp_path, "case-444444444444"),
        ]
        _run_fake(
            tmp_path,
            cases,
            evaluate,
            interpreters={"source-111111111111": "/opt/pinned/python3.8"},
            env=env,
        )
        assert observed == {
            "case-333333333333": "/opt/pinned/python3.8",
            "case-444444444444": "/opt/pinned/python3.8",
        }
        assert env["ATTEST_PROJECT_PYTHON"] == "preexisting"
        assert env["UNRELATED"] == "kept"

    def test_unmapped_source_leaves_the_environment_untouched(
        self, tmp_path: Path
    ) -> None:
        env: dict[str, str] = {}
        observed: dict[str, str | None] = {}

        def evaluate(
            request: ProjectEvaluationRequest, provider: object
        ) -> ProjectEvaluationResult:
            observed[request.case_id] = env.get("ATTEST_PROJECT_PYTHON")
            return _completed_result(request.case_id)

        _run_fake(
            tmp_path,
            [_fake_case(tmp_path, "case-333333333333")],
            evaluate,
            interpreters={"source-other": "/opt/other"},
            env=env,
        )
        assert observed == {"case-333333333333": None}
        assert "ATTEST_PROJECT_PYTHON" not in env


_PROPOSAL = json.dumps(
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
_SILENT = json.dumps({"findings": []})
_EMPTY_REPRO = json.dumps({"test_body": ""})


def test_two_case_live_run_interrupted_after_provider_completion_resumes_cleanly(
    tmp_path: Path,
) -> None:
    """End to end on the real product path with scripted fake providers.

    Case one (the silent control) completes and settles; the run is interrupted
    immediately after case two's provider work is checkpointed. Resume finishes
    case two without a single further provider call, settles each cost exactly
    once, and writes the live calibration report.
    """
    manifest_path, root, source_id = _oracle_fixture(tmp_path)
    _freeze(manifest_path)
    manifest = load_manifest(manifest_path)
    cases_by_role = {case.role: case for case in manifest.cases}
    control = cases_by_role["developer_fix_control"]
    replay = cases_by_role["historical_bug_replay"]
    truth = ProjectTruth(defects=manifest.truth_defects, fixed_ref=replay.fixed_commit)
    config = ReviewConfig(k_samples=2)
    plan = [
        LiveCase(
            request=ProjectEvaluationRequest(
                case_id=control.case_id,
                repo=root / source_id / control.pair_id / "control",
                base_ref=control.buggy_commit,
                head_ref=control.fixed_commit,
                workspace_root=tmp_path / "ws",
                config=config,
                repeats=1,
                truth=manifest_project_truth(manifest, control.case_id),
            ),
            source_id=source_id,
        ),
        LiveCase(
            request=ProjectEvaluationRequest(
                case_id=replay.case_id,
                repo=root / source_id / replay.pair_id / "replay",
                base_ref=replay.fixed_commit,
                head_ref=replay.buggy_commit,
                workspace_root=tmp_path / "ws",
                config=config,
                repeats=1,
                truth=truth,
            ),
            source_id=source_id,
        ),
    ]
    providers = {
        control.case_id: ReplayProvider(
            Cassette(_SILENT, _EMPTY_REPRO, input_tokens=800, output_tokens=200)
        ),
        replay.case_id: ReplayProvider(
            Cassette(_PROPOSAL, _REPRO, input_tokens=800, output_tokens=200)
        ),
    }
    factory_calls: list[str] = []

    def provider_factory(request: ProjectEvaluationRequest) -> ReplayProvider:
        factory_calls.append(request.case_id)
        return providers[request.case_id]

    def interrupt(case_id: str, state: str) -> None:
        if case_id == replay.case_id and state == STATE_PROVIDER_COMPLETE:
            raise _Interrupt(state)

    manifest_sha256 = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    prereg_sha256 = (
        (manifest_path.parent / "preregistration.sha256")
        .read_text(encoding="utf-8")
        .split()[0]
    )
    kwargs: dict[str, object] = {
        "run_id": "pilot-live-1",
        "state_dir": tmp_path / "state",
        "output_dir": tmp_path / "out",
        "manifest": manifest,
        "manifest_sha256": manifest_sha256,
        "preregistration_sha256": prereg_sha256,
        "interpreters": {source_id: sys.executable},
    }
    before = os.environ.get("ATTEST_PROJECT_PYTHON")

    with pytest.raises(_Interrupt):
        run_live_local(
            plan,
            provider_factory=provider_factory,
            on_transition=interrupt,
            **kwargs,  # type: ignore[arg-type]
        )

    assert os.environ.get("ATTEST_PROJECT_PYTHON") == before
    assert factory_calls == [control.case_id, replay.case_id]
    state_dir = tmp_path / "state" / "pilot-live-1"
    control_state = json.loads(
        (state_dir / "cases" / f"{control.case_id}.json").read_text(encoding="utf-8")
    )
    replay_state = json.loads(
        (state_dir / "cases" / f"{replay.case_id}.json").read_text(encoding="utf-8")
    )
    assert control_state["state"] == STATE_SETTLED
    assert replay_state["state"] == STATE_PROVIDER_COMPLETE
    cost_rows = [
        json.loads(line)
        for line in (state_dir / "costs.jsonl").read_text(encoding="utf-8").splitlines()
        if line
    ]
    assert [row["case_id"] for row in cost_rows] == [control.case_id]
    assert not (tmp_path / "out" / "calibration.json").exists()
    control_samples = providers[control.case_id].proposal_calls
    replay_samples = (
        providers[replay.case_id].proposal_calls
        + providers[replay.case_id].generator_calls
    )
    assert control_samples > 0
    assert replay_samples > 0

    def refuse_factory(request: ProjectEvaluationRequest) -> ReplayProvider:
        raise AssertionError("resume must never repeat a completed model call")

    result = run_live_local(
        plan,
        provider_factory=refuse_factory,
        resume=True,
        **kwargs,  # type: ignore[arg-type]
    )

    assert providers[control.case_id].proposal_calls == control_samples
    assert (
        providers[replay.case_id].proposal_calls
        + providers[replay.case_id].generator_calls
        == replay_samples
    )
    assert result.executed_cases == 0
    assert result.resumed_cases == 2
    assert result.case_states == {
        control.case_id: STATE_REPORTED,
        replay.case_id: STATE_REPORTED,
    }
    cost_rows = [
        json.loads(line)
        for line in (state_dir / "costs.jsonl").read_text(encoding="utf-8").splitlines()
        if line
    ]
    assert sorted(row["case_id"] for row in cost_rows) == sorted(
        [control.case_id, replay.case_id]
    )
    assert len(cost_rows) == 2
    assert result.settled_spend_usd == pytest.approx(
        sum(row["spend_usd"] for row in cost_rows)
    )
    assert result.settled_oracle_spend_usd == pytest.approx(
        sum(row["oracle_spend_usd"] for row in cost_rows)
    )
    replay_cost = next(row for row in cost_rows if row["case_id"] == replay.case_id)
    assert {call["role"] for call in replay_cost["paid_calls"]} == {
        CALL_ROLE_PRODUCT,
        CALL_ROLE_BENCHMARK_ORACLE,
    }
    assert replay_cost["spend_usd"] == pytest.approx(
        sum(
            call["cost_usd"]
            for call in replay_cost["paid_calls"]
            if call["role"] == CALL_ROLE_PRODUCT
        )
    )
    assert replay_cost["oracle_spend_usd"] == pytest.approx(
        sum(
            call["cost_usd"]
            for call in replay_cost["paid_calls"]
            if call["role"] == CALL_ROLE_BENCHMARK_ORACLE
        )
    )

    report = json.loads(
        (tmp_path / "out" / "calibration.json").read_text(encoding="utf-8")
    )
    assert report["mode"] == LIVE_MODE
    assert report["run_id"] == "pilot-live-1"
    assert report["cost"]["spend_total_usd"] == pytest.approx(
        result.settled_spend_usd
    )
    assert report["cost"]["oracle_spend_total_usd"] == pytest.approx(
        result.settled_oracle_spend_usd
    )
    assert report["cost"]["total_spend_usd"] == pytest.approx(
        result.settled_spend_usd + result.settled_oracle_spend_usd
    )
    assert report["accuracy_withheld_reason"] == "validation_receipt_missing"
    assert report["accuracy"] is None
    assert report["channel_outcomes"]["regression_reproduced"]["matched"] is None
    assert report["differential_v"]["confirmed"] == 1
    assert report["sample_sufficiency"]["status"] == "recommendation_only"
    assert report["sample_sufficiency"]["constants_patch"] == "prohibited"
    assert "live observation" in " ".join(report["limitations"])

    again = run_live_local(
        plan,
        provider_factory=refuse_factory,
        resume=True,
        **kwargs,  # type: ignore[arg-type]
    )
    assert again.report.digest == result.report.digest
    assert json.loads(
        (tmp_path / "out" / "calibration.json").read_text(encoding="utf-8")
    ) == report


def _tp_prediction(case_id: str) -> Prediction:
    return Prediction(
        finding_id="finding-1",
        case_id=case_id,
        file="calc.py",
        line=2,
        placement=Placement.INLINE,
        action="surface",
        repro_status="buggy_fail_fixed_pass",
        evidence_class="regression_reproduced",
    )


def _confirmed_receipt(finding_id: str = "finding-1") -> ReproReceipt:
    return ReproReceipt(
        finding_id=finding_id,
        buggy_sha="h" * 40,
        fixed_sha="b" * 40,
        repeats=1,
        outcome="reproduced",
        evidence_class="regression_reproduced",
        repro_status="buggy_fail_fixed_pass",
        reason="",
        buggy_runs=("failed",),
        fixed_runs=("passed",),
    )


def _report_call(
    case_id: str, role: str, cost_usd: float, ordinal: int
) -> dict[str, object]:
    trial_id = f"report:{case_id}"
    return {
        "trial_id": trial_id,
        "call_id": f"{trial_id}:{ordinal}",
        "ordinal": ordinal,
        "role": role,
        "cost_usd": cost_usd,
    }


class TestCalibrationReport:
    def _payloads(self, tmp_path: Path) -> tuple[Path, list[dict[str, object]]]:
        manifest_path, _, _ = _oracle_fixture(tmp_path)
        manifest = load_manifest(manifest_path)
        replay = next(
            case for case in manifest.cases if case.role == "historical_bug_replay"
        )
        control = next(
            case for case in manifest.cases if case.role == "developer_fix_control"
        )
        payloads = [
            case_payload(
                _completed_result(
                    replay.case_id,
                    spend=0.03,
                    oracle=0.01,
                    latency=4.0,
                    predictions=(_tp_prediction(replay.case_id),),
                    receipts=(_confirmed_receipt(),),
                )
            ),
            case_payload(
                _completed_result(control.case_id, spend=0.02, latency=2.0)
            ),
        ]
        payloads[0]["paid_calls"] = [
            _report_call(replay.case_id, CALL_ROLE_PRODUCT, 0.03, 0),
            _report_call(replay.case_id, CALL_ROLE_BENCHMARK_ORACLE, 0.01, 1),
        ]
        payloads[1]["paid_calls"] = [
            _report_call(control.case_id, CALL_ROLE_PRODUCT, 0.02, 0)
        ]
        defect_id = next(
            defect.defect_id
            for defect in manifest.truth_defects
            if defect.case_id == replay.case_id
        )
        replay_measurement = decode_measurement_record(payloads[0]["measurement"])
        payloads[0]["measurement"] = replace(
            replay_measurement,
            findings=tuple(
                replace(
                    finding,
                    accuracy_status=AccuracyStatus.CORRECT,
                    defect_id=defect_id,
                )
                for finding in replay_measurement.findings
            ),
            eligible_defect_ids=(defect_id,),
            truth_status=TruthStatus.POSITIVE,
        ).to_json_dict()
        payloads[1]["measurement"] = replace(
            decode_measurement_record(payloads[1]["measurement"]),
            truth_status=TruthStatus.NULL,
        ).to_json_dict()
        return manifest_path, payloads

    def test_live_report_carries_every_preregistered_section(
        self, tmp_path: Path
    ) -> None:
        manifest_path, payloads = self._payloads(tmp_path)
        manifest = load_manifest(manifest_path)
        receipt = _current_validation_authority(manifest_path)

        report = build_calibration_report(
            manifest,
            payloads,
            run_id="pilot-live-1",
            mode=LIVE_MODE,
            manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            preregistration_sha256="f" * 64,
            validation_receipt=receipt,
        )
        payload = report.to_json_dict()

        assert payload["schema_version"] == CALIBRATION_SCHEMA_VERSION
        assert payload["mode"] == LIVE_MODE
        assert payload["accuracy_withheld_reason"] is None
        assert (
            payload["validation_authority"]
            == report.underlying.to_json_dict()["validation_authority"]
        )
        assert payload["validation_authority"]["authority"] == ("current_scoring_authority")
        accuracy = payload["accuracy"]
        assert accuracy["true_positives"] == 1
        assert accuracy["true_negatives"] == 1
        assert accuracy["finding_precision"] == pytest.approx(1.0)
        assert accuracy["finding_precision_interval"] is not None
        assert accuracy["clean_false_positive_rate"] == pytest.approx(0.0)
        assert payload["operational"]["abstained_cases"] == 0
        channel = payload["channel_outcomes"]["regression_reproduced"]
        assert channel == {
            "predictions": 1,
            "surfaced": 1,
            "withheld": 0,
            "matched": 1,
        }
        differential = payload["differential_v"]
        assert differential["oracle_receipts"] == 1
        assert differential["confirmed"] == 1
        assert differential["confirmed_share"] == pytest.approx(1.0)
        assert differential["confirmed_interval"] is not None
        assert differential["status_counts"] == {"buggy_fail_fixed_pass": 1}
        strata = {
            (row["source_id"], row["role"]): row for row in payload["strata"]
        }
        assert strata[("source-111111111111", "historical_bug_replay")]["cases"] == 1
        assert strata[("source-111111111111", "historical_bug_replay")]["surfaced_cases"] == 1
        assert strata[("source-111111111111", "developer_fix_control")]["cases"] == 1
        assert payload["latency"]["p50_s"] == pytest.approx(2.0)
        assert payload["latency"]["p95_s"] == pytest.approx(4.0)
        assert payload["cost"]["spend_total_usd"] == pytest.approx(0.05)
        assert payload["cost"]["oracle_spend_total_usd"] == pytest.approx(0.01)
        sufficiency = payload["sample_sufficiency"]
        assert sufficiency["globally_labeled_findings"] == 1
        assert sufficiency["minimum_required"] == MINIMUM_GLOBAL_LABELS
        assert sufficiency["status"] == "recommendation_only"
        assert sufficiency["constants_patch"] == "prohibited"
        notes = " ".join(payload["limitations"])
        assert "recommendation_only" in notes
        assert "constant" in notes
        assert report.digest

    def test_current_channel_outcomes_project_measurement_accuracy(
        self, tmp_path: Path
    ) -> None:
        manifest_path, payloads = self._payloads(tmp_path)
        manifest = load_manifest(manifest_path)
        payload = payloads[0]
        measurement = decode_measurement_record(payload["measurement"])
        payload["measurement"] = replace(
            measurement,
            findings=tuple(
                replace(
                    finding,
                    accuracy_status=AccuracyStatus.WRONG,
                    defect_id=None,
                )
                for finding in measurement.findings
            ),
        ).to_json_dict()

        report = build_calibration_report(
            manifest,
            [payload],
            run_id="pilot-live-channel-authority",
            mode=LIVE_MODE,
            manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            preregistration_sha256="f" * 64,
            validation_receipt=_current_validation_authority(manifest_path),
        ).to_json_dict()

        assert report["outcome_accounting"]["correct"] == 0
        assert report["outcome_accounting"]["wrong"] == 1
        assert report["accuracy"]["finding_precision"] == 0.0
        assert report["channel_outcomes"]["regression_reproduced"]["matched"] == 0

    @pytest.mark.parametrize(
        ("accuracy", "truth_status", "expected_matched", "operational_unadjudicated"),
        (
            ("wrong", "positive", 1, 0),
            ("unadjudicated", "positive", None, 1),
            ("unadjudicated", "unadjudicated", None, 1),
        ),
    )
    def test_current_channel_outcomes_join_exact_operational_repeat(
        self,
        tmp_path: Path,
        accuracy: str,
        truth_status: str,
        expected_matched: int | None,
        operational_unadjudicated: int,
    ) -> None:
        manifest_path, payloads = self._payloads(tmp_path)
        first = payloads[0]
        measurement = decode_measurement_record(first["measurement"])
        second = dict(first)
        second["repeat"] = 1
        second["run_id"] = f"{first['run_id']}-repeat-1"
        second["paid_calls"] = [
            _report_call(
                f"{first['case_id']}-repeat-1", CALL_ROLE_PRODUCT, 0.03, 0
            ),
            _report_call(
                f"{first['case_id']}-repeat-1",
                CALL_ROLE_BENCHMARK_ORACLE,
                0.01,
                1,
            ),
        ]
        second["measurement"] = replace(
            measurement,
            repeat=1,
            findings=tuple(
                replace(
                    finding,
                    accuracy_status=AccuracyStatus(accuracy),
                    defect_id=None,
                )
                for finding in measurement.findings
            ),
            eligible_defect_ids=(
                measurement.eligible_defect_ids
                if truth_status == "positive"
                else ()
            ),
            truth_status=TruthStatus(truth_status),
        ).to_json_dict()

        report = build_calibration_report(
            load_manifest(manifest_path),
            [first, second],
            run_id="pilot-live-channel-repeats",
            mode=LIVE_MODE,
            manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            preregistration_sha256="f" * 64,
            validation_receipt=_current_validation_authority(manifest_path),
        ).to_json_dict()

        channel = report["channel_outcomes"]["regression_reproduced"]
        assert channel["predictions"] == 2
        assert channel["matched"] == expected_matched
        assert report["accuracy"]["finding_precision"] == 1.0
        assert report["outcome_accounting"]["operational_unadjudicated"] == (
            operational_unadjudicated
        )
        replay_stratum = next(
            row
            for row in report["strata"]
            if row["role"] == "historical_bug_replay"
        )
        assert replay_stratum["cases"] == 1
        assert replay_stratum["surfaced_cases"] == 1

    def test_calibration_report_rejects_totals_that_disagree_with_paid_rows(
        self, tmp_path: Path
    ) -> None:
        manifest_path, payloads = self._payloads(tmp_path)
        payloads[0]["paid_calls"] = [
            {
                "trial_id": "trial-product",
                "call_id": "trial-product:0",
                "ordinal": 0,
                "role": CALL_ROLE_PRODUCT,
                "cost_usd": 0.0003,
            },
            {
                "trial_id": "trial-oracle",
                "call_id": "trial-oracle:0",
                "ordinal": 0,
                "role": CALL_ROLE_BENCHMARK_ORACLE,
                "cost_usd": 0.0001,
            },
        ]

        with pytest.raises(ValueError, match="spend|total|paid.call|reconciliation"):
            build_calibration_report(
                load_manifest(manifest_path),
                payloads,
                run_id="tampered-costs",
                mode=LIVE_MODE,
                manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
                preregistration_sha256="f" * 64,
                validation_receipt=None,
            )

    def test_replay_provenance_never_claims_accuracy_even_under_a_receipt(
        self, tmp_path: Path
    ) -> None:
        manifest_path, payloads = self._payloads(tmp_path)
        manifest = load_manifest(manifest_path)
        receipt = _current_validation_authority(manifest_path)

        report = build_calibration_report(
            manifest,
            payloads,
            run_id="replay-check",
            mode=REPLAY_MODE,
            manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            preregistration_sha256="f" * 64,
            validation_receipt=receipt,
        )
        payload = report.to_json_dict()

        assert payload["mode"] == REPLAY_MODE
        assert payload["accuracy"] is None
        assert payload["accuracy_withheld_reason"] == ACCURACY_WITHHELD_REPLAY
        assert payload["channel_outcomes"]["regression_reproduced"]["matched"] is None
        assert "correct" not in payload["outcome_accounting"]
        assert payload["outcome_accounting"]["deployment_misses"] is None
        notes = " ".join(payload["limitations"])
        assert "replay" in notes
        assert payload["operational"]["decided_cases"] == 2

    def test_receiptless_live_report_withholds_accuracy_with_the_missing_reason(
        self, tmp_path: Path
    ) -> None:
        manifest_path, payloads = self._payloads(tmp_path)
        manifest = load_manifest(manifest_path)

        report = build_calibration_report(
            manifest,
            payloads,
            run_id="pilot-live-2",
            mode=LIVE_MODE,
            manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            preregistration_sha256="f" * 64,
            validation_receipt=None,
        )
        payload = report.to_json_dict()

        assert payload["accuracy"] is None
        assert payload["accuracy_withheld_reason"] == "validation_receipt_missing"
        assert payload["channel_outcomes"]["regression_reproduced"]["matched"] is None
        assert "wrong" not in payload["outcome_accounting"]
        assert payload["outcome_accounting"]["deployment_misses"] is None

    def test_sufficient_labels_still_require_an_owner_decision(
        self, tmp_path: Path
    ) -> None:
        manifest_path, payloads = self._payloads(tmp_path)
        manifest = load_manifest(manifest_path)
        receipt = _current_validation_authority(manifest_path)

        report = build_calibration_report(
            manifest,
            payloads,
            run_id="pilot-live-3",
            mode=LIVE_MODE,
            manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            preregistration_sha256="f" * 64,
            validation_receipt=receipt,
            globally_labeled_findings=MINIMUM_GLOBAL_LABELS,
        )
        sufficiency = report.to_json_dict()["sample_sufficiency"]
        assert sufficiency["status"] == "sufficient"
        assert sufficiency["constants_patch"] == "owner_decision_required"

    def test_abstention_is_reported_and_current_measurements_stay_authoritative(
        self, tmp_path: Path
    ) -> None:
        manifest_path, _, _ = _oracle_fixture(tmp_path)
        manifest = load_manifest(manifest_path)
        replay = next(
            case for case in manifest.cases if case.role == "historical_bug_replay"
        )
        control = next(
            case for case in manifest.cases if case.role == "developer_fix_control"
        )
        defect_id = next(
            defect.defect_id
            for defect in manifest.truth_defects
            if defect.case_id == replay.case_id
        )
        replay_result = _completed_result(
            replay.case_id,
            predictions=(_tp_prediction(replay.case_id),),
            receipts=(_confirmed_receipt(),),
        )
        replay_measurement = replace(
            replay_result.measurement,
            findings=tuple(
                replace(
                    finding,
                    accuracy_status=AccuracyStatus.CORRECT,
                    defect_id=defect_id,
                )
                for finding in replay_result.measurement.findings
            ),
            eligible_defect_ids=(defect_id,),
            truth_status=TruthStatus.POSITIVE,
        )
        control_result = _completed_result(
            control.case_id, abstain_reason="budget: deferred before any call"
        )
        payloads = [
            case_payload(replace(replay_result, measurement=replay_measurement)),
            case_payload(
                replace(
                    control_result,
                    measurement=replace(
                        control_result.measurement,
                        truth_status=TruthStatus.NULL,
                    ),
                )
            ),
        ]
        receipt = _current_validation_authority(manifest_path)

        report = build_calibration_report(
            manifest,
            payloads,
            run_id="pilot-live-4",
            mode=LIVE_MODE,
            manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            preregistration_sha256="f" * 64,
            validation_receipt=receipt,
        )
        payload = report.to_json_dict()
        assert payload["abstained_cases"] == [
            {"case_id": control.case_id, "reason": "budget: deferred before any call"}
        ]
        assert payload["accuracy"]["true_negatives"] == 0
        assert payload["accuracy"]["true_positives"] == 1

    def test_silent_partial_defer_control_is_abstention_not_true_negative(
        self, tmp_path: Path
    ) -> None:
        manifest_path, _, _ = _oracle_fixture(tmp_path)
        manifest = load_manifest(manifest_path)
        control = next(
            case for case in manifest.cases if case.role == "developer_fix_control"
        )
        original = _completed_result(control.case_id)
        rejected = FindingOutcome(
            finding_id="rejected",
            finding_status=FindingStatus.REJECTED,
            accuracy_status=AccuracyStatus.NOT_APPLICABLE,
            defect_id=None,
            publication_event_ids=(),
            authority=FindingAuthority.AUTOMATED,
        )
        unresolved = FindingOutcome(
            finding_id="unresolved",
            finding_status=FindingStatus.UNRESOLVED,
            accuracy_status=AccuracyStatus.UNADJUDICATED,
            defect_id=None,
            publication_event_ids=(),
            authority=FindingAuthority.AUTOMATED,
        )
        measurement = replace(
            original.measurement,
            stop_kind=StopKind.CANDIDATE_DEFER,
            task_status=TaskStatus.PARTIALLY_DEFERRED,
            findings=(rejected, unresolved),
            truth_status=TruthStatus.NULL,
            candidate_count=2,
            unresolved_count=1,
        )
        result = replace(
            original,
            status="deferred",
            abstain_reason="candidate evidence remained unresolved",
            measurement=measurement,
        )

        report = build_calibration_report(
            manifest,
            [case_payload(result)],
            run_id="pilot-live-partial-null",
            mode=LIVE_MODE,
            manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            preregistration_sha256="f" * 64,
            validation_receipt=_current_validation_authority(manifest_path),
        ).to_json_dict()

        assert report["accuracy"]["true_negatives"] == 0
        assert report["outcome_accounting"]["task_status_counts"] == {
            "completed": 0,
            "partially_deferred": 1,
            "fully_deferred": 0,
            "failed": 0,
        }
        assert report["outcome_accounting"]["null_pull_requests"] == 0
        assert report["outcome_accounting"]["true_negative_pull_requests"] == 0
        assert report["outcome_accounting"]["pr_false_positive_rate"] is None

    def test_fully_deferred_positive_remains_deployment_miss_while_abstained(
        self, tmp_path: Path
    ) -> None:
        manifest_path, _, _ = _oracle_fixture(tmp_path)
        manifest = load_manifest(manifest_path)
        replay = next(
            case for case in manifest.cases if case.role == "historical_bug_replay"
        )
        defect_id = next(
            defect.defect_id
            for defect in manifest.truth_defects
            if defect.case_id == replay.case_id
        )
        original = _completed_result(
            replay.case_id, abstain_reason="task evidence remained unresolved"
        )
        unresolved = FindingOutcome(
            finding_id="unresolved-positive",
            finding_status=FindingStatus.UNRESOLVED,
            accuracy_status=AccuracyStatus.UNADJUDICATED,
            defect_id=None,
            publication_event_ids=(),
            authority=FindingAuthority.AUTOMATED,
        )
        measurement = replace(
            original.measurement,
            findings=(unresolved,),
            eligible_defect_ids=(defect_id,),
            truth_status=TruthStatus.POSITIVE,
            candidate_count=1,
            unresolved_count=1,
        )

        report = build_calibration_report(
            manifest,
            [case_payload(replace(original, measurement=measurement))],
            run_id="pilot-live-fully-deferred-positive",
            mode=LIVE_MODE,
            manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            preregistration_sha256="f" * 64,
            validation_receipt=_current_validation_authority(manifest_path),
        ).to_json_dict()

        assert report["accuracy"]["true_positives"] == 0
        assert report["accuracy"]["false_negatives"] == 1
        assert report["outcome_accounting"]["eligible_defects"] == 1
        assert report["outcome_accounting"]["detected_defects"] == 0
        assert report["outcome_accounting"]["missed_defects"] == 1
        assert report["outcome_accounting"]["detection_rate"] == 0.0
        assert report["outcome_accounting"]["task_status_counts"]["fully_deferred"] == 1
        assert report["abstained_cases"] == [
            {
                "case_id": replay.case_id,
                "reason": "task evidence remained unresolved",
            }
        ]

    def test_fully_deferred_current_measurement_requires_an_abstain_reason(
        self, tmp_path: Path
    ) -> None:
        manifest_path, _, _ = _oracle_fixture(tmp_path)
        manifest = load_manifest(manifest_path)
        control = next(
            case for case in manifest.cases if case.role == "developer_fix_control"
        )
        payload = case_payload(
            _completed_result(
                control.case_id, abstain_reason="budget: deferred before any call"
            )
        )
        payload.pop("abstain_reason")

        with pytest.raises(
            ValueError,
            match="fully deferred current measurement requires.*abstain_reason",
        ):
            build_calibration_report(
                manifest,
                [payload],
                run_id="pilot-live-missing-abstain-reason",
                mode=LIVE_MODE,
                manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
                preregistration_sha256="f" * 64,
                validation_receipt=_current_validation_authority(manifest_path),
            )

    def test_taskless_current_measurement_must_join_the_sealed_transcript(
        self, tmp_path: Path
    ) -> None:
        manifest_path, _, _ = _oracle_fixture(tmp_path)
        manifest = load_manifest(manifest_path)
        control = next(
            case for case in manifest.cases if case.role == "developer_fix_control"
        )
        payload = case_payload(replace(_completed_result(control.case_id), task_id=None))

        with pytest.raises(ValueError, match="exact pre-execution failure measurement"):
            build_calibration_report(
                manifest,
                [payload],
                run_id="pilot-live-taskless-current",
                mode=LIVE_MODE,
                manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
                preregistration_sha256="f" * 64,
                validation_receipt=_current_validation_authority(manifest_path),
            )

    def test_taskless_preexecution_failure_remains_an_exclusion(
        self, tmp_path: Path
    ) -> None:
        manifest_path, _, _ = _oracle_fixture(tmp_path)
        manifest = load_manifest(manifest_path)
        control = next(
            case for case in manifest.cases if case.role == "developer_fix_control"
        )
        reason = "ProjectEvaluationPreExecutionError: checkout refused"
        result = _deferred(_fake_case(tmp_path, control.case_id).request, reason)

        report = build_calibration_report(
            manifest,
            [case_payload(result)],
            run_id="pilot-live-preexecution-exclusion",
            mode=LIVE_MODE,
            manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            preregistration_sha256="f" * 64,
            validation_receipt=_current_validation_authority(manifest_path),
        ).to_json_dict()

        assert report["excluded_cases"] == [
            {"case_id": control.case_id, "reason": reason}
        ]
        assert report["outcome_accounting"]["scoring_semantics"] == (
            "legacy_v1_scoring"
        )

    def test_taskless_payload_still_rejects_a_malformed_current_measurement(
        self, tmp_path: Path
    ) -> None:
        manifest_path, _, _ = _oracle_fixture(tmp_path)
        manifest = load_manifest(manifest_path)
        control = next(
            case for case in manifest.cases if case.role == "developer_fix_control"
        )
        payload = case_payload(replace(_completed_result(control.case_id), task_id=None))
        payload["measurement"] = {"schema_version": "future"}

        with pytest.raises(ValueError, match="measurement record fields"):
            build_calibration_report(
                manifest,
                [payload],
                run_id="pilot-live-taskless-malformed-measurement",
                mode=LIVE_MODE,
                manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
                preregistration_sha256="f" * 64,
                validation_receipt=_current_validation_authority(manifest_path),
            )

    @pytest.mark.parametrize("task_id", ("wrong-task", "", 7))
    def test_current_measurement_requires_the_exact_outer_task_id(
        self, tmp_path: Path, task_id: object
    ) -> None:
        manifest_path, _, _ = _oracle_fixture(tmp_path)
        manifest = load_manifest(manifest_path)
        control = next(
            case for case in manifest.cases if case.role == "developer_fix_control"
        )
        payload = case_payload(_completed_result(control.case_id))
        payload["task_id"] = task_id

        with pytest.raises(
            ValueError,
            match="current measurement task_id must be a non-empty exact string "
            "matching delivery_transcript.task_id",
        ):
            build_calibration_report(
                manifest,
                [payload],
                run_id="pilot-live-task-id-join",
                mode=LIVE_MODE,
                manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
                preregistration_sha256="f" * 64,
                validation_receipt=_current_validation_authority(manifest_path),
            )

    @pytest.mark.parametrize("repeat", (True, "0", None))
    def test_current_measurement_requires_the_exact_outer_repeat(
        self, tmp_path: Path, repeat: object
    ) -> None:
        manifest_path, _, _ = _oracle_fixture(tmp_path)
        manifest = load_manifest(manifest_path)
        control = next(
            case for case in manifest.cases if case.role == "developer_fix_control"
        )
        payload = case_payload(_completed_result(control.case_id))
        payload["repeat"] = repeat

        with pytest.raises(ValueError, match="repeat does not match measurement"):
            build_calibration_report(
                manifest,
                [payload],
                run_id="pilot-live-repeat-join",
                mode=LIVE_MODE,
                manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
                preregistration_sha256="f" * 64,
                validation_receipt=_current_validation_authority(manifest_path),
            )

    def test_current_measurement_requires_the_exact_outer_status(
        self, tmp_path: Path
    ) -> None:
        manifest_path, _, _ = _oracle_fixture(tmp_path)
        manifest = load_manifest(manifest_path)
        control = next(
            case for case in manifest.cases if case.role == "developer_fix_control"
        )
        payload = case_payload(_completed_result(control.case_id))
        payload["status"] = "deferred"
        payload["abstain_reason"] = "caller status rewrite"

        with pytest.raises(ValueError, match="status does not match.*task_status"):
            build_calibration_report(
                manifest,
                [payload],
                run_id="pilot-live-status-join",
                mode=LIVE_MODE,
                manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
                preregistration_sha256="f" * 64,
                validation_receipt=_current_validation_authority(manifest_path),
            )


class TestLiveLocalCli:
    def _environment(self, traps: Path, *, key: bool = True) -> dict[str, str]:
        environment = dict(os.environ)
        environment["PATH"] = str(traps)
        environment.pop("ANTHROPIC_API_KEY", None)
        if key:
            environment["ANTHROPIC_API_KEY"] = "must-not-be-used-" + "0" * 24
        return environment

    def _traps(self, tmp_path: Path) -> tuple[Path, Path]:
        traps = tmp_path / "traps"
        traps.mkdir(exist_ok=True)
        marker = tmp_path / "invoked"
        for command in ("git", "gh", "curl"):
            trap = traps / command
            trap.write_text(f"#!/bin/sh\ntouch '{marker}'\nexit 99\n")
            trap.chmod(0o755)
        return traps, marker

    def test_live_local_refuses_without_allow_paid_api_before_anything_else(
        self, tmp_path: Path
    ) -> None:
        traps, marker = self._traps(tmp_path)

        completed = _run(
            "live-local",
            "--manifest",
            str(tmp_path / "missing-manifest.json"),
            "--output",
            str(tmp_path / "out"),
            "--run-id",
            "pilot-1",
            "--devspend",
            str(tmp_path / "missing-devspend.md"),
            "--validation-receipt",
            str(tmp_path / "receipt-read-trap.json"),
            "--validation-results",
            str(tmp_path / "results-read-trap.json"),
            env=self._environment(traps),
        )

        assert completed.returncode == 2
        error = json.loads(completed.stderr)["error"]
        assert "--allow-paid-api" in error
        assert REASON_PAID_API_NOT_ALLOWED in error
        assert not marker.exists()
        assert not (tmp_path / "out").exists()

    def test_live_local_rejects_each_missing_authorisation_distinctly(
        self, tmp_path: Path
    ) -> None:
        manifest_path, root, source_id = _oracle_fixture(tmp_path)
        traps, marker = self._traps(tmp_path)
        devspend = _devspend(tmp_path)
        base = (
            "live-local",
            "--allow-paid-api",
            "--manifest",
            str(manifest_path),
            "--output",
            str(tmp_path / "out"),
            "--run-id",
            "pilot-1",
            "--devspend",
            str(devspend),
        )

        no_key = _run(*base, env=self._environment(traps, key=False))
        assert no_key.returncode == 2
        assert REASON_API_KEY_UNAVAILABLE in json.loads(no_key.stderr)["error"]

        unfrozen = _run(*base, env=self._environment(traps))
        assert unfrozen.returncode == 2
        assert REASON_PREREGISTRATION_NOT_FROZEN in json.loads(unfrozen.stderr)["error"]

        _freeze(manifest_path)
        document = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest_path.write_text(json.dumps(document, indent=1), encoding="utf-8")
        drifted = _run(*base, env=self._environment(traps))
        assert drifted.returncode == 2
        assert REASON_MANIFEST_NOT_IMMUTABLE in json.loads(drifted.stderr)["error"]

        _freeze(manifest_path)
        exhausted = _devspend(tmp_path, total="9.99", cap="10.00")
        no_headroom = _run(
            *base[:-1],
            str(exhausted),
            "--root",
            str(root),
            env=self._environment(traps),
        )
        assert no_headroom.returncode == 2
        assert REASON_INSUFFICIENT_HEADROOM in json.loads(no_headroom.stderr)["error"]
        assert not marker.exists()

    def test_live_local_without_prepared_root_excludes_and_never_pays(
        self, tmp_path: Path
    ) -> None:
        """No selected case means no reservation, no client, and exit code 3."""
        manifest_path, _, _ = _oracle_fixture(tmp_path)
        _freeze(manifest_path)
        traps, marker = self._traps(tmp_path)

        completed = _run(
            "live-local",
            "--allow-paid-api",
            "--manifest",
            str(manifest_path),
            "--output",
            str(tmp_path / "out"),
            "--run-id",
            "pilot-1",
            "--devspend",
            str(_devspend(tmp_path)),
            env=self._environment(traps),
        )

        assert completed.returncode == 3
        summary = json.loads(completed.stdout)
        assert summary["status"] == "not_executed"
        assert summary["mode"] == "live"
        assert summary["offline"] is False
        assert summary["evaluated_cases"] == 0
        assert summary["excluded_cases"] == 2
        assert summary["spend_usd"] == 0.0
        assert not marker.exists()

    def test_live_local_cli_rejects_v2_hmac_authority_before_preflight(
        self, tmp_path: Path
    ) -> None:
        """A paid executor never receives or runs alongside the symmetric key."""
        manifest_path, root, _ = _oracle_fixture(tmp_path)
        _freeze(manifest_path)
        bundle = build_validation_v2_bundle(tmp_path / "live-cli-v2", manifest_path, root)
        key_file = tmp_path / "live-authority.key"
        key_file.write_bytes(KEY)
        traps, marker = self._traps(tmp_path)
        common = (
            "live-local",
            "--allow-paid-api",
            "--manifest",
            str(manifest_path),
            "--run-id",
            "pilot-v2",
            "--devspend",
            str(_devspend(tmp_path)),
            "--validation-receipt",
            str(bundle.receipt_path),
            "--validation-results",
            str(bundle.results_path),
            "--validation-artifacts",
            str(bundle.artifact_root),
            "--validation-provenance-key-id",
            KEY_ID,
            "--validation-provenance-key-file",
            str(key_file),
        )
        output = tmp_path / "live-v2-out"

        completed = _run(
            *common,
            "--output",
            str(output),
            env=self._environment(traps),
        )

        assert completed.returncode == 2
        assert "X-01" in json.loads(completed.stderr)["error"]
        assert not output.exists()
        assert not marker.exists()
        assert KEY not in (completed.stdout + completed.stderr).encode()

    def test_live_local_requires_exactly_one_of_run_id_and_resume(self, tmp_path: Path) -> None:
        manifest_path, _, _ = _oracle_fixture(tmp_path)
        _freeze(manifest_path)
        traps, _ = self._traps(tmp_path)

        neither = _run(
            "live-local",
            "--allow-paid-api",
            "--manifest",
            str(manifest_path),
            "--output",
            str(tmp_path / "out"),
            "--devspend",
            str(_devspend(tmp_path)),
            env=self._environment(traps),
        )
        assert neither.returncode == 2
        assert "--run-id" in json.loads(neither.stderr)["error"]

        both = _run(
            "live-local",
            "--allow-paid-api",
            "--manifest",
            str(manifest_path),
            "--output",
            str(tmp_path / "out"),
            "--run-id",
            "pilot-1",
            "--resume",
            "pilot-1",
            "--devspend",
            str(_devspend(tmp_path)),
            env=self._environment(traps),
        )
        assert both.returncode == 2
        assert "--run-id" in json.loads(both.stderr)["error"]
