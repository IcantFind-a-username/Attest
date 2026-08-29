"""Real-corpus import and oracle validation tests."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
import tracemalloc
from pathlib import Path

import pytest

from attest.benchmark.corpus import (
    RunOutcome,
    SubprocessCorpusRunner,
    import_bugsinpy,
    load_validation_receipt,
    parse_unified_diff,
    require_validated_pair,
    validate_corpus,
)
from attest.benchmark.schema import (
    load_manifest,
    normalize_unified_diff_bytes,
    verify_descriptor_bytes,
)

_MIT = """MIT License

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

_BSD2 = """Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:
1. Redistributions of source code must retain the above copyright notice,
   this list of conditions and the following disclaimer.
2. Redistributions in binary form must reproduce the above copyright notice,
   this list of conditions and the following disclaimer in the documentation.
THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
"""

_BSD3 = _BSD2.replace(
    "THIS SOFTWARE IS PROVIDED",
    "3. Neither the name of the copyright holder nor the names of its contributors may be "
    "used to endorse or promote products derived from this software.\nTHIS SOFTWARE IS PROVIDED",
)


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
    project_license: str = _MIT,
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
    commits: list[tuple[str, str, bytes]] = []
    for number in range(1, bug_count + 1):
        (upstream / "value.py").write_text(f"VALUE = -{number}\n")
        _git(upstream, "add", ".")
        _git(upstream, "commit", "-qm", f"buggy {number}")
        buggy_commit = _git(upstream, "rev-parse", "HEAD")
        (upstream / "value.py").write_text(f"VALUE = {number}\n")
        _git(upstream, "add", ".")
        _git(upstream, "commit", "-qm", f"fixed {number}")
        fixed_commit = _git(upstream, "rev-parse", "HEAD")
        patch = subprocess.run(
            ["git", "diff", buggy_commit, fixed_commit, "--"],
            cwd=upstream,
            check=True,
            capture_output=True,
        ).stdout
        commits.append((buggy_commit, fixed_commit, patch))

    source = tmp_path / "BugsInPy"
    source.mkdir()
    _git(source, "init", "-q")
    _git(source, "config", "user.email", "fixture@example.invalid")
    _git(source, "config", "user.name", "Fixture")
    _git(source, "remote", "add", "origin", "https://example.invalid/BugsInPy.git")
    (source / "LICENSE").write_text(_MIT)
    project = source / "projects" / "demo"
    project.mkdir(parents=True)
    (project / "project.info").write_text(
        'github_url="https://example.invalid/demo.git"\n',
        encoding="utf-8",
    )
    for number, (buggy_commit, fixed_commit, patch) in enumerate(commits, start=1):
        _write_bug(
            source,
            number,
            buggy_commit=buggy_commit,
            fixed_commit=fixed_commit,
            patch=patch,
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
    assert all(case["patch"]["normalization"] == "unified_diff" for case in result["cases"])
    assert all(case["tests"]["normalization"] == "normalized_text" for case in result["cases"])
    assert all(case["changed_locations"][0]["path"] == "value.py" for case in result["cases"])
    location_sides = {
        location["side"] for case in result["cases"] for location in case["changed_locations"]
    }
    assert location_sides == {
        "old",
        "new",
    }
    source_by_case = {case["case_id"]: case["source_id"] for case in result["cases"]}
    for runtime in result["runtime"]:
        case = next(case for case in result["cases"] if case["case_id"] == runtime["case_id"])
        role_dir = "replay" if runtime["role"] == "historical_bug_replay" else "control"
        expected_cwd = f"{source_by_case[runtime['case_id']]}/{case['pair_id']}/{role_dir}"
        assert runtime["cwd"] == expected_cwd
        assert runtime["command"] == {
            "tool": "python",
            "args": ["-m", "pytest", "-q", "tests/test_calc.py"],
        }
    assert len({runtime["cwd"] for runtime in result["runtime"]}) == 4

    manifest = load_manifest(first)
    assert len(manifest.cases) == 4
    for case in manifest.cases:
        artifact = source / case.patch.relative_path
        assert verify_descriptor_bytes(case.patch, artifact.read_bytes())
        test_artifact = source / case.tests.relative_path
        assert verify_descriptor_bytes(case.tests, test_artifact.read_bytes())


def test_parse_unified_diff_tracks_only_changed_old_and_new_lines() -> None:
    """Context lines and hunk sizes must not inflate defect ranges or the size filter."""
    patch = """diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -10,5 +10,6 @@
 context
-old one
-old two
+new one
 context
+new tail
 context
"""

    assert parse_unified_diff(patch) == (
        [
            {"path": "app.py", "side": "old", "start_line": 11, "end_line": 12},
            {"path": "app.py", "side": "new", "start_line": 11, "end_line": 11},
            {"path": "app.py", "side": "new", "start_line": 13, "end_line": 13},
        ],
        3,
    )


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
        (
            lambda source, bug: (bug / "bug_patch.txt").write_text(
                "diff --git a/value.py b/value.py\n--- a/value.py\n+++ b/value.py\n"
                "@@ -1 +1 @@\n-VALUE = 999\n+VALUE = 1000\n"
            ),
            "patch_mismatch",
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
            _MIT.replace("MIT License", "Released under the MIT licence.")
        ),
        license_filename="LICENCE",
    )

    result = import_bugsinpy(source, tmp_path / "manifest.json", limit=1, seed=1)

    assert result["selection"]["selected_pairs"] == 1
    assert result["sources"][0]["source_license"] == "MIT"


