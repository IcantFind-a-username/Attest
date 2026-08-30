"""Three-arm comparison: identical blinded diff bytes, honest evidence classes."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from attest.benchmark.api import ProjectEvaluationRequest, ProjectTruth
from attest.benchmark.baselines import (
    ARM_BARE_PROMPT,
    ARM_PRODUCT,
    ARM_RUFF,
    EVIDENCE_STATIC_DIAGNOSTIC,
    EVIDENCE_UNVERIFIED_CLAIM,
    BarePromptBaseline,
    ComparisonPlan,
    RuffBaseline,
    compare_arms,
)
from attest.benchmark.corpus import load_validation_receipt
from attest.benchmark.report import (
    RECEIPT_MISSING,
    build_comparison_report,
    render_comparison_markdown,
)
from attest.benchmark.runner import Cassette, ReplayProvider
from attest.benchmark.schema import TruthDefect, load_manifest, normalize_unified_diff_bytes
from attest.review.config import ReviewConfig
from attest.review.diffs import parse_diff
from attest.review.executor import ExecutorLimits
from attest.review.proposer import PROPOSER_MAX_OUTPUT_TOKENS, ProviderResult

from .test_corpus import _git

_SCRIPT = Path(__file__).parents[2] / "scripts" / "benchmark.py"

_DIFF = """diff --git a/calc.py b/calc.py
index 1111111..2222222 100644
--- a/calc.py
+++ b/calc.py
@@ -4,1 +4,1 @@
-    return 1
+    return undefined_name()
"""

#: Unit-test worktree content matching ``_DIFF``: the defect sits at line 4 and
#: the unused import at line 1 stays outside the hunk.
_UNIT_CALC = "import os\n\ndef value():\n    return undefined_name()\n"

#: Fixture bug ruff can flag (F632) that still fails at runtime by returning
#: the wrong value -- never by NameError, whose head signature the product's
#: classifier rightly voids as a stale reference.
_BUGGY_CALC = "def value():\n    return 2 if (1 is 1) else 0\n"
_FIXED_CALC = "def value():\n    return 1\n"
_TEST_CALC = "from calc import value\n\ndef test_value():\n    assert value() == 1\n"

_PROPOSAL = json.dumps(
    {
        "findings": [
            {
                "claim": "value() returns 2 instead of the documented 1.",
                "anchor": {"file": "calc.py", "line": 2},
                "failure_scenario": "value() returns 2 and callers act on it",
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


def _ruff_executable() -> str:
    candidate = Path(sys.executable).with_name("ruff")
    if candidate.is_file():
        return str(candidate)
    import shutil

    found = shutil.which("ruff")
    if found is None:
        pytest.skip("requires a local ruff executable")
    return found


class _RecordingProvider:
    """A fake provider that records exactly what one baseline call sends."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.calls: list[dict[str, Any]] = []

    def sample(
        self,
        system: str,
        prompt: str,
        schema: dict[str, Any],
        max_tokens: int,
        *,
        timeout_s: float | None = None,
    ) -> ProviderResult:
        self.calls.append(
            {"system": system, "prompt": prompt, "schema": schema, "max_tokens": max_tokens}
        )
        return ProviderResult(text=self.text, input_tokens=500, output_tokens=100)


def test_bare_prompt_baseline_makes_one_schema_call_and_keeps_valid_findings() -> None:
    """Arm B is one direct PROPOSAL_SCHEMA call with no gate: every valid
    returned finding is surfaced and carries the unverified evidence class."""
    payload = json.dumps(
        {
            "findings": [
                {
                    "claim": "value() calls a name that does not exist.",
                    "anchor": {"file": "calc.py", "line": 4},
                    "failure_scenario": "any call to value() raises NameError",
                    "falsification_plan": "call value()",
                },
                {
                    "claim": "An anchor outside every hunk is void.",
                    "anchor": {"file": "calc.py", "line": 99},
                    "failure_scenario": "never",
                    "falsification_plan": "never",
                },
            ]
        }
    )
    provider = _RecordingProvider(payload)
    baseline = BarePromptBaseline(provider)

    run = baseline.evaluate(
        case_id="case-aaaaaaaaaaaa",
        role="historical_bug_replay",
        diff=parse_diff(_DIFF),
        config=ReviewConfig(tier0_commands=[]),
    )

    assert len(provider.calls) == 1
    call = provider.calls[0]
    assert call["max_tokens"] == PROPOSER_MAX_OUTPUT_TOKENS
    assert call["schema"]["properties"]["findings"]
    assert run.arm == ARM_BARE_PROMPT
    assert run.status == "completed"
    assert [(f.file, f.line) for f in run.findings] == [("calc.py", 4)]
    assert run.findings[0].evidence_class == EVIDENCE_UNVERIFIED_CLAIM
    assert run.model_calls == 1
    assert run.input_tokens == 500
    assert run.output_tokens == 100
    assert run.spend_usd > 0
    assert run.tool_cost_s == 0.0


