"""Owner item 9 (2026-09-03): the drawer is visible to the owner in `attest stats`."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from attest.cli.main import main
from attest.review.config import ReviewConfig
from attest.review.executor import ExecutorLimits
from attest.review.proposer import ProviderResult
from attest.review.run import run_review


class UnfaithfulProvider:
    """Proposes one finding whose reproduction fails on both trees."""

    def sample(
        self,
        system: str,
        prompt: str,
        schema: dict[str, object],
        max_tokens: int,
        *,
        timeout_s: float | None = None,
    ) -> ProviderResult:
        if "focused pytest reproduction" in system:
            payload = json.dumps({"test_body": "def test_repro():\n    assert False\n"})
        else:
            payload = json.dumps(
                {
                    "findings": [
                        {
                            "claim": "average() divides by zero when items is empty.",
                            "anchor": {"file": "app.py", "line": 2},
                            "failure_scenario": "average([]) raises ZeroDivisionError",
                            "falsification_plan": "call average([]) and require 0",
                        }
                    ]
                }
            )
        return ProviderResult(text=payload, input_tokens=10, output_tokens=10)


def _plant(tmp_path: Path) -> tuple[Path, str]:
    def git(*args: str) -> str:
        completed = subprocess.run(
            ["git", "-C", str(tmp_path), *args], check=True, capture_output=True, text=True
        )
        return completed.stdout.strip()

    git("init", "-b", "main")
    git("config", "user.email", "test@example.com")
    git("config", "user.name", "Test")
    (tmp_path / "app.py").write_text(
        "def average(items):\n    if not items:\n        return 0\n"
        "    return sum(items) / len(items)\n",
        encoding="utf-8",
    )
    git("add", "app.py")
    git("commit", "-m", "base")
    base_sha = git("rev-parse", "HEAD")
    (tmp_path / "app.py").write_text(
        "def average(items):\n    return sum(items) / len(items)\n", encoding="utf-8"
    )
    git("add", "app.py")
    git("commit", "-m", "regress")
    return tmp_path, base_sha


def test_uncertified_candidate_is_visible_in_the_drawer_with_its_failure_reason(
    tmp_path: Path, capsys
) -> None:
    repo, base_sha = _plant(tmp_path)
    review = run_review(
        repo,
        base_sha,
        ReviewConfig(k_samples=2, tier0_commands=[]),
        UnfaithfulProvider(),
        verify=True,
        limits=ExecutorLimits(wall_timeout_s=20.0),
    )
    assert review.published == []
    finding_id = review.results[0].finding.finding_id

    assert main(["--repo", str(repo), "stats", "--drawer"]) == 0
    out = capsys.readouterr().out
    assert f"[{finding_id}] app.py:2 votes 2; reproduction: unfaithful test" in out
    assert "average() divides by zero" in out
    assert "attest feedback <id>" in out

    assert main(["--repo", str(repo), "feedback", finding_id, "--dismiss"]) == 0
    capsys.readouterr()
    assert main(["--repo", str(repo), "stats", "--drawer"]) == 0
    assert "label: dismiss" in capsys.readouterr().out
