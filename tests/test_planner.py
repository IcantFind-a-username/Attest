"""R-01: the proposer sees bounded repository context, not only the diff."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from attest.review.config import ReviewConfig
from attest.review.proposer import ProviderResult
from attest.review.run import run_review


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


class PromptRecorder:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def sample(
        self,
        system: str,
        prompt: str,
        schema: dict[str, object],
        max_tokens: int,
        *,
        timeout_s: float | None = None,
    ) -> ProviderResult:
        self.prompts.append(prompt)
        return ProviderResult(text=json.dumps({"findings": []}), input_tokens=10, output_tokens=5)


def test_cross_file_defect_context_contains_the_unchanged_caller(tmp_path: Path) -> None:
    """A callee's signature changes in lib.py; its caller in main.py does not.

    The diff never mentions main.py, so the proposer can only see the defect if
    the planner retrieves the caller. The existing test that pins the old
    behaviour is context too.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "fixture@example.invalid")
    _git(repo, "config", "user.name", "Fixture")
    (repo / "lib.py").write_text("def area(w, h):\n    return w * h\n", encoding="utf-8")
    (repo / "main.py").write_text(
        "from lib import area\n\n\ndef report():\n    return area(2, 3)\n", encoding="utf-8"
    )
    (repo / "tests").mkdir()
    (repo / "tests" / "test_lib.py").write_text(
        "from lib import area\n\n\ndef test_area():\n    assert area(2, 3) == 6\n",
        encoding="utf-8",
    )
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "base")
    base = _git(repo, "rev-parse", "HEAD")
    (repo / "lib.py").write_text(
        "def area(w, h, unit):\n    return w * h * unit\n", encoding="utf-8"
    )
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "head changes the signature; the caller is untouched")

    provider = PromptRecorder()
    run_review(repo, base, ReviewConfig(k_samples=1, tier0_commands=[]), provider)

    assert len(provider.prompts) == 1
    prompt = provider.prompts[0]
    assert "main.py" in prompt
    assert "area(2, 3)" in prompt
    assert "tests/test_lib.py::test_area" in prompt
    # the old-side definition is visible even though only the head is checked out
    assert "def area(w, h):" in prompt
