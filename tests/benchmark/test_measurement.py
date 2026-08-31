"""M-01 RED checkpoint for authoritative mixed-outcome measurement."""

from __future__ import annotations

import hashlib
import json
import os
import threading
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from attest.benchmark.api import (
    ProjectEvaluationRequest,
    ProjectTruth,
    evaluate_project,
)
from attest.benchmark.artifacts import ArtifactStore
from attest.benchmark.baselines import (
    ARM_BARE_PROMPT,
    ARM_PRODUCT,
    ARM_RUFF,
    _summarize_arm,
    compare_arms,
)
from attest.benchmark.checkpoints import (
    CALL_ROLE_BENCHMARK_ORACLE,
    CALL_ROLE_PRODUCT,
)
from attest.benchmark.live import LIVE_MODE, build_calibration_report, case_payload
from attest.benchmark.report import build_comparison_report
from attest.benchmark.runner import (
    BenchmarkRunner,
    LoopbackGitHub,
    ReplayProvider,
)
from attest.benchmark.schema import is_scored_placement, load_manifest
from attest.review.config import ReviewConfig
from attest.review.executor import ExecutorLimits
from attest.review.proposer import ProviderResult

from .test_baselines import _comparison_authority, _plans, _ruff_executable
from .test_corpus import _oracle_fixture


def test_canonical_outcome_codec_is_write_once_and_exact(tmp_path: Path) -> None:
    from attest.benchmark.outcomes import (
        canonical_json_bytes,
        read_canonical_json,
        write_canonical_json_once,
    )

    root = tmp_path / "state"
    payload = {"schema_version": "1", "nested": {"value": 3}, "rows": [1, 2]}
    expected = b'{"nested":{"value":3},"rows":[1,2],"schema_version":"1"}\n'

    assert canonical_json_bytes(payload) == expected
    written = write_canonical_json_once(root, "outcomes/000000.json", payload)
    assert written.data == expected
    assert read_canonical_json(root, written.relative_path).value == payload
    assert write_canonical_json_once(root, written.relative_path, payload) == written
    with pytest.raises(ValueError, match="write-once|different"):
        write_canonical_json_once(
            root,
            written.relative_path,
            {**payload, "nested": {"value": 4}},
        )


@pytest.mark.parametrize(
    "relative_path",
    (
        "/absolute.json",
        "outcomes/../escape.json",
        "C:\\outcomes\\000000.json",
        "outcomes//000000.json",
        "outcomes/./000000.json",
        "outcomes/\x01.json",
        "outcomes/\x00.json",
    ),
)
def test_authoritative_outcome_reader_rejects_nonrelative_paths(
    tmp_path: Path, relative_path: str
) -> None:
    from attest.benchmark.outcomes import read_canonical_json

    with pytest.raises(ValueError, match="relative|below|path"):
        read_canonical_json(tmp_path, relative_path)


@pytest.mark.parametrize(
    "raw",
    (
        b'{"schema_version":"1","nested":{"x":1,"x":2}}\n',
        b'{"schema_version":"1","value":NaN}\n',
        b'{"schema_version":"1","value":1e400}\n',
        b' {"schema_version":"1"}\n',
        b'\xef\xbb\xbf{"schema_version":"1"}\n',
        b'{"schema_version":"1"}',
    ),
)
def test_authoritative_outcome_reader_rejects_noncanonical_json(
    tmp_path: Path, raw: bytes
) -> None:
    from attest.benchmark.outcomes import read_canonical_json

    root = tmp_path / "state"
    path = root / "outcomes" / "000000.json"
    path.parent.mkdir(parents=True)
    path.write_bytes(raw)

    with pytest.raises(ValueError, match="canonical|duplicate|finite"):
        read_canonical_json(root, "outcomes/000000.json")


@pytest.mark.parametrize(
    "kind",
    ("root_symlink", "parent_symlink", "file_symlink", "hardlink", "fifo", "directory"),
)
def test_authoritative_outcome_reader_rejects_unsafe_filesystem_objects(
    tmp_path: Path, kind: str
) -> None:
    from attest.benchmark.outcomes import read_canonical_json

    real_root = tmp_path / "real"
    relative = Path("outcomes/000000.json")
    target = real_root / relative
    target.parent.mkdir(parents=True)
    target.write_bytes(b'{"schema_version":"1"}\n')
    root = real_root
    if kind == "root_symlink":
        root = tmp_path / "root-link"
        root.symlink_to(real_root, target_is_directory=True)
    elif kind == "parent_symlink":
        moved = tmp_path / "moved-outcomes"
        (real_root / "outcomes").rename(moved)
        (real_root / "outcomes").symlink_to(moved, target_is_directory=True)
    elif kind == "file_symlink":
        target.unlink()
        target.symlink_to(tmp_path / "elsewhere.json")
    elif kind == "hardlink":
        os.link(target, tmp_path / "second-link.json")
    elif kind == "fifo":
        target.unlink()
        os.mkfifo(target)
    else:
        target.unlink()
        target.mkdir()

    with pytest.raises(ValueError, match="symlink|regular|link|unsafe|authoritative"):
        read_canonical_json(root, relative)