def test_bare_prompt_baseline_defers_on_budget_and_on_invalid_response() -> None:
    """The same per-case USD ceiling applies before the call is made, and a
    broken response is an abstention, never inferred silence."""
    provider = _RecordingProvider(json.dumps({"findings": []}))
    tiny = ReviewConfig(budget_usd=1e-06, tier0_commands=[])

    refused = BarePromptBaseline(provider).evaluate(
        case_id="case-aaaaaaaaaaaa",
        role="historical_bug_replay",
        diff=parse_diff(_DIFF),
        config=tiny,
    )
    assert refused.status == "deferred"
    assert refused.abstain_reason is not None and "budget" in refused.abstain_reason
    assert provider.calls == []

    broken = BarePromptBaseline(_RecordingProvider("not-json-at-all")).evaluate(
        case_id="case-aaaaaaaaaaaa",
        role="historical_bug_replay",
        diff=parse_diff(_DIFF),
        config=ReviewConfig(tier0_commands=[]),
    )
    assert broken.status == "deferred"
    assert broken.abstain_reason == "invalid_model_response"
    assert broken.findings == ()

    silent = BarePromptBaseline(_RecordingProvider(json.dumps({"findings": []}))).evaluate(
        case_id="case-aaaaaaaaaaaa",
        role="historical_bug_replay",
        diff=parse_diff(_DIFF),
        config=ReviewConfig(tier0_commands=[]),
    )
    assert silent.status == "completed"
    assert silent.findings == ()


def test_ruff_baseline_keeps_only_diff_anchored_diagnostics(tmp_path: Path) -> None:
    """Arm C runs the preregistered local command and keeps a diagnostic only
    when its anchor falls inside the diff hunks."""
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    (worktree / "calc.py").write_text(_UNIT_CALC, encoding="utf-8")

    run = RuffBaseline(_ruff_executable()).evaluate(
        case_id="case-aaaaaaaaaaaa",
        role="historical_bug_replay",
        diff=parse_diff(_DIFF),
        worktree=worktree,
    )

    assert run.arm == ARM_RUFF
    assert run.status == "completed"
    assert [(f.file, f.line) for f in run.findings] == [("calc.py", 4)]
    assert run.findings[0].evidence_class == EVIDENCE_STATIC_DIAGNOSTIC
    assert run.model_calls == 0
    assert run.input_tokens == 0
    assert run.spend_usd == 0.0
    assert run.tool_cost_s is not None and run.tool_cost_s > 0


def test_ruff_baseline_never_infers_a_negative_from_missing_tool_support(
    tmp_path: Path,
) -> None:
    """No executable and no Python file both mean the tool could not judge:
    the run defers instead of being scored as silence."""
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    (worktree / "calc.py").write_text(_UNIT_CALC, encoding="utf-8")

    unavailable = RuffBaseline(None).evaluate(
        case_id="case-aaaaaaaaaaaa",
        role="historical_bug_replay",
        diff=parse_diff(_DIFF),
        worktree=worktree,
    )
    assert unavailable.status == "deferred"
    assert unavailable.abstain_reason == "static_tool_unavailable"

    non_python_diff = parse_diff(
        "diff --git a/notes.txt b/notes.txt\n"
        "--- a/notes.txt\n"
        "+++ b/notes.txt\n"
        "@@ -1,1 +1,1 @@\n"
        "-old\n"
        "+new\n"
    )
    (worktree / "notes.txt").write_text("new\n", encoding="utf-8")
    no_python = RuffBaseline(_ruff_executable()).evaluate(
        case_id="case-aaaaaaaaaaaa",
        role="historical_bug_replay",
        diff=non_python_diff,
        worktree=worktree,
    )
    assert no_python.status == "deferred"
    assert no_python.abstain_reason == "diff_contains_no_python_files"


def _comparison_fixture(tmp_path: Path) -> tuple[Path, Path, str, str]:
    """A replay/control pair whose bug is an undefined name ruff can also see."""
    upstream = tmp_path / "upstream"
    upstream.mkdir()
    _git(upstream, "init", "-q")
    _git(upstream, "config", "user.email", "fixture@example.invalid")
    _git(upstream, "config", "user.name", "Fixture")
    (upstream / "calc.py").write_text(_BUGGY_CALC, encoding="utf-8")
    (upstream / "test_calc.py").write_text(_TEST_CALC, encoding="utf-8")
    _git(upstream, "add", ".")
    _git(upstream, "commit", "-qm", "first")
    buggy_commit = _git(upstream, "rev-parse", "HEAD")
    (upstream / "calc.py").write_text(_FIXED_CALC, encoding="utf-8")
    _git(upstream, "add", ".")
    _git(upstream, "commit", "-qm", "second")
    fixed_commit = _git(upstream, "rev-parse", "HEAD")

    root = tmp_path / "cache"
    source_id = "source-aaaaaaaaaaaa"
    pair_id = "pair-bbbbbbbbbbbb"
    for role, commit in (("replay", buggy_commit), ("control", fixed_commit)):
        checkout = root / source_id / pair_id / role
        checkout.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "clone", "-q", str(upstream), str(checkout)],
            check=True,
            capture_output=True,
        )
        _git(checkout, "checkout", "-q", commit)
    artifacts = root / "artifacts"
    artifacts.mkdir()
    patch = subprocess.run(
        ["git", "diff", buggy_commit, fixed_commit],
        cwd=upstream,
        check=True,
        capture_output=True,
    ).stdout
    (artifacts / "fix.patch").write_bytes(patch)
    test_command = b"{python} -m pytest -q test_calc.py\n"
    (artifacts / "test.argv").write_bytes(test_command)
    replay_id = "case-cccccccccccc"
    control_id = "case-dddddddddddd"
    common = {
        "pair_id": pair_id,
        "source_id": source_id,
        "provenance_kind": "historical_fix",
        "source_license": "MIT",
        "buggy_commit": buggy_commit,
        "fixed_commit": fixed_commit,
        "patch": {
            "relative_path": "artifacts/fix.patch",
            "sha256": hashlib.sha256(normalize_unified_diff_bytes(patch)).hexdigest(),
            "normalization": "unified_diff",
        },
        "tests": {
            "relative_path": "artifacts/test.argv",
            "sha256": hashlib.sha256(test_command).hexdigest(),
            "normalization": "normalized_text",
        },
        "changed_locations": [{"path": "calc.py", "start_line": 2, "end_line": 2}],
        "split": "test",
    }
    document = {
        "schema_version": "1",
        "protocol_version": "1",
        "corpus_commit": "6" * 64,
        "cases": [
            {**common, "case_id": replay_id, "role": "historical_bug_replay"},
            {**common, "case_id": control_id, "role": "developer_fix_control"},
        ],
        "truth_defects": [
            {
                "defect_id": "truth_1",
                "case_id": replay_id,
                "file": "calc.py",
                "start_line": 2,
                "end_line": 2,
            }
        ],
        "runtime": [
            {
                "case_id": replay_id,
                "cwd": f"{source_id}/{pair_id}/replay",
                "command": {"tool": "python", "args": ["-m", "pytest", "-q", "test_calc.py"]},
            },
            {
                "case_id": control_id,
                "cwd": f"{source_id}/{pair_id}/control",
                "command": {"tool": "python", "args": ["-m", "pytest", "-q", "test_calc.py"]},
            },
        ],
    }
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(document), encoding="utf-8")
    return manifest, root, replay_id, control_id


