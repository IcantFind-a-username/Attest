"""Owner fix 2 (2026-09-03): sample counting for the review notes."""

from __future__ import annotations

from pathlib import Path

import pytest

from attest.review.config import ReviewConfig
from attest.review.run import run_review


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    import subprocess

    def git(*args: str) -> None:
        subprocess.run(["git", "-C", str(tmp_path), *args], check=True, capture_output=True)

    git("init", "-b", "main")
    git("config", "user.email", "test@example.com")
    git("config", "user.name", "Test")
    (tmp_path / "app.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    git("add", "app.py")
    git("commit", "-m", "base")
    (tmp_path / "app.py").write_text("def f():\n    return 2\n", encoding="utf-8")
    return tmp_path


class NoTextThenAbstainingProvider:
    """Sample 0 has no text block (exhausted by reasoning); sample 1 abstains."""

    def __init__(self) -> None:
        self.calls = 0

    def sample(
        self,
        system: str,
        prompt: str,
        schema: dict[str, object],
        max_tokens: int,
        *,
        timeout_s: float | None = None,
    ):
        from attest.review.proposer import ProviderResult

        self.calls += 1
        if self.calls == 1:
            return ProviderResult(
                text=None,
                input_tokens=10,
                output_tokens=max_tokens,
                stop_reason="max_tokens",
                content_types=("thinking",),
            )
        return ProviderResult(
            text='{"findings": []}', input_tokens=10, output_tokens=5, stop_reason="end_turn"
        )


def test_review_reports_no_text_and_true_abstention_apart(repo: Path) -> None:
    """Owner fix 2 (2026-09-03): the run's notes count samples without text
    separately from the model's own empty findings lists; only the latter is
    silence."""
    review = run_review(
        repo, None, ReviewConfig(k_samples=2, tier0_commands=[]), NoTextThenAbstainingProvider()
    )
    counts = [note for note in review.notes if note.startswith("samples:")]
    assert counts == [
        "samples: 2; intact: 0; no text returned: 1; abstained (empty findings list): 1; other: 0"
    ]
    assert review.deferred_reason is None