def test_authoritative_outcome_reader_rejects_oversize_and_growth(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import attest.benchmark.outcomes as outcomes

    root = tmp_path / "state"
    path = root / "outcomes" / "000000.json"
    path.parent.mkdir(parents=True)
    path.write_bytes(b'{"value":"0123456789"}\n')
    with pytest.raises(ValueError, match="size"):
        outcomes.read_canonical_json(root, "outcomes/000000.json", maximum_bytes=8)

    original_read = outcomes.os.read
    changed = False

    def growing_read(file_descriptor: int, size: int) -> bytes:
        nonlocal changed
        data = original_read(file_descriptor, size)
        if not changed:
            changed = True
            with path.open("ab") as stream:
                stream.write(b" ")
        return data

    monkeypatch.setattr(outcomes.os, "read", growing_read)
    with pytest.raises(ValueError, match="grew|changed"):
        outcomes.read_canonical_json(root, "outcomes/000000.json")


def test_write_once_rejects_oversize_before_creating_state(tmp_path: Path) -> None:
    import attest.benchmark.outcomes as outcomes

    root = tmp_path / "state"
    with pytest.raises(ValueError, match="size|large"):
        outcomes.write_canonical_json_once(
            root,
            "outcomes/000000.json",
            {"blob": "x" * outcomes.DEFAULT_MAX_OUTCOME_BYTES},
        )
    assert not root.exists()


def test_measurement_outcome_writer_rejects_malformed_payload_before_occupying_slot(
    tmp_path: Path,
) -> None:
    from attest.benchmark.outcomes import write_measurement_outcome_once

    root = tmp_path / "state"
    slot = _outcome_slot(0, "case-1", ARM_PRODUCT)

    with pytest.raises(ValueError, match="measurement|record|outcome"):
        write_measurement_outcome_once(
            root,
            slot,
            {"schema_version": "malformed", "future": True},
        )

    assert not (root / slot.relative_path).exists()
    assert not (root / ".outcome-staging").exists()


def test_authoritative_outcome_reader_uses_open_inode_across_path_swap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import attest.benchmark.outcomes as outcomes

    root = tmp_path / "state"
    path = root / "outcomes" / "000000.json"
    path.parent.mkdir(parents=True)
    path.write_bytes(b'{"value":"original"}\n')
    original_open = outcomes._open_regular_component
    swapped = False

    def swapping_open(parent: int, component: str) -> int:
        nonlocal swapped
        file_descriptor = original_open(parent, component)
        if not swapped and component == "000000.json":
            swapped = True
            path.rename(path.with_name("opened-inode.json"))
            path.write_bytes(b'{"value":"replacement"}\n')
        return file_descriptor

    monkeypatch.setattr(outcomes, "_open_regular_component", swapping_open)
    assert outcomes.read_canonical_json(root, "outcomes/000000.json").value == {
        "value": "original"
    }
    assert path.read_bytes() == b'{"value":"replacement"}\n'


def test_authoritative_outcome_reader_rejects_same_inode_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import attest.benchmark.outcomes as outcomes

    root = tmp_path / "state"
    path = root / "outcomes" / "000000.json"
    path.parent.mkdir(parents=True)
    original = outcomes.canonical_json_bytes({"value": "a" * 70000})
    changed = outcomes.canonical_json_bytes({"value": "b" * 70000})
    assert len(original) == len(changed)
    path.write_bytes(original)
    original_read = outcomes.os.read
    mutated = False

    def mutating_read(file_descriptor: int, size: int) -> bytes:
        nonlocal mutated
        data = original_read(file_descriptor, size)
        if not mutated:
            mutated = True
            path.write_bytes(changed)
        return data

    monkeypatch.setattr(outcomes.os, "read", mutating_read)
    with pytest.raises(ValueError, match="changed"):
        outcomes.read_canonical_json(root, "outcomes/000000.json")


def _outcome_slot(ordinal: int, case_id: str, arm: str, repeat: int = 0):
    from attest.benchmark.outcomes import OutcomeSlot

    return OutcomeSlot.create(
        ordinal=ordinal,
        case_id=case_id,
        arm=arm,
        repeat=repeat,
        bindings_sha256="b" * 64,
    )


def _case_outcome_slots(case_id: str = "case-1", repeat: int = 0):
    return tuple(
        _outcome_slot(ordinal, case_id, arm, repeat)
        for ordinal, arm in enumerate((ARM_PRODUCT, ARM_BARE_PROMPT, ARM_RUFF))
    )


def _outcome_payload(slot) -> dict[str, object]:
    record = replace(
        _measurement_record(
            findings=(), eligible_defect_ids=(), truth_status="unadjudicated"
        ),
        case_id=slot.case_id,
        arm=slot.arm,
        repeat=slot.repeat,
    )
    return {
        "schema_version": "1",
        "slot": slot.to_json_dict(),
        "outcome": record.to_json_dict(),
    }


def _write_outcome_predeclaration(root: Path, slots) -> str:
    from attest.benchmark.outcomes import (
        OUTCOME_PREDECLARATION_PATH,
        write_canonical_json_once,
    )

    slots = tuple(slots)
    case_bindings = {
        slot.case_id: slot.bindings_sha256
        for slot in slots
    }

    return write_canonical_json_once(
        root,
        OUTCOME_PREDECLARATION_PATH,
        {
            "schema_version": "1",
            "protocol": "comparison-authoritative-outcomes-v1",
            "manifest_sha256": "a" * 64,
            "repeats": max((slot.repeat for slot in slots), default=-1) + 1,
            "case_bindings": [
                {"case_id": case_id, "bindings_sha256": binding}
                for case_id, binding in sorted(case_bindings.items())
            ],
            "outcome_slots": [slot.to_json_dict() for slot in slots],
        },
    ).sha256


def test_outcome_slot_identity_and_path_are_canonically_derived() -> None:
    first = _outcome_slot(0, "case-1", ARM_PRODUCT)
    second = _outcome_slot(1, "case-1", ARM_RUFF)

    assert first.relative_path == "outcomes/000000.json"
    assert second.relative_path == "outcomes/000001.json"
    assert first.slot_id != second.slot_id
    with pytest.raises(TypeError):
        type(first)(slot_id="chosen", relative_path="outcomes/chosen.json")


def test_outcome_predeclaration_recomputes_every_derived_slot_field(tmp_path: Path) -> None:
    from attest.benchmark.outcomes import seal_outcomes

    root = tmp_path / "state"
    slot = _outcome_slot(0, "case-1", ARM_PRODUCT)
    object.__setattr__(slot, "case_id", "forged-case")
    _write_outcome_predeclaration(root, (slot,))
    with pytest.raises(ValueError, match="derived|slot|identity"):
        seal_outcomes(root)


@pytest.mark.parametrize(("field", "value"), (("ordinal", 0.0), ("repeat", False)))
def test_outcome_predeclaration_rejects_equality_subclass_numeric_fields(
    tmp_path: Path, field: str, value: object
) -> None:
    from attest.benchmark.outcomes import seal_outcomes, write_canonical_json_once

    root = tmp_path / "state"
    rows = [slot.to_json_dict() for slot in _case_outcome_slots()]
    rows[0][field] = value
    write_canonical_json_once(
        root,
        "outcomes.predeclaration.json",
        {
            "schema_version": "1",
            "protocol": "comparison-authoritative-outcomes-v1",
            "manifest_sha256": "a" * 64,
            "repeats": 1,
            "case_bindings": [{"case_id": "case-1", "bindings_sha256": "b" * 64}],
            "outcome_slots": rows,
        },
    )
    with pytest.raises(ValueError, match="exact|integer|derived"):
        seal_outcomes(root)


def test_outcome_predeclaration_requires_exact_three_arm_coverage(tmp_path: Path) -> None:
    from attest.benchmark.outcomes import seal_outcomes

    root = tmp_path / "state"
    _write_outcome_predeclaration(root, _case_outcome_slots()[:-1])
    with pytest.raises(ValueError, match="coverage|arm|slot"):
        seal_outcomes(root)


def test_comparison_outcome_writer_freshly_resolves_nonzero_ordinal_slot(
    tmp_path: Path,
) -> None:
    from attest.benchmark.measurement import TaskStatus
    from attest.benchmark.outcomes import (
        ComparisonArmOutcome,
        predeclare_comparison_outcomes,
        write_comparison_arm_outcome_once,
    )

    root = tmp_path / "state"
    authority = predeclare_comparison_outcomes(
        root,
        authority_id="d" * 64,
        manifest_sha256="a" * 64,
        case_bindings={"case-1": "b" * 64},
        repeats=1,
    )
    slot = authority.slots[1]
    outcome = ComparisonArmOutcome(
        task_status=TaskStatus.COMPLETED,
        abstain_reason=None,
        surfaced_findings=(),
        product_measurement=None,
        paid_calls_sha256=hashlib.sha256(b"[]").hexdigest(),
        wall_time_s=1.0,
        tool_cost_s=None,
    )

    document = write_comparison_arm_outcome_once(
        authority,
        slot,
        outcome,
    )

    assert document.relative_path == slot.relative_path


def test_comparison_outcome_writer_rejects_slot_from_another_predeclaration(
    tmp_path: Path,
) -> None:
    from attest.benchmark.measurement import TaskStatus
    from attest.benchmark.outcomes import (
        ComparisonArmOutcome,
        predeclare_comparison_outcomes,
        write_comparison_arm_outcome_once,
    )

    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    first = predeclare_comparison_outcomes(
        first_root,
        authority_id="d" * 64,
        manifest_sha256="a" * 64,
        case_bindings={"case-1": "b" * 64},
        repeats=1,
    )
    second = predeclare_comparison_outcomes(
        second_root,
        authority_id="e" * 64,
        manifest_sha256="a" * 64,
        case_bindings={"case-1": "c" * 64},
        repeats=1,
    )
    outcome = ComparisonArmOutcome(
        task_status=TaskStatus.COMPLETED,
        abstain_reason=None,
        surfaced_findings=(),
        product_measurement=None,
        paid_calls_sha256=hashlib.sha256(b"[]").hexdigest(),
        wall_time_s=1.0,
        tool_cost_s=None,
    )

    with pytest.raises(ValueError, match="predeclaration|slot|binding"):
        write_comparison_arm_outcome_once(second, first.slots[1], outcome)


def test_comparison_slot_identity_and_path_are_domain_separated_from_generic_v1(
    tmp_path: Path,
) -> None:
    from attest.benchmark.outcomes import predeclare_comparison_outcomes

    generic = _outcome_slot(0, "case-1", ARM_PRODUCT)
    comparison = predeclare_comparison_outcomes(
        tmp_path / "comparison",
        authority_id="d" * 64,
        manifest_sha256="a" * 64,
        case_bindings={"case-1": "b" * 64},
        repeats=1,
    ).slots[0]

    assert comparison.slot_id != generic.slot_id
    assert comparison.relative_path != generic.relative_path


def test_product_comparison_outcome_requires_exact_published_finding_join(
    tmp_path: Path,
) -> None:
    from attest.benchmark.measurement import TaskStatus
    from attest.benchmark.outcomes import (
        ComparisonArmOutcome,
        predeclare_comparison_outcomes,
        write_comparison_arm_outcome_once,
    )

    authority = predeclare_comparison_outcomes(
        tmp_path / "comparison",
        authority_id="d" * 64,
        manifest_sha256="a" * 64,
        case_bindings={"case-1": "b" * 64},
        repeats=1,
    )
    slot = authority.slots[0]
    measurement = replace(
        _measurement_record(findings=(_finding("published-finding"),)),
        case_id=slot.case_id,
        arm=slot.arm,
        repeat=slot.repeat,
    )
    outcome = ComparisonArmOutcome(
        task_status=TaskStatus.COMPLETED,
        abstain_reason=None,
        surfaced_findings=(),
        product_measurement=measurement,
        paid_calls_sha256=hashlib.sha256(b"[]").hexdigest(),
        wall_time_s=1.0,
        tool_cost_s=None,
    )

    with pytest.raises(ValueError, match="surfaced findings|MeasurementRecord"):
        write_comparison_arm_outcome_once(authority, slot, outcome)


def test_outcome_predeclaration_rejects_resource_exhausting_repeats_before_range(
    tmp_path: Path,
) -> None:
    from attest.benchmark.outcomes import build_outcome_predeclaration

    with pytest.raises(ValueError, match="repeat|limit|maximum"):
        build_outcome_predeclaration(
            manifest_sha256="a" * 64,
            case_bindings={"case-1": "b" * 64},
            repeats=21,
        )


@pytest.mark.parametrize(
    ("case_count", "repeats", "message"),
    ((129, 1, "case"), (69, 20, "slot")),
)
def test_outcome_predeclaration_rejects_case_and_slot_resource_limits(
    case_count: int, repeats: int, message: str
) -> None:
    from attest.benchmark.outcomes import build_outcome_predeclaration

    case_bindings = {
        f"case-{index:03d}": hashlib.sha256(str(index).encode()).hexdigest()
        for index in range(case_count)
    }
    with pytest.raises(ValueError, match=f"{message}.*limit"):
        build_outcome_predeclaration(
            manifest_sha256="a" * 64,
            case_bindings=case_bindings,
            repeats=repeats,
        )


@pytest.mark.parametrize("repeat_set", ((1,), (0, 2)))
def test_outcome_predeclaration_requires_contiguous_repeats_from_zero(
    tmp_path: Path, repeat_set: tuple[int, ...]
) -> None:
    from attest.benchmark.outcomes import seal_outcomes

    slots = tuple(
        _outcome_slot(ordinal, "case-1", arm, repeat)
        for ordinal, (repeat, arm) in enumerate(
            (repeat, arm)
            for repeat in repeat_set
            for arm in (ARM_PRODUCT, ARM_BARE_PROMPT, ARM_RUFF)
        )
    )
    root = tmp_path / "state"
    _write_outcome_predeclaration(root, slots)
    with pytest.raises(ValueError, match="repeat|contiguous|zero|coverage"):
        seal_outcomes(root)


def test_outcome_predeclaration_rejects_unknown_protocol_or_version(tmp_path: Path) -> None:
    from attest.benchmark.outcomes import seal_outcomes, write_canonical_json_once

    root = tmp_path / "state"
    slots = _case_outcome_slots()
    write_canonical_json_once(
        root,
        "outcomes.predeclaration.json",
        {
            "schema_version": "legacy-v0",
            "protocol": "comparison-authoritative-outcomes-v1",
            "manifest_sha256": "a" * 64,
            "repeats": 1,
            "case_bindings": [{"case_id": "case-1", "bindings_sha256": "b" * 64}],
            "outcome_slots": [slot.to_json_dict() for slot in slots],
            "future": True,
        },
    )
    with pytest.raises(ValueError, match="predeclaration|schema|field|version"):
        seal_outcomes(root)


def test_authoritative_outcome_capability_absence_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import attest.benchmark.outcomes as outcomes

    monkeypatch.delattr(outcomes.os, "O_NOFOLLOW")
    with pytest.raises(ValueError, match="capabilit|O_NOFOLLOW"):
        outcomes.read_canonical_json(tmp_path, "outcomes/000000.json")

    monkeypatch.undo()
    monkeypatch.setattr(outcomes.os, "O_NOFOLLOW", 0)
    with pytest.raises(ValueError, match="capabilit|O_NOFOLLOW"):
        outcomes.read_canonical_json(tmp_path, "outcomes/000000.json")

    monkeypatch.undo()
    monkeypatch.setattr(outcomes, "_SUPPORTED_FD_NAMES", frozenset())
    with pytest.raises(ValueError, match="capabilit|listdir"):
        outcomes.read_canonical_json(tmp_path, "outcomes/000000.json")


def test_authoritative_outcome_root_rejects_an_ancestor_symlink(tmp_path: Path) -> None:
    from attest.benchmark.outcomes import write_canonical_json_once

    outside = tmp_path / "outside"
    outside.mkdir()
    anchor = tmp_path / "anchor"
    anchor.mkdir()
    (anchor / "link").symlink_to(outside, target_is_directory=True)

    with pytest.raises(ValueError, match="symlink|unsafe"):
        write_canonical_json_once(
            anchor / "link" / "state",
            "outcomes/000000.json",
            {"schema_version": "1"},
        )
    assert not (outside / "state").exists()


def test_write_once_never_exposes_a_partial_final_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import attest.benchmark.outcomes as outcomes

    root = tmp_path / "state"
    final = root / "outcomes" / "000000.json"
    entered = threading.Event()
    release = threading.Event()
    original_write = outcomes.os.write

    def paused_write(file_descriptor: int, data: bytes | memoryview) -> int:
        entered.set()
        assert release.wait(timeout=5.0)
        return original_write(file_descriptor, data)

    monkeypatch.setattr(outcomes.os, "write", paused_write)
    errors: list[BaseException] = []

    def writer() -> None:
        try:
            outcomes.write_canonical_json_once(
                root, "outcomes/000000.json", {"schema_version": "1"}
            )
        except BaseException as exc:  # pragma: no cover - assertion reports it
            errors.append(exc)

    thread = threading.Thread(target=writer)
    thread.start()
    assert entered.wait(timeout=5.0)
    assert not final.exists()
    release.set()
    thread.join(timeout=5.0)
    assert not thread.is_alive()
    assert errors == []
    assert final.read_bytes() == b'{"schema_version":"1"}\n'
    assert not any(path.name.startswith(".outcome-tmp-") for path in final.parent.iterdir())


def test_write_once_recovers_crash_after_publish_before_staging_unlink(
    tmp_path: Path,
) -> None:
    import attest.benchmark.outcomes as outcomes

    root = tmp_path / "state"
    final = root / "outcomes" / "000000.json"
    staging = root / ".outcome-staging"
    final.parent.mkdir(parents=True)
    staging.mkdir()
    temporary = staging / ".outcome-tmp-crash"
    temporary.write_bytes(b'{"schema_version":"1"}\n')
    with temporary.open("rb") as stream:
        os.fsync(stream.fileno())
    os.link(temporary, final)
    assert not any(path.name.startswith(".outcome-tmp-") for path in final.parent.iterdir())

    recovered = outcomes.write_canonical_json_once(
        root, "outcomes/000000.json", {"schema_version": "1"}
    )
    assert recovered.data == b'{"schema_version":"1"}\n'
    assert os.stat(final).st_nlink == 1
    assert not temporary.exists()


@pytest.mark.parametrize("corruption", ("different_inode", "multiple_links", "different_bytes"))
def test_write_once_refuses_ambiguous_staging_recovery(
    tmp_path: Path, corruption: str
) -> None:
    import attest.benchmark.outcomes as outcomes

    root = tmp_path / "state"
    final = root / "outcomes" / "000000.json"
    staging = root / ".outcome-staging"
    final.parent.mkdir(parents=True)
    staging.mkdir()
    final.write_bytes(b'{"schema_version":"1"}\n')
    first = staging / ".outcome-tmp-first"
    if corruption == "different_inode":
        first.write_bytes(final.read_bytes())
    else:
        os.link(final, first)
        if corruption == "multiple_links":
            os.link(final, staging / ".outcome-tmp-second")
        else:
            with final.open("r+b") as stream:
                stream.write(b'{"schema_version":"2"}\n')

    with pytest.raises(ValueError, match="staging|recovery|link|bytes"):
        outcomes.write_canonical_json_once(
            root, "outcomes/000000.json", {"schema_version": "1"}
        )


@pytest.mark.parametrize(
    "slots",
    (
        lambda: (_outcome_slot(0, "case-1", ARM_PRODUCT),) * 2,
        lambda: (
            _outcome_slot(0, "case-1", ARM_PRODUCT),
            _outcome_slot(1, "case-1", ARM_PRODUCT),
        ),
        lambda: (
            _outcome_slot(0, "case-1", ARM_PRODUCT),
            _outcome_slot(0, "case-2", ARM_RUFF),
        ),
    ),
)
def test_outcome_seal_rejects_duplicate_identity_or_path(
    tmp_path: Path, slots
) -> None:
    from attest.benchmark.outcomes import seal_outcomes

    root = tmp_path / "state"
    _write_outcome_predeclaration(root, slots())
    with pytest.raises(ValueError, match="duplicate"):
        seal_outcomes(root)


def test_outcome_seal_requires_exact_predeclared_slots(tmp_path: Path) -> None:
    from attest.benchmark.outcomes import (
        canonical_json_bytes,
        seal_outcomes,
        verify_outcome_seal,
        write_canonical_json_once,
    )

    root = tmp_path / "state"
    slots = _case_outcome_slots()
    predeclaration_sha256 = _write_outcome_predeclaration(root, slots)
    product = write_canonical_json_once(root, slots[0].relative_path, _outcome_payload(slots[0]))
    with pytest.raises(ValueError, match="missing.*slot"):
        seal_outcomes(root)

    for slot in slots[1:]:
        write_canonical_json_once(root, slot.relative_path, _outcome_payload(slot))
    extra = root / "outcomes" / "999999.json"
    extra.write_bytes(b'{"schema_version":"1"}\n')
    with pytest.raises(ValueError, match="extra"):
        seal_outcomes(root)
    extra.unlink()
    seal = seal_outcomes(root)
    assert seal.value["predeclaration_sha256"] == predeclaration_sha256
    verified = verify_outcome_seal(root)
    assert verified[slots[0].slot_id].sha256 == product.sha256

    (root / slots[0].relative_path).write_bytes(
        canonical_json_bytes(_outcome_payload(slots[1]))
    )
    with pytest.raises(ValueError, match="digest|slot"):
        verify_outcome_seal(root)


def test_outcome_tree_rejects_extra_subdirectories(tmp_path: Path) -> None:
    from attest.benchmark.outcomes import seal_outcomes, write_canonical_json_once

    root = tmp_path / "state"
    slots = _case_outcome_slots()
    _write_outcome_predeclaration(root, slots)
    for slot in slots:
        write_canonical_json_once(root, slot.relative_path, _outcome_payload(slot))
    (root / "outcomes" / "extra-directory").mkdir()

    with pytest.raises(ValueError, match="extra|flat|directory"):
        seal_outcomes(root)


@pytest.mark.parametrize(
    "payload",
    (
        {"schema_version": "1", "slot": None, "outcome": {"status": "completed"}},
        {"schema_version": "1", "slot": {}, "outcome": {"status": "completed"}},
        {"schema_version": "1", "slot": "descriptor", "outcome": {}},
        {
            "schema_version": "1",
            "slot": "descriptor",
            "outcome": {"status": "completed"},
            "future": True,
        },
    ),
)
def test_outcome_seal_rejects_nonexact_or_empty_envelopes(
    tmp_path: Path, payload: dict[str, object]
) -> None:
    from attest.benchmark.outcomes import seal_outcomes, write_canonical_json_once

    root = tmp_path / "state"
    slots = _case_outcome_slots()
    slot = slots[0]
    _write_outcome_predeclaration(root, slots)
    if payload["slot"] == "descriptor":
        payload = {**payload, "slot": slot.to_json_dict()}
    write_canonical_json_once(root, slot.relative_path, payload)
    for other in slots[1:]:
        write_canonical_json_once(root, other.relative_path, _outcome_payload(other))
    with pytest.raises(ValueError, match="envelope|slot|outcome|field"):
        seal_outcomes(root)


@pytest.mark.parametrize(
    "mutation",
    ("extra", "missing", "version", "case", "arm", "repeat", "legacy"),
)
def test_outcome_seal_strictly_decodes_measurement_and_slot_binding(
    tmp_path: Path, mutation: str
) -> None:
    from attest.benchmark.outcomes import seal_outcomes, write_canonical_json_once

    root = tmp_path / "state"
    slots = _case_outcome_slots()
    slot = slots[0]
    _write_outcome_predeclaration(root, slots)
    payload = _outcome_payload(slot)
    outcome = dict(payload["outcome"])
    if mutation == "extra":
        outcome["future"] = True
    elif mutation == "missing":
        outcome.pop("task_status")
    elif mutation == "version":
        outcome["schema_version"] = 999
    elif mutation in {"case", "arm", "repeat"}:
        field = {"case": "case_id", "arm": "arm", "repeat": "repeat"}[mutation]
        outcome[field] = {"case": "other-case", "arm": "other-arm", "repeat": 1}[mutation]
    else:
        outcome = {
            "run_id": "legacy",
            "case_id": "case-1",
            "repeat": 0,
            "predictions": [],
            "delivery_at_s": None,
            "deadline_s": 60.0,
        }
    payload["outcome"] = outcome
    write_canonical_json_once(root, slot.relative_path, payload)
    for other in slots[1:]:
        write_canonical_json_once(root, other.relative_path, _outcome_payload(other))

    with pytest.raises(ValueError, match="measurement|schema|field|case|arm|repeat"):
        seal_outcomes(root)


@pytest.mark.parametrize(
    "mutation", ("missing", "duplicate", "extra", "predecl", "size_bool", "sha", "order")
)
def test_outcome_seal_reader_rejects_corrupt_membership(
    tmp_path: Path, mutation: str
) -> None:
    from attest.benchmark.outcomes import (
        OUTCOME_SEAL_PATH,
        canonical_json_bytes,
        seal_outcomes,
        verify_outcome_seal,
        write_canonical_json_once,
    )

    root = tmp_path / "state"
    slots = _case_outcome_slots()
    _write_outcome_predeclaration(root, slots)
    for slot in slots:
        write_canonical_json_once(root, slot.relative_path, _outcome_payload(slot))
    if mutation == "missing":
        with pytest.raises(ValueError, match="missing|unsafe"):
            verify_outcome_seal(root)
        return
    seal_outcomes(root)
    seal_path = root / OUTCOME_SEAL_PATH
    payload = json.loads(seal_path.read_bytes())
    if mutation == "duplicate":
        payload["slots"].append(payload["slots"][0])
    elif mutation == "extra":
        payload["slots"].append(
            {"slot_id": "extra", "path": "outcomes/999999.json", "sha256": "c" * 64, "size": 1}
        )
    else:
        if mutation == "predecl":
            payload["predeclaration_sha256"] = "d" * 64
        elif mutation == "size_bool":
            payload["slots"][0]["size"] = True
        elif mutation == "sha":
            payload["slots"][0]["sha256"] = "not-a-digest"
        else:
            payload["slots"].reverse()
    seal_path.write_bytes(canonical_json_bytes(payload))

    with pytest.raises(ValueError, match="seal|duplicate|predeclaration"):
        verify_outcome_seal(root)


def test_outcome_seal_rejects_fresh_predeclaration_digest_drift(tmp_path: Path) -> None:
    from attest.benchmark.outcomes import (
        canonical_json_bytes,
        seal_outcomes,
        verify_outcome_seal,
        write_canonical_json_once,
    )

    root = tmp_path / "state"
    slots = _case_outcome_slots()
    _write_outcome_predeclaration(root, slots)
    for slot in slots:
        write_canonical_json_once(root, slot.relative_path, _outcome_payload(slot))
    seal_outcomes(root)
    predecl = json.loads((root / "outcomes.predeclaration.json").read_bytes())
    predecl["schema_version"] = "drifted"
    (root / "outcomes.predeclaration.json").write_bytes(canonical_json_bytes(predecl))

    with pytest.raises(ValueError, match="predeclaration|digest"):
        verify_outcome_seal(root)


def test_outcome_seal_rejects_coordinated_whole_root_rewrite_against_frozen_digest(
    tmp_path: Path,
) -> None:
    from attest.benchmark.measurement import TaskStatus
    from attest.benchmark.outcomes import (
        COMPARISON_OUTCOME_PREDECLARATION_PATH,
        COMPARISON_OUTCOME_SEAL_PATH,
        ComparisonArmOutcome,
        finalize_comparison_outcomes,
        predeclare_comparison_outcomes,
        seal_comparison_outcomes,
        verify_comparison_outcomes,
        write_comparison_arm_outcome_once,
    )

    original_root = tmp_path / "original"
    replacement_root = tmp_path / "replacement"
    original = predeclare_comparison_outcomes(
        original_root,
        authority_id="d" * 64,
        manifest_sha256="a" * 64,
        case_bindings={"case-1": "b" * 64},
        repeats=1,
    )
    replacement = predeclare_comparison_outcomes(
        replacement_root,
        authority_id="e" * 64,
        manifest_sha256="f" * 64,
        case_bindings={"case-1": "c" * 64},
        repeats=1,
    )
    for authority in (original, replacement):
        for slot in authority.slots:
            write_comparison_arm_outcome_once(
                authority,
                slot,
                ComparisonArmOutcome(
                    task_status=TaskStatus.COMPLETED,
                    abstain_reason=None,
                    surfaced_findings=(),
                    product_measurement=(
                        replace(
                            _measurement_record(
                                findings=(),
                                eligible_defect_ids=(),
                                truth_status="unadjudicated",
                            ),
                            case_id=slot.case_id,
                            arm=slot.arm,
                            repeat=slot.repeat,
                        )
                        if slot.arm == ARM_PRODUCT
                        else None
                    ),
                    paid_calls_sha256=hashlib.sha256(b"[]").hexdigest(),
                    wall_time_s=1.0,
                    tool_cost_s=None,
                ),
            )
    checkpoint_root = tmp_path / "original-checkpoint"
    checkpoint_root.mkdir()
    authority_root = tmp_path / "original-owner"
    launch = _comparison_launch(
        original,
        checkpoint_root=checkpoint_root,
        authority_root=authority_root,
        run_identity="1" * 64,
    )
    final = finalize_comparison_outcomes(
        original,
        launch,
        checkpoint_root=checkpoint_root,
        authority_root=authority_root,
    )
    seal_comparison_outcomes(replacement)

    for relative_path in (
        COMPARISON_OUTCOME_PREDECLARATION_PATH,
        *(slot.relative_path for slot in replacement.slots),
        COMPARISON_OUTCOME_SEAL_PATH,
    ):
        (original_root / relative_path).write_bytes(
            (replacement_root / relative_path).read_bytes()
        )

    with pytest.raises(ValueError, match="predeclaration|frozen|digest"):
        verify_comparison_outcomes(
            original_root,
            expected_final_receipt=final,
            expected_comparison_sha256=launch.comparison_sha256,
        )


def _write_complete_comparison_outcomes(authority, *, ruff_wall_time_s: float = 1.0):
    from attest.benchmark.measurement import TaskStatus
    from attest.benchmark.outcomes import (
        ComparisonArmOutcome,
        write_comparison_arm_outcome_once,
    )

    for slot in authority.slots:
        write_comparison_arm_outcome_once(
            authority,
            slot,
            ComparisonArmOutcome(
                task_status=TaskStatus.COMPLETED,
                abstain_reason=None,
                surfaced_findings=(),
                product_measurement=(
                    replace(
                        _measurement_record(
                            findings=(),
                            eligible_defect_ids=(),
                            truth_status="unadjudicated",
                        ),
                        case_id=slot.case_id,
                        arm=slot.arm,
                        repeat=slot.repeat,
                    )
                    if slot.arm == ARM_PRODUCT
                    else None
                ),
                paid_calls_sha256=hashlib.sha256(b"[]").hexdigest(),
                wall_time_s=(
                    ruff_wall_time_s if slot.arm == ARM_RUFF else 1.0
                ),
                tool_cost_s=None,
            ),
        )


def _comparison_launch(
    authority,
    *,
    checkpoint_root: Path,
    authority_root: Path,
    run_identity: str,
):
    from attest.benchmark.outcomes import (
        issue_comparison_launch_receipt,
        write_canonical_json_once,
    )

    comparison = write_canonical_json_once(
        checkpoint_root,
        "comparison.json",
        {"run_identity": run_identity},
    )
    return issue_comparison_launch_receipt(
        authority,
        checkpoint_root=checkpoint_root,
        authority_root=authority_root,
        run_identity=run_identity,
        comparison_sha256=comparison.sha256,
    )


def test_comparison_final_receipt_rejects_a_resealed_ruff_outcome_rewrite(
    tmp_path: Path,
) -> None:
    """An original owner receipt, not a self-consistent seal, authorizes bytes."""
    from attest.benchmark.outcomes import (
        COMPARISON_OUTCOME_SEAL_PATH,
        finalize_comparison_outcomes,
        predeclare_comparison_outcomes,
        read_comparison_final_receipt,
        read_comparison_launch_receipt,
        seal_comparison_outcomes,
        verify_comparison_outcomes,
        write_comparison_final_receipt_once,
        write_comparison_launch_receipt_once,
    )

    original_root = tmp_path / "original"
    forged_root = tmp_path / "forged"
    checkpoint_root = tmp_path / "checkpoint"
    authority_root = tmp_path / "owner-receipts"
    checkpoint_root.mkdir()
    original = predeclare_comparison_outcomes(
        original_root,
        authority_id="d" * 64,
        manifest_sha256="a" * 64,
        case_bindings={"case-1": "b" * 64},
        repeats=1,
    )
    forged = predeclare_comparison_outcomes(
        forged_root,
        authority_id=original.authority_id,
        manifest_sha256=original.manifest_sha256,
        case_bindings={"case-1": "b" * 64},
        repeats=1,
    )
    assert forged.predeclaration_sha256 == original.predeclaration_sha256
    _write_complete_comparison_outcomes(original)
    _write_complete_comparison_outcomes(forged, ruff_wall_time_s=9.0)
    launch = _comparison_launch(
        original,
        checkpoint_root=checkpoint_root,
        authority_root=authority_root,
        run_identity="1" * 64,
    )
    write_comparison_launch_receipt_once(authority_root, launch)
    assert read_comparison_launch_receipt(authority_root) == launch
    final = finalize_comparison_outcomes(
        original,
        launch,
        checkpoint_root=checkpoint_root,
        authority_root=authority_root,
    )
    write_comparison_final_receipt_once(
        authority_root,
        final,
        checkpoint_root=checkpoint_root,
        outcome_root=original.root,
    )
    assert read_comparison_final_receipt(authority_root) == final
    seal_comparison_outcomes(forged)
    ruff_slot = next(slot for slot in original.slots if slot.arm == ARM_RUFF)
    (original_root / ruff_slot.relative_path).write_bytes(
        (forged_root / ruff_slot.relative_path).read_bytes()
    )
    (original_root / COMPARISON_OUTCOME_SEAL_PATH).write_bytes(
        (forged_root / COMPARISON_OUTCOME_SEAL_PATH).read_bytes()
    )

    with pytest.raises(
        ValueError, match="seal differs from its external final receipt|outcome tree"
    ):
        verify_comparison_outcomes(
            original_root,
            expected_final_receipt=final,
            expected_comparison_sha256=launch.comparison_sha256,
        )


def test_comparison_run_receipts_are_not_interchangeable_between_roots(
    tmp_path: Path,
) -> None:
    """Two legal runs of one plan have different launch/final authority."""
    from attest.benchmark.outcomes import (
        finalize_comparison_outcomes,
        predeclare_comparison_outcomes,
        verify_comparison_outcomes,
    )

    authorities = tuple(
        predeclare_comparison_outcomes(
            tmp_path / name,
            authority_id=authority_id,
            manifest_sha256="a" * 64,
            case_bindings={"case-1": "b" * 64},
            repeats=1,
        )
        for name, authority_id in (("run-a", "d" * 64), ("run-b", "e" * 64))
    )
    finals = []
    for ordinal, authority in enumerate(authorities, start=1):
        _write_complete_comparison_outcomes(authority)
        checkpoint_root = tmp_path / f"checkpoint-{ordinal}"
        checkpoint_root.mkdir()
        authority_root = tmp_path / f"owner-{ordinal}"
        launch = _comparison_launch(
            authority,
            checkpoint_root=checkpoint_root,
            authority_root=authority_root,
            run_identity=str(ordinal) * 64,
        )
        finals.append(
            finalize_comparison_outcomes(
                authority,
                launch,
                checkpoint_root=checkpoint_root,
                authority_root=authority_root,
            )
        )

    assert finals[0].digest_sha256 != finals[1].digest_sha256
    with pytest.raises(ValueError, match="final|receipt|root|authority"):
        verify_comparison_outcomes(
            authorities[1].root,
            expected_final_receipt=finals[0],
            expected_comparison_sha256=finals[0].launch.comparison_sha256,
        )


@pytest.mark.parametrize("swapped_root", ("checkpoint", "authority"))
def test_comparison_finalization_revalidates_every_launch_root_before_seal(
    tmp_path: Path, swapped_root: str
) -> None:
    from attest.benchmark.outcomes import (
        COMPARISON_OUTCOME_SEAL_PATH,
        finalize_comparison_outcomes,
        predeclare_comparison_outcomes,
    )

    outcome = predeclare_comparison_outcomes(
        tmp_path / "outcomes",
        authority_id="d" * 64,
        manifest_sha256="a" * 64,
        case_bindings={"case-1": "b" * 64},
        repeats=1,
    )
    _write_complete_comparison_outcomes(outcome)
    checkpoint_root = tmp_path / "checkpoint"
    authority_root = tmp_path / "owner"
    checkpoint_root.mkdir()
    launch = _comparison_launch(
        outcome,
        checkpoint_root=checkpoint_root,
        authority_root=authority_root,
        run_identity="1" * 64,
    )
    target = checkpoint_root if swapped_root == "checkpoint" else authority_root
    moved = target.with_name(target.name + "-original")
    target.rename(moved)
    target.mkdir()

    with pytest.raises(ValueError, match="root.*(identity|launch)|launch.*root"):
        finalize_comparison_outcomes(
            outcome,
            launch,
            checkpoint_root=checkpoint_root,
            authority_root=authority_root,
        )

    assert not (outcome.root / COMPARISON_OUTCOME_SEAL_PATH).exists()


def test_comparison_launch_rejects_run_identity_that_differs_from_comparison(
    tmp_path: Path,
) -> None:
    from attest.benchmark.outcomes import (
        issue_comparison_launch_receipt,
        predeclare_comparison_outcomes,
        write_canonical_json_once,
    )

    outcome = predeclare_comparison_outcomes(
        tmp_path / "outcomes",
        authority_id="d" * 64,
        manifest_sha256="a" * 64,
        case_bindings={"case-1": "b" * 64},
        repeats=1,
    )
    checkpoint_root = tmp_path / "checkpoint"
    checkpoint_root.mkdir()
    comparison = write_canonical_json_once(
        checkpoint_root,
        "comparison.json",
        {"run_identity": "1" * 64},
    )

    with pytest.raises(ValueError, match="run identity"):
        issue_comparison_launch_receipt(
            outcome,
            checkpoint_root=checkpoint_root,
            authority_root=tmp_path / "owner",
            run_identity="2" * 64,
            comparison_sha256=comparison.sha256,
        )


def test_comparison_finalization_rejects_fresh_comparison_document_drift(
    tmp_path: Path,
) -> None:
    from attest.benchmark.outcomes import (
        COMPARISON_OUTCOME_SEAL_PATH,
        canonical_json_bytes,
        finalize_comparison_outcomes,
        predeclare_comparison_outcomes,
    )

    outcome = predeclare_comparison_outcomes(
        tmp_path / "outcomes",
        authority_id="d" * 64,
        manifest_sha256="a" * 64,
        case_bindings={"case-1": "b" * 64},
        repeats=1,
    )
    _write_complete_comparison_outcomes(outcome)
    checkpoint_root = tmp_path / "checkpoint"
    authority_root = tmp_path / "owner"
    checkpoint_root.mkdir()
    launch = _comparison_launch(
        outcome,
        checkpoint_root=checkpoint_root,
        authority_root=authority_root,
        run_identity="1" * 64,
    )
    (checkpoint_root / "comparison.json").write_bytes(
        canonical_json_bytes({"run_identity": "2" * 64})
    )

    with pytest.raises(ValueError, match="comparison.json|comparison.*(digest|identity)"):
        finalize_comparison_outcomes(
            outcome,
            launch,
            checkpoint_root=checkpoint_root,
            authority_root=authority_root,
        )

    assert not (outcome.root / COMPARISON_OUTCOME_SEAL_PATH).exists()


@pytest.mark.parametrize("rogue_kind", ("file", "directory"))
def test_comparison_verifier_rejects_rogue_top_level_outcome_entry(
    tmp_path: Path, rogue_kind: str
) -> None:
    from attest.benchmark.outcomes import (
        finalize_comparison_outcomes,
        predeclare_comparison_outcomes,
        verify_comparison_outcomes,
    )

    outcome = predeclare_comparison_outcomes(
        tmp_path / "outcomes",
        authority_id="d" * 64,
        manifest_sha256="a" * 64,
        case_bindings={"case-1": "b" * 64},
        repeats=1,
    )
    _write_complete_comparison_outcomes(outcome)
    checkpoint_root = tmp_path / "checkpoint"
    authority_root = tmp_path / "owner"
    checkpoint_root.mkdir()
    launch = _comparison_launch(
        outcome,
        checkpoint_root=checkpoint_root,
        authority_root=authority_root,
        run_identity="1" * 64,
    )
    final = finalize_comparison_outcomes(
        outcome,
        launch,
        checkpoint_root=checkpoint_root,
        authority_root=authority_root,
    )
    rogue = outcome.root / "rogue"
    if rogue_kind == "file":
        rogue.write_text("unbound\n", encoding="utf-8")
    else:
        rogue.mkdir()

    with pytest.raises(ValueError, match="rogue|unrecognized|outcome root"):
        verify_comparison_outcomes(
            outcome.root,
            expected_final_receipt=final,
            expected_comparison_sha256=launch.comparison_sha256,
        )


def test_comparison_final_receipt_write_rejects_stale_outcome_bytes(
    tmp_path: Path,
) -> None:
    from attest.benchmark.outcomes import (
        COMPARISON_FINAL_RECEIPT_PATH,
        COMPARISON_OUTCOME_SEAL_PATH,
        canonical_json_bytes,
        finalize_comparison_outcomes,
        predeclare_comparison_outcomes,
        seal_comparison_outcomes,
        write_comparison_final_receipt_once,
        write_comparison_launch_receipt_once,
    )

    outcome = predeclare_comparison_outcomes(
        tmp_path / "outcomes",
        authority_id="d" * 64,
        manifest_sha256="a" * 64,
        case_bindings={"case-1": "b" * 64},
        repeats=1,
    )
    _write_complete_comparison_outcomes(outcome)
    checkpoint_root = tmp_path / "checkpoint"
    authority_root = tmp_path / "owner"
    checkpoint_root.mkdir()
    launch = _comparison_launch(
        outcome,
        checkpoint_root=checkpoint_root,
        authority_root=authority_root,
        run_identity="1" * 64,
    )
    write_comparison_launch_receipt_once(authority_root, launch)
    final = finalize_comparison_outcomes(
        outcome,
        launch,
        checkpoint_root=checkpoint_root,
        authority_root=authority_root,
    )
    ruff_slot = next(slot for slot in outcome.slots if slot.arm == ARM_RUFF)
    ruff_path = outcome.root / ruff_slot.relative_path
    rewritten = json.loads(ruff_path.read_bytes())
    rewritten["outcome"]["wall_time_s"] = 9.0
    ruff_path.write_bytes(canonical_json_bytes(rewritten))
    (outcome.root / COMPARISON_OUTCOME_SEAL_PATH).unlink()
    seal_comparison_outcomes(outcome)

    with pytest.raises(ValueError, match="seal|outcome tree|final receipt"):
        write_comparison_final_receipt_once(
            authority_root,
            final,
            checkpoint_root=checkpoint_root,
            outcome_root=outcome.root,
        )

    assert not (authority_root / COMPARISON_FINAL_RECEIPT_PATH).exists()


def _finding(
    finding_id: str,
    *,
    status: str = "published",
    accuracy: str = "correct",
    defect_id: str | None = "defect-1",
    authority: str = "automated",
):
    from attest.benchmark.measurement import (
        AccuracyStatus,
        FindingAuthority,
        FindingOutcome,
        FindingStatus,
    )

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
    findings=(),
    repeat: int = 0,
    eligible_defect_ids: tuple[str, ...] = ("defect-1",),
    pull_request_number: int = 17,
    truth_status: str = "positive",
):
    from attest.benchmark.measurement import (
        CURRENT_MEASUREMENT_SCHEMA_VERSION,
        CURRENT_MEASUREMENT_SEMANTICS,
        DELIVERY_TRANSCRIPT_PROTOCOL,
        DELIVERY_TRANSCRIPT_SCHEMA_VERSION,
        EMPTY_DELIVERY_TRANSCRIPT_SHA256,
        DeliveryStatus,
        DeliveryTranscriptReceipt,
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

    stop_kind = StopKind(stop)
    task_status = derive_task_status(stop_kind, tuple(findings))
    published_count = sum(finding.author_visible for finding in findings)
    unresolved_count = sum(
        finding.finding_status.value == "unresolved" for finding in findings
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
        findings=tuple(findings),
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


def _repeat_record(primary, repeat: int):
    event_id = f"repeat-{repeat}:publication"
    finding_by_id = {
        finding.finding_id: replace(
            finding,
            publication_event_ids=((event_id,) if finding.author_visible else ()),
        )
        for finding in primary.findings
    }
    return replace(
        primary,
        repeat=repeat,
        findings=tuple(finding_by_id[finding.finding_id] for finding in primary.findings),
        publication_events=tuple(
            replace(
                event,
                event_id=event_id,
                delivered_at_s=5.0 + repeat,
            )
            for event in primary.publication_events
        ),
    )


def _synthetic_delivery_transcript(record, attempt_count: int):
    from attest.benchmark.measurement import EMPTY_DELIVERY_TRANSCRIPT_SHA256

    return replace(
        record.delivery_transcript,
        task_id=("task:measurement" if attempt_count else None),
        expected_attempt_count=attempt_count,
        last_attempt_ordinal=(attempt_count - 1 if attempt_count else None),
        transcript_sha256=(
            "f" * 64 if attempt_count else EMPTY_DELIVERY_TRANSCRIPT_SHA256
        ),
    )


@pytest.mark.parametrize("published", [0, 1, 4])
@pytest.mark.parametrize(
    ("stop", "expected"),
    [
        ("none", "completed"),
        ("candidate_defer", None),
        ("task_defer", None),
        ("failure", "failed"),
    ],
)
def test_task_status_matrix_keeps_publication_independent_from_stop(
    published: int,
    stop: str,
    expected: str | None,
) -> None:
    from attest.benchmark.measurement import derive_task_status

    findings = tuple(_finding(f"finding-{index}") for index in range(published))
    if stop == "candidate_defer":
        findings += (
            _finding(
                "candidate-unresolved",
                status="unresolved",
                accuracy="unadjudicated",
                defect_id=None,
            ),
        )
    actual = derive_task_status(stop, findings)
    expected_status = expected or ("partially_deferred" if published else "fully_deferred")

    assert actual.value == expected_status
    assert sum(finding.author_visible for finding in findings) == published
    record = _measurement_record(stop=stop, findings=findings)
    from attest.benchmark.measurement import reduce_measurements

    summary = reduce_measurements((record,))
    assert getattr(summary, expected_status) == 1
    assert summary.published == published
    assert summary.eligible_defects == 1
    assert summary.detected_defects == (1 if published else 0)
    assert summary.missed_defects == (0 if published else 1)


@pytest.mark.parametrize("resolved_status", ["certified_suppressed", "rejected"])
def test_defer_with_a_resolved_nonpublication_is_partially_deferred(
    resolved_status: str,
) -> None:
    from attest.benchmark.measurement import derive_task_status

    findings = (
        _finding(
            "resolved",
            status=resolved_status,
            accuracy="not_applicable",
            defect_id=None,
        ),
        _finding(
            "unresolved",
            status="unresolved",
            accuracy="unadjudicated",
            defect_id=None,
        ),
    )

    assert derive_task_status("candidate_defer", findings).value == "partially_deferred"


def test_stop_none_cannot_coexist_with_an_unresolved_outcome() -> None:
    with pytest.raises(ValueError, match="stop.*unresolved|unresolved.*stop"):
        _measurement_record(
            findings=(
                _finding(
                    "unresolved",
                    status="unresolved",
                    accuracy="unadjudicated",
                    defect_id=None,
                ),
            )
        )


def test_explicit_task_status_must_equal_the_derived_status() -> None:
    from attest.benchmark.measurement import TaskStatus

    record = _measurement_record(findings=(_finding("published"),))

    with pytest.raises(ValueError, match="task_status"):
        replace(record, task_status=TaskStatus.FAILED)


def test_measurement_reducer_uses_finding_accuracy_and_eligible_defects() -> None:
    from attest.benchmark.measurement import reduce_measurements

    record = _measurement_record(
        findings=(
            _finding("correct", accuracy="correct", defect_id="defect-1"),
            _finding("wrong", accuracy="wrong", defect_id=None),
            _finding("unknown", accuracy="unadjudicated", defect_id=None),
        ),
    )

    summary = reduce_measurements((record,))

    assert summary.published == 3
    assert summary.correct == 1
    assert summary.wrong == 1
    assert summary.unadjudicated == 1
    assert summary.finding_precision == pytest.approx(0.5)
    assert summary.eligible_defects == 1
    assert summary.detected_defects == 1
    assert summary.missed_defects == 0
    assert summary.detection_rate == pytest.approx(1.0)
    assert summary.null_pull_requests == 0
    assert summary.pr_false_positive_events == 0
    assert summary.pr_false_positive_rate is None
    assert summary.adjudicated_pull_requests == 0
    assert summary.pr_any_wrong_events is None
    assert summary.pr_any_wrong_rate is None
    assert summary.pr_any_wrong_withheld_reason == (
        "visible_finding_accuracy_incomplete"
    )


def test_measurement_reducer_counts_harm_only_for_adjudicated_null_prs() -> None:
    from attest.benchmark.measurement import reduce_measurements

    record = _measurement_record(
        findings=(_finding("wrong", accuracy="wrong", defect_id=None),),
        eligible_defect_ids=(),
        truth_status="null",
    )

    summary = reduce_measurements((record,))

    assert summary.null_pull_requests == 1
    assert summary.pr_false_positive_events == 1
    assert summary.pr_false_positive_rate == pytest.approx(1.0)
    assert summary.adjudicated_pull_requests == 1
    assert summary.pr_any_wrong_events == 1
    assert summary.pr_any_wrong_rate == pytest.approx(1.0)


def test_adjudicated_null_pr_cannot_hide_an_automated_publication_as_unadjudicated(
) -> None:
    with pytest.raises(ValueError, match="null.*automated.*wrong|automated.*null.*wrong"):
        _measurement_record(
            findings=(
                _finding("hidden-harm", accuracy="unadjudicated", defect_id=None),
            ),
            eligible_defect_ids=(),
            truth_status="null",
        )


@pytest.mark.parametrize(
    ("terminal_status", "findings", "expected_stop", "expected_task"),
    (
        ("completed", (), "none", "completed"),
        (
            "completed",
            (
                _finding(
                    "unresolved",
                    status="unresolved",
                    accuracy="unadjudicated",
                    defect_id=None,
                ),
            ),
            "task_defer",
            "fully_deferred",
        ),
        (
            "deferred",
            (
                _finding("published"),
                _finding(
                    "unresolved",
                    status="unresolved",
                    accuracy="unadjudicated",
                    defect_id=None,
                ),
            ),
            "candidate_defer",
            "partially_deferred",
        ),
        ("deferred", (_finding("published"),), "task_defer", "partially_deferred"),
        ("failed", (_finding("published"),), "failure", "failed"),
    ),
)
def test_terminal_status_derives_stop_without_reason_text(
    terminal_status: str,
    findings: tuple,
    expected_stop: str,
    expected_task: str,
) -> None:
    from attest.benchmark.measurement import (
        TaskDeliveryTerminalStatus,
        derive_stop_kind,
        derive_task_status,
    )

    stop = derive_stop_kind(TaskDeliveryTerminalStatus(terminal_status), findings)
    assert stop.value == expected_stop
    assert derive_task_status(stop, findings).value == expected_task


def test_any_wrong_metric_withholds_a_pr_with_visible_unadjudicated_findings() -> None:
    from attest.benchmark.measurement import reduce_measurements

    record = _measurement_record(
        findings=(
            _finding("known", accuracy="correct"),
            _finding("unknown", accuracy="unadjudicated", defect_id=None),
        ),
    )

    summary = reduce_measurements((record,))
    assert summary.correct == 1
    assert summary.unadjudicated == 1
    assert summary.adjudicated_pull_requests == 0
    assert summary.pr_any_wrong_events is None
    assert summary.pr_any_wrong_rate is None
    assert summary.pr_any_wrong_withheld_reason == "visible_finding_accuracy_incomplete"


def test_finding_delivery_uses_earliest_successful_batch_event() -> None:
    from attest.benchmark.measurement import (
        DeliveryStatus,
        PublicationChannel,
        PublicationEvent,
        PublicationOutcome,
    )

    record = _measurement_record(findings=(_finding("published"),))
    first = record.publication_events[0]
    late = PublicationEvent(
        event_id="publication:summary",
        attempt_id="attempt:summary",
        attempt_ordinal=1,
        repository="local/project",
        pull_request_number=17,
        head_sha="1" * 40,
        members=first.members,
        channel=PublicationChannel.INLINE_REVIEW,
        outcome=PublicationOutcome.SUCCEEDED,
        body_sha256="b" * 64,
        request_sha256="e" * 64,
        remote_response_id="102",
        delivered_at_s=70.0,
        deadline_s=60.0,
    )
    finding = replace(
        record.findings[0],
        publication_event_ids=(first.event_id, late.event_id),
    )

    duplicated = replace(
        record,
        findings=(finding,),
        publication_events=(first, late),
        delivery_transcript=_synthetic_delivery_transcript(record, 2),
        delivery_status=DeliveryStatus.PUBLISHED_ON_TIME,
    )

    assert duplicated.delivery_status is DeliveryStatus.PUBLISHED_ON_TIME


def test_known_on_time_success_before_ambiguity_does_not_withhold_delivery() -> None:
    from attest.benchmark.measurement import (
        PublicationChannel,
        PublicationEvent,
        PublicationOutcome,
        reduce_measurements,
    )

    record = _measurement_record(findings=(_finding("published"),))
    success = replace(
        record.publication_events[0],
        attempt_id="attempt:success",
        attempt_ordinal=0,
    )
    ambiguous = PublicationEvent(
        event_id="publication:ambiguous-later",
        attempt_id="attempt:ambiguous-later",
        attempt_ordinal=1,
        repository="local/project",
        pull_request_number=17,
        head_sha="1" * 40,
        members=success.members,
        channel=PublicationChannel.INLINE_REVIEW,
        outcome=PublicationOutcome.AMBIGUOUS,
        body_sha256="c" * 64,
        request_sha256="f" * 64,
        remote_response_id=None,
        delivered_at_s=None,
        deadline_s=60.0,
    )
    record = replace(
        record,
        publication_events=(success, ambiguous),
        delivery_transcript=_synthetic_delivery_transcript(record, 2),
    )

    summary = reduce_measurements((record,))

    assert record.delivery_withheld_reason is None
    assert summary.delivery_withheld_reason is None
    assert summary.published == 1


def test_successful_summary_task_view_cannot_hide_its_publication_members() -> None:
    from attest.benchmark.measurement import (
        DeliveryStatus,
        PublicationChannel,
        PublicationOutcome,
        StopKind,
        TaskDeliveryEvent,
        TaskDeliveryTerminalStatus,
        derive_task_status,
    )

    record = _measurement_record(findings=(_finding("published"),))
    publication = replace(
        record.publication_events[0], channel=PublicationChannel.STATUS_SUMMARY
    )
    task_event = TaskDeliveryEvent(
        event_id="task:summary",
        attempt_id=publication.attempt_id,
        attempt_ordinal=publication.attempt_ordinal,
        repository=publication.repository,
        pull_request_number=publication.pull_request_number,
        head_sha=publication.head_sha,
        channel=publication.channel,
        members=publication.members,
        terminal_status=TaskDeliveryTerminalStatus.COMPLETED,
        outcome=PublicationOutcome.SUCCEEDED,
        body_sha256=publication.body_sha256,
        request_sha256=publication.request_sha256,
        remote_response_id=publication.remote_response_id,
        delivered_at_s=publication.delivered_at_s,
        deadline_s=publication.deadline_s,
    )
    unresolved = _finding(
        "published",
        status="unresolved",
        accuracy="unadjudicated",
        defect_id=None,
    )
    stop_kind = StopKind.TASK_DEFER

    with pytest.raises(ValueError, match="publication|members|attempt"):
        replace(
            record,
            stop_kind=stop_kind,
            task_status=derive_task_status(stop_kind, (unresolved,)),
            findings=(unresolved,),
            delivery_status=DeliveryStatus.NO_PUBLICATION,
            published_count=0,
            unresolved_count=1,
            publication_events=(),
            task_delivery_events=(task_event,),
        )


def test_inline_publication_cannot_share_a_status_task_delivery_attempt() -> None:
    from attest.benchmark.measurement import (
        PublicationChannel,
        PublicationOutcome,
        TaskDeliveryEvent,
        TaskDeliveryTerminalStatus,
    )

    record = _measurement_record(findings=(_finding("published"),))
    publication = record.publication_events[0]
    task_event = TaskDeliveryEvent(
        event_id="task:forged-inline-pair",
        attempt_id=publication.attempt_id,
        attempt_ordinal=publication.attempt_ordinal,
        repository=publication.repository,
        pull_request_number=publication.pull_request_number,
        head_sha=publication.head_sha,
        channel=PublicationChannel.STATUS_SUMMARY,
        members=publication.members,
        terminal_status=TaskDeliveryTerminalStatus.COMPLETED,
        outcome=PublicationOutcome.SUCCEEDED,
        body_sha256=publication.body_sha256,
        request_sha256=publication.request_sha256,
        remote_response_id=publication.remote_response_id,
        delivered_at_s=publication.delivered_at_s,
        deadline_s=publication.deadline_s,
    )

    with pytest.raises(ValueError, match="channel|attempt|publication"):
        replace(record, task_delivery_events=(task_event,))


def test_empty_status_task_view_cannot_share_an_inline_publication_attempt() -> None:
    from attest.benchmark.measurement import (
        PublicationChannel,
        PublicationOutcome,
        TaskDeliveryEvent,
        TaskDeliveryTerminalStatus,
    )

    record = _measurement_record(findings=(_finding("published"),))
    publication = record.publication_events[0]
    task_event = TaskDeliveryEvent(
        event_id="task:forged-empty-inline-pair",
        attempt_id=publication.attempt_id,
        attempt_ordinal=publication.attempt_ordinal,
        repository=publication.repository,
        pull_request_number=publication.pull_request_number,
        head_sha=publication.head_sha,
        channel=PublicationChannel.STATUS_SUMMARY,
        members=(),
        terminal_status=TaskDeliveryTerminalStatus.COMPLETED,
        outcome=PublicationOutcome.SUCCEEDED,
        body_sha256=publication.body_sha256,
        request_sha256=publication.request_sha256,
        remote_response_id=publication.remote_response_id,
        delivered_at_s=publication.delivered_at_s,
        deadline_s=publication.deadline_s,
    )

    with pytest.raises(ValueError, match="channel|attempt|publication"):
        replace(record, task_delivery_events=(task_event,))


def test_delivery_attempt_ordinal_is_globally_bound_to_one_attempt_id() -> None:
    from attest.benchmark.measurement import (
        PublicationChannel,
        PublicationOutcome,
        TaskDeliveryEvent,
        TaskDeliveryTerminalStatus,
    )

    record = _measurement_record(findings=(_finding("published"),))
    publication = record.publication_events[0]
    task_event = TaskDeliveryEvent(
        event_id="task:different-attempt-same-ordinal",
        attempt_id="attempt:different",
        attempt_ordinal=publication.attempt_ordinal,
        repository=publication.repository,
        pull_request_number=publication.pull_request_number,
        head_sha=publication.head_sha,
        channel=PublicationChannel.STATUS_SUMMARY,
        members=(),
        terminal_status=TaskDeliveryTerminalStatus.COMPLETED,
        outcome=PublicationOutcome.SUCCEEDED,
        body_sha256="b" * 64,
        request_sha256="c" * 64,
        remote_response_id="102",
        delivered_at_s=6.0,
        deadline_s=publication.deadline_s,
    )

    with pytest.raises(ValueError, match="global|ordinal|bijection"):
        replace(record, task_delivery_events=(task_event,))


def test_measurement_event_rejects_a_noncanonical_response_identity() -> None:
    record = _measurement_record(findings=(_finding("published"),))

    with pytest.raises(ValueError, match="response|identity|canonical|positive"):
        replace(record.publication_events[0], remote_response_id=" ")


@pytest.mark.parametrize("event_kind", ("publication", "task"))
def test_delivery_event_numbers_have_one_canonical_byte_representation(
    event_kind: str,
) -> None:
    from attest.benchmark.measurement import (
        PublicationChannel,
        PublicationOutcome,
        TaskDeliveryEvent,
        TaskDeliveryTerminalStatus,
        decode_measurement_record,
    )
    from attest.benchmark.outcomes import canonical_json_bytes

    if event_kind == "publication":
        record = _measurement_record(findings=(_finding("published"),))
        event = replace(
            record.publication_events[0], delivered_at_s=5, deadline_s=60
        )
        record = replace(record, publication_events=(event,))
    else:
        record = _measurement_record(findings=())
        event = TaskDeliveryEvent(
            event_id="task:one",
            attempt_id="attempt:one",
            attempt_ordinal=0,
            repository="local/project",
            pull_request_number=17,
            head_sha="1" * 40,
            channel=PublicationChannel.STATUS_SUMMARY,
            members=(),
            terminal_status=TaskDeliveryTerminalStatus.COMPLETED,
            outcome=PublicationOutcome.SUCCEEDED,
            body_sha256="a" * 64,
            request_sha256="b" * 64,
            remote_response_id="102",
            delivered_at_s=5,
            deadline_s=60,
        )
        record = replace(
            record,
            task_delivery_events=(event,),
            delivery_transcript=_synthetic_delivery_transcript(record, 1),
        )

    payload = record.to_json_dict()
    decoded = decode_measurement_record(payload)
    assert canonical_json_bytes(payload) == canonical_json_bytes(
        decoded.to_json_dict()
    )


def test_delivery_events_cover_every_sealed_transcript_attempt() -> None:
    record = _measurement_record(findings=(_finding("published"),))
    forged_transcript = replace(
        record.delivery_transcript,
        expected_attempt_count=2,
        last_attempt_ordinal=1,
        transcript_sha256="f" * 64,
    )

    with pytest.raises(ValueError, match="transcript|attempt|ordinal"):
        replace(record, delivery_transcript=forged_transcript)


def test_task_delivery_ambiguity_with_later_success_has_no_point_estimate() -> None:
    from attest.benchmark.measurement import (
        PublicationChannel,
        PublicationOutcome,
        TaskDeliveryEvent,
        TaskDeliveryTerminalStatus,
        reduce_measurements,
    )

    record = _measurement_record(findings=())
    common = {
        "repository": "local/project",
        "pull_request_number": 17,
        "head_sha": "1" * 40,
        "channel": PublicationChannel.STATUS_SUMMARY,
        "members": (),
        "terminal_status": TaskDeliveryTerminalStatus.COMPLETED,
        "deadline_s": 60.0,
    }
    ambiguous = TaskDeliveryEvent(
        event_id="task:ambiguous",
        attempt_id="attempt:ambiguous",
        attempt_ordinal=0,
        outcome=PublicationOutcome.AMBIGUOUS,
        body_sha256="a" * 64,
        request_sha256="b" * 64,
        remote_response_id=None,
        delivered_at_s=None,
        **common,
    )
    success = TaskDeliveryEvent(
        event_id="task:success",
        attempt_id="attempt:success",
        attempt_ordinal=1,
        outcome=PublicationOutcome.SUCCEEDED,
        body_sha256="c" * 64,
        request_sha256="d" * 64,
        remote_response_id="102",
        delivered_at_s=70.0,
        **common,
    )
    record = replace(
        record,
        task_delivery_events=(ambiguous, success),
        delivery_transcript=_synthetic_delivery_transcript(record, 2),
        task_delivery_withheld_reason="ambiguous_task_delivery",
    )

    summary = reduce_measurements((record,))

    assert summary.task_delivery_withheld_reason == "ambiguous_task_delivery"
    assert summary.task_delivered is None


def test_unresolved_ambiguous_publication_withholds_quality_metrics() -> None:
    from attest.benchmark.measurement import (
        PublicationChannel,
        PublicationEvent,
        PublicationMember,
        PublicationOutcome,
        PublicationPlacement,
        reduce_measurements,
    )

    unresolved = _finding(
        "ambiguous",
        status="unresolved",
        accuracy="unadjudicated",
        defect_id=None,
    )
    record = _measurement_record(stop="task_defer", findings=(unresolved,))
    ambiguous = PublicationEvent(
        event_id="attempt:ambiguous",
        attempt_id="attempt:ambiguous",
        attempt_ordinal=0,
        repository="local/project",
        pull_request_number=17,
        head_sha="1" * 40,
        members=(
            PublicationMember(
                finding_id="ambiguous", placement=PublicationPlacement.INLINE
            ),
        ),
        channel=PublicationChannel.INLINE_REVIEW,
        outcome=PublicationOutcome.AMBIGUOUS,
        body_sha256="c" * 64,
        request_sha256="f" * 64,
        remote_response_id=None,
        delivered_at_s=None,
        deadline_s=60.0,
    )
    record = replace(
        record,
        publication_events=(ambiguous,),
        delivery_transcript=_synthetic_delivery_transcript(record, 1),
        metrics_withheld_reason="ambiguous_publication",
        delivery_withheld_reason="ambiguous_publication",
    )

    summary = reduce_measurements((record,))

    assert summary.metrics_withheld_reason == "ambiguous_publication"
    assert summary.delivery_withheld_reason == "ambiguous_publication"
    assert summary.published is None
    assert summary.correct is None
    assert summary.wrong is None
    assert summary.detected_defects is None
    assert summary.pr_false_positive_events is None
    assert summary.pr_any_wrong_events is None
    assert summary.finding_precision is None
    assert summary.detection_rate is None
    assert summary.missed_defects is None


def test_ambiguous_attempt_followed_by_late_success_withholds_only_delivery() -> None:
    from attest.benchmark.measurement import (
        DeliveryStatus,
        PublicationChannel,
        PublicationEvent,
        PublicationOutcome,
        reduce_measurements,
    )

    record = _measurement_record(findings=(_finding("published"),))
    success = replace(
        record.publication_events[0],
        event_id="attempt:success",
        attempt_id="attempt:success",
        attempt_ordinal=1,
        delivered_at_s=70.0,
        request_sha256="e" * 64,
        remote_response_id="103",
    )
    ambiguous = PublicationEvent(
        event_id="attempt:ambiguous",
        attempt_id="attempt:ambiguous",
        attempt_ordinal=0,
        repository="local/project",
        pull_request_number=17,
        head_sha="1" * 40,
        members=success.members,
        channel=PublicationChannel.INLINE_REVIEW,
        outcome=PublicationOutcome.AMBIGUOUS,
        body_sha256="c" * 64,
        request_sha256="f" * 64,
        remote_response_id=None,
        delivered_at_s=None,
        deadline_s=60.0,
    )
    finding = replace(
        record.findings[0], publication_event_ids=(success.event_id,)
    )
    record = replace(
        record,
        findings=(finding,),
        publication_events=(ambiguous, success),
        delivery_transcript=_synthetic_delivery_transcript(record, 2),
        delivery_status=DeliveryStatus.PUBLISHED_LATE,
        delivery_withheld_reason="ambiguous_publication",
    )

    summary = reduce_measurements((record,))

    assert summary.metrics_withheld_reason is None
    assert summary.delivery_withheld_reason == "ambiguous_publication"
    assert summary.published == 1
    assert summary.correct == 1
    assert summary.finding_precision == 1.0


def test_measurement_reducer_treats_fully_deferred_positive_as_a_miss() -> None:
    from attest.benchmark.measurement import reduce_measurements

    record = _measurement_record(
        stop="task_defer",
        findings=(
            _finding(
                "task-unresolved",
                status="unresolved",
                accuracy="unadjudicated",
                defect_id=None,
            ),
        ),
    )

    summary = reduce_measurements((record,))

    assert summary.published == 0
    assert summary.unresolved == 1
    assert summary.finding_precision is None
    assert summary.eligible_defects == 1
    assert summary.detected_defects == 0
    assert summary.missed_defects == 1
    assert summary.detection_rate == pytest.approx(0.0)


def test_unadjudicated_only_publications_have_null_precision() -> None:
    from attest.benchmark.measurement import reduce_measurements

    summary = reduce_measurements(
        (
            _measurement_record(
                findings=(
                    _finding("unknown", accuracy="unadjudicated", defect_id=None),
                ),
            ),
        )
    )

    assert summary.finding_precision is None
    assert summary.unadjudicated == 1


def test_self_reported_findings_do_not_enter_automated_precision_or_pr_harm() -> None:
    from attest.benchmark.measurement import reduce_measurements

    positive_summary = reduce_measurements(
        (
            _measurement_record(
                findings=(
                    _finding("automated", accuracy="correct"),
                    _finding(
                        "self-reported",
                        accuracy="wrong",
                        defect_id=None,
                        authority="self_reported",
                    ),
                ),
            ),
        )
    )
    null_summary = reduce_measurements(
        (
            _measurement_record(
                findings=(
                    _finding(
                        "self-reported-null",
                        accuracy="wrong",
                        defect_id=None,
                        authority="self_reported",
                    ),
                ),
                eligible_defect_ids=(),
                truth_status="null",
            ),
        )
    )

    assert positive_summary.published == 2
    assert positive_summary.automated_published == 1
    assert positive_summary.finding_precision == pytest.approx(1.0)
    assert null_summary.published == 1
    assert null_summary.automated_published == 0
    assert null_summary.pr_false_positive_events == 0


def test_operational_repeats_do_not_inflate_semantic_sample_or_metrics() -> None:
    from attest.benchmark.measurement import reduce_measurements

    primary = _measurement_record(findings=(_finding("correct"),))
    repeats = tuple(_repeat_record(primary, repeat) for repeat in range(20))

    summary = reduce_measurements(repeats)

    assert summary.operational_repeats == 20
    assert summary.semantic_n == 1
    assert summary.published == 1
    assert summary.correct == 1
    assert summary.eligible_defects == 1
    assert summary.detected_defects == 1
    assert len(summary.unique_semantic_outcome_digests) == 1
    assert summary.semantic_agreement_rate == pytest.approx(1.0)


def test_operational_repeat_audit_counts_retain_all_publication_events() -> None:
    from attest.benchmark.measurement import reduce_measurements

    findings = tuple(_finding(f"published-{index}") for index in range(4)) + (
        _finding(
            "unresolved",
            status="unresolved",
            accuracy="unadjudicated",
            defect_id=None,
        ),
    )
    primary = _measurement_record(stop="candidate_defer", findings=findings)
    repeats = tuple(_repeat_record(primary, repeat) for repeat in range(20))

    forward = reduce_measurements(repeats)
    reverse = reduce_measurements(tuple(reversed(repeats)))

    assert forward == reverse
    assert forward.semantic_n == 1
    assert forward.operational_repeats == 20
    assert forward.published == 4
    assert forward.unresolved == 1
    assert forward.correct == 4
    assert forward.detected_defects == 1
    assert forward.operational_published == 80
    assert forward.operational_unresolved == 20
    assert forward.operational_correct == 80
    assert len(forward.unique_semantic_outcome_digests) == 1
    assert forward.semantic_agreement_rate == pytest.approx(1.0)


def test_operational_repeat_semantic_drift_is_retained_as_stability_data() -> None:
    from attest.benchmark.measurement import reduce_measurements

    primary = _measurement_record(findings=(_finding("finding"),))
    drifted = _repeat_record(primary, 1)
    drifted = replace(
        drifted,
        findings=(
            replace(
                drifted.findings[0],
                accuracy_status=type(drifted.findings[0].accuracy_status).WRONG,
                defect_id=None,
            ),
        ),
    )

    summary = reduce_measurements((primary, drifted))

    assert summary.semantic_n == 1
    assert summary.operational_repeats == 2
    assert len(summary.unique_semantic_outcome_digests) == 2
    assert summary.semantic_agreement_rate == pytest.approx(0.5)


def test_semantic_agreement_is_grouped_by_case_and_arm() -> None:
    from attest.benchmark.measurement import reduce_measurements

    case_one = _measurement_record(findings=(_finding("one"),))
    case_two = replace(
        _measurement_record(findings=(_finding("two"),)), case_id="case-2"
    )
    records = (
        case_one,
        _repeat_record(case_one, 1),
        case_two,
        _repeat_record(case_two, 1),
    )

    summary = reduce_measurements(tuple(reversed(records)))

    assert summary.semantic_n == 2
    assert summary.semantic_agreement_rate == 1.0
    assert summary.semantic_agreement_by_unit == (
        ("case-1", "product", 1.0),
        ("case-2", "product", 1.0),
    )


def test_reducer_refuses_to_merge_arm_sample_sizes() -> None:
    from attest.benchmark.measurement import reduce_measurements

    product = _measurement_record(findings=(_finding("product"),))
    ruff = replace(product, arm="ruff")

    with pytest.raises(ValueError, match="single arm|mixed arms"):
        reduce_measurements((product, ruff))


@pytest.mark.parametrize(
    "mutate",
    [
        lambda payload: {key: value for key, value in payload.items() if key != "task_status"},
        lambda payload: {**payload, "schema_version": 999},
        lambda payload: {**payload, "task_status": "future"},
        lambda payload: {**payload, "future_semantics": True},
        lambda payload: {
            **payload,
            "findings": [{**payload["findings"][0], "future_semantics": True}],
        },
    ],
    ids=["missing-status", "future-version", "future-enum", "extra", "nested-extra"],
)
def test_current_measurement_decoder_fails_closed_on_schema_drift(mutate) -> None:
    from attest.benchmark.measurement import decode_measurement_record

    payload = _measurement_record(findings=(_finding("correct"),)).to_json_dict()

    with pytest.raises(ValueError):
        decode_measurement_record(mutate(payload))


def test_current_measurement_decoder_round_trips_exact_schema() -> None:
    from attest.benchmark.measurement import decode_measurement_record

    record = _measurement_record(findings=(_finding("correct"),))

    assert decode_measurement_record(record.to_json_dict()) == record


def test_finding_and_record_cross_field_mutations_fail_closed() -> None:
    from attest.benchmark.measurement import AccuracyStatus, FindingStatus

    published = _finding("published")
    with pytest.raises(ValueError, match="publication_event_ids"):
        replace(published, publication_event_ids=())
    with pytest.raises(ValueError, match="non-published.*accuracy"):
        replace(
            published,
            finding_status=FindingStatus.CERTIFIED_SUPPRESSED,
            publication_event_ids=(),
        )
    with pytest.raises(ValueError, match="correct.*defect"):
        replace(published, defect_id=None)
    with pytest.raises(ValueError, match="accuracy"):
        replace(
            published,
            finding_status=FindingStatus.UNRESOLVED,
            publication_event_ids=(),
            accuracy_status=AccuracyStatus.CORRECT,
        )

    record = _measurement_record(findings=(published,))
    duplicate_id = published
    with pytest.raises(ValueError, match="duplicate finding_id"):
        replace(
            record,
            findings=(published, duplicate_id),
            candidate_count=2,
            published_count=2,
        )
    duplicate_event = record.publication_events[0]
    with pytest.raises(ValueError, match="duplicate publication event_id"):
        replace(
            record,
            publication_events=(duplicate_event, duplicate_event),
        )


def test_legacy_v1_decoder_is_explicit_and_always_withholds_metrics() -> None:
    from attest.benchmark.measurement import (
        LEGACY_V1_METRICS_WITHHELD,
        decode_legacy_v1_scoring,
        decode_measurement_record,
    )

    legacy = {
        "run_id": "legacy-run",
        "case_id": "case-1",
        "repeat": 0,
        "predictions": [
            {
                "finding_id": "legacy-finding",
                "case_id": "case-1",
                "file": "app.py",
                "line": 7,
                "placement": "inline",
                "action": "surface",
                "repro_status": "buggy_fail_fixed_pass",
                "evidence_class": "regression_reproduced",
            }
        ],
        "delivery_at_s": None,
        "deadline_s": 300.0,
    }

    decoded = decode_legacy_v1_scoring(legacy)
    assert decoded.metrics_withheld_reason == LEGACY_V1_METRICS_WITHHELD
    assert decoded.scoring_semantics == "legacy_v1_scoring"
    assert decoded.prediction_count == 1
    with pytest.raises(ValueError):
        decode_measurement_record(legacy)
    with pytest.raises(ValueError):
        decode_legacy_v1_scoring({**legacy, "future_semantics": True})


def test_comparison_publication_rejects_coordinated_outcome_rewrite(
    tmp_path: Path,
) -> None:
    """Removing findings and recomputing every caller aggregate cannot alter publication.

    Production mutation caught: publishing caller-owned ``ArmRun`` values instead of
    rebuilding them from a durable canonical outcome artifact.
    """
    plans, cassettes, manifest_path = _plans(tmp_path)
    execution = compare_arms(
        plans,
        provider_factory=lambda request: ReplayProvider(cassettes[request.case_id]),
        bare_provider_factory=lambda case_id: ReplayProvider(cassettes[case_id]),
        ruff_executable=_ruff_executable(),
        checkpoint_root=tmp_path / "comparison-state",
        **_comparison_authority(tmp_path / "comparison-state"),
    )
    measurements = execution.measurements
    original_product = next(summary for summary in measurements.arms if summary.arm == ARM_PRODUCT)
    assert original_product.accuracy.detection_rate == 1.0
    assert any(run.findings for run in measurements.runs if run.arm == ARM_PRODUCT)

    rewritten_runs = tuple(
        replace(run, findings=(), matched_defect_ids=())
        if run.arm == ARM_PRODUCT
        else run
        for run in measurements.runs
    )
    rewritten = replace(
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
    rewritten_product = next(summary for summary in rewritten.arms if summary.arm == ARM_PRODUCT)
    assert rewritten_product.accuracy.detection_rate == 0.0

    with pytest.raises(ValueError, match="authoritative.*outcome|outcome.*artifact"):
        build_comparison_report(
            load_manifest(manifest_path),
            rewritten,
            manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            validation_receipt=None,
            publication_authority=execution.publication_authority,
        )


def test_real_mixed_publications_remain_scored_when_one_candidate_defers(
    tmp_path: Path,
) -> None:
    """Four real publications survive one unresolved candidate in calibration scoring.

    Production mutation caught: filtering an entire case from scoring whenever its
    top-level result also carries a DEFER reason.
    """
    manifest_path, root, source_id = _oracle_fixture(tmp_path)
    manifest = load_manifest(manifest_path)
    replay = next(case for case in manifest.cases if case.role == "historical_bug_replay")
    surfaced = (
        {
            "claim": "Empty batch division crashes request processing.",
            "anchor": {"file": "calc.py", "line": 2},
            "failure_scenario": "A request submits an empty batch.",
            "falsification_plan": "Call the helper with no batch entries.",
        },
        {
            "claim": "Missing measurements abort the scheduled aggregation.",
            "anchor": {"file": "calc.py", "line": 2},
            "failure_scenario": "A scheduled job receives no measurements.",
            "falsification_plan": "Run the scheduled job without measurements.",
        },
        {
            "claim": "Vacant samples terminate the health calculation.",
            "anchor": {"file": "calc.py", "line": 2},
            "failure_scenario": "A health window contains vacant samples.",
            "falsification_plan": "Evaluate a health window containing no samples.",
        },
        {
            "claim": "Zero observations make the reporting endpoint unavailable.",
            "anchor": {"file": "calc.py", "line": 2},
            "failure_scenario": "The endpoint handles a period with zero observations.",
            "falsification_plan": "Request a report for an observation-free period.",
        },
    )
    deferred = {
        "claim": "Absent telemetry corrupts the archival checkpoint.",
        "anchor": {"file": "calc.py", "line": 1},
        "failure_scenario": "An archival checkpoint receives absent telemetry.",
        "falsification_plan": "Inspect the private archival checkpoint path.",
    }
    proposal = json.dumps({"findings": [*surfaced, deferred]})
    repro = json.dumps(
        {
            "test_body": "import runpy\n\n"
            "def test_value_is_one():\n"
            "    assert runpy.run_path('calc.py')['value']() == 1\n"
        }
    )

    class MixedProvider:
        def sample(
            self,
            system: str,
            prompt: str,
            schema: dict[str, Any],
            max_tokens: int,
            *,
            timeout_s: float | None = None,
        ) -> ProviderResult:
            if "focused pytest reproduction" not in system:
                return ProviderResult(text=proposal, input_tokens=10, output_tokens=10)
            text = "{}" if deferred["claim"] in prompt else repro
            return ProviderResult(text=text, input_tokens=10, output_tokens=10)

    with LoopbackGitHub() as github:
        result = BenchmarkRunner(
            limits=ExecutorLimits(wall_timeout_s=30.0),
            repeats=1,
        ).run_case(
            root / source_id / replay.pair_id / "replay",
            case_id=replay.case_id,
            base_sha=replay.fixed_commit,
            head_sha=replay.buggy_commit,
            fixed_sha=replay.fixed_commit,
            config=ReviewConfig(k_samples=2, max_findings=3, tier0_commands=[]),
            provider=MixedProvider(),
            oracle_provider=MixedProvider(),
            client=github.client(),
        )
        inline_events = tuple(github.review_comments)
        final_summary = github.status_bodies[-1]

    assert result.candidate_count == 5
    assert result.surfaced_count == 4
    assert result.deferred_reason is not None
    assert len(inline_events) == 3
    assert all(str(finding["claim"]) in final_summary for finding in surfaced)
    scored_predictions = tuple(
        prediction
        for prediction in result.run.predictions
        if is_scored_placement(prediction.placement)
    )
    assert len(scored_predictions) == 4
    assert result.measurement.task_status.value == "partially_deferred"
    assert result.measurement.published_count == 4
    assert result.measurement.unresolved_count == 1
    assert result.measurement.delivery_status.value == "published_on_time"
    assert result.run.delivery_at_s is not None

    request = ProjectEvaluationRequest(
        case_id=replay.case_id,
        repo=root / source_id / replay.pair_id / "replay",
        base_ref=replay.fixed_commit,
        head_ref=replay.buggy_commit,
        workspace_root=tmp_path / "api-workspace",
        config=ReviewConfig(k_samples=2, max_findings=3, tier0_commands=[]),
        limits=ExecutorLimits(wall_timeout_s=30.0),
        repeats=1,
        truth=ProjectTruth(
            fixed_ref=replay.fixed_commit,
            defects=tuple(
                defect for defect in manifest.truth_defects if defect.case_id == replay.case_id
            ),
        ),
    )
    evaluated = evaluate_project(
        request,
        provider=MixedProvider(),
        oracle_provider=MixedProvider(),
        artifact_store=ArtifactStore(tmp_path / "artifacts"),
    )
    assert evaluated.abstain_reason is not None
    assert evaluated.measurement.task_status.value == "partially_deferred"
    assert evaluated.measurement.published_count == 4
    assert evaluated.measurement.unresolved_count == 1
    assert {
        finding.accuracy_status.value
        for finding in evaluated.measurement.findings
        if finding.author_visible
    } == {"unadjudicated"}

    payload = case_payload(evaluated)
    payload["paid_calls"] = [
        {
            "trial_id": f"measurement:{replay.case_id}",
            "call_id": f"measurement:{replay.case_id}:product",
            "ordinal": 0,
            "role": CALL_ROLE_PRODUCT,
            "cost_usd": evaluated.spend_usd,
        },
        {
            "trial_id": f"measurement:{replay.case_id}",
            "call_id": f"measurement:{replay.case_id}:oracle",
            "ordinal": 1,
            "role": CALL_ROLE_BENCHMARK_ORACLE,
            "cost_usd": evaluated.oracle_spend_usd,
        },
    ]
    report = build_calibration_report(
        manifest,
        [payload],
        run_id="mixed-red",
        mode=LIVE_MODE,
        manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        preregistration_sha256="f" * 64,
        validation_receipt=None,
    ).to_json_dict()

    assert report["evaluated_cases"] == 1
    assert report["accuracy"] is None
    assert report["accuracy_withheld_reason"] is not None
    assert report["outcome_accounting"]["task_status_counts"] == {
        "completed": 0,
        "partially_deferred": 1,
        "fully_deferred": 0,
        "failed": 0,
    }
    assert report["outcome_accounting"]["published"] == 4
    assert report["outcome_accounting"]["unresolved"] == 1
