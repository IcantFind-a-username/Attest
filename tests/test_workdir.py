"""D-138: the working directory leaves the repository tree; the record does not.

Two properties, and the owner named both:

1. **no execution path is inside the repository tree** -- not the generated
   test, not the controller's inputs/outputs mounts, not the throwaway
   worktrees. On macOS that is what keeps a Docker bind-mount source out of
   ``/Users``, where a Docker Desktop fault froze every mount on 2026-09-05;
2. **the durable record still lands in ``<repo>/.attest``** -- the evidence
   bundle above all, which is the thing an auditor is handed.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from attest.github.client import GitHubClient
from attest.review.ci import run_ci
from attest.review.config import ReviewConfig
from attest.review.executor import (
    ExecutionOutcome,
    ExecutorLimits,
    ReproSpec,
    execute_differential,
    execute_repro,
)
from attest.review.workdir import (
    ENV_WORK_ROOT,
    gate_root,
    inside,
    repo_key,
    repro_root,
    session_id,
    work_parent,
    work_root,
)
from test_ci_flow import (  # noqa: F401 - fixtures are re-exported into this module
    RecordingGitHub,
    RecordingProvider,
    _context,
    _finding_payload,
    github_server,
    planted_repo,
)
from test_executor import candidate, differential_repo


def test_work_root_is_never_inside_the_repository_it_serves(tmp_path: Path) -> None:
    """Including the awkward case: a repository that itself lives in the
    temporary directory, which is where every test repository lives."""

    for repo in (tmp_path, tmp_path / "nested" / "repo", Path("/Users/somebody/project")):
        root = work_root(repo)
        assert not inside(root, repo), f"{root} is inside {repo}"
        assert inside(root, work_parent())
        assert not inside(repro_root(repo, "t", "f"), repo)
        assert not inside(gate_root(repo, "t", "f"), repo)


def test_two_repositories_of_the_same_name_do_not_share_a_working_root(
    tmp_path: Path,
) -> None:
    """The corpus keeps clones of the same project side by side; a shared
    working root would let one review's worktree land in another's mounts."""

    one = tmp_path / "a" / "click"
    two = tmp_path / "b" / "click"
    one.mkdir(parents=True)
    two.mkdir(parents=True)

    assert repo_key(one) != repo_key(two)
    assert work_root(one) != work_root(two)
    assert work_root(one).parent == work_root(two).parent  # one session, one parent


def test_the_session_component_is_stable_within_a_process(tmp_path: Path) -> None:
    assert session_id() and session_id() == session_id()
    assert session_id() in str(work_root(tmp_path))
    assert str(os.getpid()) in session_id()


def test_work_parent_honours_the_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.setenv(ENV_WORK_ROOT, str(elsewhere))

    assert work_parent() == Path(os.path.realpath(elsewhere))
    assert inside(work_root(tmp_path / "repo"), elsewhere)


def test_the_child_of_a_session_root_is_a_real_directory_after_a_run(
    tmp_path: Path,
) -> None:
    """A live ``execute_repro``: the generated source is written, it is written
    outside the repository, and the repository gains no ``.attest`` at all."""

    stored = candidate(file="mod.py", line=1)
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "mod.py").write_text("value = 1\n", encoding="utf-8")

    result = execute_repro(
        repo,
        stored,
        ReproSpec("def test_repro():\n    assert True"),
        ExecutorLimits(),
    )

    work = repro_root(repo, stored.task_id, stored.finding.finding_id)
    assert result.outcome is ExecutionOutcome.NOT_REPRODUCED, result.reason
    assert (work / "test_repro.py").is_file()
    assert not inside(work, repo)
    assert not (repo / ".attest").exists()


def test_a_differential_puts_both_worktrees_outside_the_repository(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The strongest form of the property: while the run is in flight, every
    path git has registered as a worktree of this repository is outside it."""

    repo, base_sha, head_sha = differential_repo(tmp_path)
    stored = candidate(file="mod.py", line=1)
    seen: list[str] = []

    def record_worktrees() -> None:
        listed = subprocess.run(
            ["git", "-C", str(repo), "worktree", "list", "--porcelain"],
            capture_output=True,
            text=True,
            check=False,
        )
        seen.extend(
            line.split(" ", 1)[1]
            for line in listed.stdout.splitlines()
            if line.startswith("worktree ")
        )

    real_execute = execute_repro

    def spy(*args: object, **kwargs: object) -> object:
        record_worktrees()
        return real_execute(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr("attest.review.executor.execute_repro", spy)

    result = execute_differential(
        repo,
        stored,
        ReproSpec("import mod\n\ndef test_repro():\n    assert mod.add(2, 2) == 4"),
        ExecutorLimits(),
        base_sha=base_sha,
        head_sha=head_sha,
    )

    assert result.outcome is ExecutionOutcome.REPRODUCED, result.reason
    # the repository's own root is a worktree of itself and is expected here;
    # every *other* registered worktree must sit outside it
    others = [path for path in seen if Path(os.path.realpath(path)) != Path(os.path.realpath(repo))]
    assert others, "the differential registered no worktree at all"
    assert all(not inside(Path(path), repo) for path in others), others
    assert not (repo / ".attest" / "repro").exists()


@pytest.mark.skipif(sys.platform != "darwin", reason="the fault this decision answers is macOS")
def test_the_working_root_is_not_under_the_user_home_on_macos(tmp_path: Path) -> None:
    """D-138's operational point, stated as a test: a bind-mount source under
    ``/Users`` is what hung. ``$HOME`` is where the repositories live and the
    working root must not follow them there."""

    home = Path(os.path.realpath(Path.home()))
    assert not inside(work_root(tmp_path / "repo"), home)


def test_the_bundle_still_lands_under_dot_attest(
    planted_repo: tuple[Path, str, str],  # noqa: F811 - fixture re-exported above
    github_server: RecordingGitHub,  # noqa: F811
) -> None:
    """The other half of D-138, on the product's own path: a full ``run_ci``
    certifies a defect, and the record it leaves behind -- bundle, ledger,
    receipt -- is under ``<repo>/.attest`` while nothing that executed is."""

    repo, base_sha, head_sha = planted_repo
    provider = RecordingProvider(
        _finding_payload(),
        json.dumps(
            {
                "test_body": "import runpy\n\n"
                "def test_average_handles_empty_input():\n"
                "    average = runpy.run_path('app.py')['average']\n"
                "    assert average([]) == 0\n"
            }
        ),
    )

    result = run_ci(
        repo,
        _context(base_sha, head_sha),
        GitHubClient("local-token", github_server.url),
        ReviewConfig(k_samples=2, tier0_commands=[]),
        provider,
        limits=ExecutorLimits(wall_timeout_s=20.0),
    )

    assert result.surfaced_count == 1
    bundles = sorted((repo / ".attest" / "evidence").rglob("receipt.json"))
    assert len(bundles) == 1, bundles
    assert (repo / ".attest" / "ledger.jsonl").is_file()
    # and the execution left nothing behind inside the tree under review
    assert not (repo / ".attest" / "repro").exists()
    assert not (repo / ".attest" / "gate").exists()
    assert sorted(path.name for path in (repo / ".attest").iterdir()) == [
        "cache",
        "candidates.jsonl",
        "controller.key",
        "evidence",
        "ledger.jsonl",
    ]
