"""Three-arm comparison: identical blinded diff bytes, honest evidence classes."""

from __future__ import annotations

import errno
import hashlib
import json
import os
import shutil
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

import attest.benchmark.baselines as baselines_module
from attest.benchmark.api import (
    ProjectEvaluationAuthorityError,
    ProjectEvaluationRequest,
    ProjectEvaluationResult,
    manifest_project_truth,
    project_truth_sha256,
)
from attest.benchmark.api import (
    evaluate_project as real_evaluate_project,
)
from attest.benchmark.baselines import (
    ARM_BARE_PROMPT,
    ARM_PRODUCT,
    ARM_RUFF,
    COMPARISON_CHECKPOINT_SCHEMA_VERSION,
    EVIDENCE_STATIC_DIAGNOSTIC,
    EVIDENCE_UNVERIFIED_CLAIM,
    BarePromptBaseline,
    ComparisonEvidenceError,
    ComparisonExecution,
    ComparisonMeasurements,
    ComparisonPlan,
    RuffBaseline,
    _summarize_arm,
)
from attest.benchmark.baselines import (
    compare_arms as _compare_arms,
)
from attest.benchmark.checkpoints import (
    CALL_ROLE_BENCHMARK_ORACLE,
    CALL_ROLE_PRODUCT,
)
from attest.benchmark.corpus import (
    ValidationReceipt,
    load_validation_receipt,
    validation_receipt_binding_bytes,
)
from attest.benchmark.measurement import (
    CURRENT_MEASUREMENT_SCHEMA_VERSION,
    CURRENT_MEASUREMENT_SEMANTICS,
    DELIVERY_TRANSCRIPT_PROTOCOL,
    DELIVERY_TRANSCRIPT_SCHEMA_VERSION,
    EMPTY_DELIVERY_TRANSCRIPT_SHA256,
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
    TruthStatus,
    derive_task_status,
)
from attest.benchmark.report import (
    RECEIPT_HISTORICAL,
    RECEIPT_MISSING,
    render_comparison_markdown,
)
from attest.benchmark.report import (
    build_comparison_report as _build_comparison_report,
)
from attest.benchmark.runner import Cassette, ReplayProvider
from attest.benchmark.schema import load_manifest, normalize_unified_diff_bytes
from attest.review.config import ReviewConfig
from attest.review.diffs import parse_diff
from attest.review.executor import ExecutorLimits
from attest.review.proposer import PROPOSER_MAX_OUTPUT_TOKENS, ProviderResult

from ._validation_v2 import (
    KEY,
    KEY_ID,
    build_validation_v2_bundle,
    verified_validation_authority,
)
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

    found = shutil.which("ruff")
    if found is None:
        pytest.skip("requires a local ruff executable")
    return found


def _comparison_authority(root: Path) -> dict[str, object]:
    """External owner inputs used consistently across one test run/resume."""
    return {
        "authority_root": root.with_name(root.name + "-owner"),
        "run_identity": hashlib.sha256(str(root).encode("utf-8")).hexdigest(),
    }


def compare_arms(plans, **kwargs):
    """Give every checkpointed test an explicit external owner identity."""
    root = kwargs.get("checkpoint_root")
    if root is not None and plans and "authority_root" not in kwargs:
        kwargs.update(_comparison_authority(root))
    return _compare_arms(plans, **kwargs)


def build_comparison_report(manifest, measurements, **kwargs):
    """Pass the execution bundle's external capability explicitly to production."""
    if "publication_authority" not in kwargs:
        kwargs["publication_authority"] = measurements.publication_authority
    return _build_comparison_report(manifest, measurements, **kwargs)


def _finding(
    finding_id: str,
    *,
    status: str = "published",
    accuracy: str = "correct",
    defect_id: str | None = "defect-1",
    authority: str = "automated",
) -> FindingOutcome:
    return FindingOutcome(
        finding_id=finding_id,
        finding_status=FindingStatus(status),
        accuracy_status=AccuracyStatus(accuracy),
        defect_id=defect_id,
        publication_event_ids=(
            ("publication:event",) if status == "published" else ()
        ),
        authority=FindingAuthority(authority),
    )


def _measurement_record(
    *,
    stop: str = "none",
    findings: tuple[FindingOutcome, ...] = (),
    repeat: int = 0,
    eligible_defect_ids: tuple[str, ...] = ("defect-1",),
    pull_request_number: int = 17,
    truth_status: str = "positive",
) -> MeasurementRecord:
    stop_kind = StopKind(stop)
    task_status = derive_task_status(stop_kind, findings)
    published_count = sum(finding.author_visible for finding in findings)
    unresolved_count = sum(
        finding.finding_status is FindingStatus.UNRESOLVED for finding in findings
    )
    publication_events = (
        (
            PublicationEvent(
                event_id="publication:event",
                attempt_id="attempt:publication",
                attempt_ordinal=0,
                repository="local/project",
                pull_request_number=pull_request_number,
                head_sha="1" * 40,
                members=tuple(
                    PublicationMember(
                        finding_id=finding.finding_id,
                        placement=PublicationPlacement.INLINE,
                    )
                    for finding in findings
                    if finding.author_visible
                ),
                channel=PublicationChannel.INLINE_REVIEW,
                outcome=PublicationOutcome.SUCCEEDED,
                body_sha256="a" * 64,
                request_sha256="d" * 64,
                remote_response_id="101",
                delivered_at_s=5.0,
                deadline_s=60.0,
            ),
        )
        if published_count
        else ()
    )
    return MeasurementRecord(
        schema_version=CURRENT_MEASUREMENT_SCHEMA_VERSION,
        scoring_semantics=CURRENT_MEASUREMENT_SEMANTICS,
        case_id="case-1",
        arm="product",
        repeat=repeat,
        stop_kind=stop_kind,
        task_status=task_status,
        findings=findings,
        eligible_defect_ids=eligible_defect_ids,
        pull_request_number=pull_request_number,
        truth_status=TruthStatus(truth_status),
        delivery_status=(
            DeliveryStatus.PUBLISHED_ON_TIME
            if published_count
            else DeliveryStatus.NO_PUBLICATION
        ),
        candidate_count=len(findings),
        published_count=published_count,
        unresolved_count=unresolved_count,
        publication_events=publication_events,
        task_delivery_events=(),
        delivery_transcript=DeliveryTranscriptReceipt(
            schema_version=DELIVERY_TRANSCRIPT_SCHEMA_VERSION,
            protocol=DELIVERY_TRANSCRIPT_PROTOCOL,
            task_id=("task:measurement" if publication_events else None),
            expected_attempt_count=(1 if publication_events else 0),
            last_attempt_ordinal=(0 if publication_events else None),
            transcript_sha256=(
                "e" * 64 if publication_events else EMPTY_DELIVERY_TRANSCRIPT_SHA256
            ),
        ),
        metrics_withheld_reason=None,
        delivery_withheld_reason=None,
        task_delivery_withheld_reason=None,
    )


def _replace_execution_measurements(
    execution: ComparisonExecution, **changes: object
) -> ComparisonExecution:
    return ComparisonExecution(
        measurements=replace(execution.measurements, **changes),
        publication_authority=execution.publication_authority,
    )


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


@pytest.mark.parametrize(
    ("state", "expected"),
    (
        ("missing", False),
        ("empty", False),
        ("calls", True),
        ("artifacts", True),
        ("costs", True),
        ("rogue", "error"),
        ("root_file", "error"),
        ("root_symlink", "error"),
        ("calls_file", "error"),
        ("costs_symlink", "error"),
        ("lstat_error", "error"),
        ("reader_error", "error"),
    ),
)
def test_paid_call_evidence_presence_is_an_exact_fail_closed_authority_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    state: str,
    expected: bool | str,
) -> None:
    """Missing reconciliation cannot ignore paid bytes or unsafe aliases."""

    root = tmp_path / "paid"
    if state == "empty":
        root.mkdir()
    elif state in {"calls", "artifacts"}:
        evidence = root / state
        evidence.mkdir(parents=True)
        (evidence / "000000.json").write_text("{}\n", encoding="utf-8")
    elif state == "costs":
        root.mkdir()
        (root / "costs.jsonl").write_text("{}\n", encoding="utf-8")
    elif state == "rogue":
        root.mkdir()
        (root / "unbound").write_text("evidence\n", encoding="utf-8")
    elif state == "root_file":
        root.write_text("not a directory\n", encoding="utf-8")
    elif state == "root_symlink":
        target = tmp_path / "real-paid"
        target.mkdir()
        root.symlink_to(target, target_is_directory=True)
    elif state == "calls_file":
        root.mkdir()
        (root / "calls").write_text("not a directory\n", encoding="utf-8")
    elif state == "costs_symlink":
        root.mkdir()
        target = tmp_path / "outside-costs"
        target.write_text("{}\n", encoding="utf-8")
        (root / "costs.jsonl").symlink_to(target)
    elif state == "lstat_error":
        real_lstat = Path.lstat

        def unreadable_lstat(path: Path):
            if path == root:
                raise OSError("simulated unreadable paid root")
            return real_lstat(path)

        monkeypatch.setattr(Path, "lstat", unreadable_lstat)
    elif state == "reader_error":
        root.mkdir()

        def unreadable_directory(*_args, **_kwargs):
            raise ValueError("simulated authoritative reader refusal")

        monkeypatch.setattr(
            baselines_module,
            "list_authoritative_directory",
            unreadable_directory,
        )

    if expected == "error":
        with pytest.raises(ComparisonEvidenceError, match="unreadable|unsafe|entry"):
            baselines_module._call_evidence_exists(root)
    else:
        assert baselines_module._call_evidence_exists(root) is expected


@pytest.mark.parametrize(
    "state",
    (
        "exact_reuse",
        "exact_write_race",
        "missing_write_race",
        "unreadable",
        "unsupported_version",
        "payload_drift",
        "returned_document_drift",
    ),
)
def test_comparison_predeclaration_recovery_refuses_every_immutable_state_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    state: str,
) -> None:
    """Provider-before recovery accepts only the exact canonical declaration."""

    from attest.benchmark.outcomes import write_canonical_json_once

    root = tmp_path / "checkpoint"
    expected = {
        "schema_version": COMPARISON_CHECKPOINT_SCHEMA_VERSION,
        "mode": "comparison",
        "run_identity": "a" * 64,
    }
    if state in {"exact_reuse", "exact_write_race"}:
        write_canonical_json_once(root, "comparison.json", expected)
    elif state == "unreadable":
        root.mkdir()
        (root / "comparison.json").write_bytes(b'{"schema_version":7}\ntrailing')
    elif state == "unsupported_version":
        write_canonical_json_once(
            root,
            "comparison.json",
            {**expected, "schema_version": "6"},
        )
    elif state == "payload_drift":
        write_canonical_json_once(
            root,
            "comparison.json",
            {**expected, "run_identity": "b" * 64},
        )
    elif state == "returned_document_drift":
        returned = write_canonical_json_once(
            tmp_path / "other",
            "comparison.json",
            {**expected, "run_identity": "c" * 64},
        )
        monkeypatch.setattr(
            baselines_module,
            "write_canonical_json_once",
            lambda *_args, **_kwargs: returned,
        )

    if state in {"exact_write_race", "missing_write_race"}:
        monkeypatch.setattr(
            baselines_module,
            "write_canonical_json_once",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                ValueError("simulated write race")
            ),
        )

    if state in {"exact_reuse", "exact_write_race"}:
        document = baselines_module._require_comparison_predeclaration(root, expected)
        assert document.value == expected
    else:
        with pytest.raises(
            ValueError,
            match="write race|unreadable|unsupported|drift|canonical bytes",
        ):
            baselines_module._require_comparison_predeclaration(root, expected)


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
    plans: list[ComparisonPlan] = []
    for case in manifest.cases:
        runtime = next(r for r in manifest.runtime if r.case_id == case.case_id)
        replayed = case.role == "historical_bug_replay"
        plans.append(
            ComparisonPlan(
                manifest=manifest,
                manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
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
                    truth=manifest_project_truth(manifest, case.case_id),
                ),
            )
        )
    return plans, cassettes, manifest_path


