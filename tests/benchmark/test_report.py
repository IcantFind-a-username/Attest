"""Reports are deterministic and state what they cannot claim."""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from attest.benchmark.corpus import (
    ValidationAuthorityCheck,
    ValidationProvenanceEnvelope,
    ValidationReceipt,
    ValidationReceiptV2,
    ValidationVerification,
)
from attest.benchmark.report import (
    LIVE_MODE,
    REPLAY_MODE,
    ReportAbstention,
    ReportExclusion,
    build_report,
    render_markdown,
    write_report,
)
from attest.benchmark.schema import (
    BenchmarkCase,
    BenchmarkManifest,
    ChangedLocation,
    PatchDescriptor,
    Placement,
    Prediction,
    RunRecord,
    TestDescriptor,
    TruthDefect,
    load_manifest,
)

from ._validation_v2 import verified_validation_authority

REPLAY_CASE = "case-aaaaaaaaaaaa"
CONTROL_CASE = "case-bbbbbbbbbbbb"
UNRUN_CASE = "case-cccccccccccc"
UNRUN_CONTROL = "case-dddddddddddd"
MANIFEST_SHA = "e" * 64
_TEST_BYTES = b"{python} -m pytest -q test_calc.py\n"
_DEFAULT_AUTHORITY = object()


def _historical_receipt(manifest_sha256: str = MANIFEST_SHA) -> ValidationReceipt:
    """A frozen v1 receipt has inspectable integrity but no current authority."""
    return ValidationReceipt(
        schema_version="1",
        manifest_sha256=manifest_sha256,
        validated_pair_ids=("pair-111111111111", "pair-222222222222"),
        validation_results_sha256="a" * 64,
    )


def _verified_receipt(manifest_sha256: str = MANIFEST_SHA) -> ValidationVerification:
    """A report consumes the separated result of offline v2 verification."""
    accepted = ValidationAuthorityCheck(True)
    receipt = ValidationReceiptV2(
        schema_version="2",
        protocol_version="attest-validation-v2",
        manifest_sha256=manifest_sha256,
        validated_pair_ids=("pair-111111111111", "pair-222222222222"),
        validation_results_sha256="a" * 64,
        artifact_manifest_sha256="b" * 64,
        provenance_envelope=ValidationProvenanceEnvelope(
            envelope_version="1",
            algorithm="hmac-sha256",
            key_id="local-test-authority",
            payload_sha256="c" * 64,
            authentication_tag="d" * 64,
        ),
    )
    return ValidationVerification(
        integrity=accepted,
        provenance=accepted,
        semantic_policy=accepted,
        _authority="current_scoring_authority",
        receipt=receipt,
    )


def _case(case_id: str, pair_id: str, role: str) -> BenchmarkCase:
    return BenchmarkCase(
        case_id=case_id,
        pair_id=pair_id,
        source_id="source-111111111111",
        role=role,
        provenance_kind="historical_fix",
        source_license="MIT",
        buggy_commit="a" * 40,
        fixed_commit="b" * 40,
        patch=PatchDescriptor("artifacts/fix.patch", "c" * 64, "unified_diff"),
        tests=TestDescriptor(
            "artifacts/test.argv",
            hashlib.sha256(_TEST_BYTES).hexdigest(),
            "normalized_text",
        ),
        changed_locations=(ChangedLocation("app.py", 1, 2),),
        split="test",
    )


def _manifest() -> BenchmarkManifest:
    return BenchmarkManifest(
        schema_version="1",
        protocol_version="1",
        corpus_commit="f" * 40,
        cases=(
            _case(REPLAY_CASE, "pair-111111111111", "historical_bug_replay"),
            _case(CONTROL_CASE, "pair-111111111111", "developer_fix_control"),
            _case(UNRUN_CASE, "pair-222222222222", "historical_bug_replay"),
            _case(UNRUN_CONTROL, "pair-222222222222", "developer_fix_control"),
        ),
        truth_defects=(
            TruthDefect("defect-1", REPLAY_CASE, "app.py", 1, 2),
            TruthDefect("defect-2", UNRUN_CASE, "app.py", 1, 2),
        ),
    )