@pytest.mark.parametrize(
    ("license_text", "identifier"),
    [(_BSD2, "BSD-2-Clause"), (_BSD3, "BSD-3-Clause")],
)
def test_import_distinguishes_complete_bsd_license_terms(
    tmp_path: Path, license_text: str, identifier: str
) -> None:
    """BSD two- and three-clause grants must be classified from complete terms."""
    source, _ = _source(tmp_path, bug_count=1, project_license=license_text)

    result = import_bugsinpy(source, tmp_path / "manifest.json", limit=1, seed=1)

    assert result["sources"][0]["source_license"] == identifier


def test_import_rejects_incomplete_license_excerpt(tmp_path: Path) -> None:
    """A familiar header plus one sentence is not auditable complete license evidence."""
    source, _ = _source(
        tmp_path,
        bug_count=1,
        project_license="MIT License\nPermission is hereby granted, free of charge",
    )

    result = import_bugsinpy(source, tmp_path / "manifest.json", limit=1, seed=1)

    assert result["exclusions"] == [
        {"upstream_case": "demo/1", "reason": "source_license_missing"}
    ]


@pytest.mark.parametrize(
    "license_text",
    [_MIT.partition("IN NO EVENT")[0], _BSD2.partition("IN NO EVENT")[0]],
)
def test_import_rejects_license_missing_complete_disclaimer(
    tmp_path: Path, license_text: str
) -> None:
    """A grant without the complete liability disclaimer must not infer an SPDX id."""
    source, _ = _source(tmp_path, bug_count=1, project_license=license_text)

    result = import_bugsinpy(source, tmp_path / "manifest.json", limit=1, seed=1)

    assert result["selection"]["eligible_pairs"] == 0
    assert result["exclusions"][0]["reason"] == "source_license_missing"


