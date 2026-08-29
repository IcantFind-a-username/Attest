"""Real-corpus import and oracle validation tests."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from attest.benchmark.corpus import (
    RunOutcome,
    SubprocessCorpusRunner,
    import_bugsinpy,
    validate_corpus,
)
from attest.benchmark.schema import load_manifest, verify_descriptor_bytes


def _git(path: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args], cwd=path, check=True, capture_output=True, text=True
    )
    return completed.stdout.strip()


def _write_bug(
    source: Path,
    number: int,
    *,
    buggy_commit: str | None = None,
    fixed_commit: str | None = None,
    patch: bytes | None = None,
    test_command: str = "python -m pytest -q tests/test_calc.py",
) -> Path:
    bug = source / "projects" / "demo" / "bugs" / str(number)
    bug.mkdir(parents=True)
    (bug / "bug.info").write_text(
        'python_version="3.11"\n'
        f'buggy_commit_id="{buggy_commit or f"{number:040x}"}"\n'
        f'fixed_commit_id="{fixed_commit or f"{number + 100:040x}"}"\n'
        'test_file="tests/test_calc.py"\n',
        encoding="utf-8",
    )
    (bug / "bug_patch.txt").write_bytes(
        patch
        or (
            "diff --git a/src/calc.py b/src/calc.py\n"
            "index 1111111..2222222 100644\n"
            "--- a/src/calc.py\n"
            "+++ b/src/calc.py\n"
            f"@@ -{number + 4},2 +{number + 4},2 @@\n"
            "-    return 0\n"
            "+    return 1\n"
        ).encode()
    )
    (bug / "run_test.sh").write_text(test_command + "\n", encoding="utf-8")
    (bug / "bug_buggy.txt").write_text("FAILED tests/test_calc.py::test_value\n")
    (bug / "bug_fixed.txt").write_text("1 passed\n")
    return bug


def _source(
    tmp_path: Path,
    bug_count: int = 3,
    *,
    project_license: str = "MIT License\n\nPermission is hereby granted, free of charge",
    license_filename: str = "LICENSE",
) -> tuple[Path, str]:
    upstream = tmp_path / "project-cache" / "demo"
    upstream.mkdir(parents=True)
    _git(upstream, "init", "-q")
    _git(upstream, "config", "user.email", "fixture@example.invalid")
    _git(upstream, "config", "user.name", "Fixture")
    _git(upstream, "remote", "add", "origin", "https://example.invalid/demo.git")
    (upstream / license_filename).write_text(project_license, encoding="utf-8")
    (upstream / "value.py").write_text("VALUE = 0\n")
    _git(upstream, "add", ".")
    _git(upstream, "commit", "-qm", "base")
    commits: list[tuple[str, str]] = []
    for number in range(1, bug_count + 1):
        (upstream / "value.py").write_text(f"VALUE = -{number}\n")
        _git(upstream, "add", ".")
        _git(upstream, "commit", "-qm", f"buggy {number}")
        buggy_commit = _git(upstream, "rev-parse", "HEAD")
        (upstream / "value.py").write_text(f"VALUE = {number}\n")
        _git(upstream, "add", ".")
        _git(upstream, "commit", "-qm", f"fixed {number}")
        commits.append((buggy_commit, _git(upstream, "rev-parse", "HEAD")))

    source = tmp_path / "BugsInPy"
    source.mkdir()
    _git(source, "init", "-q")
    _git(source, "config", "user.email", "fixture@example.invalid")
    _git(source, "config", "user.name", "Fixture")
    _git(source, "remote", "add", "origin", "https://example.invalid/BugsInPy.git")
    (source / "LICENSE").write_text("MIT License\n\nPermission is hereby granted, free of charge")
    project = source / "projects" / "demo"
    project.mkdir(parents=True)
    (project / "project.info").write_text(
        'github_url="https://example.invalid/demo.git"\n',
        encoding="utf-8",
    )
    for number, (buggy_commit, fixed_commit) in enumerate(commits, start=1):
        _write_bug(
            source, number, buggy_commit=buggy_commit, fixed_commit=fixed_commit
        )
    _git(source, "add", ".")
    _git(source, "commit", "-qm", "fixture")
    return source, _git(source, "rev-parse", "HEAD")


def test_import_bugsinpy_writes_deterministic_pinned_opaque_pairs(tmp_path: Path) -> None:
    """Selection drift, semantic IDs, or lost provenance would invalidate preregistration."""
    source, commit = _source(tmp_path)
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"

    result = import_bugsinpy(source, first, limit=2, seed=17)
    import_bugsinpy(source, second, limit=2, seed=17)

    assert first.read_bytes() == second.read_bytes()
    assert result["corpus_commit"] == commit
    assert result["provenance"]["kind"] == "BugsInPy"
    assert result["provenance"]["source_url"] == "https://example.invalid/BugsInPy.git"
    assert result["provenance"]["license"] == "MIT"
    assert result["provenance"]["license_file"] == "LICENSE"
    assert re.fullmatch(r"[0-9a-f]{64}", result["provenance"]["license_sha256"])
    assert result["selection"]["seed"] == 17
    assert result["selection"]["selected_pairs"] == 2
    assert len(result["cases"]) == 4
    assert {case["role"] for case in result["cases"]} == {
        "historical_bug_replay",
        "developer_fix_control",
    }
    assert all(re.fullmatch(r"case-[0-9a-f]{12}", case["case_id"]) for case in result["cases"])
    assert all("demo" not in case["case_id"] for case in result["cases"])
    assert len({case["pair_id"] for case in result["cases"]}) == 2
    assert result["sources"] == [
        {
            "source_id": result["sources"][0]["source_id"],
            "project_url": "https://example.invalid/demo.git",
            "source_license": "MIT",
            "license_file": "LICENSE",
            "license_sha256": result["sources"][0]["license_sha256"],
            "license_commits_verified": result["sources"][0]["license_commits_verified"],
        }
    ]
    assert len(result["sources"][0]["license_commits_verified"]) == 4
    assert all(case["buggy_commit"] != case["fixed_commit"] for case in result["cases"])
    assert all(case["patch"]["normalization"] == "bytes" for case in result["cases"])
    assert all(case["tests"]["normalization"] == "normalized_text" for case in result["cases"])
    assert all(case["changed_locations"][0]["path"] == "src/calc.py" for case in result["cases"])
    assert all(case["changed_locations"][0]["start_line"] >= 5 for case in result["cases"])
    source_by_case = {case["case_id"]: case["source_id"] for case in result["cases"]}
    for runtime in result["runtime"]:
        role_dir = "replay" if runtime["role"] == "historical_bug_replay" else "control"
        assert runtime["cwd"] == f"{source_by_case[runtime['case_id']]}/{role_dir}"

    manifest = load_manifest(first)
    assert len(manifest.cases) == 4
    for case in manifest.cases:
        artifact = source / case.patch.relative_path
        assert verify_descriptor_bytes(case.patch, artifact.read_bytes())
        test_artifact = source / case.tests.relative_path
        assert verify_descriptor_bytes(case.tests, test_artifact.read_bytes())


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        (
            lambda source, bug: (source.parent / "project-cache/demo").rename(
                source.parent / "project-cache/unavailable"
            ),
            "source_license_missing",
        ),
        (
            lambda source, bug: (bug / "bug_patch.txt").symlink_to(
                source.parent / "outside.patch"
            ),
            "unsafe_symlink",
        ),
        (lambda source, bug: (bug / "bug_patch.txt").write_bytes(b"\x00binary"), "binary_patch"),
        (
            lambda source, bug: (bug / "bug_patch.txt").write_text(
                "diff --git a/README.md b/README.md\n--- a/README.md\n+++ b/README.md\n"
                "@@ -1 +1 @@\n-old\n+new\n"
            ),
            "non_python_change",
        ),
        (
            lambda source, bug: (bug / "bug_patch.txt").write_text(
                "diff --git a/src/calc.py b/src/calc.py\n--- a/src/calc.py\n+++ b/src/calc.py\n"
                "@@ -1,401 +1,401 @@\n" + "-old\n+new\n" * 401
            ),
            "oversized_diff",
        ),
        (lambda source, bug: (bug / "run_test.sh").unlink(), "missing_regression_test"),
    ],
)
def test_import_bugsinpy_excludes_unsafe_or_unusable_metadata(
    tmp_path: Path, mutation: object, reason: str
) -> None:
    """An unsafe or unlicensed artifact must never become a benchmark case."""
    source, _ = _source(tmp_path, bug_count=1)
    bug = source / "projects/demo/bugs/1"
    if reason == "unsafe_symlink":
        (source.parent / "outside.patch").write_text("outside")
        (bug / "bug_patch.txt").unlink()
    mutation(source, bug)  # type: ignore[operator]
    if _git(source, "status", "--porcelain"):
        _git(source, "add", "-A")
        _git(source, "commit", "-qm", "mutate fixture")

    result = import_bugsinpy(source, tmp_path / "manifest.json", limit=1, seed=1)

    assert result["cases"] == []
    assert result["truth_defects"] == []
    assert result["exclusions"] == [{"upstream_case": "demo/1", "reason": reason}]


def test_import_records_unspecified_dataset_license_without_excluding_project(
    tmp_path: Path,
) -> None:
    """Dataset metadata may be read without treating an absent dataset license as project code."""
    source, _ = _source(tmp_path, bug_count=1)
    (source / "LICENSE").unlink()
    _git(source, "add", "-A")
    _git(source, "commit", "-qm", "remove dataset license")

    result = import_bugsinpy(source, tmp_path / "manifest.json", limit=1, seed=1)

    assert result["selection"]["selected_pairs"] == 1
    assert result["provenance"]["license_status"] == "UNSPECIFIED"
    assert result["provenance"]["license"] is None


def test_import_recognizes_complete_mit_terms_without_american_header_spelling(
    tmp_path: Path,
) -> None:
    """A full MIT grant must not be rejected solely because its heading says licence."""
    source, _ = _source(
        tmp_path,
        bug_count=1,
        project_license=(
            "Released under the MIT licence.\n"
            "Permission is hereby granted, free of charge, to any person obtaining a copy.\n"
            'THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND.\n'
        ),
        license_filename="LICENCE",
    )

    result = import_bugsinpy(source, tmp_path / "manifest.json", limit=1, seed=1)

    assert result["selection"]["selected_pairs"] == 1
    assert result["sources"][0]["source_license"] == "MIT"


def test_import_bugsinpy_rejects_uncommitted_or_non_repository_source(tmp_path: Path) -> None:
    """A mutable or non-git input cannot substantiate an exact corpus commit."""
    source, _ = _source(tmp_path, bug_count=1)
    (source / "README.md").write_text("dirty")
    with pytest.raises(ValueError, match="clean"):
        import_bugsinpy(source, tmp_path / "dirty.json", limit=1, seed=1)

    with pytest.raises(ValueError, match="git"):
        import_bugsinpy(tmp_path / "missing", tmp_path / "missing.json", limit=1, seed=1)


def test_import_does_not_copy_third_party_artifacts(tmp_path: Path) -> None:
    """Importing metadata must not vendor patches, tests, or project source into output."""
    source, _ = _source(tmp_path, bug_count=1)
    output = tmp_path / "out" / "manifest.json"

    import_bugsinpy(source, output, limit=1, seed=1)

    assert [path.relative_to(output.parent).as_posix() for path in output.parent.rglob("*")] == [
        "manifest.json"
    ]


def _oracle_fixture(tmp_path: Path) -> tuple[Path, Path, str]:
    upstream = tmp_path / "upstream"
    upstream.mkdir()
    _git(upstream, "init", "-q")
    _git(upstream, "config", "user.email", "fixture@example.invalid")
    _git(upstream, "config", "user.name", "Fixture")
    (upstream / "calc.py").write_text("def value():\n    return 0\n")
    (upstream / "test_calc.py").write_text(
        "from calc import value\n\ndef test_value():\n    assert value() == 1\n"
    )
    _git(upstream, "add", ".")
    _git(upstream, "commit", "-qm", "buggy")
    buggy_commit = _git(upstream, "rev-parse", "HEAD")
    (upstream / "calc.py").write_text("def value():\n    return 1\n")
    _git(upstream, "add", ".")
    _git(upstream, "commit", "-qm", "fixed")
    fixed_commit = _git(upstream, "rev-parse", "HEAD")

    root = tmp_path / "cache"
    source_id = "source-111111111111"
    for role, commit in (("replay", buggy_commit), ("control", fixed_commit)):
        checkout = root / source_id / role
        checkout.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "clone", "-q", str(upstream), str(checkout)], check=True, capture_output=True
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
    sha = __import__("hashlib").sha256
    pair_id = "pair-222222222222"
    replay_id = "case-333333333333"
    control_id = "case-444444444444"
    common = {
        "pair_id": pair_id,
        "source_id": source_id,
        "provenance_kind": "historical_fix",
        "source_license": "MIT",
        "buggy_commit": buggy_commit,
        "fixed_commit": fixed_commit,
        "patch": {
            "relative_path": "artifacts/fix.patch",
            "sha256": sha(patch).hexdigest(),
            "normalization": "bytes",
        },
        "tests": {
            "relative_path": "artifacts/test.argv",
            "sha256": sha(test_command).hexdigest(),
            "normalization": "normalized_text",
        },
        "changed_locations": [{"path": "calc.py", "start_line": 2, "end_line": 2}],
        "split": "test",
    }
    document = {
        "schema_version": "1",
        "protocol_version": "1",
        "corpus_commit": "5" * 64,
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
                "cwd": f"{source_id}/replay",
                "test_argv": ["{python}", "-m", "pytest", "-q", "test_calc.py"],
            },
            {
                "case_id": control_id,
                "cwd": f"{source_id}/control",
                "test_argv": ["{python}", "-m", "pytest", "-q", "test_calc.py"],
            },
        ],
    }
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(document), encoding="utf-8")
    return manifest, root, source_id


def test_validate_corpus_requires_three_real_fixed_passes_and_stable_buggy_failures(
    tmp_path: Path,
) -> None:
    """A one-off or non-differential test result must not become benchmark truth."""
    manifest, root, source_id = _oracle_fixture(tmp_path)
    runner = SubprocessCorpusRunner(
        interpreters={source_id: (sys.executable,)}, timeout_s=10, max_output_bytes=16_384
    )

    report = validate_corpus(manifest, root, runner)

    assert report["validated_pairs"] == 1
    assert report["excluded_pairs"] == 0
    assert report["results"][0]["status"] == "validated"
    assert len(report["results"][0]["fixed_runs"]) == 3
    assert len(report["results"][0]["buggy_runs"]) == 3
    assert all(run["returncode"] == 0 for run in report["results"][0]["fixed_runs"])
    assert all(run["returncode"] != 0 for run in report["results"][0]["buggy_runs"])
    assert re.fullmatch(r"[0-9a-f]{64}", report["results"][0]["failure_signature"])


class _SequenceRunner:
    def __init__(self, outcomes: list[RunOutcome]) -> None:
        self.outcomes = iter(outcomes)

    def run(self, source_id: str, argv: tuple[str, ...], cwd: Path) -> RunOutcome:
        return next(self.outcomes)


@pytest.mark.parametrize(
    ("outcomes", "reason"),
    [
        (
            [RunOutcome(0, b"pass", False)] * 3
            + [RunOutcome(1, b"FAILED test_calc.py::test_value - assert 0 == 1", False),
               RunOutcome(0, b"pass", False),
               RunOutcome(1, b"FAILED test_calc.py::test_value - assert 0 == 1", False)],
            "flaky",
        ),
        (
            [RunOutcome(0, b"pass", False)] * 3
            + [RunOutcome(1, b"FAILED test_calc.py::test_value - assert 0 == 1", False),
               RunOutcome(1, b"FAILED test_calc.py::test_value - assert 0 == 2", False),
               RunOutcome(1, b"FAILED test_calc.py::test_value - assert 0 == 1", False)],
            "inconsistent_failure_signature",
        ),
        (
            [RunOutcome(1, b"ModuleNotFoundError: No module named 'missing'", False)],
            "dependency_or_setup_failure",
        ),
        (
            [RunOutcome(0, b"pass", False)] * 3 + [RunOutcome(-9, b"", True)],
            "timeout",
        ),
    ],
)
def test_validate_corpus_excludes_unreliable_oracle_outcomes(
    tmp_path: Path, outcomes: list[RunOutcome], reason: str
) -> None:
    """Flaky, inconsistent, setup-failed, and timed-out pairs need explicit exclusions."""
    manifest, root, _ = _oracle_fixture(tmp_path)

    report = validate_corpus(manifest, root, _SequenceRunner(outcomes))

    assert report["validated_pairs"] == 0
    assert report["excluded_pairs"] == 1
    assert report["results"][0]["status"] == "excluded"
    assert report["results"][0]["reason"] == reason


def test_validate_corpus_excludes_tampered_artifacts_and_wrong_checkout(tmp_path: Path) -> None:
    """Hash or commit drift in caller materialization must fail closed before test execution."""
    manifest, root, source_id = _oracle_fixture(tmp_path)
    (root / "artifacts/fix.patch").write_text("tampered")
    runner = SubprocessCorpusRunner(interpreters={source_id: (sys.executable,)})

    report = validate_corpus(manifest, root, runner)

    assert report["results"] == [
        {"pair_id": "pair-222222222222", "status": "excluded", "reason": "integrity_failure"}
    ]


def test_real_pilot_manifest_is_large_diverse_pinned_and_preregistered() -> None:
    """A tiny, unlicensed, mutable pilot cannot support the planned real-data evaluation."""
    root = Path(__file__).parents[2]
    benchmark = root / "benchmarks/attest-v1"
    manifest_path = benchmark / "manifest.json"
    protocol_path = benchmark / "protocol.md"
    digest_path = benchmark / "preregistration.sha256"

    document = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest = load_manifest(manifest_path)
    pairs = {case.pair_id for case in manifest.cases}
    sources = {case.source_id for case in manifest.cases}

    assert manifest.corpus_commit == "316b95e2353ecda832bad9b42f86fa7c2fcec8ac"
    assert len(pairs) >= 20
    assert len(manifest.cases) == len(pairs) * 2
    assert len(sources) >= 4
    assert document["provenance"]["license_status"] == "UNSPECIFIED"
    assert document["provenance"]["source_url"] == (
        "https://github.com/reproducing-research-projects/BugsInPy.git"
    )
    assert all(source["source_license"] != "UNKNOWN" for source in document["sources"])
    assert all(len(source["license_commits_verified"]) >= 2 for source in document["sources"])
    assert len(manifest.sources) == 4
    assert len(manifest.runtime) == len(manifest.cases)
    assert len(manifest.exclusions) == 459
    assert manifest.provenance is not None
    assert manifest.provenance.license_status == "UNSPECIFIED"
    for source in manifest.sources:
        case_commits = {
            commit
            for case in manifest.cases
            if case.source_id == source.source_id
            for commit in (case.buggy_commit, case.fixed_commit)
        }
        assert case_commits <= set(source.license_commits_verified)
    expected = __import__("hashlib").sha256(
        protocol_path.read_bytes() + b"\0" + manifest_path.read_bytes()
    ).hexdigest()
    assert digest_path.read_text(encoding="ascii") == f"{expected}  protocol.md+manifest.json\n"