def _plans(tmp_path: Path) -> tuple[list[ComparisonPlan], dict[str, Cassette], Path]:
    manifest_path, root, replay_id, control_id = _comparison_fixture(tmp_path)
    manifest = load_manifest(manifest_path)
    cassettes = {
        replay_id: Cassette(
            proposal=_PROPOSAL, repro=_REPRO, input_tokens=800, output_tokens=200
        ),
        control_id: Cassette(
            proposal=json.dumps({"findings": []}),
            repro=json.dumps({"test_body": ""}),
            input_tokens=800,
            output_tokens=200,
        ),
    }
    truths: dict[str, tuple[TruthDefect, ...]] = {}
    for truth in manifest.truth_defects:
        truths[truth.case_id] = (*truths.get(truth.case_id, ()), truth)
    plans: list[ComparisonPlan] = []
    for case in manifest.cases:
        runtime = next(r for r in manifest.runtime if r.case_id == case.case_id)
        replayed = case.role == "historical_bug_replay"
        plans.append(
            ComparisonPlan(
                case=case,
                request=ProjectEvaluationRequest(
                    case_id=case.case_id,
                    repo=root / runtime.cwd,
                    base_ref=case.fixed_commit if replayed else case.buggy_commit,
                    head_ref=case.buggy_commit if replayed else case.fixed_commit,
                    workspace_root=tmp_path / "workspace",
                    config=ReviewConfig(
                        k_samples=2, tier0_commands=[], auto_tighten_alpha=False
                    ),
                    limits=ExecutorLimits(wall_timeout_s=60.0),
                    verification_timeout_s=120.0,
                    repeats=1,
                    deadline_s=60.0,
                    truth=(
                        ProjectTruth(
                            fixed_ref=case.fixed_commit, defects=truths[case.case_id]
                        )
                        if case.case_id in truths
                        else None
                    ),
                ),
            )
        )
    return plans, cassettes, manifest_path


def test_compare_arms_measures_all_three_arms_with_honest_evidence(tmp_path: Path) -> None:
    """Every arm sees identical blinded diff bytes; findings match on
    preregistered location truth; evidence classes never claim a verification
    that was not purchased."""
    plans, cassettes, _ = _plans(tmp_path)

    measurements = compare_arms(
        plans,
        provider_factory=lambda request: ReplayProvider(cassettes[request.case_id]),
        bare_provider_factory=lambda case_id: ReplayProvider(cassettes[case_id]),
        ruff_executable=_ruff_executable(),
        checkpoint_root=tmp_path / "comparison-calls",
    )

    assert [arm.arm for arm in measurements.arms] == [ARM_PRODUCT, ARM_BARE_PROMPT, ARM_RUFF]
    by_arm = {arm.arm: arm for arm in measurements.arms}

    ruff_arm = by_arm[ARM_RUFF]
    assert "deterministic" in ruff_arm.description
    assert "not an AI reviewer" in ruff_arm.description
    assert ruff_arm.evidence_class_counts == {EVIDENCE_STATIC_DIAGNOSTIC: 1}
    assert by_arm[ARM_BARE_PROMPT].evidence_class_counts == {EVIDENCE_UNVERIFIED_CLAIM: 1}
    assert by_arm[ARM_PRODUCT].evidence_class_counts == {"regression_reproduced": 1}

    for arm in measurements.arms:
        accuracy = arm.accuracy
        assert accuracy.decided_positive_cases == 1
        assert accuracy.detected_positive_cases == 1
        assert accuracy.detection_rate == 1.0
        assert accuracy.detection_rate_interval is not None
        assert accuracy.decided_control_cases == 1
        assert accuracy.flagged_control_cases == 0
        assert accuracy.clean_false_positive_rate == 0.0
        assert accuracy.finding_precision == 1.0
        assert accuracy.silence_precision == 1.0
        assert arm.operational.silence_rate == 0.5

    product = by_arm[ARM_PRODUCT].operational
    bare = by_arm[ARM_BARE_PROMPT].operational
    ruff_op = by_arm[ARM_RUFF].operational
    assert bare.model_calls == 2  # one call per case
    assert bare.input_tokens == 1600
    assert product.model_calls >= 4  # K samples per case, plus generation
    assert product.spend_usd > bare.spend_usd
    assert ruff_op.model_calls == 0
    assert ruff_op.spend_usd == 0.0
    assert ruff_op.tool_cost_s > 0
    assert bare.tool_cost_s == 0.0

    assert len(measurements.runs) == 6
    assert all(run.status == "completed" for run in measurements.runs)
    assert sorted(measurements.evaluated_case_ids) == sorted(
        {plan.case.case_id for plan in plans}
    )