def test_import_recognizes_complete_mit_terms_across_line_wrapping(tmp_path: Path) -> None:
    """Pinned license evidence is semantic text, not one repository's wrapping width."""
    wrapped = _MIT.replace(
        "FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT",
        "FITNESS FOR A PARTICULAR\nPURPOSE AND NONINFRINGEMENT",
    )
    source, _ = _source(tmp_path, bug_count=1, project_license=wrapped)

    result = import_bugsinpy(source, tmp_path / "manifest.json", limit=1, seed=1)

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
    pair_id = "pair-222222222222"
    for role, commit in (("replay", buggy_commit), ("control", fixed_commit)):
        checkout = root / source_id / pair_id / role
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
            "sha256": sha(normalize_unified_diff_bytes(patch)).hexdigest(),
            "normalization": "unified_diff",
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
                "cwd": f"{source_id}/{pair_id}/replay",
                "command": {
                    "tool": "python",
                    "args": ["-m", "pytest", "-q", "test_calc.py"],
                },
            },
            {
                "case_id": control_id,
                "cwd": f"{source_id}/{pair_id}/control",
                "command": {
                    "tool": "python",
                    "args": ["-m", "pytest", "-q", "test_calc.py"],
                },
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
        interpreters={source_id: (sys.executable,)},
        timeout_s=10,
        max_output_bytes=16_384,
        network_isolated=True,
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
    assert report["command_success"] is True
    assert report["corpus_valid"] is True
    assert report["validation_status"] == "valid"
    assert report["scorable"] is True
    assert report["receipt"]["validated_pair_ids"] == ["pair-222222222222"]
    assert report["receipt"]["manifest_sha256"] == __import__("hashlib").sha256(
        manifest.read_bytes()
    ).hexdigest()


def test_validation_receipt_is_manifest_bound_and_only_allows_validated_pairs(
    tmp_path: Path,
) -> None:
    """Downstream evaluators must not score excluded pairs or a changed manifest."""
    manifest, root, _ = _oracle_fixture(tmp_path)
    passing = [RunOutcome(0, b"pass", False)] * 3
    failing = [
        RunOutcome(1, b"FAILED test_calc.py::test_value - assert 0 == 1", False)
    ] * 3
    report = validate_corpus(manifest, root, _SequenceRunner(passing + failing))
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text(json.dumps(report["receipt"]), encoding="utf-8")

    receipt = load_validation_receipt(receipt_path, manifest)
    require_validated_pair(receipt, "pair-222222222222")
    with pytest.raises(ValueError, match="not in validation receipt"):
        require_validated_pair(receipt, "pair-999999999999")

    manifest.write_text(manifest.read_text() + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="manifest digest"):
        load_validation_receipt(receipt_path, manifest)


def test_validation_models_empty_and_partial_corpora_separately_from_command_success(
    tmp_path: Path,
) -> None:
    """A completed validator command does not imply every pair is valid or scorable."""
    manifest, root, _ = _oracle_fixture(tmp_path)
    document = json.loads(manifest.read_text())
    source_id = "source-111111111111"
    original_pair = "pair-222222222222"
    second_pair = "pair-333333333333"
    original_cases = list(document["cases"])
    original_runtime = {row["case_id"]: row for row in document["runtime"]}
    for case in original_cases:
        copied = json.loads(json.dumps(case))
        copied["pair_id"] = second_pair
        copied["case_id"] = (
            "case-333333333331"
            if case["role"] == "historical_bug_replay"
            else "case-333333333332"
        )
        document["cases"].append(copied)
        runtime = json.loads(json.dumps(original_runtime[case["case_id"]]))
        runtime["case_id"] = copied["case_id"]
        role_dir = "replay" if copied["role"] == "historical_bug_replay" else "control"
        runtime["cwd"] = f"{source_id}/{second_pair}/{role_dir}"
        document["runtime"].append(runtime)
        if copied["role"] == "historical_bug_replay":
            truth = json.loads(json.dumps(document["truth_defects"][0]))
            truth["defect_id"] = "truth_2"
            truth["case_id"] = copied["case_id"]
            document["truth_defects"].append(truth)
        shutil.copytree(
            root / source_id / original_pair / role_dir,
            root / source_id / second_pair / role_dir,
        )
    manifest.write_text(json.dumps(document), encoding="utf-8")
    passing = [RunOutcome(0, b"pass", False)] * 3
    stable_failure = [
        RunOutcome(1, b"FAILED test_calc.py::test_value - assert 0 == 1", False)
    ] * 3
    dependency_failure = [RunOutcome(1, b"ModuleNotFoundError: missing", False)]

    partial = validate_corpus(
        manifest,
        root,
        _SequenceRunner(passing + stable_failure + dependency_failure),
    )
    assert partial["command_success"] is True
    assert partial["corpus_valid"] is False
    assert partial["validation_status"] == "partial"
    assert partial["scorable"] is True
    assert partial["receipt"]["validated_pair_ids"] == [original_pair]

    document["cases"] = []
    document["runtime"] = []
    document["truth_defects"] = []
    manifest.write_text(json.dumps(document), encoding="utf-8")
    empty = validate_corpus(manifest, root, _SequenceRunner([]))
    assert empty["command_success"] is True
    assert empty["corpus_valid"] is False
    assert empty["validation_status"] == "empty"
    assert empty["scorable"] is False
    assert empty["receipt"] is None


def test_subprocess_runner_requires_network_isolation_and_explicit_tool_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Offline mode must never resolve python, pytest, tox, or arbitrary tools through PATH."""
    source_id = "source-111111111111"
    trap = tmp_path / "tox"
    marker = tmp_path / "path-tool-ran"
    trap.write_text(f"#!/bin/sh\ntouch '{marker}'\n")
    trap.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path))
    no_isolation = SubprocessCorpusRunner(interpreters={source_id: (sys.executable,)})
    with pytest.raises(ValueError, match="network isolation"):
        no_isolation.run(source_id, "python", ("-c", "pass"), tmp_path)

    runner = SubprocessCorpusRunner(
        interpreters={source_id: (sys.executable,)}, network_isolated=True
    )
    with pytest.raises(ValueError, match="not allowed"):
        runner.run(source_id, "tox", (), tmp_path)
    assert not marker.exists()

    explicit_marker = tmp_path / "explicit-tool-ran"
    allowed = SubprocessCorpusRunner(
        interpreters={source_id: (sys.executable,)},
        allowed_tools={
            (source_id, "tox"): (
                sys.executable,
                "-c",
                f"from pathlib import Path; Path({str(explicit_marker)!r}).touch()",
            )
        },
        network_isolated=True,
    )
    outcome = allowed.run(source_id, "tox", (), tmp_path)
    assert outcome.returncode == 0
    assert explicit_marker.is_file()
    assert not marker.exists()


def test_subprocess_runner_bounds_streaming_output_memory(tmp_path: Path) -> None:
    """Large child output must be drained continuously without an unbounded parent buffer."""
    source_id = "source-111111111111"
    runner = SubprocessCorpusRunner(
        interpreters={source_id: (sys.executable,)},
        max_output_bytes=128,
        network_isolated=True,
    )
    tracemalloc.start()
    tracemalloc.reset_peak()
    try:
        outcome = runner.run(
            source_id,
            "python",
            ("-c", "import os; [os.write(1, b'x' * 65536) for _ in range(128)]"),
            tmp_path,
        )
        _, peak_bytes = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    assert outcome.returncode == 0
    assert 0 < len(outcome.output) <= 128
    assert peak_bytes < 4_000_000


@pytest.mark.skipif(os.name != "posix", reason="process-group ownership is POSIX-only")
def test_subprocess_runner_timeout_cleans_child_pipe_holder(tmp_path: Path) -> None:
    """A descendant holding stdout open must be killed with the owned process group."""
    source_id = "source-111111111111"
    marker = tmp_path / "orphan-ran"
    child = (
        "import time; from pathlib import Path; time.sleep(1); "
        f"Path({str(marker)!r}).touch()"
    )
    parent = (
        "import subprocess,sys; "
        f"subprocess.Popen([sys.executable, '-c', {child!r}], stdout=sys.stdout); "
        "sys.exit(0)"
    )
    runner = SubprocessCorpusRunner(
        interpreters={source_id: (sys.executable,)},
        timeout_s=0.2,
        network_isolated=True,
    )

    started = time.monotonic()
    outcome = runner.run(source_id, "python", ("-c", parent), tmp_path)
    elapsed = time.monotonic() - started
    observation_deadline = time.monotonic() + 1.2
    while not marker.exists() and time.monotonic() < observation_deadline:
        time.sleep(0.02)

    assert outcome.timed_out
    assert elapsed < 1.0
    assert not marker.exists()


def test_real_pilot_runtime_uses_typed_tools_not_path_executables() -> None:
    """Frozen commands must require caller mappings rather than bare PATH resolution."""
    manifest = load_manifest(Path(__file__).parents[2] / "benchmarks/attest-v1/manifest.json")

    assert {runtime.tool for runtime in manifest.runtime} <= {"python", "tox"}
    assert all(runtime.args and runtime.args[0] != runtime.tool for runtime in manifest.runtime)


class _SequenceRunner:
    def __init__(self, outcomes: list[RunOutcome]) -> None:
        self.outcomes = iter(outcomes)

    def run(
        self, source_id: str, tool: str, args: tuple[str, ...], cwd: Path
    ) -> RunOutcome:
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
    manifest, root, _ = _oracle_fixture(tmp_path)
    (root / "artifacts/fix.patch").write_text("tampered")

    report = validate_corpus(manifest, root, _SequenceRunner([]))

    assert report["results"] == [
        {
            "pair_id": "pair-222222222222",
            "status": "excluded",
            "reason": "descriptor_hash_mismatch",
        }
    ]


@pytest.mark.parametrize(("role", "path"), [("replay", "calc.py"), ("control", "test_calc.py")])
def test_validate_corpus_rejects_dirty_source_or_test_checkout(
    tmp_path: Path, role: str, path: str
) -> None:
    """Locally edited source or regression tests must invalidate the historical oracle."""
    manifest, root, _ = _oracle_fixture(tmp_path)
    checkout = root / "source-111111111111/pair-222222222222" / role
    (checkout / path).write_text("tampered\n")

    report = validate_corpus(manifest, root, _SequenceRunner([]))

    assert report["results"][0]["reason"] == "dirty_checkout"


def test_validate_corpus_requires_exact_head_for_each_pair_role(tmp_path: Path) -> None:
    """A clean checkout at the other member's commit is still the wrong oracle input."""
    manifest, root, _ = _oracle_fixture(tmp_path)
    document = json.loads(manifest.read_text())
    control = root / "source-111111111111/pair-222222222222/control"
    _git(control, "checkout", "-q", document["cases"][0]["buggy_commit"])

    report = validate_corpus(manifest, root, _SequenceRunner([]))

    assert report["results"][0]["reason"] == "checkout_commit_mismatch"


def test_validate_corpus_binds_descriptor_test_to_executed_command(tmp_path: Path) -> None:
    """A manifest must not hash one regression command and execute another."""
    manifest, root, _ = _oracle_fixture(tmp_path)
    document = json.loads(manifest.read_text())
    document["runtime"][0]["command"]["args"][-1] = "different_test.py"
    manifest.write_text(json.dumps(document))

    report = validate_corpus(manifest, root, _SequenceRunner([]))

    assert report["results"][0]["reason"] == "test_command_mismatch"


def test_validate_corpus_rejects_patch_not_equal_to_checkout_diff(tmp_path: Path) -> None:
    """A self-consistent descriptor hash cannot bless the wrong commit direction or patch."""
    manifest, root, _ = _oracle_fixture(tmp_path)
    document = json.loads(manifest.read_text())
    reversed_patch = subprocess.run(
        ["git", "diff", document["cases"][0]["fixed_commit"], document["cases"][0]["buggy_commit"]],
        cwd=root / "source-111111111111/pair-222222222222/replay",
        check=True,
        capture_output=True,
    ).stdout
    (root / "artifacts/fix.patch").write_bytes(reversed_patch)
    digest = __import__("hashlib").sha256(normalize_unified_diff_bytes(reversed_patch)).hexdigest()
    for case in document["cases"]:
        case["patch"]["sha256"] = digest
    manifest.write_text(json.dumps(document))

    report = validate_corpus(manifest, root, _SequenceRunner([]))

    assert report["results"][0]["reason"] == "patch_mismatch"


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
    assert len(manifest.exclusions) == 463
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
    cookiecutter = next(
        source
        for source in manifest.sources
        if source.project_url == "https://github.com/cookiecutter/cookiecutter"
    )
    assert cookiecutter.source_license == "BSD-3-Clause"
    assert cookiecutter.license_file == "LICENSE"
    assert cookiecutter.license_sha256 == (
        "7cc392465cc129046da7e088d618be67238e0c1a440e207f494333979f1e60dc"
    )
    assert set(cookiecutter.license_commits_verified) == {
        "5c282f020a8db7e5e7c4e7b51b010556ca31fb7f",
        "7129d474206761a6156925db78eee4b62a0e3944",
        "7f6804c4953a18386809f11faf4d86898570debc",
        "c15633745df6abdb24e02746b82aadb20b8cdf8c",
    }
    expected = __import__("hashlib").sha256(
        protocol_path.read_bytes() + b"\0" + manifest_path.read_bytes()
    ).hexdigest()
    assert digest_path.read_text(encoding="ascii") == f"{expected}  protocol.md+manifest.json\n"
