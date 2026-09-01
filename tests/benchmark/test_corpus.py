"""Real-corpus import and oracle validation tests."""

from __future__ import annotations

import hashlib
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

from attest.benchmark.artifacts import MAX_BOUNDED_ARTIFACT_BYTES, ArtifactStore
from attest.benchmark.corpus import (
    IsolationAdapter,
    IsolationError,
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

from ._validation_v2 import KEY_ID, ValidationV2Bundle, build_validation_v2_bundle

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
   this list of conditions and the following disclaimer in the documentation
   and/or other materials provided with the distribution.
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
    "used to endorse or promote products derived from this software without specific prior "
    "written permission.\nTHIS SOFTWARE IS PROVIDED",
)

_APACHE_NOTICE = """Apache License
Version 2.0, January 2004
TERMS AND CONDITIONS FOR USE, REPRODUCTION, AND DISTRIBUTION
You may reproduce and distribute copies of the Work provided that You give
recipients a copy of this License and retain all notices.
Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
WARRANTIES OR CONDITIONS OF ANY KIND.
END OF TERMS AND CONDITIONS
"""

_GPL_NOTICE = """GNU GENERAL PUBLIC LICENSE
Version 3, 29 June 2007
Everyone is permitted to copy and distribute verbatim copies of this license.
You may convey verbatim copies of the Program's source code as you receive it.
THERE IS NO WARRANTY FOR THE PROGRAM, TO THE EXTENT PERMITTED BY APPLICABLE LAW.
END OF TERMS AND CONDITIONS
"""

_ISC = """Permission to use, copy, modify, and/or distribute this software for
any purpose with or without fee is hereby granted, provided that the above
copyright notice and this permission notice appear in all copies.

THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES WITH
REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY
AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY SPECIAL, DIRECT,
INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM
LOSS OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE OR
OTHER TORTIOUS ACTION, ARISING OUT OF OR IN CONNECTION WITH THE USE OR
PERFORMANCE OF THIS SOFTWARE.
"""

_CUSTOM_LICENSE = """Example Community License

You may use this work for internal evaluation. Redistribution, modification,
and commercial use require separate written permission from the authors.

THE WORK IS PROVIDED WITHOUT WARRANTY, AND ALL LIABILITY IS DISCLAIMED.
"""


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


@pytest.mark.parametrize(
    "license_text",
    [
        _MIT + _BSD2,
        _MIT + _APACHE_NOTICE,
        _MIT + _GPL_NOTICE,
        _BSD2 + _BSD3,
        _MIT + _ISC,
    ],
    ids=["mit-bsd", "mit-apache", "mit-gpl", "bsd2-bsd3", "mit-unknown"],
)
def test_import_rejects_multiple_or_additional_license_templates(
    tmp_path: Path, license_text: str
) -> None:
    """A source license is auditable only when exactly one complete template matches."""
    source, _ = _source(tmp_path, bug_count=1, project_license=license_text)

    result = import_bugsinpy(source, tmp_path / "manifest.json", limit=1, seed=1)

    assert result["selection"]["eligible_pairs"] == 0
    assert result["exclusions"][0]["reason"] == "source_license_missing"


@pytest.mark.parametrize(
    "license_text",
    [
        _CUSTOM_LICENSE + "\n" + _MIT,
        "Copyright notice. Production use requires a fee.\n\n" + _MIT,
        _MIT.replace(
            "The above copyright notice",
            "An additional fee is required for production use.\n\n"
            "The above copyright notice",
        ),
        _BSD2.replace(
            "2. Redistributions in binary form",
            "Use by competitors requires written permission.\n"
            "2. Redistributions in binary form",
        ),
    ],
    ids=[
        "unknown-before-mit",
        "copyright-lookalike-before-mit",
        "clause-inside-mit",
        "clause-inside-bsd",
    ],
)
def test_import_rejects_substantive_text_outside_a_complete_template(
    tmp_path: Path, license_text: str
) -> None:
    """Terms before or inside a supported template make its SPDX identity ambiguous."""
    source, _ = _source(tmp_path, bug_count=1, project_license=license_text)

    result = import_bugsinpy(source, tmp_path / "manifest.json", limit=1, seed=1)

    assert result["selection"]["eligible_pairs"] == 0
    assert result["exclusions"][0]["reason"] == "source_license_missing"


@pytest.mark.parametrize(
    "license_text",
    [
        _MIT.replace(
            "Permission is hereby granted, free of charge",
            "The above copyright notice and this permission notice shall be included in "
            "all copies or substantial portions of the Software.\n\n"
            "Permission is hereby granted, free of charge",
        ).replace(
            "\n\nThe above copyright notice and this permission notice shall be included in all\n"
            "copies or substantial portions of the Software.\n",
            "\n",
        ),
        (
            "1. Redistributions of source code must retain the above copyright notice,\n"
            "   this list of conditions and the following disclaimer.\n"
            + _BSD2.replace(
                "1. Redistributions of source code must retain the above copyright notice,\n"
                "   this list of conditions and the following disclaimer.\n",
                "",
            )
        ),
    ],
    ids=["reordered-mit-paragraph", "scattered-bsd-clause"],
)
def test_import_rejects_reordered_or_scattered_license_markers(
    tmp_path: Path, license_text: str
) -> None:
    """All familiar sentences must still appear as one supported template in order."""
    source, _ = _source(tmp_path, bug_count=1, project_license=license_text)

    result = import_bugsinpy(source, tmp_path / "manifest.json", limit=1, seed=1)

    assert result["selection"]["eligible_pairs"] == 0
    assert result["exclusions"][0]["reason"] == "source_license_missing"


@pytest.mark.parametrize(
    ("license_text", "identifier"),
    [
        (
            "The MIT License (MIT)\n\n"
            "Copyright (c) 2026 Example Authors\n\n"
            + _MIT.partition("\n\n")[2],
            "MIT",
        ),
        (
            "Copyright (c) 2020-2026, Example Authors\n"
            "All rights reserved.\n\n" + _BSD3,
            "BSD-3-Clause",
        ),
    ],
    ids=["mit-header-and-copyright", "bsd-copyright-and-rights"],
)
def test_import_accepts_one_contiguous_template_with_allowed_boilerplate(
    tmp_path: Path, license_text: str, identifier: str
) -> None:
    """A known header and copyright notice may precede exactly one complete template."""
    source, _ = _source(tmp_path, bug_count=1, project_license=license_text)

    result = import_bugsinpy(source, tmp_path / "manifest.json", limit=1, seed=1)

    assert result["selection"]["eligible_pairs"] == 1
    assert result["sources"][0]["source_license"] == identifier


def test_import_accepts_bsd3_copyright_holder_name_placeholder(tmp_path: Path) -> None:
    """BSD-3 permits a named project in its non-endorsement clause."""
    historical_cookiecutter_terms = _BSD3.replace(
        "the copyright holder nor the names of its contributors",
        "border nor the names of its contributors",
        1,
    )
    source, _ = _source(
        tmp_path, bug_count=1, project_license=historical_cookiecutter_terms
    )

    result = import_bugsinpy(source, tmp_path / "manifest.json", limit=1, seed=1)

    assert result["selection"]["eligible_pairs"] == 1
    assert result["sources"][0]["source_license"] == "BSD-3-Clause"


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