def test_comparison_checkpoint_root_replays_every_model_subcall(tmp_path: Path) -> None:
    plans, cassettes, _ = _plans(tmp_path)
    first_product: list[ReplayProvider] = []
    first_bare: list[ReplayProvider] = []

    def product_factory(request: ProjectEvaluationRequest) -> ReplayProvider:
        provider = ReplayProvider(cassettes[request.case_id])
        first_product.append(provider)
        return provider

    def bare_factory(case_id: str) -> ReplayProvider:
        provider = ReplayProvider(cassettes[case_id])
        first_bare.append(provider)
        return provider

    compare_arms(
        plans,
        provider_factory=product_factory,
        bare_provider_factory=bare_factory,
        ruff_executable=None,
        checkpoint_root=tmp_path / "calls",
    )
    assert sum(p.proposal_calls + p.generator_calls for p in first_product) > 0
    assert sum(p.proposal_calls + p.generator_calls for p in first_bare) > 0

    resumed_product: list[ReplayProvider] = []
    resumed_bare: list[ReplayProvider] = []

    def resumed_product_factory(request: ProjectEvaluationRequest) -> ReplayProvider:
        provider = ReplayProvider(cassettes[request.case_id])
        resumed_product.append(provider)
        return provider

    def resumed_bare_factory(case_id: str) -> ReplayProvider:
        provider = ReplayProvider(cassettes[case_id])
        resumed_bare.append(provider)
        return provider

    compare_arms(
        plans,
        provider_factory=resumed_product_factory,
        bare_provider_factory=resumed_bare_factory,
        ruff_executable=None,
        checkpoint_root=tmp_path / "calls",
    )
    assert sum(p.proposal_calls + p.generator_calls for p in resumed_product) == 0
    assert sum(p.proposal_calls + p.generator_calls for p in resumed_bare) == 0


