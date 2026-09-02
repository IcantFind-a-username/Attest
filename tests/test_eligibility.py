"""R-03: clusters and eligibility are functions of the candidate multiset."""

from __future__ import annotations

import itertools
import subprocess
from pathlib import Path

from attest.review.dedup import merge_findings
from attest.review.diffs import git_diff
from attest.review.eligibility import classify_finding
from attest.review.schema import Finding


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def _repo(root: Path) -> tuple[Path, str]:
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "fixture@example.invalid")
    _git(root, "config", "user.name", "Fixture")
    (root / "app.py").write_text(
        "def average(items):\n"
        "    if not items:\n"
        "        return 0\n"
        "    return sum(items) / len(items)\n",
        encoding="utf-8",
    )
    (root / "notes.txt").write_text("old\n", encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "base")
    base = _git(root, "rev-parse", "HEAD")
    (root / "app.py").write_text(
        "def average(items):\n"
        "    return sum(items) / len(items)\n"
        "\n"
        "\n"
        "def ratio(a, b):\n"
        "    return a / b\n",
        encoding="utf-8",
    )
    (root / "fresh.py").write_text("def brand_new(x):\n    return x[0]\n", encoding="utf-8")
    (root / "notes.txt").write_text("new\n", encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "head")
    return root, base


def _f(claim: str, file: str, line: int, scenario: str = "boom") -> Finding:
    return Finding(
        claim=claim,
        file=file,
        line=line,
        failure_scenario=scenario,
        falsification_plan="check",
    )


def test_permuted_batches_yield_identical_clusters_and_eligibility(tmp_path: Path) -> None:
    repo, base = _repo(tmp_path / "repo")
    diff = git_diff(repo, base)
    # a transitive chain on the regression (lines 2/2/2 wording drifts), one
    # distinct defect on the new function, one on a new file, one non-Python
    samples = [
        [
            _f("Division by zero when items is empty.", "app.py", 2, "average([]) crashes"),
            _f("ratio divides by zero for b == 0.", "app.py", 6, "ratio(1, 0) crashes"),
        ],
        [
            _f("Empty items list divides by zero.", "app.py", 2, "average([]) raises"),
            _f("brand_new indexes an empty sequence.", "fresh.py", 2, "brand_new([]) raises"),
        ],
        [
            _f("average divides by zero on empty input list.", "app.py", 2, "empty list raises"),
            _f("Notes changed without review.", "notes.txt", 1, "text edited"),
        ],
    ]

    def projection(per_sample: list[list[Finding]]) -> list[tuple[object, ...]]:
        merged = merge_findings(per_sample)
        rows = []
        for finding in merged:
            eligibility = classify_finding(repo, diff, base, finding, executor_reason=None)
            rows.append(
                (
                    finding.file,
                    finding.line,
                    finding.claim,
                    finding.votes,
                    finding.cluster_id,
                    sorted(
                        (member.file, member.line, member.claim) for member in finding.members
                    ),
                    eligibility.eligibility.value,
                )
            )
        return rows

    reference = projection(samples)
    assert [row[6] for row in reference] == [
        "regression",
        "new_code",
        "new_code",
        "non_python",
    ]
    assert [row[3] for row in reference] == [3, 1, 1, 1]
    for order in itertools.permutations(range(len(samples))):
        for reverse_inner in (False, True):
            permuted = [
                list(reversed(samples[i])) if reverse_inner else list(samples[i])
                for i in order
            ]
            assert projection(permuted) == reference, (order, reverse_inner)
