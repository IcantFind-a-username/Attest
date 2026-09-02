"""E-04 (G-SHADOW-001) prechange RED: the collector refuses every unauthorized or
post-hoc design, never treats unknown truth as clean, and would publish exactly
what CI publishes while producing no author-visible side effect."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from attest.benchmark import prospective
from attest.benchmark.prospective import (
    REASON_AUTHORIZATION_MISSING,
    REASON_INCLUSION_PROBABILITY_INVALID,
    REASON_INSUFFICIENT_HEADROOM,
    REASON_PAID_API_NOT_ALLOWED,
    REASON_PREREGISTRATION_NOT_FROZEN,
    REASON_SAMPLE_AFTER_OUTCOMES,
    ProspectivePreflightError,
    ShadowTrial,
    TrafficUnit,
    classify_subject,
    freeze,
    preflight_prospective,
    record_sample,
    record_trial,
    report,
    trial_from_ledger,
)

FREEZE = "2026-09-03T12:00:00+00:00"
ENV = {"ANTHROPIC_API_KEY": "k" * 32}


def _study(tmp_path: Path, **overrides: object) -> Path:
    study = tmp_path / "e04"
    study.mkdir(parents=True)
    (study / "protocol.md").write_text("# protocol\n", encoding="utf-8")
    preregistration = {
        "freeze_at": FREEZE,
        "population": ["owner/repo"],
        "per_pr_budget_usd": 0.25,
        "k_samples": 4,
        "silent_audit_inclusion_probability": 0.5,
        "silent_audit_seed": 7,
        "cost_cap_usd": 2.0,
        "safety_stop_wrong_findings": 5,
    }
    preregistration.update(overrides)
    (study / "preregistration.json").write_text(json.dumps(preregistration), encoding="utf-8")
    (study / "authorization.json").write_text(
        json.dumps(
            {
                "authorized_by": "owner",
                "granted_at": "2026-09-02T00:00:00+00:00",
                "population": ["owner/repo"],
                "scope": "shadow only; no author-visible output",
            }
        ),
        encoding="utf-8",
    )
    return study


def _devspend(tmp_path: Path, total: float = 10.0, cap: float = 30.0) -> Path:
    path = tmp_path / "DEVSPEND.md"
    path.write_text(f"**Total API spend: ${total:.6f} of ${cap:.2f}.**\n", encoding="utf-8")
    return path


def _unit(sha: str = "a" * 40, pushed_at: str = "2026-09-03T13:00:00+00:00") -> TrafficUnit:
    return TrafficUnit(
        unit_id=f"owner/repo@{sha[:7]}",
        repository="owner/repo",
        head_sha=sha,
        base_sha="b" * 40,
        subject="feat: add a guard",
        stratum=classify_subject("feat: add a guard"),
        changed_files=2,
        pushed_at=pushed_at,
    )


def _preflight(study: Path, tmp_path: Path, **kwargs: object) -> object:
    values: dict[str, object] = {"env": ENV, "allow_paid_api": True}
    values.update(kwargs)
    if "devspend_path" not in values:  # never rewrite a ledger the test supplied
        values["devspend_path"] = _devspend(tmp_path)
    return preflight_prospective(study, **values)  # type: ignore[arg-type]


def test_a_frozen_authorized_study_passes_preflight(tmp_path: Path) -> None:
    study = _study(tmp_path)
    digest = freeze(study)

    result = _preflight(study, tmp_path, reserve_usd=1.0)

    assert result.protocol_sha256 == digest  # type: ignore[attr-defined]
    assert result.headroom_usd == pytest.approx(19.0)  # type: ignore[attr-defined]


def test_preflight_refuses_without_the_paid_opt_in_or_key(tmp_path: Path) -> None:
    study = _study(tmp_path)
    freeze(study)
    with pytest.raises(ProspectivePreflightError) as refused:
        _preflight(study, tmp_path, allow_paid_api=False)
    assert refused.value.reason == REASON_PAID_API_NOT_ALLOWED
    with pytest.raises(ProspectivePreflightError) as refused:
        _preflight(study, tmp_path, env={})
    assert refused.value.reason == REASON_PAID_API_NOT_ALLOWED


def test_preflight_refuses_missing_or_late_or_narrow_authorization(tmp_path: Path) -> None:
    study = _study(tmp_path)
    freeze(study)
    (study / "authorization.json").unlink()
    with pytest.raises(ProspectivePreflightError) as refused:
        _preflight(study, tmp_path)
    assert refused.value.reason == REASON_AUTHORIZATION_MISSING

    study = _study(tmp_path / "late")
    late = json.loads((study / "authorization.json").read_text())
    late["granted_at"] = "2026-09-03T12:00:01+00:00"
    (study / "authorization.json").write_text(json.dumps(late))
    freeze(study)
    with pytest.raises(ProspectivePreflightError) as refused:
        _preflight(study, tmp_path)
    assert refused.value.reason == REASON_AUTHORIZATION_MISSING

    study = _study(tmp_path / "narrow", population=["owner/repo", "owner/other"])
    freeze(study)
    with pytest.raises(ProspectivePreflightError) as refused:
        _preflight(study, tmp_path)
    assert refused.value.reason == REASON_AUTHORIZATION_MISSING


def test_preflight_refuses_an_unfrozen_or_edited_protocol(tmp_path: Path) -> None:
    study = _study(tmp_path)
    with pytest.raises(ProspectivePreflightError) as refused:
        _preflight(study, tmp_path)
    assert refused.value.reason == REASON_PREREGISTRATION_NOT_FROZEN
    freeze(study)
    (study / "protocol.md").write_text("# edited after the freeze\n", encoding="utf-8")
    with pytest.raises(ProspectivePreflightError) as refused:
        _preflight(study, tmp_path)
    assert refused.value.reason == REASON_PREREGISTRATION_NOT_FROZEN


@pytest.mark.parametrize("probability", [0, 0.0, -0.1, 1.5, "half"])
def test_preflight_refuses_a_silent_unit_that_can_never_be_audited(
    tmp_path: Path, probability: object
) -> None:
    study = _study(tmp_path, silent_audit_inclusion_probability=probability)
    freeze(study)
    with pytest.raises(ProspectivePreflightError) as refused:
        _preflight(study, tmp_path)
    assert refused.value.reason in {
        REASON_INCLUSION_PROBABILITY_INVALID,
        prospective.REASON_PREREGISTRATION_INVALID,
    }


def test_preflight_refuses_a_sample_recorded_after_an_outcome_or_before_the_freeze(
    tmp_path: Path,
) -> None:
    study = _study(tmp_path)
    freeze(study)
    record_sample(study, [_unit()], recorded_at="2026-09-03T13:05:00+00:00")
    record_trial(
        study,
        ShadowTrial(
            unit_id="owner/repo@aaaaaaa",
            task_id="t1",
            recorded_at="2026-09-03T13:10:00+00:00",
            candidates=1,
            eligible=1,
            attempted=1,
            certified=0,
            would_publish=(),
            behavior_changes_verified=0,
            behavior_changes_intent_unknown=1,
        ),
    )
    assert _preflight(study, tmp_path).trials_recorded == 1  # type: ignore[attr-defined]
    # a unit selected after that outcome was observed
    record_sample(study, [_unit("c" * 40)], recorded_at="2026-09-03T13:20:00+00:00")
    with pytest.raises(ProspectivePreflightError) as refused:
        _preflight(study, tmp_path)
    assert refused.value.reason == REASON_SAMPLE_AFTER_OUTCOMES

    # a unit pushed before the freeze is not prospective
    early = _study(tmp_path / "early")
    freeze(early)
    with pytest.raises(ValueError):
        record_sample(early, [_unit(pushed_at="2026-09-03T11:00:00+00:00")], recorded_at=FREEZE)
    (early / "sample.jsonl").write_text(
        json.dumps(
            {
                **_unit().__dict__,
                "recorded_at": "2026-09-03T11:00:00+00:00",
                "silent_audit_inclusion_probability": 0.5,
            }
        )
        + "\n"
    )
    with pytest.raises(ProspectivePreflightError) as refused:
        _preflight(early, tmp_path)
    assert refused.value.reason == REASON_SAMPLE_AFTER_OUTCOMES

    # a sample row without a timestamp is refused with a reason, not a traceback
    (early / "sample.jsonl").write_text(
        json.dumps({**_unit().__dict__, "silent_audit_inclusion_probability": 0.5}) + "\n"
    )
    with pytest.raises(ProspectivePreflightError) as refused:
        _preflight(early, tmp_path)
    assert refused.value.reason == REASON_SAMPLE_AFTER_OUTCOMES


def test_preflight_refuses_without_development_cap_headroom(tmp_path: Path) -> None:
    study = _study(tmp_path)
    freeze(study)
    with pytest.raises(ProspectivePreflightError) as refused:
        _preflight(study, tmp_path, devspend_path=_devspend(tmp_path, 29.5), reserve_usd=1.0)
    assert refused.value.reason == REASON_INSUFFICIENT_HEADROOM


def test_the_silent_audit_draw_is_recorded_before_outcomes_and_reproducible(
    tmp_path: Path,
) -> None:
    study = _study(tmp_path)
    freeze(study)
    units = [_unit(chr(ord("a") + index) * 40) for index in range(6)]

    rows = record_sample(study, units, recorded_at="2026-09-03T13:00:00+00:00")
    again = record_sample(study, units, recorded_at="2026-09-03T14:00:00+00:00")

    assert len(rows) == 6 and again == []  # idempotent by unit id
    assert all(row["silent_audit_inclusion_probability"] == 0.5 for row in rows)
    draws = [row["selected_for_silent_audit"] for row in rows]
    assert any(draws) and not all(draws)
    other = _study(tmp_path / "other")
    freeze(other)
    assert [
        row["selected_for_silent_audit"]
        for row in record_sample(other, units, recorded_at="2026-09-03T13:00:00+00:00")
    ] == draws


def test_report_never_treats_unknown_truth_as_clean(tmp_path: Path) -> None:
    study = _study(tmp_path)
    freeze(study)
    record_sample(study, [_unit(), _unit("c" * 40)], recorded_at="2026-09-03T13:00:00+00:00")
    record_trial(
        study,
        ShadowTrial(
            unit_id="owner/repo@aaaaaaa",
            task_id="t1",
            recorded_at="2026-09-03T13:10:00+00:00",
            candidates=2,
            eligible=2,
            attempted=2,
            certified=1,
            would_publish=("f1",),
            behavior_changes_verified=0,
            behavior_changes_intent_unknown=1,
            spend_usd=0.2,
            elapsed_s=30.0,
        ),
    )
    record_trial(
        study,
        ShadowTrial(
            unit_id="owner/repo@ccccccc",
            task_id="t2",
            recorded_at="2026-09-03T13:20:00+00:00",
            candidates=0,
            eligible=0,
            attempted=0,
            certified=0,
            would_publish=(),
            behavior_changes_verified=0,
            behavior_changes_intent_unknown=0,
            spend_usd=0.05,
            elapsed_s=10.0,
        ),
    )

    first = report(study)

    assert first["units_run"] == 2 and first["shadow_findings"] == 1
    assert first["pr_any_shadow_finding_rate"] == 0.5
    assert first["unadjudicated_shadow_findings"] == 1
    assert first["semantic_precision"] == "INSUFFICIENT"
    assert first["eligible_detection"] == "INSUFFICIENT"
    assert first["behavior_changes_intent_unknown"] == 1
    assert first["cost_usd_total"] == pytest.approx(0.25)
    assert first["safety_stop_reached"] is False

    (study / "adjudication.jsonl").write_text(
        json.dumps({"unit_id": "owner/repo@aaaaaaa", "finding_id": "f1", "label": "not_defect"})
        + "\n"
    )
    second = report(study)
    assert second["wrong_shadow_findings"] == 1
    assert second["semantic_precision"] == "adjudicated"
    assert second["eligible_detection"] == "INSUFFICIENT"  # silent audit unresolved / n too small


def test_trial_from_ledger_counts_without_naming_a_candidate() -> None:
    rows = [
        {"kind": "review_plan", "task_id": "t", "units": [{"unit_id": "u"}]},
        {"kind": "eligibility", "task_id": "t", "finding_id": "a", "eligibility": "regression"},
        {"kind": "executor_backend", "task_id": "t", "profile": "linux-container-v1"},
        {
            "kind": "verification",
            "task_id": "t",
            "finding_id": "a",
            "outcome": "deferred",
            "evidence_class": "behavior_change",
            "reason": (
                "intent: behavior change confirmed, intent unknown: … (行为变化已证实，意图未知)"
            ),
        },
        {"kind": "certification", "task_id": "t", "finding_id": "a", "outcome": "not_attempted"},
        {"kind": "publication_policy", "task_id": "t", "published": []},
    ]

    trial = trial_from_ledger(
        rows,
        unit_id="owner/repo@abc",
        task_id="t",
        recorded_at=datetime.now(UTC).isoformat(),
        would_publish=(),
        deferred_reason=None,
        spend_usd=0.1,
        elapsed_s=12.0,
    )

    assert (trial.candidates, trial.eligible, trial.attempted, trial.certified) == (1, 1, 1, 0)
    assert trial.behavior_changes_intent_unknown == 1
    assert trial.failure_categories == {"behavior change, intent unknown": 1}
    assert trial.executor_profile == "linux-container-v1"
    assert "a" not in json.dumps(trial.to_json_dict()).split('"unit_id"')[0]


def test_shadow_would_publish_exactly_what_ci_publishes_with_no_remote_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Shadow on/off publication identity, zero cost: the local review path the
    collector uses and the CI path share one verification stage, so on the same
    planted regression they select the same receipt -- and the collector opens
    no GitHub connection at all."""
    from attest.github.client import GitHubClient
    from attest.review.ci import run_ci
    from attest.review.config import ReviewConfig
    from attest.review.executor import ExecutorLimits
    from attest.review.run import run_review
    from test_ci_flow import (
        RecordingGitHub,
        RecordingProvider,
        _context,
        _finding_payload,
        planted_repo,
    )

    (tmp_path / "ci").mkdir()
    (tmp_path / "shadow").mkdir()
    repo, base_sha, head_sha = planted_repo.__wrapped__(tmp_path / "ci")  # type: ignore[attr-defined]
    repro = json.dumps(
        {
            "test_body": "import runpy\n\n"
            "def test_average_handles_empty_input():\n"
            "    average = runpy.run_path('app.py')['average']\n"
            "    assert average([]) == 0\n"
        }
    )
    server = RecordingGitHub()
    server.start()
    try:
        ci = run_ci(
            repo,
            _context(base_sha, head_sha),
            GitHubClient("local-token", server.url),
            ReviewConfig(k_samples=2, tier0_commands=[]),
            RecordingProvider(_finding_payload(), repro),
            limits=ExecutorLimits(wall_timeout_s=20.0),
        )
    finally:
        server.close()
    assert ci.surfaced_count == 1
    ci_published = {
        finding_id
        for review_body in server.review_bodies
        for comment in review_body["comments"]  # type: ignore[union-attr]
        for finding_id in [str(comment["body"]).split("finding-id:")[1].split(" ")[0]]
    }

    shadow_repo, shadow_base, _shadow_head = planted_repo.__wrapped__(tmp_path / "shadow")  # type: ignore[attr-defined]
    monkeypatch.setattr(
        "attest.github.client.GitHubClient.__init__",
        lambda *args, **kwargs: pytest.fail("the shadow collector must never open GitHub"),
    )
    shadow = run_review(
        shadow_repo,
        shadow_base,
        ReviewConfig(k_samples=2, tier0_commands=[]),
        RecordingProvider(_finding_payload(), repro),
        verify=True,
        limits=ExecutorLimits(wall_timeout_s=20.0),
    )
    shadow_published = {
        finding.accepted_receipt.receipt.candidate_id for finding in shadow.published
    }

    assert shadow_published == ci_published and len(shadow_published) == 1
    trial = trial_from_ledger(
        [
            json.loads(line)
            for line in (shadow_repo / ".attest" / "ledger.jsonl").read_text().splitlines()
        ],
        unit_id="owner/repo@shadow",
        task_id=shadow.task_id,
        recorded_at=(datetime.now(UTC) + timedelta(seconds=1)).isoformat(),
        would_publish=tuple(sorted(shadow_published)),
        deferred_reason=shadow.deferred_reason,
        spend_usd=shadow.budget.spent_usd,
        elapsed_s=shadow.elapsed_s,
    )
    assert trial.certified == 1 and trial.would_publish == tuple(sorted(ci_published))