def _oracle_fixture(
    tmp_path: Path, *, failure_message_size: int = 0, missing_dependency: bool = False
) -> tuple[Path, Path, str]:
    upstream = tmp_path / "upstream"
    upstream.mkdir()
    _git(upstream, "init", "-q")
    _git(upstream, "config", "user.email", "fixture@example.invalid")
    _git(upstream, "config", "user.name", "Fixture")
    (upstream / "calc.py").write_text("def value():\n    return 0\n")
    failure_message = (
        f", {'x' * failure_message_size!r}" if failure_message_size else ""
    )
    test_source = (
        "import attest_missing_dependency\n"
        if missing_dependency
        else (
            "from calc import value\n\ndef test_value():\n"
            f"    assert value() == 1{failure_message}\n"
        )
    )
    (upstream / "test_calc.py").write_text(test_source)
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
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A one-off or non-differential test result must not become benchmark truth."""
    monkeypatch.setenv("LANG", "M02_ENVIRONMENT_SENTINEL")
    manifest, root, source_id = _oracle_fixture(tmp_path)
    runner = SubprocessCorpusRunner(
        interpreters={source_id: (sys.executable,)},
        timeout_s=10,
        max_output_bytes=16_384,
        isolation=_sandbox_isolation(),
    )

    artifact_root = tmp_path / "issued-validation-artifacts"
    report = validate_corpus(
        manifest,
        root,
        runner,
        artifact_store=ArtifactStore(artifact_root),
    )

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
    assert report["scorable"] is False
    assert report["receipt"] is None
    result_v2 = report["validation_results"]["results"][0]
    assert len(result_v2["attempts"][0]["runs"]) == 6
    environment_record = result_v2["attempts"][0]["runs"][0]["artifacts"][
        "environment"
    ]
    environment = json.loads(
        (artifact_root / environment_record["name"]).read_text()
    )
    assert environment["variables"]["LANG"] == "M02_ENVIRONMENT_SENTINEL"


def test_validate_corpus_preserves_failure_digest_through_stdout_bound(
    tmp_path: Path,
) -> None:
    """Bounded stdout retains a digest marker for the failure-defining lines."""
    manifest, root, _ = _oracle_fixture(tmp_path)
    outcomes = [RunOutcome(0, b"1 passed\n", False)] * 3 + [
        RunOutcome(1, b"FAILED test_calc.py::test_value\n" + b"x" * 512, False)
    ] * 3

    report = validate_corpus(
        manifest,
        root,
        _SequenceRunner(outcomes),
        artifact_store=ArtifactStore(tmp_path / "bounded-artifacts", max_bounded_bytes=64),
    )

    result = report["validation_results"]["results"][0]
    assert result["status"] == "validated"
    buggy_runs = result["attempts"][0]["runs"][3:]
    signatures = {run["failure_signature"] for run in buggy_runs}
    assert len(signatures) == 1
    stdout_name = buggy_runs[0]["artifacts"]["stdout"]["name"]
    assert (tmp_path / "bounded-artifacts" / stdout_name).read_bytes().startswith(
        b"FAILED attest:"
    )


def test_validate_corpus_rejects_legacy_signing_credentials_before_project_execution(
    tmp_path: Path,
) -> None:
    """The Phase0 execution API has no same-process HMAC issuance capability."""
    manifest, root, _ = _oracle_fixture(tmp_path)
    calls: list[str] = []

    class ForbiddenRunner:
        def run(
            self, source_id: str, tool: str, args: tuple[str, ...], cwd: Path
        ) -> RunOutcome:
            calls.append(source_id)
            return RunOutcome(0, b"1 passed\n", False)

    with pytest.raises(TypeError, match="provenance_key"):
        validate_corpus(
            manifest,
            root,
            ForbiddenRunner(),
            artifact_store=ArtifactStore(tmp_path / "must-not-exist"),
            provenance_key_id=KEY_ID,
            provenance_key=b"must-not-enter-project-execution",
        )
    assert calls == []
    assert not (tmp_path / "must-not-exist").exists()


def test_validate_corpus_rejects_manifest_path_replacement_before_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest, root, _ = _oracle_fixture(tmp_path)
    original = manifest.read_bytes()
    changed = json.loads(original)
    changed["corpus_commit"] = "6" * 64
    changed_bytes = json.dumps(changed).encode()
    real_read_bytes = Path.read_bytes
    manifest_reads = 0

    def staged_read(path: Path) -> bytes:
        nonlocal manifest_reads
        if path == manifest:
            manifest_reads += 1
            return original if manifest_reads == 1 else changed_bytes
        return real_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", staged_read)
    calls: list[str] = []

    class ForbiddenRunner:
        def run(
            self, source_id: str, tool: str, args: tuple[str, ...], cwd: Path
        ) -> RunOutcome:
            calls.append(source_id)
            return RunOutcome(0, b"1 passed\n", False)

    with pytest.raises(ValueError, match="manifest changed"):
        validate_corpus(manifest, root, ForbiddenRunner())
    assert calls == []


def test_v2_verifier_uses_one_manifest_snapshot_under_path_replacement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from attest.benchmark.corpus import verify_validation_receipt

    manifest, root, _ = _oracle_fixture(tmp_path)
    bundle = build_validation_v2_bundle(tmp_path / "toctou-bundle", manifest, root)
    original = manifest.read_bytes()
    changed = json.loads(original)
    changed["corpus_commit"] = "6" * 64
    changed_bytes = json.dumps(changed).encode()
    real_read_bytes = Path.read_bytes
    manifest_reads = 0

    def staged_read(path: Path) -> bytes:
        nonlocal manifest_reads
        if path == manifest:
            manifest_reads += 1
            return original if manifest_reads == 1 else changed_bytes
        return real_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", staged_read)
    verification = verify_validation_receipt(
        bundle.receipt_path,
        manifest,
        bundle.results_path,
        bundle.artifact_root,
        authorized_provenance_keys=bundle.authorized_keys,
    )

    assert verification.authority == "none"
    assert "manifest" in verification.integrity.failure_paths


def test_validate_corpus_preserves_dependency_classification_through_stdout_bound(
    tmp_path: Path,
) -> None:
    """A truncated dependency failure remains an exclusion after offline verification."""
    manifest, root, _ = _oracle_fixture(tmp_path)
    dependency_output = (
        b"ModuleNotFoundError: missing_dependency\n"
        + b"x" * 512
        + b"\nFAILED test_calc.py::test_value\n"
    )
    artifact_root = tmp_path / "bounded-dependency-artifacts"
    report = validate_corpus(
        manifest,
        root,
        _SequenceRunner(
            [RunOutcome(0, b"1 passed\n", False)] * 3
            + [RunOutcome(1, dependency_output, False)] * 3
        ),
        artifact_store=ArtifactStore(artifact_root, max_bounded_bytes=64),
    )

    result = report["validation_results"]["results"][0]
    assert result["status"] == "excluded"
    assert result["exclusion_reason"] == "dependency_or_setup_failure"
    buggy_runs = result["attempts"][0]["runs"][3:]
    stdout_name = buggy_runs[0]["artifacts"]["stdout"]["name"]
    assert (artifact_root / stdout_name).read_bytes().startswith(b"DEPENDENCY attest\n")

    from attest.benchmark.corpus import (
        _validation_receipt_v2,
        verify_validation_receipt,
    )

    results_path = tmp_path / "bounded-dependency-validation-results.json"
    receipt_path = tmp_path / "bounded-dependency-validation-receipt.json"
    _write_canonical_json(results_path, report["validation_results"])
    receipt = _validation_receipt_v2(
        hashlib.sha256(manifest.read_bytes()).hexdigest(),
        results_path.read_bytes(),
        hashlib.sha256((artifact_root / "artifacts.json").read_bytes()).hexdigest(),
        [],
        KEY_ID,
        b"test-only-local-validation-authority-key",
    )
    _write_canonical_json(receipt_path, receipt)

    verification = verify_validation_receipt(
        receipt_path,
        manifest,
        results_path,
        artifact_root,
        authorized_provenance_keys={
            KEY_ID: b"test-only-local-validation-authority-key"
        },
    )

    assert verification.integrity.accepted is True
    assert verification.provenance.accepted is True
    assert "validation_results.results[0].exclusion_reason" not in (
        verification.semantic_policy.failure_paths
    )


def test_validate_corpus_preserves_unsigned_all_excluded_evidence(
    tmp_path: Path,
) -> None:
    """Real exclusion attempts remain hash-bound but never become authority."""
    manifest, root, source_id = _oracle_fixture(tmp_path, missing_dependency=True)
    artifact_root = tmp_path / "excluded-artifacts"
    runner = SubprocessCorpusRunner(
        interpreters={source_id: (sys.executable,)},
        timeout_s=10,
        max_output_bytes=16_384,
        isolation=_sandbox_isolation(),
    )
    report = validate_corpus(
        manifest,
        root,
        runner,
        artifact_store=ArtifactStore(artifact_root),
    )

    assert report["validated_pairs"] == 0
    assert report["excluded_pairs"] == 1
    assert report["scorable"] is False
    assert report["receipt"] is None
    result = report["validation_results"]["results"][0]
    assert result["exclusion_reason"] == "dependency_or_setup_failure"
    assert len(result["attempts"][0]["runs"]) == 1

    assert (artifact_root / "artifacts.json").is_file()


def test_validate_corpus_preserves_unsigned_preflight_exclusions(
    tmp_path: Path,
) -> None:
    """A controller envelope preserves a real preflight attempt with no run evidence."""
    manifest, root, source_id = _oracle_fixture(tmp_path)
    control = root / source_id / "pair-222222222222" / "control" / "calc.py"
    control.write_text("def value():\n    return 2\n", encoding="utf-8")
    artifact_root = tmp_path / "preflight-excluded-artifacts"
    runner = SubprocessCorpusRunner(
        interpreters={source_id: (sys.executable,)},
        timeout_s=10,
        max_output_bytes=16_384,
        isolation=_sandbox_isolation(),
    )

    report = validate_corpus(
        manifest,
        root,
        runner,
        artifact_store=ArtifactStore(artifact_root),
    )

    assert report["validated_pairs"] == 0
    assert report["scorable"] is False
    assert report["receipt"] is None
    result = report["validation_results"]["results"][0]
    assert result["exclusion_reason"] == "dirty_checkout"
    assert result["attempts"][0]["phase"] == "preflight"
    assert result["attempts"][0]["runs"] == []

    assert (artifact_root / "artifacts.json").is_file()


def test_validate_corpus_preserves_large_junit_semantics_through_bound(
    tmp_path: Path,
) -> None:
    """Large JUnit evidence remains content-addressed and offline-verifiable."""
    manifest, root, source_id = _oracle_fixture(
        tmp_path, failure_message_size=20_000
    )
    artifact_root = tmp_path / "bounded-junit-artifacts"
    runner = SubprocessCorpusRunner(
        interpreters={source_id: (sys.executable,)},
        timeout_s=10,
        max_output_bytes=32_768,
        isolation=_sandbox_isolation(),
    )
    report = validate_corpus(
        manifest,
        root,
        runner,
        artifact_store=ArtifactStore(artifact_root),
    )

    result = report["validation_results"]["results"][0]
    assert result["status"] == "validated"
    junit_name = result["attempts"][0]["runs"][3]["artifacts"]["junit"]["name"]
    bounded_junit = (artifact_root / junit_name).read_bytes()
    assert bounded_junit.startswith(b"J attest:")
    assert bounded_junit.endswith(b"</testsuites>")

    assert report["receipt"] is None


def test_validate_corpus_hashes_redacted_persisted_stdout_bytes(tmp_path: Path) -> None:
    """Unsigned evidence hashes the exact redacted bytes persisted for inspection."""
    manifest, root, _ = _oracle_fixture(tmp_path)
    secret = "M02_PRIVATE_SENTINEL"
    failure = f"FAILED test_calc.py::test_{secret}\n".encode()
    outcomes = [RunOutcome(0, b"1 passed\n", False)] * 3 + [
        RunOutcome(1, failure, False)
    ] * 3
    artifact_root = tmp_path / "redacted-artifacts"

    report = validate_corpus(
        manifest,
        root,
        _SequenceRunner(outcomes),
        artifact_store=ArtifactStore(artifact_root, secrets=(secret,)),
    )

    result = report["validation_results"]["results"][0]
    assert result["status"] == "validated"
    buggy_run = result["attempts"][0]["runs"][3]
    stdout_name = buggy_run["artifacts"]["stdout"]["name"]
    stored = (artifact_root / stdout_name).read_bytes()
    assert secret.encode() not in stored
    assert buggy_run["failure_signature"] == hashlib.sha256(stored.strip()).hexdigest()


def test_validate_corpus_hashes_redacted_environment_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Secret redaction preserves the unsigned environment-evidence binding."""
    secret = "M02_PRIVATE_ENV_SENTINEL"
    runtime_tmp = tmp_path / f"runtime-{secret}"
    runtime_tmp.mkdir()
    monkeypatch.setenv("TMPDIR", str(runtime_tmp))
    manifest, root, source_id = _oracle_fixture(tmp_path)
    artifact_root = tmp_path / "redacted-environment-artifacts"
    report = validate_corpus(
        manifest,
        root,
        SubprocessCorpusRunner(
            interpreters={source_id: (sys.executable,)},
            timeout_s=10,
            max_output_bytes=16_384,
            isolation=_sandbox_isolation(),
        ),
        artifact_store=ArtifactStore(artifact_root, secrets=(secret,)),
    )

    run = report["validation_results"]["results"][0]["attempts"][0]["runs"][0]
    environment_name = run["artifacts"]["environment"]["name"]
    environment_bytes = (artifact_root / environment_name).read_bytes()
    assert secret.encode() not in environment_bytes
    assert b"[REDACTED]" in environment_bytes

    assert report["receipt"] is None