def _prediction(
    finding_id: str,
    line: int,
    *,
    repro_status: str,
    evidence_class: str,
    case_id: str = REPLAY_CASE,
) -> Prediction:
    return Prediction(
        finding_id=finding_id,
        case_id=case_id,
        file="app.py",
        line=line,
        placement=Placement.INLINE,
        action="surface",
        repro_status=repro_status,
        evidence_class=evidence_class,
    )


def _runs() -> tuple[RunRecord, ...]:
    return (
        RunRecord(
            run_id="run-1",
            case_id=REPLAY_CASE,
            repeat=0,
            predictions=(
                _prediction(
                    "f-hit",
                    2,
                    repro_status="buggy_fail_fixed_pass",
                    evidence_class="regression_reproduced",
                ),
                _prediction(
                    "f-new",
                    40,
                    repro_status="new_code_candidate",
                    evidence_class="new_code_candidate",
                ),
            ),
            delivery_at_s=12.0,
            deadline_s=60.0,
        ),
        RunRecord(
            run_id="run-2",
            case_id=CONTROL_CASE,
            repeat=0,
            predictions=(),
            delivery_at_s=9.0,
            deadline_s=60.0,
        ),
        RunRecord(
            run_id="run-1-repeat",
            case_id=REPLAY_CASE,
            repeat=1,
            predictions=(),
            delivery_at_s=11.0,
            deadline_s=60.0,
        ),
    )


_VALID_RECEIPT: ValidationVerification = _verified_receipt()
_BOUND_MANIFEST: BenchmarkManifest = _manifest()


