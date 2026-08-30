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
from pathlib import Path

import pytest

from attest.benchmark.api import (
    ProjectEvaluationRequest,
    ProjectEvaluationResult,
    ProjectTruth,
)
from attest.benchmark.live import (
    ACCURACY_WITHHELD_REPLAY,
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
from attest.benchmark.report import LIVE_MODE, REPLAY_MODE
from attest.benchmark.runner import Cassette, ReplayProvider, ReproReceipt
from attest.benchmark.schema import (
    Placement,
    Prediction,
    RunRecord,
    load_manifest,
)
from attest.review.config import ReviewConfig

from ._validation_v2 import verified_validation_authority
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
        "# Development spend ledger\n\n"
        f"**Total API spend: ${total} of ${cap}.**\n",
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


def _completed_result(
    case_id: str,
    *,
    spend: float = 0.01,
    oracle: float = 0.0,
    latency: float = 1.5,
    predictions: tuple[Prediction, ...] = (),
    receipts: tuple[ReproReceipt, ...] = (),
    abstain_reason: str | None = None,
) -> ProjectEvaluationResult:
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
        task_id=f"task-{case_id}",
        base_sha="b" * 40,
        head_sha="h" * 40,
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
    )


def _fake_case(tmp_path: Path, case_id: str, *, budget: float = 0.25) -> LiveCase:
    request = ProjectEvaluationRequest(
        case_id=case_id,
        repo=tmp_path / "unused-repo",
        base_ref="base",
        head_ref="head",
        workspace_root=tmp_path / "ws",
        config=ReviewConfig(budget_usd=budget),
        repeats=1,
    )
    return LiveCase(request=request, source_id="source-111111111111")


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
        provider_factory=lambda request: ReplayProvider(Cassette("{}", "{}")),
        resume=resume,
        evaluate=evaluate,
        on_transition=on_transition,
        interpreters=dict(interpreters or {}),
        env=env,
    )


class _Interrupt(RuntimeError):
    pass


class TestCheckpoints:
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

    def test_case_interrupted_between_reservation_and_completion_fails_closed(
        self, tmp_path: Path
    ) -> None:
        """A case stuck in ``reserved`` has an unknown cost: never re-call silently."""

        def crash(request: ProjectEvaluationRequest, provider: object) -> ProjectEvaluationResult:
            raise _Interrupt("crashed mid-call")

        cases = [_fake_case(tmp_path, "case-333333333333")]
        with pytest.raises(_Interrupt):
            _run_fake(tmp_path, cases, crash)
        state = tmp_path / "state" / "pilot-1" / "cases" / "case-333333333333.json"
        assert json.loads(state.read_text(encoding="utf-8"))["state"] == STATE_RESERVED

        calls: list[str] = []

        def must_not_run(
            request: ProjectEvaluationRequest, provider: object
        ) -> ProjectEvaluationResult:
            calls.append(request.case_id)
            return _completed_result(request.case_id)

        with pytest.raises(ValueError, match="reserved"):
            _run_fake(tmp_path, cases, must_not_run, resume=True)
        assert calls == []
        assert state.exists(), "evidence must be retained"

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
                lambda request, provider: _completed_result(request.case_id, spend=0.02),
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
        assert rows[0]["spend_usd"] == pytest.approx(0.02)

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
    receipt = _current_validation_authority(manifest_path)
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
        "validation_receipt": receipt,
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

    report = json.loads(
        (tmp_path / "out" / "calibration.json").read_text(encoding="utf-8")
    )
    assert report["mode"] == LIVE_MODE
    assert report["run_id"] == "pilot-live-1"
    assert report["accuracy_withheld_reason"] is None
    assert report["accuracy"]["true_positives"] == 1
    assert report["accuracy"]["true_negatives"] == 1
    assert report["accuracy"]["finding_false_positives"] == 0
    assert report["channel_outcomes"]["regression_reproduced"]["matched"] == 1
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

        assert payload["mode"] == LIVE_MODE
        assert payload["accuracy_withheld_reason"] is None
        assert payload["validation_authority"] == report.underlying.to_json_dict()[
            "validation_authority"
        ]
        assert payload["validation_authority"]["authority"] == (
            "current_scoring_authority"
        )
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
        assert (
            strata[("source-111111111111", "historical_bug_replay")]["surfaced_cases"]
            == 1
        )
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

    def test_abstention_is_reported_with_its_reason_and_enters_no_denominator(
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
        payloads = [
            case_payload(
                _completed_result(
                    replay.case_id,
                    predictions=(_tp_prediction(replay.case_id),),
                    receipts=(_confirmed_receipt(),),
                )
            ),
            case_payload(
                _completed_result(
                    control.case_id, abstain_reason="budget: deferred before any call"
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
        manifest_path, _, _ = _oracle_fixture(tmp_path)
        _freeze(manifest_path)
        traps, marker = self._traps(tmp_path)

        completed = _run(
            "live-local",
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

    def test_live_local_requires_exactly_one_of_run_id_and_resume(
        self, tmp_path: Path
    ) -> None:
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