def test_validate_corpus_rejects_raw_failures_collapsed_by_stdout_bound(
    tmp_path: Path,
) -> None:
    """A common retained tail cannot hide three different raw failure signatures."""
    manifest, root, _ = _oracle_fixture(tmp_path)
    buggy = [
        RunOutcome(
            1,
            f"FAILED test_calc.py::test_raw_{index}\n".encode()
            + b"x" * 512
            + b"\nFAILED test_calc.py::test_common\n",
            False,
        )
        for index in range(3)
    ]

    report = validate_corpus(
        manifest,
        root,
        _SequenceRunner([RunOutcome(0, b"1 passed\n", False)] * 3 + buggy),
        artifact_store=ArtifactStore(tmp_path / "collapsed-artifacts", max_bounded_bytes=64),
    )

    result = report["validation_results"]["results"][0]
    assert result["status"] == "excluded"
    assert result["exclusion_reason"] == "inconsistent_failure_signature"
    buggy_runs = result["attempts"][0]["runs"][3:]
    assert len({run["failure_signature"] for run in buggy_runs}) == 3

    from attest.benchmark.corpus import (
        _validation_receipt_v2,
        verify_validation_receipt,
    )

    results_path = tmp_path / "collapsed-validation-results.json"
    receipt_path = tmp_path / "collapsed-validation-receipt.json"
    _write_canonical_json(results_path, report["validation_results"])
    receipt = _validation_receipt_v2(
        hashlib.sha256(manifest.read_bytes()).hexdigest(),
        results_path.read_bytes(),
        hashlib.sha256(
            (tmp_path / "collapsed-artifacts/artifacts.json").read_bytes()
        ).hexdigest(),
        [],
        KEY_ID,
        b"test-only-local-validation-authority-key",
    )
    _write_canonical_json(receipt_path, receipt)
    verification = verify_validation_receipt(
        receipt_path,
        manifest,
        results_path,
        tmp_path / "collapsed-artifacts",
        authorized_provenance_keys={
            KEY_ID: b"test-only-local-validation-authority-key"
        },
    )

    assert verification.integrity.accepted is True
    assert verification.provenance.accepted is True
    assert "validation_results.results[0].exclusion_reason" not in (
        verification.semantic_policy.failure_paths
    )


def test_v1_validation_receipt_is_manifest_bound_but_historical_only(
    tmp_path: Path,
) -> None:
    """The v1 reader preserves integrity inspection without granting scoring authority."""
    manifest, _, _ = _oracle_fixture(tmp_path)
    receipt_value, results_value = _two_pair_validation_artifacts(manifest)
    receipt_path = tmp_path / "receipt.json"
    results_path = tmp_path / "validation-results.json"
    _write_canonical_json(receipt_path, receipt_value)
    _write_canonical_json(results_path, results_value)

    receipt = load_validation_receipt(receipt_path, manifest, results_path)
    assert receipt.authority == "historical_integrity_only"
    with pytest.raises(ValueError, match="historical_integrity_only"):
        require_validated_pair(receipt, "pair-222222222222")
    with pytest.raises(ValueError, match="historical_integrity_only"):
        require_validated_pair(receipt, "pair-555555555555")

    manifest.write_text(manifest.read_text() + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="manifest digest"):
        load_validation_receipt(receipt_path, manifest, results_path)


def test_protocol_runner_produces_unsigned_non_authorizing_evidence(
    tmp_path: Path,
) -> None:
    """Synthetic outcomes can test oracle logic but cannot become scoring authority."""
    manifest, root, _ = _oracle_fixture(tmp_path)
    outcomes = [RunOutcome(0, b"pass", False)] * 3 + [
        RunOutcome(1, b"FAILED test_calc.py::test_value", False)
    ] * 3

    report = validate_corpus(manifest, root, _SequenceRunner(outcomes))

    assert report["validated_pairs"] == 1
    assert report["receipt"] is None
    assert report["scorable"] is False


def _write_canonical_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def test_validation_v2_rejects_validated_row_without_six_runs(tmp_path: Path) -> None:
    """Removing the attempt/run evidence must revoke semantic authority."""
    from attest.benchmark.corpus import verify_validation_receipt

    manifest, _, _ = _oracle_fixture(tmp_path)
    manifest_sha256 = hashlib.sha256(manifest.read_bytes()).hexdigest()
    results = {
        "schema_version": "2",
        "protocol_version": "attest-validation-v2",
        "manifest_sha256": manifest_sha256,
        "results": [
            {
                "pair_id": "pair-222222222222",
                "status": "validated",
            }
        ],
    }
    results_path = tmp_path / "validation-results.json"
    _write_canonical_json(results_path, results)
    receipt = {
        "schema_version": "2",
        "protocol_version": "attest-validation-v2",
        "manifest_sha256": manifest_sha256,
        "validation_results_sha256": hashlib.sha256(results_path.read_bytes()).hexdigest(),
        "artifact_manifest_sha256": "0" * 64,
        "validated_pair_ids": ["pair-222222222222"],
        "provenance_envelope": {},
    }
    receipt_path = tmp_path / "receipt.json"
    _write_canonical_json(receipt_path, receipt)

    verification = verify_validation_receipt(
        receipt_path,
        manifest,
        results_path,
        tmp_path / "artifacts",
        authorized_provenance_keys={},
    )

    assert verification.semantic_policy.accepted is False
    assert verification.semantic_policy.failure_paths == (
        "validation_results.results[0].attempts",
    )


def test_validation_v2_accepts_only_complete_authorized_run_evidence(
    tmp_path: Path,
) -> None:
    """Six artifact-backed runs under an authorized envelope earn current authority."""
    from attest.benchmark.corpus import (
        ValidationAttempt,
        ValidationReceiptV2,
        ValidationResultV2,
        ValidationRun,
        verify_validation_receipt,
    )

    manifest, _, _ = _oracle_fixture(tmp_path)
    bundle = build_validation_v2_bundle(tmp_path, manifest)

    verification = verify_validation_receipt(
        bundle.receipt_path,
        manifest,
        bundle.results_path,
        bundle.artifact_root,
        authorized_provenance_keys=bundle.authorized_keys,
    )

    assert verification.integrity.accepted is True
    assert verification.provenance.accepted is True
    assert verification.semantic_policy.accepted is True
    assert verification.authority == "current_scoring_authority"
    assert isinstance(verification.receipt, ValidationReceiptV2)
    assert verification.receipt.authority == "unverified"
    with pytest.raises(ValueError, match="requires offline authority verification"):
        require_validated_pair(verification.receipt, "pair-222222222222")
    assert isinstance(verification.results[0], ValidationResultV2)
    assert isinstance(verification.results[0].attempts[0], ValidationAttempt)
    assert all(
        isinstance(run, ValidationRun)
        for run in verification.results[0].attempts[0].runs
    )


def test_validation_verification_binding_is_canonical_complete_and_uncopyable(
    tmp_path: Path,
) -> None:
    """The paid-run binding covers verifier evidence without serializing its seal."""
    from dataclasses import replace

    from attest.benchmark.corpus import (
        validation_receipt_binding_bytes,
        verify_validation_receipt,
    )

    manifest, _, _ = _oracle_fixture(tmp_path)
    verifications = []
    for name in ("first", "second"):
        bundle = build_validation_v2_bundle(tmp_path / name, manifest)
        verifications.append(
            verify_validation_receipt(
                bundle.receipt_path,
                manifest,
                bundle.results_path,
                bundle.artifact_root,
                authorized_provenance_keys=bundle.authorized_keys,
            )
        )

    first = validation_receipt_binding_bytes(verifications[0])
    second = validation_receipt_binding_bytes(verifications[1])
    assert first == second
    document = json.loads(first)
    assert document["authority"] == "current_scoring_authority"
    assert document["receipt"]["schema_version"] == "2"
    assert len(document["results"][0]["attempts"][0]["runs"]) == 6

    copied_capability = replace(verifications[0])
    assert copied_capability.authority == "none"
    with pytest.raises(ValueError, match="verifier capability"):
        validation_receipt_binding_bytes(copied_capability)


def test_validation_v2_binds_result_revisions_to_the_manifest_pair(tmp_path: Path) -> None:
    """A self-consistent result/source pair for unrelated commits has no authority."""
    from attest.benchmark.corpus import verify_validation_receipt

    manifest, _, _ = _oracle_fixture(tmp_path)
    bundle = build_validation_v2_bundle(tmp_path, manifest)
    bundle.results["results"][0]["buggy_sha"] = "a" * 40
    bundle.results["results"][0]["fixed_sha"] = "b" * 40
    runs = bundle.results["results"][0]["attempts"][0]["runs"]
    for revision, repository_sha, run_index in (
        ("fixed", "b" * 40, 0),
        ("buggy", "a" * 40, 3),
    ):
        source_name = runs[run_index]["artifacts"]["source"]["name"]
        bundle.replace_artifact(
            source_name,
            {"revision": revision, "repository_sha": repository_sha},
        )

    verification = verify_validation_receipt(
        bundle.receipt_path,
        manifest,
        bundle.results_path,
        bundle.artifact_root,
        authorized_provenance_keys=bundle.authorized_keys,
    )

    assert verification.authority == "none"
    assert verification.semantic_policy.failure_paths == (
        "validation_results.results[0].buggy_sha",
        "validation_results.results[0].fixed_sha",
    )


def test_validation_v2_recomputes_buggy_signature_from_stdout(tmp_path: Path) -> None:
    """A stable declared hash cannot hide failure text that proves another outcome."""
    from attest.benchmark.corpus import verify_validation_receipt

    manifest, _, _ = _oracle_fixture(tmp_path)
    bundle = build_validation_v2_bundle(tmp_path, manifest)
    for run in bundle.results["results"][0]["attempts"][0]["runs"][3:]:
        run["failure_signature"] = "0" * 64
    bundle.reseal()

    verification = verify_validation_receipt(
        bundle.receipt_path,
        manifest,
        bundle.results_path,
        bundle.artifact_root,
        authorized_provenance_keys=bundle.authorized_keys,
    )

    assert verification.authority == "none"
    assert verification.semantic_policy.failure_paths == (
        "validation_results.results[0].attempts[0].runs[3].failure_signature",
        "validation_results.results[0].attempts[0].runs[4].failure_signature",
        "validation_results.results[0].attempts[0].runs[5].failure_signature",
    )


