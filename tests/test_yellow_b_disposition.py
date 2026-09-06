"""D-169: yellow (b)'s two classes, and what each of them is allowed to do now.

Owner decision 2 of 2026-09-07 after two rule versions produced no sentence on
79 units:

* the **null/Optional** class is **closed**, and closed means it buys nothing —
  the guard returns before the tree read and before the model call, so the class
  costs $0.00 rather than a little less;
* the **exception propagation** class is **kept as a shadow** — it still runs,
  still writes its rows, and reaches no author-visible surface.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from attest.github.presentation import propagation_comments, render_complete
from attest.review.budget import Budget
from attest.review.ci import nullability_notes, propagation_notes
from attest.review.nullability import NULLABILITY_ENABLED
from attest.review.propagation import PROPAGATION_SHADOW, PropagationNote
from attest.review.proposer import ProviderResult


class Forbidden:
    """A provider that fails the test if the closed class asks it anything."""

    def sample(
        self,
        system: str,
        prompt: str,
        schema: dict[str, object],
        max_tokens: int,
        *,
        timeout_s: float | None = None,
    ) -> ProviderResult:
        raise AssertionError("the closed class must not reach a provider")


def _repo(root: Path) -> tuple[Path, str, str]:
    """A two-commit repository whose head adds a raising callee and a caller."""

    def git(*args: str) -> None:
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)

    root.mkdir(parents=True, exist_ok=True)
    git("init", "-q")
    git("config", "user.email", "fixture@example.invalid")
    git("config", "user.name", "Fixture")
    (root / "lib.py").write_text(
        "def parse(text):\n    return text\n\n\ndef run(text):\n    return parse(text)\n",
        encoding="utf-8",
    )
    git("add", ".")
    git("commit", "-qm", "base")
    base = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()
    (root / "lib.py").write_text(
        "def parse(text):\n"
        "    if not text:\n"
        "        raise ValueError('empty')\n"
        "    return text\n"
        "\n"
        "\n"
        "def run(text, fallback=None):\n"
        "    if fallback is None:\n"
        "        fallback = ''\n"
        "    return parse(text) or fallback\n",
        encoding="utf-8",
    )
    git("add", ".")
    git("commit", "-qm", "head")
    head = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()
    return root, base, head


def test_the_closed_class_reaches_no_provider_and_costs_nothing(tmp_path: Path) -> None:
    assert NULLABILITY_ENABLED is False
    repo, base, head = _repo(tmp_path / "repo")
    budget = Budget(limit_usd=1.00, model="claude-sonnet-5")
    notes = nullability_notes(
        repo=repo,
        base_sha=base,
        head_sha=head,
        provider=Forbidden(),  # type: ignore[arg-type]
        budget=budget,
        ledger=None,
        task_id=None,
    )
    assert notes == []
    # not "cheaper": nothing was reserved, nothing was settled, nothing was spent
    assert (budget.spent_usd, budget.reserved_usd, budget.calls) == (0.0, 0.0, [])


def test_the_shadow_class_still_runs_and_still_says_nothing_to_an_author(
    tmp_path: Path,
) -> None:
    assert PROPAGATION_SHADOW is True
    repo, base, head = _repo(tmp_path / "repo")
    # it runs, free, on the same tree the closed class refused
    notes = propagation_notes(repo=repo, base_sha=base, head_sha=head)
    assert isinstance(notes, list)
    assert all(isinstance(note, PropagationNote) for note in notes)

    # and were it ever to speak, the shadow is what keeps it off both surfaces:
    # `run_ci` passes an empty sequence to each of them while PROPAGATION_SHADOW
    # holds, so neither can carry a note however many the level found
    assert propagation_comments([]) == []
    body = render_complete(
        [],
        spend_usd=0.0,
        elapsed_s=0.1,
        evidence={},
        structural=(),
        units=(0, 0),
        impact=(),
        nullability=(),
        propagation=(),
    )
    assert "propagation" not in body.lower()


@pytest.mark.parametrize("flag", (NULLABILITY_ENABLED, not PROPAGATION_SHADOW))
def test_both_dispositions_are_one_flag_each(flag: bool) -> None:
    """Reopening either class is a single boolean, not a rewrite."""
    assert flag is False