@pytest.mark.parametrize("drift", ("truth_absent", "truth_altered", "commit", "role"))
def test_compare_arms_rejects_manifest_contract_drift_before_provider(
    tmp_path: Path, drift: str
) -> None:
    """A caller cannot redefine hidden truth or immutable case identity."""
    plans, cassettes, _ = _plans(tmp_path)
    original = plans[0]
    if drift == "truth_absent":
        changed = replace(original, request=replace(original.request, truth=None))
    elif drift == "truth_altered":
        assert original.request.truth is not None
        changed_truth = replace(
            original.request.truth,
            defects=(
                replace(original.request.truth.defects[0], file="different.py"),
                *original.request.truth.defects[1:],
            ),
        )
        changed = replace(
            original, request=replace(original.request, truth=changed_truth)
        )
    elif drift == "commit":
        changed = replace(
            original,
            request=replace(original.request, base_ref=original.request.head_ref),
        )
    else:
        changed = replace(
            original,
            case=replace(original.case, role="developer_fix_control"),
        )
    drifted = [changed, *plans[1:]]
    provider_calls: list[str] = []
    checkpoint_root = tmp_path / f"{drift}-calls"

    with pytest.raises(ValueError, match="manifest|truth|commit|role"):
        compare_arms(
            drifted,
            provider_factory=lambda request: (
                provider_calls.append(f"product:{request.case_id}")
                or ReplayProvider(cassettes[request.case_id])
            ),
            bare_provider_factory=lambda case_id: (
                provider_calls.append(f"bare:{case_id}")
                or ReplayProvider(cassettes[case_id])
            ),
            ruff_executable=None,
            checkpoint_root=checkpoint_root,
        )
    assert provider_calls == []
    assert not checkpoint_root.exists()


@pytest.mark.parametrize("receipt_kind", ("verification", "raw_v2"))
def test_compare_arms_rejects_v2_authority_before_provider_or_checkpoint(
    tmp_path: Path, receipt_kind: str
) -> None:
    """Phase0 execution accepts no symmetric-key current authority object."""
    plans, cassettes, manifest_path = _plans(tmp_path)
    authority = verified_validation_authority(
        tmp_path / "execution-authority", manifest_path
    )
    receipt: object = authority if receipt_kind == "verification" else authority.receipt
    provider_calls: list[str] = []
    checkpoint_root = tmp_path / f"{receipt_kind}-execution-calls"

    with pytest.raises(ValueError, match="X-01|public-key|symmetric"):
        compare_arms(
            plans,
            provider_factory=lambda request: (
                provider_calls.append(f"product:{request.case_id}")
                or ReplayProvider(cassettes[request.case_id])
            ),
            bare_provider_factory=lambda case_id: (
                provider_calls.append(f"bare:{case_id}")
                or ReplayProvider(cassettes[case_id])
            ),
            ruff_executable=None,
            checkpoint_root=checkpoint_root,
            validation_receipt=receipt,  # type: ignore[arg-type]
        )
    assert provider_calls == []
    assert not checkpoint_root.exists()


def test_compare_arms_no_longer_accepts_an_opaque_receipt_digest(
    tmp_path: Path,
) -> None:
    """A digest cannot masquerade as typed execution authority."""
    plans, cassettes, _ = _plans(tmp_path)
    checkpoint_root = tmp_path / "opaque-digest-calls"

    with pytest.raises(TypeError, match="receipt_sha256"):
        compare_arms(
            plans,
            provider_factory=lambda request: ReplayProvider(cassettes[request.case_id]),
            bare_provider_factory=lambda case_id: ReplayProvider(cassettes[case_id]),
            ruff_executable=None,
            checkpoint_root=checkpoint_root,
            receipt_sha256="a" * 64,
        )
    assert not checkpoint_root.exists()


@pytest.mark.parametrize("alias_kind", ("same", "descendant", "symlink"))
def test_comparison_rejects_authority_root_alias_before_provider(
    tmp_path: Path, alias_kind: str
) -> None:
    plans, cassettes, _ = _plans(tmp_path)
    checkpoint_root = tmp_path / "calls"
    if alias_kind == "same":
        authority_root = checkpoint_root
    elif alias_kind == "descendant":
        authority_root = checkpoint_root / "owner"
    else:
        checkpoint_root.mkdir()
        authority_root = tmp_path / "owner-alias"
        authority_root.symlink_to(checkpoint_root, target_is_directory=True)
    provider_calls: list[str] = []

    with pytest.raises(ValueError, match="authority root must be external"):
        compare_arms(
            plans,
            provider_factory=lambda request: (
                provider_calls.append(request.case_id)
                or ReplayProvider(cassettes[request.case_id])
            ),
            bare_provider_factory=lambda case_id: pytest.fail(
                "authority alias must fail before bare provider"
            ),
            ruff_executable=None,
            checkpoint_root=checkpoint_root,
            authority_root=authority_root,
            run_identity="1" * 64,
        )

    assert provider_calls == []


@pytest.mark.parametrize("line_slack", (-1, True))
def test_compare_arms_rejects_invalid_line_slack_before_side_effects(
    tmp_path: Path, line_slack: object
) -> None:
    plans, cassettes, _ = _plans(tmp_path)
    provider_calls: list[str] = []
    checkpoint_root = tmp_path / "invalid-line-slack"

    with pytest.raises(ValueError, match="line_slack"):
        compare_arms(
            plans,
            provider_factory=lambda request: (
                provider_calls.append(f"product:{request.case_id}")
                or ReplayProvider(cassettes[request.case_id])
            ),
            bare_provider_factory=lambda case_id: (
                provider_calls.append(f"bare:{case_id}")
                or ReplayProvider(cassettes[case_id])
            ),
            ruff_executable=None,
            checkpoint_root=checkpoint_root,
            line_slack=line_slack,  # type: ignore[arg-type]
        )
    assert provider_calls == []
    assert not checkpoint_root.exists()


def test_compare_arms_rejects_request_line_slack_drift_before_side_effects(
    tmp_path: Path,
) -> None:
    plans, cassettes, _ = _plans(tmp_path)
    plans[0] = replace(
        plans[0], request=replace(plans[0].request, line_slack=1)
    )
    provider_calls: list[str] = []
    checkpoint_root = tmp_path / "request-line-slack"

    with pytest.raises(ValueError, match="line_slack"):
        compare_arms(
            plans,
            provider_factory=lambda request: (
                provider_calls.append(f"product:{request.case_id}")
                or ReplayProvider(cassettes[request.case_id])
            ),
            bare_provider_factory=lambda case_id: (
                provider_calls.append(f"bare:{case_id}")
                or ReplayProvider(cassettes[case_id])
            ),
            ruff_executable=None,
            checkpoint_root=checkpoint_root,
            line_slack=0,
        )
    assert provider_calls == []
    assert not checkpoint_root.exists()


def test_comparison_resume_rejects_pull_request_policy_drift_before_provider(
    tmp_path: Path,
) -> None:
    plans, cassettes, _ = _plans(tmp_path)
    checkpoint_root = tmp_path / "comparison-pr-policy"
    compare_arms(
        plans,
        provider_factory=lambda request: ReplayProvider(cassettes[request.case_id]),
        bare_provider_factory=lambda case_id: ReplayProvider(cassettes[case_id]),
        ruff_executable=None,
        checkpoint_root=checkpoint_root,
    )
    before = {
        str(path.relative_to(checkpoint_root)): path.read_bytes()
        for path in sorted(checkpoint_root.rglob("*"))
        if path.is_file()
    }
    drifted = [
        replace(
            plans[0],
            request=replace(plans[0].request, pull_request_number=2),
        ),
        *plans[1:],
    ]
    provider_calls: list[str] = []

    with pytest.raises(ValueError, match="predeclaration|drift"):
        compare_arms(
            drifted,
            provider_factory=lambda request: (
                provider_calls.append(f"product:{request.case_id}")
                or ReplayProvider(cassettes[request.case_id])
            ),
            bare_provider_factory=lambda case_id: (
                provider_calls.append(f"bare:{case_id}")
                or ReplayProvider(cassettes[case_id])
            ),
            ruff_executable=None,
            checkpoint_root=checkpoint_root,
        )
    assert provider_calls == []
    assert {
        str(path.relative_to(checkpoint_root)): path.read_bytes()
        for path in sorted(checkpoint_root.rglob("*"))
        if path.is_file()
    } == before


def test_compare_arms_measures_all_three_arms_with_honest_evidence(tmp_path: Path) -> None:
    """Every arm sees identical blinded diff bytes; findings match on
    preregistered location truth; evidence classes never claim a verification
    that was not purchased."""
    plans, cassettes, manifest_path = _plans(tmp_path)
    root = tmp_path / "comparison-calls"

    execution = compare_arms(
        plans,
        provider_factory=lambda request: ReplayProvider(cassettes[request.case_id]),
        bare_provider_factory=lambda case_id: ReplayProvider(cassettes[case_id]),
        ruff_executable=_ruff_executable(),
        checkpoint_root=root,
        **_comparison_authority(root),
    )
    measurements = execution.measurements

    assert [arm.arm for arm in measurements.arms] == [ARM_PRODUCT, ARM_BARE_PROMPT, ARM_RUFF]
    by_arm = {arm.arm: arm for arm in measurements.arms}

    ruff_arm = by_arm[ARM_RUFF]
    assert "deterministic" in ruff_arm.description
    assert "not an AI reviewer" in ruff_arm.description
    assert ruff_arm.evidence_class_counts["product_self_certified"] == {
        EVIDENCE_STATIC_DIAGNOSTIC: 1
    }
    assert by_arm[ARM_BARE_PROMPT].evidence_class_counts["product_self_certified"] == {
        EVIDENCE_UNVERIFIED_CLAIM: 1
    }
    assert by_arm[ARM_PRODUCT].evidence_class_counts["product_self_certified"] == {
        "regression_reproduced": 1
    }

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
    positive_product_run = next(
        run
        for run in measurements.runs
        if run.arm == ARM_PRODUCT and run.oracle_spend_usd > 0
    )
    assert positive_product_run.spend_usd == pytest.approx(0.0108)
    assert positive_product_run.oracle_spend_usd == pytest.approx(0.0036)
    product_rows = [
        row
        for run in measurements.runs
        if run.arm == ARM_PRODUCT
        for row in run.paid_calls
    ]
    assert sum(
        float(row["cost_usd"])
        for row in product_rows
        if row["role"] == CALL_ROLE_PRODUCT
    ) == pytest.approx(product.spend_usd)
    assert sum(
        float(row["cost_usd"])
        for row in product_rows
        if row["role"] == CALL_ROLE_BENCHMARK_ORACLE
    ) == pytest.approx(product.oracle_spend_usd)
    assert sum(float(row["cost_usd"]) for row in product_rows) == pytest.approx(
        product.spend_usd + product.oracle_spend_usd
    )
    assert ruff_op.model_calls == 0
    assert ruff_op.spend_usd == 0.0
    assert ruff_op.tool_cost_s > 0
    assert bare.tool_cost_s == 0.0

    assert len(measurements.runs) == 6
    assert all(run.status == "completed" for run in measurements.runs)
    assert sorted(measurements.evaluated_case_ids) == sorted(
        {plan.case.case_id for plan in plans}
    )
    report = build_comparison_report(
        load_manifest(manifest_path),
        measurements,
        manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        validation_receipt=None,
        publication_authority=execution.publication_authority,
    )
    assert sum(run.input_tokens for run in report.measurements.runs) > 0
    assert sum(run.output_tokens for run in report.measurements.runs) > 0


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
        **_comparison_authority(tmp_path / "calls"),
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
        **_comparison_authority(tmp_path / "calls"),
    )
    assert sum(p.proposal_calls + p.generator_calls for p in resumed_product) == 0
    assert sum(p.proposal_calls + p.generator_calls for p in resumed_bare) == 0


@pytest.mark.parametrize("arm", (ARM_PRODUCT, ARM_BARE_PROMPT))
def test_paid_factory_enters_after_exact_running_marker_and_may_create_empty_root(
    tmp_path: Path, arm: str
) -> None:
    """A fresh paid factory runs only after its durable trial marker exists."""
    plans, cassettes, _ = _plans(tmp_path)
    plan = plans[0]
    root = tmp_path / f"marker-before-{arm}"
    marker = root / "reconciliation" / arm / f"{plan.case.case_id}.json"
    expected_marker = {
        "schema_version": baselines_module.COMPARISON_RECONCILIATION_SCHEMA_VERSION,
        "arm": arm,
        "case_id": plan.case.case_id,
        "trial_id": f"comparison:{arm}:{plan.case.case_id}",
        "status": "running",
    }
    target_providers: list[ReplayProvider] = []

    def target_factory() -> ReplayProvider:
        document = baselines_module.read_canonical_json(
            root, marker.relative_to(root)
        )
        assert document.value == expected_marker
        case_root = root / arm / plan.case.case_id
        assert {path.name for path in case_root.iterdir()} == {"calls", "artifacts"}
        assert all(path.is_dir() and not tuple(path.iterdir()) for path in case_root.iterdir())
        provider = ReplayProvider(cassettes[plan.case.case_id])
        target_providers.append(provider)
        return provider

    execution = compare_arms(
        [plan],
        provider_factory=(
            (lambda _request: target_factory())
            if arm == ARM_PRODUCT
            else lambda request: ReplayProvider(cassettes[request.case_id])
        ),
        bare_provider_factory=(
            (lambda _case_id: target_factory())
            if arm == ARM_BARE_PROMPT
            else lambda case_id: ReplayProvider(cassettes[case_id])
        ),
        ruff_executable=None,
        checkpoint_root=root,
    )

    assert target_providers
    assert sum(
        provider.proposal_calls + provider.generator_calls
        for provider in target_providers
    ) > 0
    assert execution.publication_authority is not None
    assert (
        root.with_name(root.name + "-owner")
        / "comparison.final.receipt.json"
    ).is_file()