@pytest.mark.parametrize("artifact_name", ["stdout", "junit"])
def test_validation_v2_reports_exact_tampered_output_artifact(
    tmp_path: Path, artifact_name: str
) -> None:
    """Changing stdout or JUnit bytes under the same summary revokes integrity."""
    from attest.benchmark.corpus import verify_validation_receipt

    manifest, _, _ = _oracle_fixture(tmp_path)
    bundle = build_validation_v2_bundle(tmp_path, manifest)
    run = bundle.results["results"][0]["attempts"][0]["runs"][0]
    relative = run["artifacts"][artifact_name]["name"]
    (bundle.artifact_root / relative).write_bytes(b"tampered evidence\n")

    verification = verify_validation_receipt(
        bundle.receipt_path,
        manifest,
        bundle.results_path,
        bundle.artifact_root,
        authorized_provenance_keys=bundle.authorized_keys,
    )

    assert verification.integrity.accepted is False
    assert verification.authority == "none"
    assert f"artifacts.{relative}.sha256" in verification.integrity.failure_paths


@pytest.mark.parametrize("field", ["runner_id", "profile_id"])
def test_validation_v2_rejects_inconsistent_runner_or_profile(
    tmp_path: Path, field: str
) -> None:
    """One run cannot silently switch runner or isolation profile."""
    from attest.benchmark.corpus import verify_validation_receipt

    manifest, _, _ = _oracle_fixture(tmp_path)
    bundle = build_validation_v2_bundle(tmp_path, manifest)
    run = bundle.results["results"][0]["attempts"][0]["runs"][1]
    run[field] = f"different-{field}"
    bundle.reseal()

    verification = verify_validation_receipt(
        bundle.receipt_path,
        manifest,
        bundle.results_path,
        bundle.artifact_root,
        authorized_provenance_keys=bundle.authorized_keys,
    )

    assert verification.integrity.accepted is True
    assert verification.provenance.accepted is True
    assert verification.semantic_policy.accepted is False
    expected = f"validation_results.results[0].attempts[0].runs[1].{field}"
    assert verification.semantic_policy.failure_paths[0] == expected


def test_validation_v2_rejects_inconsistent_interpreter_reference(tmp_path: Path) -> None:
    """A per-run interpreter change must be visible and fail closed."""
    from attest.benchmark.corpus import verify_validation_receipt

    manifest, _, _ = _oracle_fixture(tmp_path)
    bundle = build_validation_v2_bundle(tmp_path, manifest)
    run = bundle.results["results"][0]["attempts"][0]["runs"][1]
    run["artifacts"]["interpreter"]["sha256"] = "9" * 64
    bundle.reseal()

    verification = verify_validation_receipt(
        bundle.receipt_path,
        manifest,
        bundle.results_path,
        bundle.artifact_root,
        authorized_provenance_keys=bundle.authorized_keys,
    )

    expected = "validation_results.results[0].attempts[0].runs[1].artifacts.interpreter"
    assert verification.integrity.accepted is False
    assert expected in verification.integrity.failure_paths
    assert expected in verification.semantic_policy.failure_paths


@pytest.mark.parametrize(
    "envelope_case",
    [
        "missing",
        "unknown_key",
        "forged_tag",
        "unknown_envelope_version",
        "unknown_algorithm",
        "forged_payload_digest",
    ],
)
def test_validation_v2_rejects_missing_or_unauthorized_provenance(
    tmp_path: Path, envelope_case: str
) -> None:
    """Hash-consistent files still need an authenticated, authorized local envelope."""
    from attest.benchmark.corpus import verify_validation_receipt

    manifest, _, _ = _oracle_fixture(tmp_path)
    bundle = build_validation_v2_bundle(tmp_path, manifest)
    if envelope_case == "missing":
        bundle.receipt.pop("provenance_envelope")
    elif envelope_case == "unknown_key":
        bundle.receipt["provenance_envelope"]["key_id"] = "unknown-key"
    elif envelope_case == "forged_tag":
        bundle.receipt["provenance_envelope"]["authentication_tag"] = "0" * 64
    elif envelope_case == "unknown_envelope_version":
        bundle.receipt["provenance_envelope"]["envelope_version"] = "999"
    elif envelope_case == "unknown_algorithm":
        bundle.receipt["provenance_envelope"]["algorithm"] = "unknown"
    else:
        bundle.receipt["provenance_envelope"]["payload_sha256"] = "0" * 64
    bundle.receipt_path.write_bytes(
        (json.dumps(bundle.receipt, sort_keys=True, separators=(",", ":")) + "\n").encode()
    )

    verification = verify_validation_receipt(
        bundle.receipt_path,
        manifest,
        bundle.results_path,
        bundle.artifact_root,
        authorized_provenance_keys={KEY_ID: bundle.authorized_keys[KEY_ID]},
    )

    assert verification.integrity.accepted is True
    assert verification.provenance.accepted is False
    assert verification.semantic_policy.accepted is True
    assert verification.authority == "none"
    assert verification.provenance.failure_paths
    assert all(
        path.startswith("receipt.provenance_envelope")
        for path in verification.provenance.failure_paths
    )


def test_validation_v2_reports_provenance_independently_of_results_canonicality(
    tmp_path: Path,
) -> None:
    """Authenticated receipt provenance remains visible when result integrity fails."""
    from attest.benchmark.corpus import verify_validation_receipt

    manifest, _, _ = _oracle_fixture(tmp_path)
    bundle = build_validation_v2_bundle(tmp_path, manifest)
    bundle.results_path.write_text(json.dumps(bundle.results, indent=2), encoding="utf-8")
    bundle.reseal_receipt()

    verification = verify_validation_receipt(
        bundle.receipt_path,
        manifest,
        bundle.results_path,
        bundle.artifact_root,
        authorized_provenance_keys=bundle.authorized_keys,
    )

    assert verification.integrity.accepted is False
    assert verification.integrity.failure_paths == (
        "validation_results.canonical_json",
    )
    assert verification.provenance.accepted is True
    assert verification.semantic_policy.accepted is True


def test_validation_v2_authenticates_raw_body_when_a_digest_field_is_malformed(
    tmp_path: Path,
) -> None:
    """Typed integrity failure must not invent a provenance-envelope failure."""
    from attest.benchmark.corpus import verify_validation_receipt

    manifest, _, _ = _oracle_fixture(tmp_path)
    bundle = build_validation_v2_bundle(tmp_path, manifest)
    bundle.receipt["manifest_sha256"] = "not-a-digest"
    bundle.reseal_receipt()

    verification = verify_validation_receipt(
        bundle.receipt_path,
        manifest,
        bundle.results_path,
        bundle.artifact_root,
        authorized_provenance_keys=bundle.authorized_keys,
    )

    assert verification.integrity.accepted is False
    assert "receipt.manifest_sha256" in verification.integrity.failure_paths
    assert verification.provenance.accepted is True


def test_validation_v2_rejects_exclusion_without_a_real_attempt(tmp_path: Path) -> None:
    """An exclusion is not an escape hatch from retaining attempt evidence."""
    from attest.benchmark.corpus import verify_validation_receipt

    manifest, _, _ = _oracle_fixture(tmp_path)
    bundle = build_validation_v2_bundle(tmp_path, manifest)
    result = bundle.results["results"][0]
    result.update(
        {
            "status": "excluded",
            "accepted_attempt_id": None,
            "exclusion_reason": "dependency_or_setup_failure",
            "attempts": [],
        }
    )
    bundle.receipt["validated_pair_ids"] = []
    bundle.reseal()

    verification = verify_validation_receipt(
        bundle.receipt_path,
        manifest,
        bundle.results_path,
        bundle.artifact_root,
        authorized_provenance_keys=bundle.authorized_keys,
    )

    assert verification.semantic_policy.accepted is False
    assert verification.semantic_policy.failure_paths == (
        "validation_results.results[0].attempts",
    )


def test_validation_v2_rejects_execution_exclusion_without_a_run(tmp_path: Path) -> None:
    """An execution-phase exclusion cannot claim an attempt without raw run evidence."""
    from attest.benchmark.corpus import verify_validation_receipt

    manifest, _, _ = _oracle_fixture(tmp_path)
    bundle = build_validation_v2_bundle(tmp_path, manifest)
    result = bundle.results["results"][0]
    attempt = result["attempts"][0]
    result.update(
        {
            "status": "excluded",
            "accepted_attempt_id": None,
            "exclusion_reason": "dependency_or_setup_failure",
        }
    )
    attempt.update(
        {
            "status": "excluded",
            "reason": "dependency_or_setup_failure",
            "runs": [],
        }
    )
    bundle.receipt["validated_pair_ids"] = []
    bundle.reseal()

    verification = verify_validation_receipt(
        bundle.receipt_path,
        manifest,
        bundle.results_path,
        bundle.artifact_root,
        authorized_provenance_keys=bundle.authorized_keys,
    )

    assert verification.authority == "none"
    assert verification.semantic_policy.failure_paths == (
        "validation_results.results[0].attempts[0].runs",
        "validation_results.results[0].exclusion_reason",
    )


def test_validation_v2_accepts_bounded_execution_exclusion_evidence(tmp_path: Path) -> None:
    """A genuine bounded attempt remains auditable even when the pair is excluded."""
    from attest.benchmark.corpus import verify_validation_receipt

    manifest, _, _ = _oracle_fixture(tmp_path)
    bundle = build_validation_v2_bundle(tmp_path, manifest)
    _make_inconsistent_failure_exclusion(bundle)

    verification = verify_validation_receipt(
        bundle.receipt_path,
        manifest,
        bundle.results_path,
        bundle.artifact_root,
        authorized_provenance_keys=bundle.authorized_keys,
    )

    assert verification.integrity.accepted is True
    assert verification.provenance.accepted is True
    assert verification.semantic_policy.accepted is True
    assert len(verification.results[0].attempts[0].runs) == 6