def _write_report_manifest(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "corpus"
    (root / "artifacts").mkdir(parents=True)
    (root / "artifacts/test.argv").write_bytes(_TEST_BYTES)
    manifest = _manifest()
    document = {
        "schema_version": "1",
        "protocol_version": "1",
        "corpus_commit": "f" * 64,
        "cases": [
            {
                "case_id": case.case_id,
                "pair_id": case.pair_id,
                "source_id": case.source_id,
                "role": case.role,
                "provenance_kind": case.provenance_kind,
                "source_license": case.source_license,
                "buggy_commit": case.buggy_commit,
                "fixed_commit": case.fixed_commit,
                "patch": {
                    "relative_path": case.patch.relative_path,
                    "sha256": case.patch.sha256,
                    "normalization": case.patch.normalization,
                },
                "tests": {
                    "relative_path": case.tests.relative_path,
                    "sha256": case.tests.sha256,
                    "normalization": case.tests.normalization,
                },
                "changed_locations": [
                    {
                        "path": location.path,
                        "start_line": location.start_line,
                        "end_line": location.end_line,
                        "side": location.side,
                    }
                    for location in case.changed_locations
                ],
                "split": case.split,
            }
            for case in manifest.cases
        ],
        "truth_defects": [
            {
                "defect_id": defect.defect_id,
                "case_id": defect.case_id,
                "file": defect.file,
                "start_line": defect.start_line,
                "end_line": defect.end_line,
            }
            for defect in manifest.truth_defects
        ],
        "runtime": [
            {
                "case_id": case.case_id,
                "cwd": f"{case.source_id}/{case.pair_id}/"
                + ("replay" if case.role == "historical_bug_replay" else "control"),
                "command": {
                    "tool": "python",
                    "args": ["-m", "pytest", "-q", "test_calc.py"],
                },
            }
            for case in manifest.cases
        ],
    }
    path = tmp_path / "report-manifest.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path, root


@pytest.fixture(autouse=True)
def _install_verified_default_authority(tmp_path: Path):
    global MANIFEST_SHA, _BOUND_MANIFEST, _VALID_RECEIPT
    original_sha = MANIFEST_SHA
    original_manifest = _BOUND_MANIFEST
    original_receipt = _VALID_RECEIPT
    manifest_path, root = _write_report_manifest(tmp_path)
    MANIFEST_SHA = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    _BOUND_MANIFEST = load_manifest(manifest_path)
    _VALID_RECEIPT = verified_validation_authority(
        tmp_path / "report-authority", manifest_path, root
    )
    assert _VALID_RECEIPT.authority == "current_scoring_authority"
    yield
    MANIFEST_SHA = original_sha
    _BOUND_MANIFEST = original_manifest
    _VALID_RECEIPT = original_receipt


def _report(
    mode: str = REPLAY_MODE,
    *,
    validation_receipt: (
        ValidationVerification | ValidationReceipt | None | object
    ) = _DEFAULT_AUTHORITY,
    runs: tuple[RunRecord, ...] | None = None,
    abstentions: tuple[ReportAbstention, ...] = (),
    manifest_sha256: str | None = None,
):
    authority = _VALID_RECEIPT if validation_receipt is _DEFAULT_AUTHORITY else validation_receipt
    return build_report(
        _BOUND_MANIFEST,
        _runs() if runs is None else runs,
        mode=mode,
        manifest_sha256=manifest_sha256 or MANIFEST_SHA,
        exclusions=(
            ReportExclusion(UNRUN_CASE, "prepared_environment_required"),
            ReportExclusion(UNRUN_CONTROL, "prepared_environment_required"),
        ),
        abstentions=abstentions,
        differential_repeats=3,
        validation_receipt=authority,  # type: ignore[arg-type]
    )


def test_report_scores_only_evaluated_cases_and_never_hides_exclusions() -> None:
    """An unevaluated case is an exclusion, never a silent negative."""
    report = _report()

    assert report.evaluated_cases == 2
    assert [exclusion.case_id for exclusion in report.excluded_cases] == [
        UNRUN_CASE,
        UNRUN_CONTROL,
    ]
    assert report.metrics is not None
    assert report.metrics.true_positives == 1
    assert report.metrics.false_negatives == 0
    assert report.metrics.true_negatives == 1
    assert report.metrics.finding_true_positives == 1
    assert report.metrics.finding_false_positives == 1


@pytest.mark.parametrize("mutation", ["truth", "role", "commit", "runtime", "descriptor"])
def test_current_authority_rejects_typed_manifest_detached_from_bound_bytes(
    tmp_path: Path, mutation: str
) -> None:
    """A receipt for manifest A cannot score any altered typed manifest B."""
    manifest_path, root = _write_report_manifest(tmp_path / "detached-manifest")
    manifest = load_manifest(manifest_path)
    authority = verified_validation_authority(
        tmp_path / "detached-manifest-authority", manifest_path, root
    )
    if mutation == "truth":
        altered = replace(
            manifest,
            truth_defects=tuple(
                replace(defect, file="different.py", start_line=999, end_line=999)
                for defect in manifest.truth_defects
            ),
        )
    elif mutation == "role":
        altered = replace(
            manifest,
            cases=(
                replace(manifest.cases[0], role="developer_fix_control"),
                *manifest.cases[1:],
            ),
        )
    elif mutation == "commit":
        altered = replace(
            manifest,
            cases=(
                replace(manifest.cases[0], buggy_commit="9" * 40),
                *manifest.cases[1:],
            ),
        )
    elif mutation == "runtime":
        altered = replace(
            manifest,
            runtime=(replace(manifest.runtime[0], cwd="different/root"), *manifest.runtime[1:]),
        )
    else:
        altered_case = replace(
            manifest.cases[0],
            patch=replace(manifest.cases[0].patch, sha256="9" * 64),
        )
        altered = replace(manifest, cases=(altered_case, *manifest.cases[1:]))

    with pytest.raises(ValueError, match="manifest.*(bytes|digest|binding)"):
        build_report(
            altered,
            _runs(),
            mode=REPLAY_MODE,
            manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            validation_receipt=authority,
        )


def test_current_authority_hard_rejects_a_different_exact_manifest(
    tmp_path: Path,
) -> None:
    """A's verified capability cannot be downgraded to withholding while scoring B."""
    manifest_a_path, root = _write_report_manifest(tmp_path / "manifest-a")
    authority_a = verified_validation_authority(
        tmp_path / "manifest-a-authority", manifest_a_path, root
    )
    document_b = json.loads(manifest_a_path.read_text(encoding="utf-8"))
    document_b["truth_defects"][0]["file"] = "different.py"
    manifest_b_path = tmp_path / "manifest-b.json"
    manifest_b_path.write_text(json.dumps(document_b), encoding="utf-8")
    manifest_b = load_manifest(manifest_b_path)

    with pytest.raises(ValueError, match="current.*manifest.*digest"):
        build_report(
            manifest_b,
            _runs(),
            mode=REPLAY_MODE,
            manifest_sha256=hashlib.sha256(manifest_b_path.read_bytes()).hexdigest(),
            validation_receipt=authority_a,
        )


def test_current_authority_rejects_digest_subclass_equality_bypass(
    tmp_path: Path,
) -> None:
    """Python equality overrides cannot join authority A to exact manifest B."""

    class DeceptiveDigest(str):
        def __eq__(self, other: object) -> bool:
            return True

        def __ne__(self, other: object) -> bool:
            return False

    manifest_a_path, root = _write_report_manifest(tmp_path / "digest-a")
    authority_a = verified_validation_authority(
        tmp_path / "digest-a-authority", manifest_a_path, root
    )
    document_b = json.loads(manifest_a_path.read_text(encoding="utf-8"))
    document_b["truth_defects"][0]["file"] = "attacker-selected.py"
    manifest_b_path = tmp_path / "digest-b.json"
    manifest_b_path.write_text(json.dumps(document_b), encoding="utf-8")
    manifest_b = load_manifest(manifest_b_path)
    deceptive_digest = DeceptiveDigest(
        hashlib.sha256(manifest_b_path.read_bytes()).hexdigest()
    )

    with pytest.raises(ValueError, match="manifest.*digest.*exact|string"):
        build_report(
            manifest_b,
            _runs(),
            mode=REPLAY_MODE,
            manifest_sha256=deceptive_digest,
            validation_receipt=authority_a,
        )


def test_current_authority_rejects_nested_truth_subclass_equality_bypass(
    tmp_path: Path,
) -> None:
    """A nested record cannot lie about equality while changing scoring truth."""

    class DeceptiveTruth(TruthDefect):
        def __eq__(self, other: object) -> bool:
            return True

        def __ne__(self, other: object) -> bool:
            return False

    manifest_path, root = _write_report_manifest(tmp_path / "nested-truth")
    manifest = load_manifest(manifest_path)
    authority = verified_validation_authority(
        tmp_path / "nested-truth-authority", manifest_path, root
    )
    original = manifest.truth_defects[0]
    deceptive = DeceptiveTruth(
        defect_id=original.defect_id,
        case_id=original.case_id,
        file="attacker-selected.py",
        start_line=999,
        end_line=999,
    )
    altered = replace(
        manifest,
        truth_defects=(deceptive, *manifest.truth_defects[1:]),
    )

    with pytest.raises(ValueError, match="manifest.*(canonical|typed|bytes)"):
        build_report(
            altered,
            _runs(),
            mode=REPLAY_MODE,
            manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            validation_receipt=authority,
        )


def test_headline_rates_carry_wilson_intervals() -> None:
    report = _report()

    assert report.metrics is not None
    assert report.metrics.all_positive_detection_interval is not None
    assert report.metrics.finding_precision_interval is not None
    assert report.metrics.clean_false_positive_rate_interval is not None
    payload = report.to_json_dict()
    assert payload["metrics"]["finding_precision_interval"] == [
        round(value, 6) for value in report.metrics.finding_precision_interval
    ]


def test_evidence_classes_are_broken_out_and_the_unpriced_class_is_named() -> None:
    """A new-code candidate is unpriced signal, not a failure; the report says so."""
    report = _report()

    assert report.evidence_class_counts == {
        "new_code_candidate": 1,
        "regression_reproduced": 1,
    }
    limitations = " ".join(report.limitations)
    assert "new_code_candidate" in limitations
    assert "unpriced" in limitations
    markdown = render_markdown(report)
    assert "new_code_candidate" in markdown
    assert "| regression_reproduced | 1 |" in markdown


def test_replay_and_live_modes_are_described_differently() -> None:
    replay = " ".join(_report(REPLAY_MODE).limitations)
    live = " ".join(_report(LIVE_MODE).limitations)

    assert "replay regression" in replay
    assert "live" not in replay.split("replay regression")[0]
    assert "live observation" in live
    assert "replay regression" not in live


def test_report_states_provenance_repeats_and_exclusions() -> None:
    report = _report()
    markdown = render_markdown(report)

    assert MANIFEST_SHA in markdown
    assert "f" * 40 in markdown
    assert "prepared_environment_required" in markdown
    assert "repeat zero" in " ".join(report.limitations)
    assert report.repeats == 2
    assert report.differential_repeats == 3
    assert "differential repeats per side: 3" in markdown


def test_report_withholds_accuracy_without_a_receipt_but_still_reports_operations() -> None:
    """D-019 makes the receipt the thing that authorises scoring at all.

    Latency, spend, and counts claim no correctness, so they survive the
    refusal; precision and recall do not.
    """
    report = _report(validation_receipt=None)
    payload = report.to_json_dict()

    assert report.metrics is None
    assert payload["metrics"] is None
    assert report.metrics_withheld_reason == "validation_receipt_missing"
    assert payload["metrics_withheld_reason"] == "validation_receipt_missing"
    operational = payload["operational"]
    assert operational["delivery_rate"] == 1.0
    assert operational["delivery_p50_s"] == 9.0
    assert operational["deadline_censored"] == 0
    assert operational["decided_cases"] == 2
    assert report.evaluated_cases == 2
    limitations = " ".join(report.limitations)
    assert "validation receipt" in limitations
    assert "D-019" in limitations
    markdown = render_markdown(report)
    assert "validation receipt" in markdown
    assert "delivery_rate" in markdown


def test_report_hard_rejects_current_authority_with_a_different_manifest_digest() -> None:
    """A current capability and typed manifest may never carry detached digests."""
    with pytest.raises(ValueError, match="manifest.*digest"):
        _report(manifest_sha256="b" * 64)


def test_report_rejects_hand_constructed_current_verification() -> None:
    """Only the offline verifier may mint the capability that authorizes scoring."""
    report = _report(validation_receipt=_verified_receipt())

    assert report.metrics is None
    assert report.validation_authority.authority == "none"
    assert report.metrics_withheld_reason == "validation_receipt_provenance_unauthorized"


def test_report_rejects_verification_subclass_authority_override() -> None:
    """A caller-defined property override cannot impersonate the offline verifier."""

    class ForgedVerification(ValidationVerification):
        @property
        def authority(self) -> str:
            return "current_scoring_authority"

    direct = _verified_receipt()
    forged = ForgedVerification(
        integrity=direct.integrity,
        provenance=direct.provenance,
        semantic_policy=direct.semantic_policy,
        _authority="current_scoring_authority",
        receipt=direct.receipt,
    )

    report = _report(validation_receipt=forged)

    assert report.metrics is None
    assert report.validation_authority.authority == "none"
    assert report.metrics_withheld_reason == "validation_receipt_provenance_unauthorized"


def test_report_rejects_copied_verifier_capability() -> None:
    """Copying fields and a private seal does not copy verifier-minted object identity."""
    assert isinstance(_VALID_RECEIPT, ValidationVerification)
    copied = copy.copy(_VALID_RECEIPT)

    report = _report(validation_receipt=copied)

    assert report.metrics is None
    assert report.validation_authority.authority == "none"
    assert report.metrics_withheld_reason == "validation_receipt_provenance_unauthorized"


def test_report_rejects_in_place_mutation_of_verifier_capability() -> None:
    """Registered identity cannot authorize fields changed after offline verification."""
    assert isinstance(_VALID_RECEIPT.receipt, ValidationReceiptV2)
    forged_manifest_sha256 = "b" * 64
    object.__setattr__(
        _VALID_RECEIPT.receipt,
        "manifest_sha256",
        forged_manifest_sha256,
    )

    report = _report(
        validation_receipt=_VALID_RECEIPT,
        manifest_sha256=forged_manifest_sha256,
    )

    assert _VALID_RECEIPT.authority == "none"
    assert report.metrics is None
    assert report.metrics_withheld_reason == "validation_receipt_provenance_unauthorized"


def test_report_marks_v1_as_historical_integrity_only_and_withholds_scoring() -> None:
    """A readable legacy receipt must never be upgraded into current scoring authority."""
    report = _report(validation_receipt=_historical_receipt())
    payload = report.to_json_dict()

    assert report.metrics is None
    assert report.metrics_withheld_reason == "validation_receipt_historical_integrity_only"
    assert payload["validation_authority"] == {
        "authority": "historical_integrity_only",
        "integrity": {"accepted": True, "failure_paths": []},
        "authorized_provenance": {
            "accepted": False,
            "failure_paths": ["receipt.provenance_envelope"],
        },
        "semantic_policy": {
            "accepted": False,
            "failure_paths": ["validation_results.results[*].attempts"],
        },
    }
    markdown = render_markdown(report)
    assert "historical_integrity_only" in markdown
    assert "integrity: PASS" in markdown
    assert "authorized provenance: FAIL" in markdown
    assert "semantic policy: FAIL" in markdown


def test_report_publishes_accuracy_for_a_receipt_bound_to_this_manifest() -> None:
    """The gate is authorisation, not a blanket refusal that can never pass."""
    report = _report()

    assert report.metrics is not None
    assert report.metrics_withheld_reason is None
    assert report.to_json_dict()["metrics"]["true_positives"] == 1
    assert report.to_json_dict()["operational"]["decided_cases"] == 2
    assert report.to_json_dict()["validation_authority"]["authority"] == (
        "current_scoring_authority"
    )
    markdown = render_markdown(report)
    assert "integrity: PASS" in markdown
    assert "authorized provenance: PASS" in markdown
    assert "semantic policy: PASS" in markdown


def test_report_surfaces_abstentions_with_counts_and_reasons() -> None:
    """A run attest could not decide is an abstention, never earned silence."""
    report = _report(
        runs=(_runs()[0], _runs()[2]),
        abstentions=(ReportAbstention(CONTROL_CASE, "budget: exhausted before review"),),
    )
    payload = report.to_json_dict()

    assert [
        (abstention.case_id, abstention.reason)
        for abstention in report.abstained_cases
    ] == [(CONTROL_CASE, "budget: exhausted before review")]
    assert payload["abstained_cases"] == [
        {"case_id": CONTROL_CASE, "reason": "budget: exhausted before review"}
    ]
    assert payload["operational"]["abstained_cases"] == 1
    assert report.metrics is not None
    assert report.metrics.true_negatives == 0
    assert report.metrics.specificity is None
    assert report.metrics.decided_cases == 1
    limitations = " ".join(report.limitations)
    assert "abstention" in limitations
    markdown = render_markdown(report)
    assert "## Abstentions" in markdown
    assert f"| `{CONTROL_CASE}` | budget: exhausted before review |" in markdown


def test_report_surfaces_an_inconclusive_oracle_exclusion_with_its_reason() -> None:
    """An undecided oracle removes the case from scoring and says so in both reports."""
    undecided = RunRecord(
        run_id="run-1",
        case_id=REPLAY_CASE,
        repeat=0,
        predictions=(
            _prediction(
                "f-undecided",
                2,
                repro_status="deferred",
                evidence_class="indeterminate",
            ),
        ),
        delivery_at_s=12.0,
        deadline_s=60.0,
    )
    report = _report(runs=(undecided, _runs()[1]))
    payload = report.to_json_dict()

    assert report.metrics is not None
    assert (report.metrics.false_negatives, report.metrics.finding_false_positives) == (0, 0)
    assert report.metrics.decided_cases == 1
    assert {
        (exclusion["case_id"], exclusion["reason"])
        for exclusion in payload["excluded_cases"]
    } >= {(REPLAY_CASE, "oracle_inconclusive")}
    assert payload["operational"]["excluded_cases"] == 3
    assert "oracle_inconclusive" in render_markdown(report)
    assert "oracle_inconclusive" in " ".join(report.limitations)


def test_report_without_runs_reports_no_metrics_rather_than_zeros() -> None:
    report = build_report(
        _manifest(),
        (),
        mode=REPLAY_MODE,
        manifest_sha256=MANIFEST_SHA,
        exclusions=(
            ReportExclusion(case.case_id, "prepared_environment_required")
            for case in _manifest().cases
        ),
    )

    assert report.metrics is None
    assert report.evaluated_cases == 0
    assert report.to_json_dict()["metrics"] is None
    assert "no case was evaluated" in render_markdown(report)


def test_report_json_and_markdown_are_deterministic(tmp_path: Path) -> None:
    first, second = _report(), _report()

    assert first.digest == second.digest
    assert json.dumps(first.to_json_dict(), sort_keys=True) == json.dumps(
        second.to_json_dict(), sort_keys=True
    )
    assert render_markdown(first) == render_markdown(second)

    json_path, markdown_path = write_report(first, tmp_path / "out")
    first_bytes = (json_path.read_bytes(), markdown_path.read_bytes())
    json_path, markdown_path = write_report(second, tmp_path / "out")

    assert (json_path.read_bytes(), markdown_path.read_bytes()) == first_bytes
    assert json.loads(json_path.read_text(encoding="utf-8"))["digest"] == first.digest