@pytest.mark.parametrize("arm", (ARM_PRODUCT, ARM_BARE_PROMPT))
@pytest.mark.parametrize(
    "mutation",
    ("unlink", "unlink_recreate_exact", "canonical_drift", "paid_evidence"),
)
def test_paid_factory_authority_tamper_is_rejected_before_dispatch_or_publication(
    tmp_path: Path, arm: str, mutation: str
) -> None:
    """A factory cannot alter its marker or inject paid-call evidence."""
    plans, cassettes, _ = _plans(tmp_path)
    plan = plans[0]
    root = tmp_path / f"marker-{mutation}-{arm}"
    marker = root / "reconciliation" / arm / f"{plan.case.case_id}.json"
    expected_marker = {
        "schema_version": baselines_module.COMPARISON_RECONCILIATION_SCHEMA_VERSION,
        "arm": arm,
        "case_id": plan.case.case_id,
        "trial_id": f"comparison:{arm}:{plan.case.case_id}",
        "status": "running",
    }
    target_providers: list[ReplayProvider] = []

    def target_factory() -> ReplayProvider:
        document = baselines_module.read_canonical_json(
            root, marker.relative_to(root)
        )
        assert document.value == expected_marker
        case_root = root / arm / plan.case.case_id
        assert {path.name for path in case_root.iterdir()} == {"calls", "artifacts"}
        if mutation == "unlink":
            marker.unlink()
        elif mutation == "unlink_recreate_exact":
            original = marker.read_bytes()
            marker.unlink()
            marker.write_bytes(original)
        elif mutation == "canonical_drift":
            marker.write_text(
                json.dumps(
                    {**expected_marker, "status": "settled"},
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n",
                encoding="utf-8",
            )
        else:
            calls = case_root / "calls"
            (calls / "000000.json").write_text("{}\n", encoding="utf-8")
        provider = ReplayProvider(cassettes[plan.case.case_id])
        target_providers.append(provider)
        return provider

    with pytest.raises(ComparisonEvidenceError) as raised:
        compare_arms(
            [plan],
            provider_factory=(
                (lambda _request: target_factory())
                if arm == ARM_PRODUCT
                else lambda request: ReplayProvider(cassettes[request.case_id])
            ),
            bare_provider_factory=(
                (lambda _case_id: target_factory())
                if arm == ARM_BARE_PROMPT
                else lambda case_id: ReplayProvider(cassettes[case_id])
            ),
            ruff_executable=None,
            checkpoint_root=root,
        )

    expected_error = (
        "paid evidence appeared during provider factory"
        if mutation == "paid_evidence"
        else "reconciliation marker changed during provider factory"
    )
    assert str(raised.value) == (
        f"comparison {arm}/{plan.case.case_id} {expected_error}"
    )
    assert target_providers
    assert sum(
        provider.proposal_calls + provider.generator_calls
        for provider in target_providers
    ) == 0
    ordinal = 0 if arm == ARM_PRODUCT else 1
    assert not (
        root
        / "authoritative-outcomes"
        / "comparison-outcomes"
        / f"{ordinal:06d}.json"
    ).exists()
    assert not (
        root.with_name(root.name + "-owner")
        / "comparison.final.receipt.json"
    ).exists()


@pytest.mark.parametrize("arm", (ARM_PRODUCT, ARM_BARE_PROMPT))
@pytest.mark.parametrize(
    "factory_outcome", ("return_after_unlink", "raise_after_unlink", "raise_unchanged")
)
def test_factory_cannot_remove_marker_and_be_retried_as_fresh(
    tmp_path: Path, arm: str, factory_outcome: str
) -> None:
    """Every factory exit leaves an exact marker that makes resume fail closed."""
    plans, cassettes, _ = _plans(tmp_path)
    plan = plans[0]
    root = tmp_path / f"failed-factory-{arm}"
    marker = root / "reconciliation" / arm / f"{plan.case.case_id}.json"
    expected_marker = {
        "schema_version": baselines_module.COMPARISON_RECONCILIATION_SCHEMA_VERSION,
        "arm": arm,
        "case_id": plan.case.case_id,
        "trial_id": f"comparison:{arm}:{plan.case.case_id}",
        "status": "running",
    }
    first_factory_calls = 0

    def attacking_factory() -> ReplayProvider:
        nonlocal first_factory_calls
        first_factory_calls += 1
        document = baselines_module.read_canonical_json(
            root, marker.relative_to(root)
        )
        assert document.value == expected_marker
        if factory_outcome != "raise_unchanged":
            marker.unlink()
        if factory_outcome.startswith("raise"):
            raise RuntimeError("factory failed after removing its marker")
        return ReplayProvider(cassettes[plan.case.case_id])

    def execute() -> ComparisonExecution:
        return compare_arms(
            [plan],
            provider_factory=(
                (lambda _request: attacking_factory())
                if arm == ARM_PRODUCT
                else lambda request: ReplayProvider(cassettes[request.case_id])
            ),
            bare_provider_factory=(
                (lambda _case_id: attacking_factory())
                if arm == ARM_BARE_PROMPT
                else lambda case_id: ReplayProvider(cassettes[case_id])
            ),
            ruff_executable=None,
            checkpoint_root=root,
        )

    if factory_outcome == "raise_unchanged":
        with pytest.raises(RuntimeError, match="factory failed"):
            execute()
    else:
        with pytest.raises(ComparisonEvidenceError) as raised:
            execute()
        assert str(raised.value) == (
            f"comparison {arm}/{plan.case.case_id} reconciliation marker changed "
            f"during {'failed ' if factory_outcome.startswith('raise') else ''}"
            "provider factory"
        )

    assert first_factory_calls == 1
    case_root = root / arm / plan.case.case_id
    assert {path.name for path in case_root.iterdir()} == {"calls", "artifacts"}
    if factory_outcome == "raise_unchanged":
        assert baselines_module.read_canonical_json(
            root, marker.relative_to(root)
        ).value == expected_marker
    else:
        assert not marker.exists()
    ordinal = 0 if arm == ARM_PRODUCT else 1
    outcome = (
        root
        / "authoritative-outcomes"
        / "comparison-outcomes"
        / f"{ordinal:06d}.json"
    )
    final = (
        root.with_name(root.name + "-owner")
        / "comparison.final.receipt.json"
    )
    assert not outcome.exists()
    assert not final.exists()

    resumed_factory_calls = 0

    def forbidden_factory(*_args: object) -> ReplayProvider:
        nonlocal resumed_factory_calls
        resumed_factory_calls += 1
        return ReplayProvider(cassettes[plan.case.case_id])

    with pytest.raises(
        ComparisonEvidenceError,
        match="no reconciliation marker|interrupted reconciliation",
    ):
        compare_arms(
            [plan],
            provider_factory=forbidden_factory,
            bare_provider_factory=forbidden_factory,
            ruff_executable=None,
            checkpoint_root=root,
        )

    assert resumed_factory_calls == 0
    assert not outcome.exists()
    assert not final.exists()


@pytest.mark.parametrize("arm", (ARM_PRODUCT, ARM_BARE_PROMPT))
def test_failed_factory_cannot_redirect_marker_recovery_outside_checkpoint_root(
    tmp_path: Path, arm: str
) -> None:
    """An aliased marker parent is rejected without writing through the alias."""
    plans, cassettes, _ = _plans(tmp_path)
    plan = plans[0]
    root = tmp_path / f"factory-parent-alias-{arm}"
    marker_parent = root / "reconciliation" / arm
    marker = marker_parent / f"{plan.case.case_id}.json"
    outside = tmp_path / f"outside-marker-{arm}"
    outside.mkdir()
    outside_marker = outside / marker.name
    outside_bytes = b"OUTSIDE-SENTINEL\n"
    outside_marker.write_bytes(outside_bytes)
    factory_calls = 0

    def attacking_factory() -> ReplayProvider:
        nonlocal factory_calls
        factory_calls += 1
        assert baselines_module.read_canonical_json(
            root, marker.relative_to(root)
        ).value["status"] == "running"
        marker_parent.rename(marker_parent.with_name(arm + "-original"))
        marker_parent.symlink_to(outside, target_is_directory=True)
        raise RuntimeError("factory failed after aliasing marker parent")

    with pytest.raises(ComparisonEvidenceError) as raised:
        compare_arms(
            [plan],
            provider_factory=(
                (lambda _request: attacking_factory())
                if arm == ARM_PRODUCT
                else lambda request: ReplayProvider(cassettes[request.case_id])
            ),
            bare_provider_factory=(
                (lambda _case_id: attacking_factory())
                if arm == ARM_BARE_PROMPT
                else lambda case_id: ReplayProvider(cassettes[case_id])
            ),
            ruff_executable=None,
            checkpoint_root=root,
        )

    assert factory_calls == 1
    assert outside_marker.read_bytes() == outside_bytes
    assert str(raised.value) == (
        f"comparison {arm}/{plan.case.case_id} reconciliation marker changed "
        "during failed provider factory"
    )
    assert not (
        root.with_name(root.name + "-owner")
        / "comparison.final.receipt.json"
    ).exists()

    resumed_factory_calls = 0

    def forbidden_factory(*_args: object) -> ReplayProvider:
        nonlocal resumed_factory_calls
        resumed_factory_calls += 1
        return ReplayProvider(cassettes[plan.case.case_id])

    with pytest.raises(ComparisonEvidenceError, match="symlink|unsafe"):
        compare_arms(
            [plan],
            provider_factory=forbidden_factory,
            bare_provider_factory=forbidden_factory,
            ruff_executable=None,
            checkpoint_root=root,
        )

    assert resumed_factory_calls == 0
    assert outside_marker.read_bytes() == outside_bytes


@pytest.mark.parametrize("arm", (ARM_PRODUCT, ARM_BARE_PROMPT))
def test_paid_factory_cannot_alias_preconstructed_checkpoint_directories(
    tmp_path: Path, arm: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A paid-root alias is rejected before checkpoint or provider dispatch."""
    plans, cassettes, _ = _plans(tmp_path)
    plan = plans[0]
    root = tmp_path / f"factory-paid-alias-{arm}"
    outside = tmp_path / f"outside-paid-{arm}"
    outside.mkdir()
    sentinel = outside / "sentinel"
    sentinel.write_bytes(b"OUTSIDE-PAID-SENTINEL\n")
    outside_before = {
        str(path.relative_to(outside)): (
            "directory" if path.is_dir() else path.read_bytes()
        )
        for path in sorted(outside.rglob("*"))
    }
    target_providers: list[ReplayProvider] = []
    bound_delegates: list[object] = []
    captured_leases: list[tuple[str, tuple[int, ...], object]] = []
    original_bind = baselines_module._LateBoundComparisonProvider.bind
    original_lease_init = baselines_module._PaidCheckpointDirectoryLease.__init__

    def recording_bind(self: object, delegate: object) -> None:
        bound_delegates.append(delegate)
        original_bind(self, delegate)

    def recording_lease_init(
        self: object, checkpoint_root: Path, *, arm: str, case_id: str
    ) -> None:
        original_lease_init(
            self, checkpoint_root, arm=arm, case_id=case_id
        )
        captured_leases.append((arm, self._descriptors, self))

    monkeypatch.setattr(
        baselines_module._LateBoundComparisonProvider, "bind", recording_bind
    )
    monkeypatch.setattr(
        baselines_module._PaidCheckpointDirectoryLease,
        "__init__",
        recording_lease_init,
    )

    def attacking_factory() -> ReplayProvider:
        marker = root / "reconciliation" / arm / f"{plan.case.case_id}.json"
        assert baselines_module.read_canonical_json(
            root, marker.relative_to(root)
        ).value["status"] == "running"
        case_root = root / arm / plan.case.case_id
        assert {path.name for path in case_root.iterdir()} == {"calls", "artifacts"}
        arm_root = root / arm
        arm_root.rename(root / f"{arm}-original")
        arm_root.symlink_to(outside, target_is_directory=True)
        provider = ReplayProvider(cassettes[plan.case.case_id])
        target_providers.append(provider)
        return provider

    with pytest.raises(ComparisonEvidenceError) as raised:
        compare_arms(
            [plan],
            provider_factory=(
                (lambda _request: attacking_factory())
                if arm == ARM_PRODUCT
                else lambda request: ReplayProvider(cassettes[request.case_id])
            ),
            bare_provider_factory=(
                (lambda _case_id: attacking_factory())
                if arm == ARM_BARE_PROMPT
                else lambda case_id: ReplayProvider(cassettes[case_id])
            ),
            ruff_executable=None,
            checkpoint_root=root,
        )

    assert target_providers
    assert sum(
        provider.proposal_calls + provider.generator_calls
        for provider in target_providers
    ) == 0
    assert all(provider not in bound_delegates for provider in target_providers)
    attacked_leases = [lease for lease in captured_leases if lease[0] == arm]
    assert len(attacked_leases) == 1
    _, initial_descriptors, lease = attacked_leases[0]
    assert len(initial_descriptors) == 5
    assert lease._descriptors == ()
    for descriptor in initial_descriptors:
        with pytest.raises(OSError) as closed:
            os.fstat(descriptor)
        assert closed.value.errno == errno.EBADF
    assert {
        str(path.relative_to(outside)): (
            "directory" if path.is_dir() else path.read_bytes()
        )
        for path in sorted(outside.rglob("*"))
    } == outside_before
    assert str(raised.value) == (
        f"comparison {arm}/{plan.case.case_id} paid checkpoint directory changed "
        "during provider factory"
    )
    ordinal = 0 if arm == ARM_PRODUCT else 1
    assert not (
        root
        / "authoritative-outcomes"
        / "comparison-outcomes"
        / f"{ordinal:06d}.json"
    ).exists()
    assert not (
        root.with_name(root.name + "-owner")
        / "comparison.final.receipt.json"
    ).exists()

    resumed_factory_calls = 0

    def forbidden_factory(*_args: object) -> ReplayProvider:
        nonlocal resumed_factory_calls
        resumed_factory_calls += 1
        return ReplayProvider(cassettes[plan.case.case_id])

    with pytest.raises(ComparisonEvidenceError):
        compare_arms(
            [plan],
            provider_factory=forbidden_factory,
            bare_provider_factory=forbidden_factory,
            ruff_executable=None,
            checkpoint_root=root,
        )

    assert resumed_factory_calls == 0
    assert {
        str(path.relative_to(outside)): (
            "directory" if path.is_dir() else path.read_bytes()
        )
        for path in sorted(outside.rglob("*"))
    } == outside_before
    assert not (
        root
        / "authoritative-outcomes"
        / "comparison-outcomes"
        / f"{ordinal:06d}.json"
    ).exists()
    assert not (
        root.with_name(root.name + "-owner")
        / "comparison.final.receipt.json"
    ).exists()


@pytest.mark.parametrize("arm", (ARM_PRODUCT, ARM_BARE_PROMPT))
@pytest.mark.parametrize("factory_outcome", ("return", "raise"))
@pytest.mark.parametrize("replacement_component", ("arm", "calls", "artifacts"))
def test_paid_checkpoint_directory_identity_rejects_real_replacement(
    tmp_path: Path,
    arm: str,
    factory_outcome: str,
    replacement_component: str,
) -> None:
    """A same-shaped replacement cannot satisfy the held directory identity."""
    root = tmp_path / (
        f"paid-directory-replacement-{arm}-{replacement_component}-{factory_outcome}"
    )
    case_id = "case-paid-directory"

    def replacing_factory() -> _RecordingProvider:
        if replacement_component == "arm":
            arm_root = root / arm
            arm_root.rename(root / f"{arm}-original")
            replacement = arm_root / case_id
            (replacement / "calls").mkdir(parents=True)
            (replacement / "artifacts").mkdir()
        else:
            leaf = root / arm / case_id / replacement_component
            leaf.rename(leaf.with_name(f"{replacement_component}-original"))
            leaf.mkdir()
        if factory_outcome == "raise":
            raise RuntimeError("factory failed after replacing paid directories")
        return _RecordingProvider("{}")

    suffix = "failed provider factory" if factory_outcome == "raise" else "provider factory"
    with pytest.raises(ComparisonEvidenceError) as raised:
        baselines_module._fresh_checkpointed_comparison_provider(
            replacing_factory,
            checkpoint_root=root,
            arm=arm,
            case_id=case_id,
            model_id="claude-sonnet-5",
            binding_sha256="a" * 64,
        )

    assert str(raised.value) == (
        f"comparison {arm}/{case_id} paid checkpoint directory changed during "
        f"{suffix}"
    )


def test_completed_comparison_resume_loads_slots_without_provider_factories(
    tmp_path: Path,
) -> None:
    """A sealed resume reconstructs exact outcomes without constructing providers."""
    plans, cassettes, _ = _plans(tmp_path)
    root = tmp_path / "calls"
    first = compare_arms(
        plans,
        provider_factory=lambda request: ReplayProvider(cassettes[request.case_id]),
        bare_provider_factory=lambda case_id: ReplayProvider(cassettes[case_id]),
        ruff_executable=_ruff_executable(),
        checkpoint_root=root,
        **_comparison_authority(root),
    )

    def product_factory(_request: ProjectEvaluationRequest):
        raise AssertionError("sealed product slot must not construct a provider")

    def bare_factory(_case_id: str):
        raise AssertionError("sealed bare slot must not construct a provider")

    resumed = compare_arms(
        plans,
        provider_factory=product_factory,
        bare_provider_factory=bare_factory,
        ruff_executable=_ruff_executable(),
        checkpoint_root=root,
        **_comparison_authority(root),
    )

    assert resumed == first


def test_bare_outcome_is_durable_before_ruff_and_resume_skips_paid_dispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A crash entering Ruff cannot erase or replay an already-settled bare arm."""
    plans, cassettes, _ = _plans(tmp_path)
    plan = plans[0]
    root = tmp_path / "calls"
    real_ruff_evaluate = RuffBaseline.evaluate

    def crash_before_ruff(self, **kwargs):
        raise KeyboardInterrupt("simulated crash before Ruff")

    monkeypatch.setattr(RuffBaseline, "evaluate", crash_before_ruff)
    with pytest.raises(KeyboardInterrupt, match="before Ruff"):
        compare_arms(
            [plan],
            provider_factory=lambda request: ReplayProvider(cassettes[request.case_id]),
            bare_provider_factory=lambda case_id: ReplayProvider(cassettes[case_id]),
            ruff_executable=_ruff_executable(),
            checkpoint_root=root,
            **_comparison_authority(root),
        )

    bare_slot = (
        root
        / "authoritative-outcomes"
        / "comparison-outcomes"
        / "000001.json"
    )
    assert bare_slot.is_file()

    monkeypatch.setattr(RuffBaseline, "evaluate", real_ruff_evaluate)

    def product_factory(_request: ProjectEvaluationRequest):
        raise AssertionError("durable product slot must skip provider construction")

    def bare_factory(_case_id: str):
        raise AssertionError("durable bare slot must skip provider construction")

    resumed = compare_arms(
        [plan],
        provider_factory=product_factory,
        bare_provider_factory=bare_factory,
        ruff_executable=_ruff_executable(),
        checkpoint_root=root,
        **_comparison_authority(root),
    )

    assert {run.arm for run in resumed.measurements.runs} == {
        ARM_PRODUCT,
        ARM_BARE_PROMPT,
        ARM_RUFF,
    }


def test_product_settlement_before_slot_crash_resumes_without_provider_factory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plans, cassettes, _ = _plans(tmp_path)
    plan = plans[0]
    root = tmp_path / "product-slot-crash"
    real_write = baselines_module.write_comparison_arm_outcome_once

    def crash_before_product_slot(authority, slot, outcome):
        if slot.arm == ARM_PRODUCT:
            raise KeyboardInterrupt("crash after product settlement")
        return real_write(authority, slot, outcome)

    monkeypatch.setattr(
        baselines_module,
        "write_comparison_arm_outcome_once",
        crash_before_product_slot,
    )
    with pytest.raises(KeyboardInterrupt, match="product settlement"):
        compare_arms(
            [plan],
            provider_factory=lambda request: ReplayProvider(
                cassettes[request.case_id]
            ),
            bare_provider_factory=lambda case_id: ReplayProvider(cassettes[case_id]),
            ruff_executable=None,
            checkpoint_root=root,
        )
    costs = root / ARM_PRODUCT / plan.case.case_id / "costs.jsonl"
    before = costs.read_bytes()
    marker = json.loads(
        (root / "reconciliation" / ARM_PRODUCT / f"{plan.case.case_id}.json").read_text(
            encoding="utf-8"
        )
    )
    assert marker["status"] == "settled"

    monkeypatch.setattr(
        baselines_module, "write_comparison_arm_outcome_once", real_write
    )
    resumed = compare_arms(
        [plan],
        provider_factory=lambda request: pytest.fail(
            "settled product recovery must not construct a provider"
        ),
        bare_provider_factory=lambda case_id: ReplayProvider(cassettes[case_id]),
        ruff_executable=None,
        checkpoint_root=root,
    )

    assert costs.read_bytes() == before
    assert next(run for run in resumed.runs if run.arm == ARM_PRODUCT)


def test_bare_settlement_before_slot_crash_resumes_without_any_paid_factory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plans, cassettes, _ = _plans(tmp_path)
    plan = plans[0]
    root = tmp_path / "bare-slot-crash"
    real_write = baselines_module.write_comparison_arm_outcome_once

    def crash_before_bare_slot(authority, slot, outcome):
        if slot.arm == ARM_BARE_PROMPT:
            raise KeyboardInterrupt("crash after bare settlement")
        return real_write(authority, slot, outcome)

    monkeypatch.setattr(
        baselines_module,
        "write_comparison_arm_outcome_once",
        crash_before_bare_slot,
    )
    with pytest.raises(KeyboardInterrupt, match="bare settlement"):
        compare_arms(
            [plan],
            provider_factory=lambda request: ReplayProvider(
                cassettes[request.case_id]
            ),
            bare_provider_factory=lambda case_id: ReplayProvider(cassettes[case_id]),
            ruff_executable=None,
            checkpoint_root=root,
        )
    product_costs = root / ARM_PRODUCT / plan.case.case_id / "costs.jsonl"
    bare_costs = root / ARM_BARE_PROMPT / plan.case.case_id / "costs.jsonl"
    before = (product_costs.read_bytes(), bare_costs.read_bytes())

    monkeypatch.setattr(
        baselines_module, "write_comparison_arm_outcome_once", real_write
    )
    resumed = compare_arms(
        [plan],
        provider_factory=lambda request: pytest.fail(
            "present product slot must not construct a provider"
        ),
        bare_provider_factory=lambda case_id: pytest.fail(
            "settled bare recovery must not construct a provider"
        ),
        ruff_executable=None,
        checkpoint_root=root,
    )

    assert (product_costs.read_bytes(), bare_costs.read_bytes()) == before
    assert {run.arm for run in resumed.runs} == {
        ARM_PRODUCT,
        ARM_BARE_PROMPT,
        ARM_RUFF,
    }


def test_comparison_post_response_failure_preserves_paid_evidence_and_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plans, cassettes, _ = _plans(tmp_path)
    plan = plans[0]

    def fail_after_response(
        request: ProjectEvaluationRequest,
        *,
        provider: object,
        oracle_provider: object,
        clock: object,
    ) -> object:
        provider.sample("system", "prompt", {"type": "object"}, 20)
        raise RuntimeError("failure after response before a trusted outcome")

    monkeypatch.setattr(
        "attest.benchmark.baselines.evaluate_project", fail_after_response
    )
    root = tmp_path / "calls"
    with pytest.raises(RuntimeError, match="trusted outcome"):
        compare_arms(
            [plan],
            provider_factory=lambda request: ReplayProvider(
                cassettes[request.case_id]
            ),
            bare_provider_factory=lambda case_id: ReplayProvider(cassettes[case_id]),
            ruff_executable=None,
            checkpoint_root=root,
        )
    costs = root / ARM_PRODUCT / plan.case.case_id / "costs.jsonl"
    rows = [json.loads(line) for line in costs.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1
    assert rows[0]["cost_usd"] > 0
    assert not (
        root.with_name(root.name + "-owner")
        / "comparison.final.receipt.json"
    ).exists()
    assert not (
        root
        / "authoritative-outcomes"
        / "comparison-outcomes"
        / "000000.json"
    ).exists()


def test_bare_post_response_failure_cannot_seal_false_terminal_outcomes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plans, cassettes, _ = _plans(tmp_path)
    plan = plans[0]
    root = tmp_path / "bare-post-response-failure"
    original_evaluate = BarePromptBaseline.evaluate

    def crash_after_bare_response(
        self: BarePromptBaseline,
        *,
        case_id: str,
        role: str,
        diff: Any,
        config: ReviewConfig,
    ) -> object:
        completed = original_evaluate(
            self,
            case_id=case_id,
            role=role,
            diff=diff,
            config=config,
        )
        assert completed.model_calls == 1
        raise RuntimeError("bare failure after a durable response")

    monkeypatch.setattr(
        BarePromptBaseline,
        "evaluate",
        crash_after_bare_response,
    )
    with pytest.raises(RuntimeError, match="durable response"):
        compare_arms(
            [plan],
            provider_factory=lambda request: ReplayProvider(
                cassettes[request.case_id]
            ),
            bare_provider_factory=lambda case_id: ReplayProvider(cassettes[case_id]),
            ruff_executable=None,
            checkpoint_root=root,
        )

    bare_costs = root / ARM_BARE_PROMPT / plan.case.case_id / "costs.jsonl"
    rows = [
        json.loads(line)
        for line in bare_costs.read_text(encoding="utf-8").splitlines()
    ]
    assert len(rows) == 1
    assert rows[0]["cost_usd"] > 0
    outcomes = root / "authoritative-outcomes" / "comparison-outcomes"
    assert not (outcomes / "000001.json").exists()
    assert not (outcomes / "000002.json").exists()
    assert not (
        root.with_name(root.name + "-owner")
        / "comparison.final.receipt.json"
    ).exists()


def test_fresh_materialization_failure_does_not_write_unreconciled_baseline_slots(
    tmp_path: Path,
) -> None:
    plans, cassettes, _ = _plans(tmp_path)
    plan = plans[0]
    root = tmp_path / "fresh-materialization-failure"
    destination = (
        plan.request.workspace_root / f"{plan.request.case_id}-baseline-arms"
    )
    destination.mkdir(parents=True)

    with pytest.raises(ValueError, match="baseline worktree.*already exists"):
        compare_arms(
            [plan],
            provider_factory=lambda request: ReplayProvider(
                cassettes[request.case_id]
            ),
            bare_provider_factory=lambda _case_id: pytest.fail(
                "materialization failure must precede bare provider construction"
            ),
            ruff_executable=None,
            checkpoint_root=root,
        )

    outcomes = root / "authoritative-outcomes" / "comparison-outcomes"
    assert not (outcomes / "000001.json").exists()
    assert not (outcomes / "000002.json").exists()
    assert not (
        root.with_name(root.name + "-owner")
        / "comparison.final.receipt.json"
    ).exists()


def test_materialization_failure_cannot_replace_settled_bare_recovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plans, cassettes, _ = _plans(tmp_path)
    plan = plans[0]
    root = tmp_path / "recovery-materialization-failure"
    real_write = baselines_module.write_comparison_arm_outcome_once

    def crash_before_bare_slot(authority, slot, outcome):
        if slot.arm == ARM_BARE_PROMPT:
            raise KeyboardInterrupt("crash after bare settlement")
        return real_write(authority, slot, outcome)

    monkeypatch.setattr(
        baselines_module,
        "write_comparison_arm_outcome_once",
        crash_before_bare_slot,
    )
    with pytest.raises(KeyboardInterrupt, match="bare settlement"):
        compare_arms(
            [plan],
            provider_factory=lambda request: ReplayProvider(
                cassettes[request.case_id]
            ),
            bare_provider_factory=lambda case_id: ReplayProvider(cassettes[case_id]),
            ruff_executable=None,
            checkpoint_root=root,
        )
    bare_costs = root / ARM_BARE_PROMPT / plan.case.case_id / "costs.jsonl"
    bare_reconciliation = (
        root / "reconciliation" / ARM_BARE_PROMPT / f"{plan.case.case_id}.json"
    )
    before = (bare_costs.read_bytes(), bare_reconciliation.read_bytes())

    monkeypatch.setattr(
        baselines_module,
        "write_comparison_arm_outcome_once",
        real_write,
    )
    destination = (
        plan.request.workspace_root / f"{plan.request.case_id}-baseline-arms"
    )
    destination.mkdir(parents=True)
    with pytest.raises(ValueError, match="baseline worktree.*already exists"):
        compare_arms(
            [plan],
            provider_factory=lambda _request: pytest.fail(
                "durable product slot must skip provider construction"
            ),
            bare_provider_factory=lambda _case_id: pytest.fail(
                "settled bare recovery must skip provider construction"
            ),
            ruff_executable=None,
            checkpoint_root=root,
        )

    assert (bare_costs.read_bytes(), bare_reconciliation.read_bytes()) == before
    outcomes = root / "authoritative-outcomes" / "comparison-outcomes"
    assert not (outcomes / "000001.json").exists()
    assert not (outcomes / "000002.json").exists()
    assert not (
        root.with_name(root.name + "-owner")
        / "comparison.final.receipt.json"
    ).exists()


def test_comparison_refuses_orphan_paid_root_before_external_final(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plans, cassettes, _ = _plans(tmp_path)
    plan = plans[0]
    root = tmp_path / "orphan-paid-root"
    real_write = baselines_module.write_comparison_arm_outcome_once

    def inject_orphan_after_last_slot(authority, slot, outcome):
        written = real_write(authority, slot, outcome)
        if slot.arm == ARM_RUFF:
            (root / ARM_PRODUCT / "orphan-case" / "calls").mkdir(parents=True)
            (root / ARM_PRODUCT / "orphan-case" / "artifacts").mkdir()
        return written

    monkeypatch.setattr(
        baselines_module,
        "write_comparison_arm_outcome_once",
        inject_orphan_after_last_slot,
    )
    with pytest.raises(ComparisonEvidenceError, match="paid-call roots do not match"):
        compare_arms(
            [plan],
            provider_factory=lambda request: ReplayProvider(
                cassettes[request.case_id]
            ),
            bare_provider_factory=lambda case_id: ReplayProvider(cassettes[case_id]),
            ruff_executable=None,
            checkpoint_root=root,
        )

    assert not (
        root.with_name(root.name + "-owner")
        / "comparison.final.receipt.json"
    ).exists()


def test_comparison_refuses_orphan_reconciliation_before_external_final(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plans, cassettes, _ = _plans(tmp_path)
    plan = plans[0]
    root = tmp_path / "orphan-reconciliation"
    real_write = baselines_module.write_comparison_arm_outcome_once

    def inject_orphan_after_last_slot(authority, slot, outcome):
        written = real_write(authority, slot, outcome)
        if slot.arm == ARM_RUFF:
            orphan = root / "reconciliation" / ARM_PRODUCT / "orphan-case.json"
            orphan.parent.mkdir(parents=True, exist_ok=True)
            orphan.write_text("{}\n", encoding="utf-8")
        return written

    monkeypatch.setattr(
        baselines_module,
        "write_comparison_arm_outcome_once",
        inject_orphan_after_last_slot,
    )
    with pytest.raises(
        ComparisonEvidenceError, match="reconciliation markers do not match"
    ):
        compare_arms(
            [plan],
            provider_factory=lambda request: ReplayProvider(
                cassettes[request.case_id]
            ),
            bare_provider_factory=lambda case_id: ReplayProvider(cassettes[case_id]),
            ruff_executable=None,
            checkpoint_root=root,
        )

    assert not (
        root.with_name(root.name + "-owner")
        / "comparison.final.receipt.json"
    ).exists()


def test_comparison_does_not_recreate_a_missing_zero_call_paid_root_before_final(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plans, cassettes, _ = _plans(tmp_path)
    original = plans[0]
    plan = replace(
        original,
        request=replace(
            original.request,
            config=replace(original.request.config, budget_usd=1e-9),
        ),
    )
    root = tmp_path / "missing-zero-call-root"
    real_write = baselines_module.write_comparison_arm_outcome_once

    def delete_paid_root_after_last_slot(authority, slot, outcome):
        written = real_write(authority, slot, outcome)
        if slot.arm == ARM_RUFF:
            marker = json.loads(
                (
                    root
                    / "reconciliation"
                    / ARM_BARE_PROMPT
                    / f"{plan.case.case_id}.json"
                ).read_text(encoding="utf-8")
            )
            assert marker["status"] == "settled"
            assert marker["call_count"] == 0
            shutil.rmtree(root / ARM_BARE_PROMPT / plan.case.case_id)
        return written

    monkeypatch.setattr(
        baselines_module,
        "write_comparison_arm_outcome_once",
        delete_paid_root_after_last_slot,
    )
    with pytest.raises(ComparisonEvidenceError, match="paid-call roots do not match"):
        compare_arms(
            [plan],
            provider_factory=lambda request: ReplayProvider(
                cassettes[request.case_id]
            ),
            bare_provider_factory=lambda case_id: ReplayProvider(cassettes[case_id]),
            ruff_executable=None,
            checkpoint_root=root,
        )

    assert not (root / ARM_BARE_PROMPT / plan.case.case_id).exists()
    assert not (
        root.with_name(root.name + "-owner")
        / "comparison.final.receipt.json"
    ).exists()


def test_zero_call_settlement_recovery_refuses_a_missing_paid_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plans, cassettes, _ = _plans(tmp_path)
    original = plans[0]
    plan = replace(
        original,
        request=replace(
            original.request,
            config=replace(original.request.config, budget_usd=1e-9),
        ),
    )
    root = tmp_path / "missing-zero-call-recovery-root"
    real_write = baselines_module.write_comparison_arm_outcome_once

    def crash_before_bare_slot(authority, slot, outcome):
        if slot.arm == ARM_BARE_PROMPT:
            raise KeyboardInterrupt("crash after zero-call bare settlement")
        return real_write(authority, slot, outcome)

    monkeypatch.setattr(
        baselines_module,
        "write_comparison_arm_outcome_once",
        crash_before_bare_slot,
    )
    with pytest.raises(KeyboardInterrupt, match="zero-call bare settlement"):
        compare_arms(
            [plan],
            provider_factory=lambda request: ReplayProvider(
                cassettes[request.case_id]
            ),
            bare_provider_factory=lambda case_id: ReplayProvider(cassettes[case_id]),
            ruff_executable=None,
            checkpoint_root=root,
        )

    marker_path = (
        root / "reconciliation" / ARM_BARE_PROMPT / f"{plan.case.case_id}.json"
    )
    marker = json.loads(marker_path.read_text(encoding="utf-8"))
    assert marker["status"] == "settled"
    assert marker["call_count"] == 0
    paid_root = root / ARM_BARE_PROMPT / plan.case.case_id
    shutil.rmtree(paid_root)
    monkeypatch.setattr(
        baselines_module,
        "write_comparison_arm_outcome_once",
        real_write,
    )

    with pytest.raises(ComparisonEvidenceError, match="paid case root is missing"):
        compare_arms(
            [plan],
            provider_factory=lambda _request: pytest.fail(
                "durable product slot must skip provider construction"
            ),
            bare_provider_factory=lambda _case_id: pytest.fail(
                "settled bare recovery must not construct a provider"
            ),
            ruff_executable=None,
            checkpoint_root=root,
        )

    assert not paid_root.exists()
    outcomes = root / "authoritative-outcomes" / "comparison-outcomes"
    assert not (outcomes / "000001.json").exists()
    assert not (outcomes / "000002.json").exists()
    assert not (
        root.with_name(root.name + "-owner")
        / "comparison.final.receipt.json"
    ).exists()


def test_comparison_propagates_post_execution_authority_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plans, cassettes, _ = _plans(tmp_path)
    plan = plans[0]
    root = tmp_path / "authority-failure"

    def fail_authority_after_response(
        request: ProjectEvaluationRequest,
        *,
        provider: object,
        oracle_provider: object,
        clock: object,
    ) -> object:
        provider.sample("system", "prompt", {"type": "object"}, 20)
        raise ProjectEvaluationAuthorityError("fresh publication authority failed")

    monkeypatch.setattr(
        "attest.benchmark.baselines.evaluate_project",
        fail_authority_after_response,
    )
    with pytest.raises(
        ProjectEvaluationAuthorityError, match="publication authority"
    ):
        compare_arms(
            [plan],
            provider_factory=lambda request: ReplayProvider(
                cassettes[request.case_id]
            ),
            bare_provider_factory=lambda case_id: ReplayProvider(cassettes[case_id]),
            ruff_executable=None,
            checkpoint_root=root,
        )

    assert not (
        root.with_name(root.name + "-owner")
        / "comparison.final.receipt.json"
    ).exists()
    assert not (
        root
        / "authoritative-outcomes"
        / "comparison-outcomes"
        / "000000.json"
    ).exists()


def test_comparison_post_publication_failure_fails_closed_without_empty_outcome(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plans, cassettes, _ = _plans(tmp_path)
    plan = plans[0]
    root = tmp_path / "post-publication-failure"

    published_results: list[ProjectEvaluationResult] = []

    def crash_after_publication(
        request: ProjectEvaluationRequest,
        *,
        provider: object,
        oracle_provider: object,
        clock: object,
    ) -> ProjectEvaluationResult:
        result = real_evaluate_project(
            request,
            provider=provider,
            oracle_provider=oracle_provider,
            clock=clock,
        )
        assert result.predictions
        published_results.append(result)
        raise RuntimeError("crash after visible publication")

    monkeypatch.setattr(
        "attest.benchmark.baselines.evaluate_project", crash_after_publication
    )
    with pytest.raises(RuntimeError, match="visible publication"):
        compare_arms(
            [plan],
            provider_factory=lambda request: ReplayProvider(
                cassettes[request.case_id]
            ),
            bare_provider_factory=lambda case_id: ReplayProvider(cassettes[case_id]),
            ruff_executable=None,
            checkpoint_root=root,
        )

    assert published_results
    assert published_results[0].predictions
    assert not (
        root.with_name(root.name + "-owner")
        / "comparison.final.receipt.json"
    ).exists()
    assert not (
        root
        / "authoritative-outcomes"
        / "comparison-outcomes"
        / "000000.json"
    ).exists()


def test_interrupted_unsettled_comparison_resume_rejects_before_factory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plans, cassettes, _ = _plans(tmp_path)
    plan = plans[0]
    checkpoint_root = tmp_path / "calls"

    def one_response_then_fail(
        request: ProjectEvaluationRequest,
        *,
        provider: object,
        oracle_provider: object,
        clock: object,
    ) -> object:
        provider.sample("system", "prompt", {"type": "object"}, 20)
        raise RuntimeError("settle one call")

    monkeypatch.setattr(
        "attest.benchmark.baselines.evaluate_project", one_response_then_fail
    )
    with pytest.raises(RuntimeError, match="settle one call"):
        compare_arms(
            [plan],
            provider_factory=lambda request: ReplayProvider(
                cassettes[request.case_id]
            ),
            bare_provider_factory=lambda case_id: ReplayProvider(cassettes[case_id]),
            ruff_executable=None,
            checkpoint_root=checkpoint_root,
        )
    costs = checkpoint_root / ARM_PRODUCT / plan.case.case_id / "costs.jsonl"
    settled_costs = costs.read_bytes()

    with pytest.raises(ValueError, match="not safe|reconciliation|interrupted"):
        compare_arms(
            [plan],
            provider_factory=lambda request: pytest.fail(
                "unsettled resume must not construct product provider"
            ),
            bare_provider_factory=lambda case_id: pytest.fail(
                "unsettled resume must not construct bare provider"
            ),
            ruff_executable=None,
            checkpoint_root=checkpoint_root,
        )
    assert costs.read_bytes() == settled_costs


def test_comparison_failed_after_settled_oracle_response_preserves_oracle_spend(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plans, cassettes, _ = _plans(tmp_path)
    plan = plans[0]

    def fail_after_oracle_response(
        request: ProjectEvaluationRequest,
        *,
        provider: object,
        oracle_provider: object,
        clock: object,
    ) -> object:
        oracle_provider.sample("oracle", "prompt", {"type": "object"}, 20)
        raise RuntimeError("failure after oracle settlement before publication")

    monkeypatch.setattr(
        "attest.benchmark.baselines.evaluate_project", fail_after_oracle_response
    )
    root = tmp_path / "oracle-calls"
    with pytest.raises(RuntimeError, match="oracle settlement"):
        compare_arms(
            [plan],
            provider_factory=lambda request: ReplayProvider(
                cassettes[request.case_id]
            ),
            bare_provider_factory=lambda case_id: ReplayProvider(cassettes[case_id]),
            ruff_executable=None,
            checkpoint_root=root,
        )

    costs = root / ARM_PRODUCT / plan.case.case_id / "costs.jsonl"
    rows = [json.loads(line) for line in costs.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1
    assert rows[0]["role"] == CALL_ROLE_BENCHMARK_ORACLE
    assert rows[0]["cost_usd"] > 0
    assert not (
        root.with_name(root.name + "-owner")
        / "comparison.final.receipt.json"
    ).exists()
    assert not (
        root
        / "authoritative-outcomes"
        / "comparison-outcomes"
        / "000000.json"
    ).exists()


def test_comparison_report_rejects_oracle_spend_field_tampering(
    tmp_path: Path,
) -> None:
    plans, cassettes, manifest_path = _plans(tmp_path)
    measurements = compare_arms(
        [plans[0]],
        provider_factory=lambda request: ReplayProvider(cassettes[request.case_id]),
        bare_provider_factory=lambda case_id: ReplayProvider(cassettes[case_id]),
        ruff_executable=None,
        checkpoint_root=tmp_path / "tamper-calls",
    )
    tampered = _replace_execution_measurements(
        measurements,
        runs=tuple(
            replace(run, oracle_spend_usd=run.oracle_spend_usd + 1.0)
            if run.arm == ARM_PRODUCT
            else run
            for run in measurements.runs
        ),
    )

    with pytest.raises(ValueError, match="oracle|spend|reconciliation|authoritative"):
        build_comparison_report(
            load_manifest(manifest_path),
            tampered,
            manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            validation_receipt=None,
        )


def test_comparison_report_rejects_coordinated_role_reclassification(
    tmp_path: Path,
) -> None:
    plans, cassettes, manifest_path = _plans(tmp_path)
    measurements = compare_arms(
        [plans[0]],
        provider_factory=lambda request: ReplayProvider(cassettes[request.case_id]),
        bare_provider_factory=lambda case_id: ReplayProvider(cassettes[case_id]),
        ruff_executable=None,
        checkpoint_root=tmp_path / "role-tamper-calls",
    )
    product = next(run for run in measurements.runs if run.arm == ARM_PRODUCT)
    rewritten = [dict(row) for row in product.paid_calls]
    rewritten[0]["role"] = CALL_ROLE_BENCHMARK_ORACLE
    product_spend = sum(
        float(row["cost_usd"])
        for row in rewritten
        if row["role"] == CALL_ROLE_PRODUCT
    )
    oracle_spend = sum(
        float(row["cost_usd"])
        for row in rewritten
        if row["role"] == CALL_ROLE_BENCHMARK_ORACLE
    )
    digest = hashlib.sha256(
        json.dumps(rewritten, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    tampered_product = replace(
        product,
        paid_calls=tuple(rewritten),
        paid_calls_sha256=digest,
        spend_usd=product_spend,
        oracle_spend_usd=oracle_spend,
    )
    tampered = _replace_execution_measurements(
        measurements,
        runs=tuple(
            tampered_product if run is product else run
            for run in measurements.runs
        ),
    )

    with pytest.raises(ValueError, match="role|summary|authoritative|reconciliation"):
        build_comparison_report(
            load_manifest(manifest_path),
            tampered,
            manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            validation_receipt=None,
        )


def test_comparison_report_rejects_fabricated_ruff_paid_calls(
    tmp_path: Path,
) -> None:
    plans, cassettes, manifest_path = _plans(tmp_path)
    measurements = compare_arms(
        [plans[0]],
        provider_factory=lambda request: ReplayProvider(cassettes[request.case_id]),
        bare_provider_factory=lambda case_id: ReplayProvider(cassettes[case_id]),
        ruff_executable=None,
        checkpoint_root=tmp_path / "ruff-paid-calls",
    )
    ruff = next(run for run in measurements.runs if run.arm == ARM_RUFF)
    trial_id = f"comparison:{ARM_RUFF}:{ruff.case_id}"
    fabricated = (
        {
            "trial_id": trial_id,
            "call_id": f"{trial_id}:0",
            "ordinal": 0,
            "role": CALL_ROLE_PRODUCT,
            "cost_usd": 0.0004,
        },
    )
    digest = hashlib.sha256(
        json.dumps(fabricated, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    tampered_ruff = replace(
        ruff,
        model_calls=1,
        input_tokens=1,
        output_tokens=1,
        spend_usd=0.0004,
        paid_calls=fabricated,
        paid_calls_sha256=digest,
    )
    runs = tuple(
        tampered_ruff if run is ruff else run for run in measurements.runs
    )
    tampered = _replace_execution_measurements(
        measurements,
        runs=runs,
        arms=tuple(
            _summarize_arm(arm, tuple(run for run in runs if run.arm == arm))
            for arm in (ARM_PRODUCT, ARM_BARE_PROMPT, ARM_RUFF)
        ),
    )

    with pytest.raises(ValueError, match="ruff|paid|provider|reconciliation"):
        build_comparison_report(
            load_manifest(manifest_path),
            tampered,
            manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            validation_receipt=None,
        )


def test_comparison_report_rechecks_authoritative_artifacts_at_publication(
    tmp_path: Path,
) -> None:
    plans, cassettes, manifest_path = _plans(tmp_path)
    plan = plans[0]
    checkpoint_root = tmp_path / "calls"

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
    tmp_path: Path,
) -> None:
    plans, cassettes, manifest_path = _plans(tmp_path)
    plan = plans[0]

    measurements = compare_arms(
        [plan],
        provider_factory=lambda request: ReplayProvider(cassettes[request.case_id]),
        bare_provider_factory=lambda case_id: ReplayProvider(cassettes[case_id]),
        ruff_executable=None,
        checkpoint_root=tmp_path / "calls",
    )
    tampered = _replace_execution_measurements(
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
    tmp_path: Path,
) -> None:
    plans, cassettes, manifest_path = _plans(tmp_path)
    plan = plans[0]

    measurements = compare_arms(
        [plan],
        provider_factory=lambda request: ReplayProvider(cassettes[request.case_id]),
        bare_provider_factory=lambda case_id: ReplayProvider(cassettes[case_id]),
        ruff_executable=None,
        checkpoint_root=tmp_path / "calls",
    )
    omitted = _replace_execution_measurements(
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
            _replace_execution_measurements(measurements, evaluated_case_ids=()),
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
            _replace_execution_measurements(
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
        manifest=load_manifest(manifest_path),
        manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
    )
    assert any(
        (measurements.measurements.checkpoint_root or tmp_path).rglob("*.json")
    )

    with pytest.raises(
        ValueError, match="checkpoint|authoritative|authority|paid|evidence"
    ):
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
    tampered = _replace_execution_measurements(
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


def test_comparison_report_rejects_coordinated_model_identity_rewrite(
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
    declaration["bindings"][0]["binding"]["model_id"] = "claude-opus-5"
    for row in declaration["paid_trials"]:
        row["model_id"] = "claude-opus-5"
    declaration_path.write_text(json.dumps(declaration) + "\n", encoding="utf-8")
    tampered = _replace_execution_measurements(
        measurements,
        runs=tuple(
            replace(run, model_id="claude-opus-5")
            if run.arm != ARM_RUFF
            else run
            for run in measurements.runs
        ),
    )

    with pytest.raises(
        ValueError,
        match="binding|model|checkpoint|evidence|authority|reconciliation|predeclaration",
    ):
        build_comparison_report(
            load_manifest(manifest_path),
            tampered,
            manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            validation_receipt=None,
        )


def test_comparison_report_rejects_orphan_paid_call_roots(
    tmp_path: Path,
) -> None:
    plans, cassettes, manifest_path = _plans(tmp_path)
    checkpoint_root = tmp_path / "calls"
    original_execution = compare_arms(
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
    empty_execution = compare_arms(
        [],
        provider_factory=lambda request: ReplayProvider(cassettes[request.case_id]),
        bare_provider_factory=lambda case_id: ReplayProvider(cassettes[case_id]),
        ruff_executable=None,
        checkpoint_root=None,
        manifest=load_manifest(manifest_path),
        manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
    )
    erased = ComparisonExecution(
        measurements=replace(
            empty_execution.measurements, checkpoint_root=checkpoint_root
        ),
        publication_authority=original_execution.publication_authority,
    )

    with pytest.raises(
        ValueError, match="orphan|checkpoint|binding|paid|evidence|predeclaration"
    ):
        build_comparison_report(
            load_manifest(manifest_path),
            erased,
            manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            validation_receipt=None,
        )


def test_comparison_report_rejects_predeclared_empty_plan_without_authority(
    tmp_path: Path,
) -> None:
    _, _, manifest_path = _plans(tmp_path)
    measurements = compare_arms(
        [],
        provider_factory=lambda request: pytest.fail("empty plan dispatched product"),
        bare_provider_factory=lambda case_id: pytest.fail("empty plan dispatched bare"),
        ruff_executable=None,
        checkpoint_root=tmp_path / "empty-calls",
        manifest=load_manifest(manifest_path),
        manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
    )

    with pytest.raises(
        ComparisonEvidenceError,
        match="external final authority|not-executed diagnostic",
    ):
        build_comparison_report(
            load_manifest(manifest_path),
            measurements,
            manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            validation_receipt=None,
        )


def test_comparison_execution_rejects_a_measurement_subclass() -> None:
    class ForgedMeasurements(ComparisonMeasurements):
        pass

    forged = ForgedMeasurements(
        line_slack=0,
        budget_ceiling_usd=0.0,
        manifest_sha256="a" * 64,
        arms=(),
        runs=(),
        evaluated_case_ids=(),
    )

    with pytest.raises(ValueError, match="exact ComparisonMeasurements"):
        ComparisonExecution(measurements=forged, publication_authority=None)


def test_comparison_publication_rejects_symlinked_paid_checkpoint_descendant(
    tmp_path: Path,
) -> None:
    plans, cassettes, manifest_path = _plans(tmp_path)
    root = tmp_path / "calls"
    execution = compare_arms(
        [plans[0]],
        provider_factory=lambda request: ReplayProvider(cassettes[request.case_id]),
        bare_provider_factory=lambda case_id: ReplayProvider(cassettes[case_id]),
        ruff_executable=None,
        checkpoint_root=root,
    )
    calls = root / ARM_PRODUCT / plans[0].case.case_id / "calls"
    moved = calls.with_name("calls-original")
    calls.rename(moved)
    calls.symlink_to(moved, target_is_directory=True)

    with pytest.raises(
        ComparisonEvidenceError,
        match="symlink|unsafe|paid-call checkpoint",
    ):
        build_comparison_report(
            load_manifest(manifest_path),
            execution,
            manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            validation_receipt=None,
        )


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

    real_write = baselines_module.write_comparison_arm_outcome_once

    def crash_before_product_slot(authority, slot, outcome):
        if slot.arm == ARM_PRODUCT:
            raise KeyboardInterrupt("crash after settled product reconciliation")
        return real_write(authority, slot, outcome)

    monkeypatch.setattr(
        baselines_module,
        "write_comparison_arm_outcome_once",
        crash_before_product_slot,
    )
    with pytest.raises(KeyboardInterrupt, match="settled product"):
        compare_arms(
            [plan],
            provider_factory=lambda request: ReplayProvider(
                cassettes[request.case_id]
            ),
            bare_provider_factory=lambda case_id: ReplayProvider(cassettes[case_id]),
            ruff_executable=None,
            checkpoint_root=checkpoint_root,
        )
    monkeypatch.setattr(
        baselines_module, "write_comparison_arm_outcome_once", real_write
    )

    product_root = checkpoint_root / ARM_PRODUCT / plan.case.case_id
    reconciliation = checkpoint_root / "reconciliation" / ARM_PRODUCT / f"{plan.case.case_id}.json"
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
        lines = spend.read_text(encoding="utf-8").splitlines()
        row = json.loads(lines[0])
        row["trial_id"] = "comparison:wrong-trial"
        spend.write_text(
            "\n".join((json.dumps(row), *lines[1:])) + "\n",
            encoding="utf-8",
        )
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


def test_comparison_authoritative_partial_defer_retains_visible_findings_in_accuracy(
) -> None:
    measurement = _measurement_record(
        stop="candidate_defer",
        findings=(
            _finding("correct", defect_id="defect-1"),
            _finding("wrong", accuracy="wrong", defect_id=None),
            _finding(
                "unresolved",
                status="unresolved",
                accuracy="unadjudicated",
                defect_id=None,
            ),
        ),
        eligible_defect_ids=("defect-1", "defect-2"),
    )
    run = baselines_module.ArmRun(
        arm=ARM_PRODUCT,
        case_id=measurement.case_id,
        role="historical_bug_replay",
        status="partially_deferred",
        abstain_reason="one candidate remained unresolved",
        findings=(
            baselines_module.BaselineFinding(
                file="app.py", line=1, evidence_class="regression_reproduced", finding_id="correct"
            ),
            baselines_module.BaselineFinding(
                file="app.py", line=2, evidence_class="regression_reproduced", finding_id="wrong"
            ),
        ),
        matched_defect_ids=("defect-1", None),
        model_calls=1,
        input_tokens=1,
        output_tokens=1,
        spend_usd=0.0,
        oracle_spend_usd=0.0,
        wall_time_s=1.0,
        tool_cost_s=None,
        product_measurement=measurement,
    )

    summary = _summarize_arm(ARM_PRODUCT, (run,))

    assert summary.scoring_semantics == "mixed_outcome_v3"
    assert summary.accuracy.finding_true_positives == 1
    assert summary.accuracy.finding_false_positives == 1
    assert summary.accuracy.finding_precision == pytest.approx(0.5)
    assert summary.accuracy.detected_positive_cases == 1
    assert summary.accuracy.decided_positive_cases == 1
    assert summary.operational.evaluated_cases == 1
    assert summary.operational.deferred_cases == 1
    assert summary.operational.surfaced_findings == 2
    assert summary.outcome_accounting["unresolved"] == 1
    assert summary.outcome_accounting["missed_defects"] == 1


def test_product_run_matches_are_an_exact_measurement_projection() -> None:
    wrong = _measurement_record(
        findings=(_finding("finding-1", accuracy="wrong", defect_id=None),)
    )
    findings = (
        baselines_module.BaselineFinding(
            file="matching-location.py",
            line=1,
            evidence_class="regression_reproduced",
            finding_id="finding-1",
        ),
    )

    assert baselines_module._product_measurement_matches(findings, wrong) == (None,)
    with pytest.raises(ValueError, match="exact.*finding_id|finding_id.*exact"):
        baselines_module._product_measurement_matches(
            (replace(findings[0], finding_id="injected"),), wrong
        )


@pytest.mark.parametrize(
    ("truth", "role", "stop", "status", "with_completed", "deferred", "failures"),
    (
        ("null", "developer_fix_control", "task_defer", "fully_deferred", False, 1, 0),
        ("positive", "historical_bug_replay", "task_defer", "fully_deferred", True, 1, 0),
        ("positive", "historical_bug_replay", "failure", "failed", True, 0, 1),
    ),
)
def test_comparison_authoritative_noncompleted_cases_never_become_silence(
    truth: str,
    role: str,
    stop: str,
    status: str,
    with_completed: bool,
    deferred: int,
    failures: int,
) -> None:
    noncompleted = _measurement_record(
        stop=stop,
        findings=(),
        eligible_defect_ids=(() if truth == "null" else ("defect-1",)),
        truth_status=truth,
    )
    run = baselines_module.ArmRun(
        arm=ARM_PRODUCT,
        case_id=noncompleted.case_id,
        role=role,
        status=status,
        abstain_reason=("task deferred" if deferred else "task failed"),
        findings=(),
        matched_defect_ids=(),
        model_calls=1,
        input_tokens=1,
        output_tokens=1,
        spend_usd=0.0,
        oracle_spend_usd=0.0,
        wall_time_s=1.0,
        tool_cost_s=None,
        product_measurement=noncompleted,
    )
    completed = replace(
        _measurement_record(eligible_defect_ids=(), truth_status="null"),
        case_id="completed-control",
    )
    runs = (run,)
    if with_completed:
        runs = (
            replace(
                run,
                case_id=completed.case_id,
                role="developer_fix_control",
                status="completed",
                abstain_reason=None,
                product_measurement=completed,
            ),
            run,
        )
    summary = _summarize_arm(ARM_PRODUCT, runs)

    assert summary.operational.evaluated_cases == 1 + with_completed
    assert summary.operational.deferred_cases == deferred
    assert summary.operational.silent_cases == int(with_completed)
    assert summary.operational.silence_rate == (
        pytest.approx(1.0) if with_completed else None
    )
    assert summary.accuracy.silent_control_cases == int(with_completed)
    assert summary.accuracy.silent_positive_cases == 0
    assert summary.accuracy.silence_precision == (
        pytest.approx(1.0) if with_completed else None
    )
    assert summary.outcome_accounting["task_status_counts"][status] == 1
    assert summary.outcome_accounting["failures"] == failures
    assert len(summary.abstentions) == deferred


def _receipt_artifacts(
    tmp_path: Path,
    manifest: Path,
    *,
    name: str = "validation",
    historical_note: str | None = None,
) -> tuple[Path, Path]:
    document = json.loads(manifest.read_text(encoding="utf-8"))
    pair_ids = sorted({case["pair_id"] for case in document["cases"]})
    manifest_sha256 = hashlib.sha256(manifest.read_bytes()).hexdigest()
    results = {
        "schema_version": "1",
        "manifest_sha256": manifest_sha256,
        "results": [
            {
                "pair_id": pair_id,
                "status": "validated",
                **(
                    {"historical_note": historical_note}
                    if historical_note is not None
                    else {}
                ),
            }
            for pair_id in pair_ids
        ],
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
    receipt_path = tmp_path / f"{name}-receipt.json"
    results_path = tmp_path / f"{name}-results.json"
    results_path.write_bytes(results_bytes)
    receipt_path.write_bytes(
        (json.dumps(receipt, sort_keys=True, separators=(",", ":")) + "\n").encode()
    )
    return receipt_path, results_path


def _two_historical_receipts(
    tmp_path: Path, manifest_path: Path
) -> tuple[ValidationReceipt, ValidationReceipt]:
    receipt_a_path, results_a_path = _receipt_artifacts(
        tmp_path, manifest_path, name="historical-a"
    )
    receipt_b_path, results_b_path = _receipt_artifacts(
        tmp_path,
        manifest_path,
        name="historical-b",
        historical_note="distinct-but-nonauthoritative-v1-evidence",
    )
    return (
        load_validation_receipt(receipt_a_path, manifest_path, results_a_path),
        load_validation_receipt(receipt_b_path, manifest_path, results_b_path),
    )


def test_comparison_report_rejects_historical_receipt_a_to_b_swap(
    tmp_path: Path,
) -> None:
    """Typed V1 execution still freezes the exact historical receipt bytes."""
    plans, cassettes, manifest_path = _plans(tmp_path)
    manifest = load_manifest(manifest_path)
    receipt_a, receipt_b = _two_historical_receipts(tmp_path, manifest_path)
    assert validation_receipt_binding_bytes(receipt_a) != validation_receipt_binding_bytes(
        receipt_b
    )
    measurements = compare_arms(
        plans,
        provider_factory=lambda request: ReplayProvider(cassettes[request.case_id]),
        bare_provider_factory=lambda case_id: ReplayProvider(cassettes[case_id]),
        ruff_executable=None,
        checkpoint_root=tmp_path / "historical-a-report-calls",
        validation_receipt=receipt_a,
    )

    with pytest.raises(ValueError, match="receipt.*(binding|predeclaration)"):
        build_comparison_report(
            manifest,
            measurements,
            manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            validation_receipt=receipt_b,
        )


def test_comparison_resume_rejects_historical_receipt_a_to_b_without_mutation(
    tmp_path: Path,
) -> None:
    """A V1 binding swap is rejected before provider construction on resume."""
    plans, cassettes, manifest_path = _plans(tmp_path)
    receipt_a, receipt_b = _two_historical_receipts(tmp_path, manifest_path)
    checkpoint_root = tmp_path / "historical-a-resume-calls"
    compare_arms(
        plans,
        provider_factory=lambda request: ReplayProvider(cassettes[request.case_id]),
        bare_provider_factory=lambda case_id: ReplayProvider(cassettes[case_id]),
        ruff_executable=None,
        checkpoint_root=checkpoint_root,
        validation_receipt=receipt_a,
    )
    before = {
        str(path.relative_to(checkpoint_root)): path.read_bytes()
        for path in sorted(checkpoint_root.rglob("*"))
        if path.is_file()
    }
    provider_calls: list[str] = []

    with pytest.raises(ValueError, match="predeclaration|drift"):
        compare_arms(
            plans,
            provider_factory=lambda request: (
                provider_calls.append(f"product:{request.case_id}")
                or ReplayProvider(cassettes[request.case_id])
            ),
            bare_provider_factory=lambda case_id: (
                provider_calls.append(f"bare:{case_id}")
                or ReplayProvider(cassettes[case_id])
            ),
            ruff_executable=None,
            checkpoint_root=checkpoint_root,
            validation_receipt=receipt_b,
        )
    assert provider_calls == []
    assert {
        str(path.relative_to(checkpoint_root)): path.read_bytes()
        for path in sorted(checkpoint_root.rglob("*"))
        if path.is_file()
    } == before


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
    historical_measurements = compare_arms(
        plans,
        provider_factory=lambda request: ReplayProvider(cassettes[request.case_id]),
        bare_provider_factory=lambda case_id: ReplayProvider(cassettes[case_id]),
        ruff_executable=_ruff_executable(),
        checkpoint_root=tmp_path / "comparison-historical-receipt-calls",
        validation_receipt=receipt,
    )
    historical = build_comparison_report(
        manifest,
        historical_measurements,
        manifest_sha256=manifest_sha256,
        validation_receipt=receipt,
    )
    assert historical.metrics_withheld_reason == RECEIPT_HISTORICAL
    expected_receipt_sha256 = hashlib.sha256(
        validation_receipt_binding_bytes(receipt)
    ).hexdigest()
    assert historical_measurements.checkpoint_root is not None
    predeclaration = json.loads(
        (historical_measurements.checkpoint_root / "comparison.json").read_text(
            encoding="utf-8"
        )
    )
    expected_predeclaration_sha256 = hashlib.sha256(
        json.dumps(predeclaration, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    assert historical.receipt_sha256 == expected_receipt_sha256
    assert historical.predeclaration_sha256 == expected_predeclaration_sha256
    assert predeclaration["receipt_sha256"] == expected_receipt_sha256
    assert {row["binding"]["receipt_sha256"] for row in predeclaration["bindings"]} == {
        expected_receipt_sha256
    }
    frozen_by_case = {
        row["case_id"]: row["binding"] for row in predeclaration["bindings"]
    }
    for plan in plans:
        frozen = frozen_by_case[plan.case.case_id]
        assert frozen["base_sha"] == plan.request.base_ref
        assert frozen["head_sha"] == plan.request.head_ref
        assert frozen["truth_sha256"] == project_truth_sha256(plan.request.truth)

    authority = verified_validation_authority(
        tmp_path / "comparison-validation-authority", manifest_path
    )
    current_root = tmp_path / "comparison-current-authority-calls"
    with pytest.raises(ValueError, match="X-01|public-key|symmetric"):
        compare_arms(
            plans,
            provider_factory=lambda request: ReplayProvider(cassettes[request.case_id]),
            bare_provider_factory=lambda case_id: ReplayProvider(cassettes[case_id]),
            ruff_executable=_ruff_executable(),
            checkpoint_root=current_root,
            validation_receipt=authority,
        )
    assert not current_root.exists()

    markdown = render_comparison_markdown(historical)
    assert ARM_PRODUCT in markdown
    assert ARM_BARE_PROMPT in markdown
    assert ARM_RUFF in markdown
    assert "not an AI reviewer" in markdown
    assert f"receipt SHA-256: `{expected_receipt_sha256}`" in markdown
    assert (
        f"predeclaration SHA-256: `{expected_predeclaration_sha256}`" in markdown
    )
    notes = " ".join(historical.limitations)
    assert "losing" in notes or "every arm" in notes
    assert "repeat zero" in notes


def test_comparison_report_rejects_authority_added_after_absent_predeclaration(
    tmp_path: Path,
) -> None:
    """A report cannot attach scoring authority after comparison outcomes exist."""
    plans, cassettes, manifest_path = _plans(tmp_path)
    manifest = load_manifest(manifest_path)
    measurements = compare_arms(
        plans,
        provider_factory=lambda request: ReplayProvider(cassettes[request.case_id]),
        bare_provider_factory=lambda case_id: ReplayProvider(cassettes[case_id]),
        ruff_executable=_ruff_executable(),
        checkpoint_root=tmp_path / "absent-authority-calls",
    )
    authority = verified_validation_authority(tmp_path / "absent-authority", manifest_path)

    with pytest.raises(ValueError, match="receipt.*(binding|predeclaration)"):
        build_comparison_report(
            manifest,
            measurements,
            manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            validation_receipt=authority,
        )


def test_comparison_resume_rejects_current_authority_before_provider_and_preserves_state(
    tmp_path: Path,
) -> None:
    """A current verifier capability cannot touch historical execution state."""
    plans, cassettes, manifest_path = _plans(tmp_path)
    receipt_path, results_path = _receipt_artifacts(tmp_path, manifest_path)
    historical = load_validation_receipt(receipt_path, manifest_path, results_path)
    checkpoint_root = tmp_path / "receipt-resume-calls"
    compare_arms(
        plans,
        provider_factory=lambda request: ReplayProvider(cassettes[request.case_id]),
        bare_provider_factory=lambda case_id: ReplayProvider(cassettes[case_id]),
        ruff_executable=_ruff_executable(),
        checkpoint_root=checkpoint_root,
        validation_receipt=historical,
    )
    before = {
        str(artifact_file.relative_to(checkpoint_root)): artifact_file.read_bytes()
        for artifact_file in sorted(checkpoint_root.rglob("*"))
        if artifact_file.is_file()
    }
    provider_calls: list[str] = []
    authority = verified_validation_authority(
        tmp_path / "resume-current-authority", manifest_path
    )

    with pytest.raises(ValueError, match="X-01|public-key|symmetric"):
        compare_arms(
            plans,
            provider_factory=lambda request: (
                provider_calls.append(f"product:{request.case_id}")
                or ReplayProvider(cassettes[request.case_id])
            ),
            bare_provider_factory=lambda case_id: (
                provider_calls.append(f"bare:{case_id}") or ReplayProvider(cassettes[case_id])
            ),
            ruff_executable=_ruff_executable(),
            checkpoint_root=checkpoint_root,
            validation_receipt=authority,
        )
    assert provider_calls == []
    assert {
        str(artifact_file.relative_to(checkpoint_root)): artifact_file.read_bytes()
        for artifact_file in sorted(checkpoint_root.rglob("*"))
        if artifact_file.is_file()
    } == before


def test_comparison_report_rejects_coordinated_manifest_role_rewrite(
    tmp_path: Path,
) -> None:
    """Run roles and recomputed summaries remain subordinate to manifest roles."""
    plans, cassettes, manifest_path = _plans(tmp_path)
    manifest = load_manifest(manifest_path)
    measurements = compare_arms(
        plans,
        provider_factory=lambda request: ReplayProvider(cassettes[request.case_id]),
        bare_provider_factory=lambda case_id: ReplayProvider(cassettes[case_id]),
        ruff_executable=_ruff_executable(),
        checkpoint_root=tmp_path / "role-rewrite-calls",
    )
    rewritten_runs = tuple(
        replace(
            run,
            role=(
                "developer_fix_control"
                if run.role == "historical_bug_replay"
                else "historical_bug_replay"
            ),
        )
        for run in measurements.runs
    )
    rewritten = _replace_execution_measurements(
        measurements,
        runs=rewritten_runs,
        arms=tuple(
            _summarize_arm(
                arm,
                tuple(run for run in rewritten_runs if run.arm == arm),
            )
            for arm in (ARM_PRODUCT, ARM_BARE_PROMPT, ARM_RUFF)
        ),
    )

    with pytest.raises(ValueError, match="role.*manifest"):
        build_comparison_report(
            manifest,
            rewritten,
            manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            validation_receipt=None,
        )


def test_comparison_report_rejects_role_subclass_equality_bypass(
    tmp_path: Path,
) -> None:
    """A caller-defined role cannot override its exact manifest join."""

    class DeceptiveRole(str):
        def __eq__(self, other: object) -> bool:
            return True

        def __ne__(self, other: object) -> bool:
            return False

    plans, cassettes, manifest_path = _plans(tmp_path)
    manifest = load_manifest(manifest_path)
    measurements = compare_arms(
        plans,
        provider_factory=lambda request: ReplayProvider(cassettes[request.case_id]),
        bare_provider_factory=lambda case_id: ReplayProvider(cassettes[case_id]),
        ruff_executable=_ruff_executable(),
        checkpoint_root=tmp_path / "role-subclass-calls",
    )
    original = measurements.runs[0]
    deceptive_role = DeceptiveRole(
        "developer_fix_control"
        if original.role == "historical_bug_replay"
        else "historical_bug_replay"
    )
    rewritten_runs = (replace(original, role=deceptive_role), *measurements.runs[1:])
    rewritten = _replace_execution_measurements(
        measurements,
        runs=rewritten_runs,
        arms=tuple(
            _summarize_arm(
                arm,
                tuple(run for run in rewritten_runs if run.arm == arm),
            )
            for arm in (ARM_PRODUCT, ARM_BARE_PROMPT, ARM_RUFF)
        ),
    )

    with pytest.raises(ValueError, match="role.*(exact|manifest)"):
        build_comparison_report(
            manifest,
            rewritten,
            manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            validation_receipt=None,
        )


def test_comparison_report_rejects_coordinated_match_and_summary_rewrite(
    tmp_path: Path,
) -> None:
    """Publication replays matching from manifest truth instead of trusting aggregates."""
    plans, cassettes, manifest_path = _plans(tmp_path)
    manifest = load_manifest(manifest_path)
    measurements = compare_arms(
        plans,
        provider_factory=lambda request: ReplayProvider(cassettes[request.case_id]),
        bare_provider_factory=lambda case_id: ReplayProvider(cassettes[case_id]),
        ruff_executable=_ruff_executable(),
        checkpoint_root=tmp_path / "truth-rewrite-calls",
    )
    rewritten_runs = tuple(
        replace(run, matched_defect_ids=(None,) * len(run.findings))
        for run in measurements.runs
    )
    rewritten = _replace_execution_measurements(
        measurements,
        runs=rewritten_runs,
        arms=tuple(
            _summarize_arm(
                arm,
                tuple(run for run in rewritten_runs if run.arm == arm),
            )
            for arm in (ARM_PRODUCT, ARM_BARE_PROMPT, ARM_RUFF)
        ),
    )

    with pytest.raises(ValueError, match="truth|match|summary"):
        build_comparison_report(
            manifest,
            rewritten,
            manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            validation_receipt=None,
        )


def test_comparison_checkpoint_v6_is_retained_and_rejected_without_replay(
    tmp_path: Path,
) -> None:
    """The v7 outcome authority must never rewrite accepted v6 paid state."""
    assert COMPARISON_CHECKPOINT_SCHEMA_VERSION == "7"
    plans, cassettes, _ = _plans(tmp_path)
    checkpoint_root = tmp_path / "legacy-v6-comparison"
    checkpoint_root.mkdir()
    legacy_path = checkpoint_root / "comparison.json"
    legacy_path.write_text(
        json.dumps({"schema_version": "6"}, sort_keys=True, separators=(",", ":"))
        + "\n",
        encoding="utf-8",
    )
    before = legacy_path.read_bytes()
    provider_calls: list[str] = []

    with pytest.raises(ValueError, match="version.*7|supported.*7|predeclaration"):
        compare_arms(
            plans,
            provider_factory=lambda request: (
                provider_calls.append(request.case_id) or ReplayProvider(cassettes[request.case_id])
            ),
            bare_provider_factory=lambda case_id: ReplayProvider(cassettes[case_id]),
            ruff_executable=_ruff_executable(),
            checkpoint_root=checkpoint_root,
        )
    assert provider_calls == []
    assert legacy_path.read_bytes() == before
    assert tuple(path.name for path in checkpoint_root.iterdir()) == ("comparison.json",)


def test_compare_cli_runs_three_arms_offline_end_to_end(tmp_path: Path) -> None:
    """The CLI mode uses recorded cassettes and a local ruff executable only,
    and refuses accuracy when given only a historical v1 receipt."""
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

    assert completed.returncode == 3, completed.stderr
    summary = json.loads(completed.stdout)
    assert summary["status"] == "not_executed"
    assert summary["offline"] is True
    assert summary["arms"] == 3
    assert summary["evaluated_cases"] == 0
    assert summary["metrics_status"] == "withheld"
    assert summary["metrics_withheld_reason"] == (
        "comparison_not_executed_no_publication_authority"
    )
    assert summary["report"] is None
    assert summary["report_markdown"] is None
    assert not (output / "comparison.json").exists()
    assert not (output / "comparison.md").exists()
    state_root = output / "state" / "comparison-calls"
    predeclaration = json.loads(
        (state_root / "comparison.json").read_text(encoding="utf-8")
    )
    assert predeclaration["bindings"] == []
    assert predeclaration["paid_trials"] == []
    assert not (state_root / "reconciliation").exists()
    assert not (state_root / ARM_PRODUCT).exists()
    assert not (state_root / ARM_BARE_PROMPT).exists()

    no_root_output = tmp_path / "no-root-out"
    no_root = subprocess.run(
        [
            sys.executable,
            str(_SCRIPT),
            "compare",
            "--manifest",
            str(manifest_path),
            "--cassette-root",
            str(cassettes_dir),
            "--output",
            str(no_root_output),
            "--ruff-executable",
            _ruff_executable(),
        ],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )
    assert no_root.returncode == 3, no_root.stderr
    assert json.loads(no_root.stdout)["status"] == "not_executed"
    no_root_state = no_root_output / "state" / "comparison-calls"
    no_root_predeclaration = json.loads(
        (no_root_state / "comparison.json").read_text(encoding="utf-8")
    )
    assert no_root_predeclaration["bindings"] == []
    assert no_root_predeclaration["paid_trials"] == []
    assert not (no_root_state / "reconciliation").exists()


def test_compare_cli_rejects_v2_hmac_authority_before_offline_execution(
    tmp_path: Path,
) -> None:
    """Local checkout execution cannot share the V2 symmetric verification key."""
    manifest_path, root, replay_id, control_id = _comparison_fixture(tmp_path)
    cassettes_dir = tmp_path / "v2-cassettes"
    cassettes_dir.mkdir()
    (cassettes_dir / f"{replay_id}.json").write_text(
        json.dumps(
            {
                "proposal": _PROPOSAL,
                "repro": _REPRO,
                "input_tokens": 800,
                "output_tokens": 200,
            }
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
    bundle = build_validation_v2_bundle(tmp_path / "compare-v2-authority", manifest_path, root)
    key_file = tmp_path / "compare-authority.key"
    key_file.write_bytes(KEY)
    output = tmp_path / "compare-v2-out"

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
            str(bundle.receipt_path),
            "--validation-results",
            str(bundle.results_path),
            "--validation-artifacts",
            str(bundle.artifact_root),
            "--validation-provenance-key-id",
            KEY_ID,
            "--validation-provenance-key-file",
            str(key_file),
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
    )

    assert completed.returncode == 2
    assert "X-01" in json.loads(completed.stderr)["error"]
    assert not output.exists()
    assert KEY not in (completed.stdout + completed.stderr).encode()