def _make_inconsistent_failure_exclusion(bundle: ValidationV2Bundle) -> None:
    result = bundle.results["results"][0]
    attempt = result["attempts"][0]
    changed_output = b"FAILED test_calc.py::test_other\n"
    changed_run = attempt["runs"][4]
    stdout_name = changed_run["artifacts"]["stdout"]["name"]
    bundle.replace_artifact(stdout_name, changed_output)
    changed_run["failure_signature"] = hashlib.sha256(changed_output.strip()).hexdigest()
    result.update(
        {
            "status": "excluded",
            "accepted_attempt_id": None,
            "exclusion_reason": "inconsistent_failure_signature",
        }
    )
    attempt.update(
        {
            "status": "excluded",
            "reason": "inconsistent_failure_signature",
        }
    )
    bundle.receipt["validated_pair_ids"] = []
    bundle.reseal()


@pytest.mark.parametrize(
    ("reason", "run_indexes"),
    [
        ("timeout", [0]),
        ("inconsistent_failure_signature", list(range(6))),
        ("invented_exclusion_reason", [0]),
    ],
)
def test_validation_v2_recomputes_exclusion_reason_from_runs(
    tmp_path: Path, reason: str, run_indexes: list[int]
) -> None:
    """An authorized envelope cannot relabel retained outcomes as an exclusion."""
    from attest.benchmark.corpus import verify_validation_receipt

    manifest, _, _ = _oracle_fixture(tmp_path)
    bundle = build_validation_v2_bundle(tmp_path, manifest)
    result = bundle.results["results"][0]
    attempt = result["attempts"][0]
    result.update(
        {
            "status": "excluded",
            "accepted_attempt_id": None,
            "exclusion_reason": reason,
        }
    )
    attempt.update(
        {
            "status": "excluded",
            "reason": reason,
            "runs": [attempt["runs"][index] for index in run_indexes],
        }
    )
    bundle.receipt["validated_pair_ids"] = []
    bundle.reseal()

    verification = verify_validation_receipt(
        bundle.receipt_path,
        manifest,
        bundle.results_path,
        bundle.artifact_root,
        authorized_provenance_keys=bundle.authorized_keys,
    )

    assert verification.authority == "none", reason
    assert (
        "validation_results.results[0].exclusion_reason"
        in verification.semantic_policy.failure_paths
    )


@pytest.mark.parametrize("artifact_name", ["stdout", "junit"])
def test_validation_v2_checks_excluded_run_output_semantics(
    tmp_path: Path, artifact_name: str
) -> None:
    """Coherently resealed excluded output must still agree with the run summary."""
    from attest.benchmark.corpus import verify_validation_receipt

    manifest, _, _ = _oracle_fixture(tmp_path)
    bundle = build_validation_v2_bundle(tmp_path, manifest)
    _make_inconsistent_failure_exclusion(bundle)
    run = bundle.results["results"][0]["attempts"][0]["runs"][3]
    name = run["artifacts"][artifact_name]["name"]
    replacement = (
        b"1 passed\n"
        if artifact_name == "stdout"
        else b'<testsuite tests="1" failures="0" errors="0" skipped="0" />\n'
    )
    bundle.replace_artifact(name, replacement)

    verification = verify_validation_receipt(
        bundle.receipt_path,
        manifest,
        bundle.results_path,
        bundle.artifact_root,
        authorized_provenance_keys=bundle.authorized_keys,
    )

    assert verification.authority == "none", artifact_name
    path = "validation_results.results[0].attempts[0].runs[3]"
    assert any(failure.startswith(path) for failure in verification.semantic_policy.failure_paths)


def test_validation_v2_rejects_retrospectively_selected_retry(tmp_path: Path) -> None:
    """V2 permits one bounded attempt; it cannot prove outcome-aware retry precommitment."""
    from attest.benchmark.corpus import verify_validation_receipt

    manifest, _, _ = _oracle_fixture(tmp_path)
    bundle = build_validation_v2_bundle(tmp_path, manifest)
    result = bundle.results["results"][0]
    result["attempts"].append(
        {
            "attempt_id": "attempt-retrospective",
            "pair_id": result["pair_id"],
            "attempt_index": 2,
            "phase": "preflight",
            "status": "excluded",
            "reason": "integrity_failure",
            "runs": [],
        }
    )
    bundle.reseal()

    verification = verify_validation_receipt(
        bundle.receipt_path,
        manifest,
        bundle.results_path,
        bundle.artifact_root,
        authorized_provenance_keys=bundle.authorized_keys,
    )

    assert verification.authority == "none"
    assert verification.semantic_policy.failure_paths == (
        "validation_results.results[0].attempts",
    )


@pytest.mark.parametrize("mutation", ["status", "reason", "too_many_runs"])
def test_validation_v2_exclusion_attempt_fields_have_semantic_teeth(
    tmp_path: Path, mutation: str
) -> None:
    """G-CODE-002: an exclusion must bind one bounded, truthful attempt record."""
    from attest.benchmark.corpus import verify_validation_receipt

    manifest, _, _ = _oracle_fixture(tmp_path)
    bundle = build_validation_v2_bundle(tmp_path, manifest)
    _make_inconsistent_failure_exclusion(bundle)
    result = bundle.results["results"][0]
    attempt = result["attempts"][0]
    if mutation == "status":
        attempt["status"] = "validated"
    elif mutation == "reason":
        attempt["reason"] = "flaky"
    else:
        attempt["runs"] = attempt["runs"] * 7
    bundle.receipt["validated_pair_ids"] = []
    bundle.reseal()

    verification = verify_validation_receipt(
        bundle.receipt_path,
        manifest,
        bundle.results_path,
        bundle.artifact_root,
        authorized_provenance_keys=bundle.authorized_keys,
    )

    assert verification.authority == "none", mutation
    assert verification.semantic_policy.accepted is False, mutation


def test_validation_v2_missing_artifact_reference_fails_closed(tmp_path: Path) -> None:
    """A missing evidence field reports its run path instead of escaping with KeyError."""
    from attest.benchmark.corpus import verify_validation_receipt

    manifest, _, _ = _oracle_fixture(tmp_path)
    bundle = build_validation_v2_bundle(tmp_path, manifest)
    run = bundle.results["results"][0]["attempts"][0]["runs"][0]
    run["artifacts"].pop("junit")
    bundle.reseal()

    verification = verify_validation_receipt(
        bundle.receipt_path,
        manifest,
        bundle.results_path,
        bundle.artifact_root,
        authorized_provenance_keys=bundle.authorized_keys,
    )

    assert verification.authority == "none"
    assert verification.semantic_policy.failure_paths == (
        "validation_results.results[0].attempts[0].runs[0].artifacts",
    )


def test_validation_v2_unknown_version_fails_every_authority_component(
    tmp_path: Path,
) -> None:
    """A future schema cannot inherit current authority through permissive parsing."""
    from attest.benchmark.corpus import verify_validation_receipt

    manifest, _, _ = _oracle_fixture(tmp_path)
    bundle = build_validation_v2_bundle(tmp_path, manifest)
    bundle.receipt["schema_version"] = "999"
    bundle.receipt_path.write_bytes(
        (json.dumps(bundle.receipt, sort_keys=True, separators=(",", ":")) + "\n").encode()
    )

    verification = verify_validation_receipt(
        bundle.receipt_path,
        manifest,
        bundle.results_path,
        bundle.artifact_root,
        authorized_provenance_keys=bundle.authorized_keys,
    )

    assert verification.authority == "none"
    assert verification.integrity.failure_paths == ("receipt.schema_version",)
    assert verification.provenance.failure_paths == ("receipt.schema_version",)
    assert verification.semantic_policy.failure_paths == ("receipt.schema_version",)


def test_validation_v2_unknown_protocol_fails_closed(tmp_path: Path) -> None:
    """Matching receipt/result strings do not make an unknown policy protocol supported."""
    from attest.benchmark.corpus import verify_validation_receipt

    manifest, _, _ = _oracle_fixture(tmp_path)
    bundle = build_validation_v2_bundle(tmp_path, manifest)
    bundle.receipt["protocol_version"] = "attest-validation-v999"
    bundle.results["protocol_version"] = "attest-validation-v999"
    bundle.reseal()

    verification = verify_validation_receipt(
        bundle.receipt_path,
        manifest,
        bundle.results_path,
        bundle.artifact_root,
        authorized_provenance_keys=bundle.authorized_keys,
    )

    assert verification.authority == "none"
    assert verification.semantic_policy.failure_paths == ("receipt.protocol_version",)


@pytest.mark.parametrize(
    ("container", "field"),
    [
        ("result", "manual_status"),
        ("attempt", "caller_authorized"),
        ("run", "summary_only"),
    ],
)
def test_validation_v2_unknown_evidence_fields_fail_closed(
    tmp_path: Path, container: str, field: str
) -> None:
    """Unknown result, attempt, or run fields cannot smuggle a new authority class."""
    from attest.benchmark.corpus import verify_validation_receipt

    manifest, _, _ = _oracle_fixture(tmp_path)
    bundle = build_validation_v2_bundle(tmp_path, manifest)
    result = bundle.results["results"][0]
    target = result
    expected = "validation_results.results[0].fields"
    if container == "attempt":
        target = result["attempts"][0]
        expected = "validation_results.results[0].attempts[0].fields"
    elif container == "run":
        target = result["attempts"][0]["runs"][0]
        expected = "validation_results.results[0].attempts[0].runs[0].fields"
    target[field] = True
    bundle.reseal()

    verification = verify_validation_receipt(
        bundle.receipt_path,
        manifest,
        bundle.results_path,
        bundle.artifact_root,
        authorized_provenance_keys=bundle.authorized_keys,
    )

    assert verification.authority == "none"
    assert expected in verification.integrity.failure_paths


@pytest.mark.parametrize("revision", ["fixed", "buggy"])
def test_validation_v2_binds_source_artifact_to_declared_repository_sha(
    tmp_path: Path, revision: str
) -> None:
    """A result SHA cannot drift away from the source artifact used by its runs."""
    from attest.benchmark.corpus import verify_validation_receipt

    manifest, _, _ = _oracle_fixture(tmp_path)
    bundle = build_validation_v2_bundle(tmp_path, manifest)
    bundle.results["results"][0][f"{revision}_sha"] = "8" * 40
    bundle.reseal()

    verification = verify_validation_receipt(
        bundle.receipt_path,
        manifest,
        bundle.results_path,
        bundle.artifact_root,
        authorized_provenance_keys=bundle.authorized_keys,
    )

    assert verification.authority == "none"
    assert verification.semantic_policy.failure_paths == (
        f"validation_results.results[0].{revision}_sha",
    )


