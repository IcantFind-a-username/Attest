"""What Attest does not review, said in one line and exited zero (D-159).

Attest reviews Python repositories that run pytest inside a Linux container.
Outside that, the failure a user meets used to be a bootstrap traceback, an
exit code 2 in a pull-request check, or -- worst -- a review that read as
"nothing found". Those are three wrong answers to "this tool cannot look at
your project".

Each unsupported scenario now has one fixed sentence naming the reason, printed
as the `[silent]` line, exit 0, before a provider is constructed and before
anything is bought.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from attest.cli.main import main
from attest.review import support
from attest.review.output_contract import SILENCE_MARKER
from attest.review.support import (
    NO_DOCKER,
    NO_PYTEST,
    NOT_PYTHON,
    UNREADABLE_LOCK,
    from_reason,
    preflight,
)


def _git_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    for args in (
        ("init", "-b", "main"),
        ("config", "user.email", "t@example.com"),
        ("config", "user.name", "T"),
    ):
        subprocess.run(["git", "-C", str(path), *args], check=True, capture_output=True)
    return path


def _python_project(path: Path) -> Path:
    _git_repo(path)
    (path / "pyproject.toml").write_text(
        '[project]\nname = "x"\ndependencies = ["pytest"]\n', encoding="utf-8"
    )
    (path / "app.py").write_text("def total(items):\n    return sum(items)\n", encoding="utf-8")
    return path


def test_a_repository_with_no_python_is_told_so(tmp_path: Path) -> None:
    repo = _git_repo(tmp_path / "go")
    (repo / "main.go").write_text("package main\n", encoding="utf-8")

    assert preflight(repo) == NOT_PYTHON


def test_an_unparsable_lock_file_is_told_so(tmp_path: Path) -> None:
    repo = _python_project(tmp_path / "badlock")
    (repo / "poetry.lock").write_text("[[package\nname = broken\n", encoding="utf-8")

    assert preflight(repo) == UNREADABLE_LOCK


def test_a_host_without_docker_is_told_so_by_the_backends_own_reason() -> None:
    assert from_reason("isolation backend unavailable: docker not found") == NO_DOCKER
    assert from_reason("docker is not installed on this host") == NO_DOCKER


def test_pytest_missing_from_the_image_is_told_so_by_the_bootstrap_reason() -> None:
    reason = (
        "environment bootstrap failed (python 3.11, roots ['.']): "
        "ERROR: Could not find a version that satisfies the requirement pytest"
    )
    assert from_reason(reason) == NO_PYTEST


def test_a_repository_with_no_test_suite_is_supported(tmp_path: Path) -> None:
    """The reproduction is generated and pytest is installed into the image, so
    "this project does not use pytest" is not a refusal -- and pretending it
    were would refuse most of this product's own test corpus."""
    repo = _git_repo(tmp_path / "notests")
    (repo / "app.py").write_text("def total(items):\n    return sum(items)\n", encoding="utf-8")

    assert preflight(repo) is None
    assert not support.declares_pytest(repo)


def test_an_ordinary_defer_is_not_dressed_up_as_unsupported() -> None:
    assert from_reason("verification deferred: intent: value change confirmed") is None
    assert from_reason("shared verification deadline exceeded after 600s") is None
    assert from_reason("") is None


def test_a_supported_project_is_not_refused(tmp_path: Path) -> None:
    repo = _python_project(tmp_path / "fine")
    (repo / "poetry.lock").write_text('name = "requests"\nversion = "2.31.0"\n', encoding="utf-8")

    assert preflight(repo) is None


@pytest.mark.parametrize(
    ("build", "expected"),
    (
        (lambda p: (p / "main.go").write_text("package main\n", encoding="utf-8"), NOT_PYTHON),
        (
            lambda p: (
                (p / "app.py").write_text("x = 1\n", encoding="utf-8"),
                (p / "uv.lock").write_text("[[package\nbroken", encoding="utf-8"),
            ),
            UNREADABLE_LOCK,
        ),
    ),
    ids=("not-python", "unreadable-lock"),
)
def test_the_cli_prints_one_silent_line_and_exits_zero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], build, expected
) -> None:
    repo = _git_repo(tmp_path / "cli")
    build(repo)

    code = main(["--repo", str(repo), "review", "--base", "HEAD"])

    out = capsys.readouterr().out.strip().splitlines()
    assert code == 0
    assert len(out) == 1
    assert out[0].startswith(SILENCE_MARKER)
    assert out[0] == expected.line
    assert "Traceback" not in out[0]


def test_every_refusal_reads_as_one_silent_line_naming_its_cause() -> None:
    for refusal in (NOT_PYTHON, NO_PYTEST, NO_DOCKER, UNREADABLE_LOCK):
        assert refusal.line.startswith(SILENCE_MARKER)
        assert "\n" not in refusal.line
        assert refusal.line.startswith(f"{SILENCE_MARKER} unsupported: ")
        assert "nothing was " in refusal.line
        assert refusal.code in support.SUPPORT_CODES