def test_comparison_defer_after_settled_response_preserves_paid_call_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plans, cassettes, manifest_path = _plans(tmp_path)
    plan = plans[0]

    def fail_after_response(
        request: ProjectEvaluationRequest, *, provider: object, clock: object
    ) -> object:
        provider.sample("system", "prompt", {"type": "object"}, 20)
        raise RuntimeError("failure after provider settlement")

    monkeypatch.setattr(
        "attest.benchmark.baselines.evaluate_project", fail_after_response
    )
    measurements = compare_arms(
        [plan],
        provider_factory=lambda request: ReplayProvider(cassettes[request.case_id]),
        bare_provider_factory=lambda case_id: ReplayProvider(cassettes[case_id]),
        ruff_executable=None,
        checkpoint_root=tmp_path / "calls",
    )

    product = next(run for run in measurements.runs if run.arm == ARM_PRODUCT)
    assert product.status == "deferred"
    assert product.spend_usd > 0
    assert len(product.paid_calls) == 1
    assert product.spend_usd == pytest.approx(
        sum(float(row["cost_usd"]) for row in product.paid_calls)
    )
    assert product.paid_calls_sha256 == hashlib.sha256(
        json.dumps(
            product.paid_calls, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()

    report = build_comparison_report(
        load_manifest(manifest_path),
        measurements,
        manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        validation_receipt=None,
    ).to_json_dict()
    assert report["schema_version"] == "2"
    product_payload = next(
        run for run in report["runs"] if run["arm"] == ARM_PRODUCT
    )
    assert product_payload["paid_calls"] == list(product.paid_calls)
    assert product_payload["paid_calls_sha256"] == product.paid_calls_sha256

    corrupted = replace(
        measurements,
        runs=(
            replace(product, paid_calls_sha256="0" * 64),
            *(run for run in measurements.runs if run is not product),
        ),
    )
    with pytest.raises(ValueError, match="reconciliation|paid.call"):
        build_comparison_report(
            load_manifest(manifest_path),
            corrupted,
            manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            validation_receipt=None,
        )


def test_settled_comparison_replay_rejects_new_ordinal_before_provider_dispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plans, cassettes, _ = _plans(tmp_path)
    plan = plans[0]
    checkpoint_root = tmp_path / "calls"

    def one_response_then_fail(
        request: ProjectEvaluationRequest, *, provider: object, clock: object
    ) -> object:
        provider.sample("system", "prompt", {"type": "object"}, 20)
        raise RuntimeError("settle one call")

    monkeypatch.setattr(
        "attest.benchmark.baselines.evaluate_project", one_response_then_fail
    )
    compare_arms(
        [plan],
        provider_factory=lambda request: ReplayProvider(cassettes[request.case_id]),
        bare_provider_factory=lambda case_id: ReplayProvider(cassettes[case_id]),
        ruff_executable=None,
        checkpoint_root=checkpoint_root,
    )
    costs = checkpoint_root / ARM_PRODUCT / plan.case.case_id / "costs.jsonl"
    settled_costs = costs.read_bytes()

    def replay_then_request_new_ordinal(
        request: ProjectEvaluationRequest, *, provider: object, clock: object
    ) -> object:
        provider.sample("system", "prompt", {"type": "object"}, 20)
        provider.sample("second", "new ordinal", {"type": "object"}, 20)
        raise AssertionError("the settled replay bound must reject first")

    monkeypatch.setattr(
        "attest.benchmark.baselines.evaluate_project", replay_then_request_new_ordinal
    )
    resumed = ReplayProvider(cassettes[plan.case.case_id])
    with pytest.raises(ValueError, match="reconciliation|settled|ordinal"):
        compare_arms(
            [plan],
            provider_factory=lambda request: resumed,
            bare_provider_factory=lambda case_id: ReplayProvider(cassettes[case_id]),
            ruff_executable=None,
            checkpoint_root=checkpoint_root,
        )
    assert resumed.proposal_calls == 0
    assert costs.read_bytes() == settled_costs


def test_comparison_report_rechecks_authoritative_artifacts_at_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plans, cassettes, manifest_path = _plans(tmp_path)
    plan = plans[0]
    checkpoint_root = tmp_path / "calls"

    def fail_after_response(
        request: ProjectEvaluationRequest, *, provider: object, clock: object
    ) -> object:
        provider.sample("system", "prompt", {"type": "object"}, 20)
        raise RuntimeError("failure after provider settlement")

    monkeypatch.setattr(
        "attest.benchmark.baselines.evaluate_project", fail_after_response
    )
    measurements = compare_arms(
        [plan],
        provider_factory=lambda request: ReplayProvider(cassettes[request.case_id]),
        bare_provider_factory=lambda case_id: ReplayProvider(cassettes[case_id]),
        ruff_executable=None,
        checkpoint_root=checkpoint_root,
    )
    (
        checkpoint_root
        / ARM_PRODUCT
        / plan.case.case_id
        / "artifacts"
        / "000000.json"
    ).unlink()

    with pytest.raises(ValueError, match="reconciliation|artifact"):
        build_comparison_report(
            load_manifest(manifest_path),
            measurements,
            manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            validation_receipt=None,
        )


def test_comparison_report_rejects_model_drift_from_frozen_predeclaration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plans, cassettes, manifest_path = _plans(tmp_path)
    plan = plans[0]

    def fail_after_response(
        request: ProjectEvaluationRequest, *, provider: object, clock: object
    ) -> object:
        provider.sample("system", "prompt", {"type": "object"}, 20)
        raise RuntimeError("failure after provider settlement")

    monkeypatch.setattr(
        "attest.benchmark.baselines.evaluate_project", fail_after_response
    )
    measurements = compare_arms(
        [plan],
        provider_factory=lambda request: ReplayProvider(cassettes[request.case_id]),
        bare_provider_factory=lambda case_id: ReplayProvider(cassettes[case_id]),
        ruff_executable=None,
        checkpoint_root=tmp_path / "calls",
    )
    tampered = replace(
        measurements,
        runs=tuple(
            replace(run, model_id="claude-opus-5")
            if run.arm == ARM_PRODUCT
            else run
            for run in measurements.runs
        ),
    )

    with pytest.raises(ValueError, match="model|predeclaration|binding"):
        build_comparison_report(
            load_manifest(manifest_path),
            tampered,
            manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            validation_receipt=None,
        )


def test_comparison_report_rejects_omitted_authoritative_paid_trial(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plans, cassettes, manifest_path = _plans(tmp_path)
    plan = plans[0]

    def fail_after_response(
        request: ProjectEvaluationRequest, *, provider: object, clock: object
    ) -> object:
        provider.sample("system", "prompt", {"type": "object"}, 20)
        raise RuntimeError("failure after provider settlement")

    monkeypatch.setattr(
        "attest.benchmark.baselines.evaluate_project", fail_after_response
    )
    measurements = compare_arms(
        [plan],
        provider_factory=lambda request: ReplayProvider(cassettes[request.case_id]),
        bare_provider_factory=lambda case_id: ReplayProvider(cassettes[case_id]),
        ruff_executable=None,
        checkpoint_root=tmp_path / "calls",
    )
    omitted = replace(
        measurements,
        runs=tuple(run for run in measurements.runs if run.arm != ARM_BARE_PROMPT),
    )

    with pytest.raises(ValueError, match="paid|trial|reconciliation|arm"):
        build_comparison_report(
            load_manifest(manifest_path),
            omitted,
            manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            validation_receipt=None,
        )


def test_comparison_report_rejects_unbound_evaluated_cases_and_arm_summary(
    tmp_path: Path,
) -> None:
    plans, cassettes, manifest_path = _plans(tmp_path)
    measurements = compare_arms(
        [plans[0]],
        provider_factory=lambda request: ReplayProvider(cassettes[request.case_id]),
        bare_provider_factory=lambda case_id: ReplayProvider(cassettes[case_id]),
        ruff_executable=None,
        checkpoint_root=tmp_path / "calls",
    )
    manifest = load_manifest(manifest_path)
    manifest_sha256 = hashlib.sha256(manifest_path.read_bytes()).hexdigest()

    with pytest.raises(ValueError, match="evaluated|case|run"):
        build_comparison_report(
            manifest,
            replace(measurements, evaluated_case_ids=()),
            manifest_sha256=manifest_sha256,
            validation_receipt=None,
        )

    product = next(summary for summary in measurements.arms if summary.arm == ARM_PRODUCT)
    corrupted_product = replace(
        product,
        operational=replace(product.operational, spend_usd=0.0),
    )
    with pytest.raises(ValueError, match="summary|arm|run"):
        build_comparison_report(
            manifest,
            replace(
                measurements,
                arms=tuple(
                    corrupted_product if summary is product else summary
                    for summary in measurements.arms
                ),
            ),
            manifest_sha256=manifest_sha256,
            validation_receipt=None,
        )


def test_comparison_report_rejects_self_consistent_empty_measurements(
    tmp_path: Path,
) -> None:
    plans, cassettes, manifest_path = _plans(tmp_path)
    measurements = compare_arms(
        [plans[0]],
        provider_factory=lambda request: ReplayProvider(cassettes[request.case_id]),
        bare_provider_factory=lambda case_id: ReplayProvider(cassettes[case_id]),
        ruff_executable=None,
        checkpoint_root=tmp_path / "calls",
    )
    erased = compare_arms(
        [],
        provider_factory=lambda request: ReplayProvider(cassettes[request.case_id]),
        bare_provider_factory=lambda case_id: ReplayProvider(cassettes[case_id]),
        ruff_executable=None,
        checkpoint_root=None,
    )
    assert any((measurements.checkpoint_root or tmp_path).rglob("*.json"))

    with pytest.raises(ValueError, match="checkpoint|authoritative|paid|evidence"):
        build_comparison_report(
            load_manifest(manifest_path),
            erased,
            manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            validation_receipt=None,
        )


def test_comparison_report_rejects_paid_trial_model_divergence_from_binding(
    tmp_path: Path,
) -> None:
    plans, cassettes, manifest_path = _plans(tmp_path)
    checkpoint_root = tmp_path / "calls"
    measurements = compare_arms(
        [plans[0]],
        provider_factory=lambda request: ReplayProvider(cassettes[request.case_id]),
        bare_provider_factory=lambda case_id: ReplayProvider(cassettes[case_id]),
        ruff_executable=None,
        checkpoint_root=checkpoint_root,
    )
    declaration_path = checkpoint_root / "comparison.json"
    declaration = json.loads(declaration_path.read_text(encoding="utf-8"))
    for row in declaration["paid_trials"]:
        if row["arm"] == ARM_PRODUCT:
            row["model_id"] = "claude-opus-5"
    declaration_path.write_text(json.dumps(declaration) + "\n", encoding="utf-8")
    tampered = replace(
        measurements,
        runs=tuple(
            replace(run, model_id="claude-opus-5")
            if run.arm == ARM_PRODUCT
            else run
            for run in measurements.runs
        ),
    )

    with pytest.raises(ValueError, match="binding|model|predeclaration"):
        build_comparison_report(
            load_manifest(manifest_path),
            tampered,
            manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            validation_receipt=None,
        )


def test_comparison_report_rejects_invalid_frozen_evaluation_binding(
    tmp_path: Path,
) -> None:
    plans, cassettes, manifest_path = _plans(tmp_path)
    checkpoint_root = tmp_path / "calls"
    measurements = compare_arms(
        [plans[0]],
        provider_factory=lambda request: ReplayProvider(cassettes[request.case_id]),
        bare_provider_factory=lambda case_id: ReplayProvider(cassettes[case_id]),
        ruff_executable=None,
        checkpoint_root=checkpoint_root,
    )
    declaration_path = checkpoint_root / "comparison.json"
    declaration = json.loads(declaration_path.read_text(encoding="utf-8"))
    binding = declaration["bindings"][0]["binding"]
    binding["schema_version"] = "unsupported"
    binding["policy_sha256"] = "not-a-digest"
    binding["prompt_sha256"] = None
    binding["code_sha256"] = ""
    declaration_path.write_text(json.dumps(declaration) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="binding|schema|digest|predeclaration"):
        build_comparison_report(
            load_manifest(manifest_path),
            measurements,
            manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            validation_receipt=None,
        )


def test_comparison_report_rejects_orphan_paid_call_roots(
    tmp_path: Path,
) -> None:
    plans, cassettes, manifest_path = _plans(tmp_path)
    checkpoint_root = tmp_path / "calls"
    compare_arms(
        [plans[0]],
        provider_factory=lambda request: ReplayProvider(cassettes[request.case_id]),
        bare_provider_factory=lambda case_id: ReplayProvider(cassettes[case_id]),
        ruff_executable=None,
        checkpoint_root=checkpoint_root,
    )
    declaration_path = checkpoint_root / "comparison.json"
    declaration = json.loads(declaration_path.read_text(encoding="utf-8"))
    declaration["paid_trials"] = []
    declaration_path.write_text(json.dumps(declaration) + "\n", encoding="utf-8")
    for marker in (checkpoint_root / "reconciliation").rglob("*.json"):
        marker.unlink()
    erased = replace(
        compare_arms(
            [],
            provider_factory=lambda request: ReplayProvider(cassettes[request.case_id]),
            bare_provider_factory=lambda case_id: ReplayProvider(cassettes[case_id]),
            ruff_executable=None,
            checkpoint_root=None,
        ),
        checkpoint_root=checkpoint_root,
    )

    with pytest.raises(ValueError, match="orphan|checkpoint|binding|paid|evidence"):
        build_comparison_report(
            load_manifest(manifest_path),
            erased,
            manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            validation_receipt=None,
        )


def test_comparison_report_allows_predeclared_empty_plan(
    tmp_path: Path,
) -> None:
    _, _, manifest_path = _plans(tmp_path)
    measurements = compare_arms(
        [],
        provider_factory=lambda request: pytest.fail("empty plan dispatched product"),
        bare_provider_factory=lambda case_id: pytest.fail("empty plan dispatched bare"),
        ruff_executable=None,
        checkpoint_root=tmp_path / "empty-calls",
    )

    payload = build_comparison_report(
        load_manifest(manifest_path),
        measurements,
        manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        validation_receipt=None,
    ).to_json_dict()

    assert payload["runs"] == []
    assert len(payload["arms"]) == 3


@pytest.mark.parametrize(
    "corruption",
    (
        "missing_reconciliation",
        "duplicate_spend",
        "orphan_spend",
        "mismatched_spend",
        "missing_artifact",
        "wrong_reconciliation_digest",
    ),
)
def test_comparison_resume_rejects_incomplete_or_mismatched_paid_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, corruption: str
) -> None:
    plans, cassettes, _ = _plans(tmp_path)
    plan = plans[0]
    checkpoint_root = tmp_path / "calls"

    def fail_after_response(
        request: ProjectEvaluationRequest, *, provider: object, clock: object
    ) -> object:
        provider.sample("system", "prompt", {"type": "object"}, 20)
        raise RuntimeError("failure after provider settlement")

    monkeypatch.setattr(
        "attest.benchmark.baselines.evaluate_project", fail_after_response
    )
    compare_arms(
        [plan],
        provider_factory=lambda request: ReplayProvider(cassettes[request.case_id]),
        bare_provider_factory=lambda case_id: ReplayProvider(cassettes[case_id]),
        ruff_executable=None,
        checkpoint_root=checkpoint_root,
    )

    product_root = checkpoint_root / ARM_PRODUCT / plan.case.case_id
    reconciliation = (
        checkpoint_root
        / "reconciliation"
        / ARM_PRODUCT
        / f"{plan.case.case_id}.json"
    )
    if corruption == "missing_reconciliation":
        reconciliation.unlink()
    elif corruption == "duplicate_spend":
        spend = product_root / "costs.jsonl"
        spend.write_text(
            spend.read_text(encoding="utf-8") * 2,
            encoding="utf-8",
        )
    elif corruption == "orphan_spend":
        with (product_root / "costs.jsonl").open("a", encoding="utf-8") as stream:
            stream.write('{"call_id":"orphan"}\n')
    elif corruption == "mismatched_spend":
        spend = product_root / "costs.jsonl"
        row = json.loads(spend.read_text(encoding="utf-8"))
        row["trial_id"] = "comparison:wrong-trial"
        spend.write_text(json.dumps(row) + "\n", encoding="utf-8")
    elif corruption == "missing_artifact":
        (product_root / "artifacts" / "000000.json").unlink()
    else:
        binding = json.loads(reconciliation.read_text(encoding="utf-8"))
        binding["paid_calls_sha256"] = "0" * 64
        reconciliation.write_text(json.dumps(binding) + "\n", encoding="utf-8")

    resumed: list[ReplayProvider] = []

    def provider_factory(request: ProjectEvaluationRequest) -> ReplayProvider:
        provider = ReplayProvider(cassettes[request.case_id])
        resumed.append(provider)
        return provider

    with pytest.raises(ValueError, match="reconciliation|spend|artifact|orphan"):
        compare_arms(
            [plan],
            provider_factory=provider_factory,
            bare_provider_factory=lambda case_id: ReplayProvider(cassettes[case_id]),
            ruff_executable=None,
            checkpoint_root=checkpoint_root,
        )
    assert sum(provider.proposal_calls for provider in resumed) == 0


def test_compare_arms_requires_repeat_zero_and_reports_deferred_arms(
    tmp_path: Path,
) -> None:
    """Wilson denominators come from repeat zero only, and an arm that cannot
    run appears as a DEFER instead of disappearing."""
    plans, cassettes, _ = _plans(tmp_path)

    shifted = [replace(plans[0], request=replace(plans[0].request, repeat=1)), *plans[1:]]
    with pytest.raises(ValueError, match="repeat zero"):
        compare_arms(
            shifted,
            provider_factory=lambda request: ReplayProvider(cassettes[request.case_id]),
            bare_provider_factory=lambda case_id: ReplayProvider(cassettes[case_id]),
            ruff_executable=None,
        )

    measurements = compare_arms(
        plans,
        provider_factory=lambda request: ReplayProvider(cassettes[request.case_id]),
        bare_provider_factory=lambda case_id: ReplayProvider(cassettes[case_id]),
        ruff_executable=None,
    )
    ruff_arm = next(arm for arm in measurements.arms if arm.arm == ARM_RUFF)
    assert len(ruff_arm.abstentions) == 2
    assert all(row.reason == "static_tool_unavailable" for row in ruff_arm.abstentions)
    assert ruff_arm.accuracy.decided_positive_cases == 0
    assert ruff_arm.accuracy.detection_rate is None
    deferred_runs = [run for run in measurements.runs if run.status == "deferred"]
    assert {run.arm for run in deferred_runs} == {ARM_RUFF}


def _receipt_artifacts(tmp_path: Path, manifest: Path) -> tuple[Path, Path]:
    document = json.loads(manifest.read_text(encoding="utf-8"))
    pair_ids = sorted({case["pair_id"] for case in document["cases"]})
    manifest_sha256 = hashlib.sha256(manifest.read_bytes()).hexdigest()
    results = {
        "schema_version": "1",
        "manifest_sha256": manifest_sha256,
        "results": [{"pair_id": pair_id, "status": "validated"} for pair_id in pair_ids],
    }
    results_bytes = (
        json.dumps(results, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()
    receipt = {
        "schema_version": "1",
        "manifest_sha256": manifest_sha256,
        "validated_pair_ids": pair_ids,
        "validation_results_sha256": hashlib.sha256(results_bytes).hexdigest(),
    }
    receipt_path = tmp_path / "validation-receipt.json"
    results_path = tmp_path / "validation-results.json"
    results_path.write_bytes(results_bytes)
    receipt_path.write_bytes(
        (json.dumps(receipt, sort_keys=True, separators=(",", ":")) + "\n").encode()
    )
    return receipt_path, results_path


def test_comparison_report_withholds_accuracy_without_a_receipt(tmp_path: Path) -> None:
    """Accuracy-flavoured numbers need the manifest-bound receipt; operational
    accounting is published either way, and losing arms are never omitted."""
    plans, cassettes, manifest_path = _plans(tmp_path)
    manifest = load_manifest(manifest_path)
    manifest_sha256 = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    measurements = compare_arms(
        plans,
        provider_factory=lambda request: ReplayProvider(cassettes[request.case_id]),
        bare_provider_factory=lambda case_id: ReplayProvider(cassettes[case_id]),
        ruff_executable=_ruff_executable(),
        checkpoint_root=tmp_path / "comparison-report-calls",
    )

    withheld = build_comparison_report(
        manifest,
        measurements,
        manifest_sha256=manifest_sha256,
        validation_receipt=None,
    )
    payload = withheld.to_json_dict()
    assert payload["metrics_withheld_reason"] == RECEIPT_MISSING
    assert len(payload["arms"]) == 3
    for arm in payload["arms"]:
        assert arm["accuracy"] is None
        assert arm["operational"]["spend_usd"] is not None
    assert "matched_defect_id" not in json.dumps(payload)
    assert any("withheld" in note or "receipt" in note for note in payload["limitations"])

    receipt_path, results_path = _receipt_artifacts(tmp_path, manifest_path)
    receipt = load_validation_receipt(receipt_path, manifest_path, results_path)
    authorized = build_comparison_report(
        manifest,
        measurements,
        manifest_sha256=manifest_sha256,
        validation_receipt=receipt,
    )
    granted = authorized.to_json_dict()
    assert granted["metrics_withheld_reason"] is None
    for arm in granted["arms"]:
        assert arm["accuracy"]["detection_rate"] == 1.0
        assert arm["accuracy"]["silence_precision"] == 1.0
        assert arm["accuracy"]["detection_rate_interval"] is not None

    markdown = render_comparison_markdown(authorized)
    assert ARM_PRODUCT in markdown
    assert ARM_BARE_PROMPT in markdown
    assert ARM_RUFF in markdown
    assert "not an AI reviewer" in markdown
    notes = " ".join(granted["limitations"])
    assert "losing" in notes or "every arm" in notes
    assert "repeat zero" in notes


def test_compare_cli_runs_three_arms_offline_end_to_end(tmp_path: Path) -> None:
    """The CLI mode uses recorded cassettes and a local ruff executable only,
    and publishes accuracy solely under a manifest-bound receipt."""
    manifest_path, root, replay_id, control_id = _comparison_fixture(tmp_path)
    cassettes_dir = tmp_path / "cassettes"
    cassettes_dir.mkdir()
    (cassettes_dir / f"{replay_id}.json").write_text(
        json.dumps(
            {"proposal": _PROPOSAL, "repro": _REPRO, "input_tokens": 800, "output_tokens": 200}
        ),
        encoding="utf-8",
    )
    (cassettes_dir / f"{control_id}.json").write_text(
        json.dumps(
            {
                "proposal": json.dumps({"findings": []}),
                "repro": json.dumps({"test_body": ""}),
                "input_tokens": 800,
                "output_tokens": 200,
            }
        ),
        encoding="utf-8",
    )
    receipt_path, results_path = _receipt_artifacts(tmp_path, manifest_path)
    environment = dict(os.environ)
    environment["ANTHROPIC_API_KEY"] = "must-not-be-used"
    output = tmp_path / "out"

    completed = subprocess.run(
        [
            sys.executable,
            str(_SCRIPT),
            "compare",
            "--manifest",
            str(manifest_path),
            "--cassette-root",
            str(cassettes_dir),
            "--root",
            str(root),
            "--output",
            str(output),
            "--validation-receipt",
            str(receipt_path),
            "--validation-results",
            str(results_path),
            "--ruff-executable",
            _ruff_executable(),
            "--k-samples",
            "2",
            "--differential-repeats",
            "1",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )

    assert completed.returncode == 0, completed.stderr
    summary = json.loads(completed.stdout)
    assert summary["status"] == "ok"
    assert summary["offline"] is True
    assert summary["arms"] == 3
    assert summary["evaluated_cases"] == 2
    assert summary["metrics_status"] == "reported"
    report = json.loads((output / "comparison.json").read_text(encoding="utf-8"))
    assert [arm["arm"] for arm in report["arms"]] == [ARM_PRODUCT, ARM_BARE_PROMPT, ARM_RUFF]
    for arm in report["arms"]:
        assert arm["accuracy"]["detection_rate"] == 1.0
        assert arm["accuracy"]["clean_false_positive_rate"] == 0.0
    assert (output / "comparison.md").is_file()
    assert report["digest"]