@pytest.mark.parametrize("field", ["runner_id", "profile_id"])
def test_validation_v2_binds_runner_fields_to_executor_artifact(
    tmp_path: Path, field: str
) -> None:
    """Consistent rewritten summaries cannot contradict the executor artifact."""
    from attest.benchmark.corpus import verify_validation_receipt

    manifest, _, _ = _oracle_fixture(tmp_path)
    bundle = build_validation_v2_bundle(tmp_path, manifest)
    for run in bundle.results["results"][0]["attempts"][0]["runs"]:
        run[field] = f"forged-{field}"
    bundle.reseal()

    verification = verify_validation_receipt(
        bundle.receipt_path,
        manifest,
        bundle.results_path,
        bundle.artifact_root,
        authorized_provenance_keys=bundle.authorized_keys,
    )

    assert verification.authority == "none"
    assert verification.semantic_policy.failure_paths[0] == (
        f"validation_results.results[0].attempts[0].runs[0].{field}"
    )


@pytest.mark.parametrize(
    ("artifact_name", "field", "value"),
    [
        ("command", "declared_cwd", "unrelated/cwd"),
        ("interpreter", "executable_sha256", "not-a-digest"),
        ("environment", "sha256", "0" * 64),
        ("executor", "isolation_capability", "unknown-profile"),
    ],
)
def test_validation_v2_binding_artifact_fields_have_semantic_teeth(
    tmp_path: Path, artifact_name: str, field: str, value: str
) -> None:
    """G-CODE-002: coherent artifact rewrites still face field-level policy guards."""
    from attest.benchmark.corpus import verify_validation_receipt

    manifest, _, _ = _oracle_fixture(tmp_path)
    bundle = build_validation_v2_bundle(tmp_path, manifest)
    run = bundle.results["results"][0]["attempts"][0]["runs"][0]
    name = run["artifacts"][artifact_name]["name"]
    payload = json.loads((bundle.artifact_root / name).read_bytes())
    payload[field] = value
    bundle.replace_artifact(name, payload)

    verification = verify_validation_receipt(
        bundle.receipt_path,
        manifest,
        bundle.results_path,
        bundle.artifact_root,
        authorized_provenance_keys=bundle.authorized_keys,
    )

    expected = (
        f"validation_results.results[0].attempts[0].runs[0].artifacts.{artifact_name}"
    )
    assert verification.authority == "none"
    assert expected in verification.semantic_policy.failure_paths


def test_validation_v2_rejects_trailing_executed_argv(tmp_path: Path) -> None:
    """The exact issued command cannot gain an extra selector under a valid envelope."""
    from attest.benchmark.corpus import verify_validation_receipt

    manifest, _, _ = _oracle_fixture(tmp_path)
    bundle = build_validation_v2_bundle(tmp_path, manifest)
    run = bundle.results["results"][0]["attempts"][0]["runs"][0]
    name = run["artifacts"]["command"]["name"]
    payload = json.loads((bundle.artifact_root / name).read_bytes())
    payload["executed_argv"].append("--ignore=test_calc.py")
    bundle.replace_artifact(name, payload)

    verification = verify_validation_receipt(
        bundle.receipt_path,
        manifest,
        bundle.results_path,
        bundle.artifact_root,
        authorized_provenance_keys=bundle.authorized_keys,
    )

    assert verification.authority == "none"
    assert (
        "validation_results.results[0].attempts[0].runs[0].artifacts.command.executed_argv"
        in verification.semantic_policy.failure_paths
    )


def test_validation_v2_binds_non_python_allowed_tool_prefix(tmp_path: Path) -> None:
    """A typed non-Python tool binds its selected executable, not the probe interpreter."""
    from attest.benchmark.corpus import verify_validation_receipt

    manifest, root, _ = _oracle_fixture(tmp_path)
    document = json.loads(manifest.read_bytes())
    test_bytes = b"tox test_calc.py\n"
    (root / "artifacts/test.argv").write_bytes(test_bytes)
    for case in document["cases"]:
        case["tests"]["sha256"] = hashlib.sha256(test_bytes).hexdigest()
    for runtime in document["runtime"]:
        runtime["command"] = {"tool": "tox", "args": ["test_calc.py"]}
    manifest.write_text(json.dumps(document), encoding="utf-8")
    bundle = build_validation_v2_bundle(tmp_path / "tox-bundle", manifest, root)

    verification = verify_validation_receipt(
        bundle.receipt_path,
        manifest,
        bundle.results_path,
        bundle.artifact_root,
        authorized_provenance_keys=bundle.authorized_keys,
    )

    assert verification.authority == "current_scoring_authority", (
        verification.to_json_dict()
    )
    interpreter = dict(verification.results[0].attempts[0].runs[0].artifacts)[
        "interpreter"
    ]
    assert json.loads((bundle.artifact_root / interpreter.name).read_bytes())["argv"] == [
        "/fixture/tox"
    ]


def test_validation_v2_test_artifact_is_bound_to_manifest_descriptor(tmp_path: Path) -> None:
    """A signed but unrelated test file cannot serve as the pair's run evidence."""
    from attest.benchmark.corpus import verify_validation_receipt

    manifest, _, _ = _oracle_fixture(tmp_path)
    bundle = build_validation_v2_bundle(tmp_path, manifest)
    run = bundle.results["results"][0]["attempts"][0]["runs"][0]
    name = run["artifacts"]["test"]["name"]
    bundle.replace_artifact(name, b"{python} -m pytest -q unrelated.py\n")

    verification = verify_validation_receipt(
        bundle.receipt_path,
        manifest,
        bundle.results_path,
        bundle.artifact_root,
        authorized_provenance_keys=bundle.authorized_keys,
    )

    expected = (
        "validation_results.results[0].attempts[0].runs[0].artifacts.test"
    )
    assert verification.authority == "none"
    assert expected in verification.semantic_policy.failure_paths


def test_validation_v2_source_artifact_rejects_unknown_fields(tmp_path: Path) -> None:
    """A signed source descriptor cannot extend its meaning with an unknown field."""
    from attest.benchmark.corpus import verify_validation_receipt

    manifest, _, _ = _oracle_fixture(tmp_path)
    bundle = build_validation_v2_bundle(tmp_path, manifest)
    run = bundle.results["results"][0]["attempts"][0]["runs"][0]
    name = run["artifacts"]["source"]["name"]
    source = json.loads((bundle.artifact_root / name).read_bytes())
    source["unreviewed_ref"] = "refs/heads/main"
    bundle.replace_artifact(name, source)

    verification = verify_validation_receipt(
        bundle.receipt_path,
        manifest,
        bundle.results_path,
        bundle.artifact_root,
        authorized_provenance_keys=bundle.authorized_keys,
    )

    assert verification.authority == "none"
    assert (
        "validation_results.results[0].attempts[0].runs[0].artifacts.source"
        in verification.semantic_policy.failure_paths
    )


@pytest.mark.parametrize("mutation", ["size", "missing", "unknown"])
def test_validation_v2_reports_exact_artifact_integrity_error_kind(
    tmp_path: Path, mutation: str
) -> None:
    """Offline integrity paths distinguish size, missing, and unknown artifacts."""
    from attest.benchmark.corpus import verify_validation_receipt

    manifest, _, _ = _oracle_fixture(tmp_path)
    bundle = build_validation_v2_bundle(tmp_path, manifest)
    artifact_manifest_path = bundle.artifact_root / "artifacts.json"
    artifact_manifest = json.loads(artifact_manifest_path.read_bytes())
    name = artifact_manifest["artifacts"][0]["name"]
    if mutation == "size":
        artifact_manifest["artifacts"][0]["size_bytes"] += 1
        artifact_manifest_path.write_bytes(
            json.dumps(
                artifact_manifest, sort_keys=True, separators=(",", ":")
            ).encode()
            + b"\n"
        )
        expected = f"artifacts.{name}.size_bytes"
    elif mutation == "missing":
        (bundle.artifact_root / name).unlink()
        expected = f"artifacts.{name}"
    else:
        (bundle.artifact_root / "stowaway.txt").write_text("unknown", encoding="utf-8")
        expected = "artifacts.stowaway.txt"
    bundle.receipt["artifact_manifest_sha256"] = hashlib.sha256(
        artifact_manifest_path.read_bytes()
    ).hexdigest()
    bundle.reseal_receipt()

    verification = verify_validation_receipt(
        bundle.receipt_path,
        manifest,
        bundle.results_path,
        bundle.artifact_root,
        authorized_provenance_keys=bundle.authorized_keys,
    )

    assert verification.integrity.accepted is False
    assert expected in verification.integrity.failure_paths


def test_validation_v2_rejects_signed_oversized_bounded_artifact(
    tmp_path: Path,
) -> None:
    """An authorized envelope cannot raise or bypass protocol evidence ceilings."""
    from attest.benchmark.corpus import verify_validation_receipt

    manifest, _, _ = _oracle_fixture(tmp_path)
    bundle = build_validation_v2_bundle(tmp_path / "bundle", manifest)
    buggy_run = bundle.results["results"][0]["attempts"][0]["runs"][3]
    stdout_name = buggy_run["artifacts"]["stdout"]["name"]
    bundle.replace_artifact(
        stdout_name,
        b"FAILED test_calc.py::test_value\n" + b"x" * MAX_BOUNDED_ARTIFACT_BYTES,
    )

    verification = verify_validation_receipt(
        bundle.receipt_path,
        manifest,
        bundle.results_path,
        bundle.artifact_root,
        authorized_provenance_keys=bundle.authorized_keys,
    )

    assert verification.authority == "none"
    assert verification.integrity.failure_paths == (
        f"artifacts.{stdout_name}.size_bytes",
    )


@pytest.mark.parametrize(
    ("mutation", "expected_suffix"),
    [
        ("truncated", "truncated"),
        ("size", "size_bytes"),
        ("unknown_field", "fields"),
    ],
)
def test_validation_v2_reports_exact_artifact_manifest_entry_field(
    tmp_path: Path, mutation: str, expected_suffix: str
) -> None:
    """Malformed manifest entries identify the artifact and exact field class."""
    from attest.benchmark.corpus import verify_validation_receipt

    manifest, _, _ = _oracle_fixture(tmp_path)
    bundle = build_validation_v2_bundle(tmp_path, manifest)
    artifact_manifest_path = bundle.artifact_root / "artifacts.json"
    artifact_manifest = json.loads(artifact_manifest_path.read_bytes())
    entry = artifact_manifest["artifacts"][0]
    name = entry["name"]
    if mutation == "truncated":
        entry["truncated"] = "false"
    elif mutation == "size":
        entry["size_bytes"] = True
    else:
        entry["unexpected"] = True
    artifact_manifest_path.write_bytes(
        json.dumps(artifact_manifest, sort_keys=True, separators=(",", ":")).encode()
        + b"\n"
    )
    bundle.receipt["artifact_manifest_sha256"] = hashlib.sha256(
        artifact_manifest_path.read_bytes()
    ).hexdigest()
    bundle.reseal_receipt()

    verification = verify_validation_receipt(
        bundle.receipt_path,
        manifest,
        bundle.results_path,
        bundle.artifact_root,
        authorized_provenance_keys=bundle.authorized_keys,
    )

    assert verification.integrity.accepted is False
    assert (
        f"artifacts.{name}.{expected_suffix}"
        in verification.integrity.failure_paths
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("name", 7),
        ("kind", "unknown-kind"),
        ("sha256", "not-a-digest"),
        ("size_bytes", True),
        ("truncated", "false"),
    ],
)
def test_validation_v2_artifact_record_fields_fail_closed_at_exact_path(
    tmp_path: Path, field: str, value: object
) -> None:
    """G-CODE-002: every content-address reference field has a precise guard."""
    from attest.benchmark.corpus import verify_validation_receipt

    manifest, _, _ = _oracle_fixture(tmp_path)
    bundle = build_validation_v2_bundle(tmp_path, manifest)
    reference = bundle.results["results"][0]["attempts"][0]["runs"][0][
        "artifacts"
    ]["stdout"]
    reference[field] = value
    bundle.reseal()

    verification = verify_validation_receipt(
        bundle.receipt_path,
        manifest,
        bundle.results_path,
        bundle.artifact_root,
        authorized_provenance_keys=bundle.authorized_keys,
    )

    expected = (
        "validation_results.results[0].attempts[0].runs[0]"
        f".artifacts.stdout.{field}"
    )
    assert verification.authority == "none"
    assert expected in verification.semantic_policy.failure_paths


@pytest.mark.parametrize(
    "unsafe_name",
    ["../outside.json", "/etc/passwd", "embedded\0null.json", "unpaired-\ud800.json"],
)
def test_validation_v2_rejects_escaping_artifact_reference_names(
    tmp_path: Path, unsafe_name: str
) -> None:
    """Semantic verification never reads an absolute or parent-traversing reference."""
    from attest.benchmark.corpus import verify_validation_receipt

    manifest, _, _ = _oracle_fixture(tmp_path)
    bundle = build_validation_v2_bundle(tmp_path, manifest)
    run = bundle.results["results"][0]["attempts"][0]["runs"][0]
    run["artifacts"]["source"]["name"] = unsafe_name
    bundle.reseal()

    verification = verify_validation_receipt(
        bundle.receipt_path,
        manifest,
        bundle.results_path,
        bundle.artifact_root,
        authorized_provenance_keys=bundle.authorized_keys,
    )

    expected = (
        "validation_results.results[0].attempts[0].runs[0].artifacts.source.name"
    )
    assert verification.authority == "none"
    assert expected in verification.semantic_policy.failure_paths


def test_validation_v2_rejects_listed_artifact_symlink_escape(tmp_path: Path) -> None:
    """A listed digest cannot authorize bytes reached through an outside-root symlink."""
    from attest.benchmark.corpus import verify_validation_receipt

    manifest, _, _ = _oracle_fixture(tmp_path)
    bundle = build_validation_v2_bundle(tmp_path, manifest)
    run = bundle.results["results"][0]["attempts"][0]["runs"][0]
    name = run["artifacts"]["source"]["name"]
    artifact_path = bundle.artifact_root / name
    outside = tmp_path / "outside-source.json"
    outside.write_bytes(artifact_path.read_bytes())
    artifact_path.unlink()
    artifact_path.symlink_to(outside)

    verification = verify_validation_receipt(
        bundle.receipt_path,
        manifest,
        bundle.results_path,
        bundle.artifact_root,
        authorized_provenance_keys=bundle.authorized_keys,
    )

    assert verification.authority == "none"
    assert f"artifacts.{name}" in verification.integrity.failure_paths


@pytest.mark.parametrize(
    ("run_index", "ordinal"),
    [(0, 3), (1, 1)],
)
def test_validation_v2_exclusion_requires_exact_run_sequence_prefix(
    tmp_path: Path, run_index: int, ordinal: int
) -> None:
    """An exclusion cannot reorder or skip issuer ordinals within its bounded prefix."""
    from attest.benchmark.corpus import verify_validation_receipt

    manifest, _, _ = _oracle_fixture(tmp_path)
    bundle = build_validation_v2_bundle(tmp_path, manifest)
    result = bundle.results["results"][0]
    attempt = result["attempts"][0]
    selected = attempt["runs"][: run_index + 1]
    selected[run_index]["ordinal"] = ordinal
    result.update(
        {
            "status": "excluded",
            "accepted_attempt_id": None,
            "exclusion_reason": "incomplete_execution",
        }
    )
    attempt.update(
        {
            "status": "excluded",
            "reason": "incomplete_execution",
            "runs": selected,
        }
    )
    bundle.receipt["validated_pair_ids"] = []
    bundle.reseal()

    verification = verify_validation_receipt(
        bundle.receipt_path,
        manifest,
        bundle.results_path,
        bundle.artifact_root,
        authorized_provenance_keys=bundle.authorized_keys,
    )

    assert verification.authority == "none"
    assert (
        "validation_results.results[0].attempts[0].runs"
        in verification.semantic_policy.failure_paths
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "attempt_id",
        "attempt_pair_id",
        "attempt_index",
        "attempt_phase",
        "attempt_status",
        "attempt_reason",
        "duplicate_run_id",
        "run_revision",
        "run_ordinal",
        "run_outcome",
        "run_returncode",
        "run_timed_out",
        "run_failure_signature",
    ],
)
def test_validation_v2_attempt_and_run_field_mutations_remove_authority(
    tmp_path: Path, mutation: str
) -> None:
    """G-CODE-002: every attempt/run policy field has a guard with observable teeth."""
    from attest.benchmark.corpus import verify_validation_receipt

    manifest, _, _ = _oracle_fixture(tmp_path)
    bundle = build_validation_v2_bundle(tmp_path, manifest)
    result = bundle.results["results"][0]
    attempt = result["attempts"][0]
    run = attempt["runs"][0]
    if mutation == "attempt_id":
        attempt["attempt_id"] = "attempt-unaccepted"
    elif mutation == "attempt_pair_id":
        attempt["pair_id"] = "pair-999999999999"
    elif mutation == "attempt_index":
        attempt["attempt_index"] = 2
    elif mutation == "attempt_phase":
        attempt["phase"] = "preflight"
    elif mutation == "attempt_status":
        attempt["status"] = "excluded"
    elif mutation == "attempt_reason":
        attempt["reason"] = "manual_override"
    elif mutation == "duplicate_run_id":
        attempt["runs"][1]["run_id"] = run["run_id"]
    elif mutation == "run_revision":
        run["revision"] = "buggy"
    elif mutation == "run_ordinal":
        run["ordinal"] = 9
    elif mutation == "run_outcome":
        run["outcome"] = "fail"
    elif mutation == "run_returncode":
        run["returncode"] = 9
    elif mutation == "run_timed_out":
        run["timed_out"] = True
    else:
        run["failure_signature"] = "e" * 64
    bundle.reseal()

    verification = verify_validation_receipt(
        bundle.receipt_path,
        manifest,
        bundle.results_path,
        bundle.artifact_root,
        authorized_provenance_keys=bundle.authorized_keys,
    )

    assert verification.authority == "none", mutation
    assert verification.semantic_policy.accepted is False, mutation


def test_validation_v2_rejects_interleaved_fixed_and_buggy_runs(tmp_path: Path) -> None:
    """Validated evidence is exactly three fixed runs followed by three buggy runs."""
    from attest.benchmark.corpus import verify_validation_receipt

    manifest, _, _ = _oracle_fixture(tmp_path)
    bundle = build_validation_v2_bundle(tmp_path, manifest)
    runs = bundle.results["results"][0]["attempts"][0]["runs"]
    runs[2], runs[3] = runs[3], runs[2]
    bundle.reseal()

    verification = verify_validation_receipt(
        bundle.receipt_path,
        manifest,
        bundle.results_path,
        bundle.artifact_root,
        authorized_provenance_keys=bundle.authorized_keys,
    )

    assert verification.authority == "none"
    assert (
        "validation_results.results[0].attempts[0].runs"
        in verification.semantic_policy.failure_paths
    )


@pytest.mark.parametrize(
    ("field", "path"),
    [
        ("attempt_index", "validation_results.results[0].attempts[0].attempt_index"),
        ("ordinal", "validation_results.results[0].attempts[0].runs[0].ordinal"),
        ("returncode", "validation_results.results[0].attempts[0].runs[0].returncode"),
    ],
)
def test_validation_v2_rejects_boolean_integer_fields_with_exact_paths(
    tmp_path: Path, field: str, path: str
) -> None:
    """JSON booleans cannot satisfy integer fields and must name the exact bad field."""
    from attest.benchmark.corpus import verify_validation_receipt

    manifest, _, _ = _oracle_fixture(tmp_path)
    bundle = build_validation_v2_bundle(tmp_path, manifest)
    attempt = bundle.results["results"][0]["attempts"][0]
    target = attempt if field == "attempt_index" else attempt["runs"][0]
    target[field] = True
    bundle.reseal()

    verification = verify_validation_receipt(
        bundle.receipt_path,
        manifest,
        bundle.results_path,
        bundle.artifact_root,
        authorized_provenance_keys=bundle.authorized_keys,
    )

    assert verification.authority == "none"
    assert path in verification.semantic_policy.failure_paths


def test_load_validation_v2_fails_closed_with_exact_artifact_path(tmp_path: Path) -> None:
    """Strict callers get a precise exception instead of a partially trusted object."""
    from attest.benchmark.corpus import load_validation_receipt_v2

    manifest, _, _ = _oracle_fixture(tmp_path)
    bundle = build_validation_v2_bundle(tmp_path, manifest)

    loaded = load_validation_receipt_v2(
        bundle.receipt_path,
        manifest,
        bundle.results_path,
        bundle.artifact_root,
        authorized_provenance_keys=bundle.authorized_keys,
    )
    assert loaded.authority == "current_scoring_authority"

    relative = bundle.results["results"][0]["attempts"][0]["runs"][0][
        "artifacts"
    ]["stdout"]["name"]
    (bundle.artifact_root / relative).write_text("tampered\n", encoding="utf-8")

    with pytest.raises(
        ValueError, match=rf"integrity:artifacts\.{re.escape(relative)}\.sha256"
    ):
        load_validation_receipt_v2(
            bundle.receipt_path,
            manifest,
            bundle.results_path,
            bundle.artifact_root,
            authorized_provenance_keys=bundle.authorized_keys,
        )


def _two_pair_validation_artifacts(manifest: Path) -> tuple[dict[str, object], dict[str, object]]:
    document = json.loads(manifest.read_text())
    original_pair = "pair-222222222222"
    second_pair = "pair-555555555555"
    runtime_by_case = {row["case_id"]: row for row in document["runtime"]}
    for case in list(document["cases"]):
        copied = json.loads(json.dumps(case))
        copied["pair_id"] = second_pair
        copied["case_id"] = (
            "case-555555555551"
            if case["role"] == "historical_bug_replay"
            else "case-555555555552"
        )
        document["cases"].append(copied)
        runtime = json.loads(json.dumps(runtime_by_case[case["case_id"]]))
        runtime["case_id"] = copied["case_id"]
        role_dir = "replay" if copied["role"] == "historical_bug_replay" else "control"
        runtime["cwd"] = f"source-111111111111/{second_pair}/{role_dir}"
        document["runtime"].append(runtime)
        if copied["role"] == "historical_bug_replay":
            truth = json.loads(json.dumps(document["truth_defects"][0]))
            truth["defect_id"] = "truth_known_second"
            truth["case_id"] = copied["case_id"]
            document["truth_defects"].append(truth)
    manifest.write_text(json.dumps(document), encoding="utf-8")
    manifest_sha256 = hashlib.sha256(manifest.read_bytes()).hexdigest()
    results: dict[str, object] = {
        "schema_version": "1",
        "manifest_sha256": manifest_sha256,
        "results": [
            {"pair_id": original_pair, "status": "validated"},
            {"pair_id": second_pair, "status": "excluded", "reason": "timeout"},
        ],
    }
    results_bytes = (
        json.dumps(results, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()
    receipt: dict[str, object] = {
        "schema_version": "1",
        "manifest_sha256": manifest_sha256,
        "validated_pair_ids": [original_pair],
        "validation_results_sha256": hashlib.sha256(results_bytes).hexdigest(),
    }
    return receipt, results


def test_v1_receipt_loader_rejects_manifest_path_replacement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest, _, _ = _oracle_fixture(tmp_path)
    receipt, validation_results = _two_pair_validation_artifacts(manifest)
    receipt_path = tmp_path / "snapshot-receipt.json"
    results_path = tmp_path / "snapshot-results.json"
    _write_canonical_json(receipt_path, receipt)
    _write_canonical_json(results_path, validation_results)
    original = manifest.read_bytes()
    changed = json.loads(original)
    changed["corpus_commit"] = "6" * 64
    changed_bytes = json.dumps(changed).encode()
    real_read_bytes = Path.read_bytes
    manifest_reads = 0

    def staged_read(path: Path) -> bytes:
        nonlocal manifest_reads
        if path == manifest:
            manifest_reads += 1
            return original if manifest_reads == 1 else changed_bytes
        return real_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", staged_read)

    with pytest.raises(ValueError, match="manifest changed"):
        load_validation_receipt(receipt_path, manifest, results_path)


def test_validation_receipt_rejects_known_pair_substitution_and_arbitrary_hash(
    tmp_path: Path,
) -> None:
    """A known manifest pair plus a well-shaped fake hash is not validation evidence."""
    manifest, _, _ = _oracle_fixture(tmp_path)
    receipt, validation_results = _two_pair_validation_artifacts(manifest)
    receipt["validated_pair_ids"] = ["pair-555555555555"]
    receipt["validation_results_sha256"] = "a" * 64
    receipt_path = tmp_path / "receipt.json"
    results_path = tmp_path / "validation-results.json"
    _write_canonical_json(receipt_path, receipt)
    _write_canonical_json(results_path, validation_results)

    with pytest.raises(ValueError, match="validation results digest"):
        load_validation_receipt(receipt_path, manifest, results_path)


def test_validation_receipt_rejects_results_and_allowlist_tampering(tmp_path: Path) -> None:
    """The receipt allowlist must be derived from the exact signed-results bytes."""
    manifest, _, _ = _oracle_fixture(tmp_path)
    receipt, validation_results = _two_pair_validation_artifacts(manifest)
    receipt_path = tmp_path / "receipt.json"
    results_path = tmp_path / "validation-results.json"
    _write_canonical_json(receipt_path, receipt)
    tampered_results = json.loads(json.dumps(validation_results))
    tampered_results["results"][0]["status"] = "excluded"
    tampered_results["results"][0]["reason"] = "forged"
    _write_canonical_json(results_path, tampered_results)
    with pytest.raises(ValueError, match="validation results digest"):
        load_validation_receipt(receipt_path, manifest, results_path)

    _write_canonical_json(results_path, validation_results)
    tampered_receipt = dict(receipt)
    tampered_receipt["validated_pair_ids"] = ["pair-555555555555"]
    _write_canonical_json(receipt_path, tampered_receipt)
    with pytest.raises(ValueError, match="validated pair allowlist"):
        load_validation_receipt(receipt_path, manifest, results_path)


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
    assert partial["scorable"] is False
    assert partial["receipt"] is None

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
    with pytest.raises(IsolationError, match="capability"):
        no_isolation.run(source_id, "python", ("-c", "pass"), tmp_path)

    runner = SubprocessCorpusRunner(
        interpreters={source_id: (sys.executable,)}, isolation=_sandbox_isolation()
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
        isolation=_sandbox_isolation(),
    )
    outcome = allowed.run(source_id, "tox", (), tmp_path)
    assert outcome.returncode == 0
    assert outcome.execution_prefix == allowed._allowed_tools[(source_id, "tox")]
    assert explicit_marker.is_file()
    assert not marker.exists()


def _sandbox_isolation() -> IsolationAdapter:
    sandbox = Path("/usr/bin/sandbox-exec")
    if sys.platform != "darwin" or not sandbox.is_file():
        pytest.skip("requires a real OS network sandbox")
    return IsolationAdapter(
        capability="attest.network-deny.v1",
        wrapper_argv=(
            str(sandbox),
            "-p",
            "(version 1) (allow default) (deny network*)",
        ),
        wrapper_sha256=hashlib.sha256(sandbox.read_bytes()).hexdigest(),
    )


def test_plain_or_forged_isolation_produces_no_authority(tmp_path: Path) -> None:
    """A claimed capability cannot make unisolated diagnostics authoritative."""
    manifest, root, source_id = _oracle_fixture(tmp_path)
    passthrough = tmp_path / "passthrough"
    passthrough.write_text("#!/bin/sh\nexec \"$@\"\n", encoding="utf-8")
    passthrough.chmod(0o755)
    forged = IsolationAdapter(
        capability="attest.network-deny.v1",
        wrapper_argv=(str(passthrough),),
        wrapper_sha256=hashlib.sha256(passthrough.read_bytes()).hexdigest(),
    )
    runner = SubprocessCorpusRunner(
        interpreters={source_id: (sys.executable,)}, isolation=forged
    )

    report = validate_corpus(manifest, root, runner)

    assert report["command_success"] is False
    assert report["scorable"] is False
    assert report["receipt"] is None
    assert report["results"][0]["reason"] == "isolation_unverified"


def test_isolation_capability_and_wrapper_hash_are_verified(tmp_path: Path) -> None:
    """Missing, unknown, or file-drifted capability evidence must fail before execution."""
    source_id = "source-111111111111"
    with pytest.raises(IsolationError, match="capability"):
        SubprocessCorpusRunner(interpreters={source_id: (sys.executable,)}).run(
            source_id, "python", ("-c", "pass"), tmp_path
        )
    unknown = IsolationAdapter(
        capability="caller-says-offline",
        wrapper_argv=(sys.executable,),
        wrapper_sha256=hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest(),
    )
    with pytest.raises(IsolationError, match="capability"):
        SubprocessCorpusRunner(
            interpreters={source_id: (sys.executable,)}, isolation=unknown
        ).run(source_id, "python", ("-c", "pass"), tmp_path)
    drifted = IsolationAdapter(
        capability="attest.network-deny.v1",
        wrapper_argv=(sys.executable,),
        wrapper_sha256="0" * 64,
    )
    with pytest.raises(IsolationError, match="wrapper digest"):
        SubprocessCorpusRunner(
            interpreters={source_id: (sys.executable,)}, isolation=drifted
        ).run(source_id, "python", ("-c", "pass"), tmp_path)

def test_subprocess_runner_bounds_streaming_output_memory(tmp_path: Path) -> None:
    """Large child output must be drained continuously without an unbounded parent buffer."""
    source_id = "source-111111111111"
    runner = SubprocessCorpusRunner(
        interpreters={source_id: (sys.executable,)},
        max_output_bytes=128,
        isolation=_sandbox_isolation(),
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
        isolation=_sandbox_isolation(),
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


class _RaiseAfterOneRunner:
    def __init__(self) -> None:
        self.calls = 0

    def run(
        self, source_id: str, tool: str, args: tuple[str, ...], cwd: Path
    ) -> RunOutcome:
        self.calls += 1
        if self.calls == 1:
            return RunOutcome(
                0,
                b"1 passed\n",
                False,
                b'<testsuite tests="1" failures="0" errors="0" skipped="0" />\n',
                ("python", "-m", "pytest", "-q", "test_calc.py"),
            )
        raise OSError("runner transport failed")


def test_validate_corpus_retains_completed_run_when_later_repeat_raises(
    tmp_path: Path,
) -> None:
    """A handled runner failure cannot erase a completed exclusion attempt run."""
    manifest, root, _ = _oracle_fixture(tmp_path)

    report = validate_corpus(
        manifest,
        root,
        _RaiseAfterOneRunner(),
        artifact_store=ArtifactStore(tmp_path / "partial-artifacts"),
    )

    attempt = report["validation_results"]["results"][0]["attempts"][0]
    assert report["results"][0]["status"] == "excluded"
    assert attempt["phase"] == "execution"
    assert len(attempt["runs"]) == 1


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
