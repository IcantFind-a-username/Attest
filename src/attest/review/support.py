"""What this product does not review, said in one line instead of a traceback.

Attest reviews Python repositories whose head code runs under `pytest` inside a
Linux container. Outside that it is unsupported, and the failure a user meets
matters: a stack trace out of a bootstrap, an exit code 2 in a pull-request
check, or a review that reads as "nothing found" are three wrong answers to
"this tool cannot look at your project". Each unsupported scenario therefore has
**one fixed sentence naming the reason**, printed as the `[silent]` line, and the
process exits **0**.

Two of the four are decided from the tree before anything is bought
(`preflight`), and two are decided by the backend and are recognised from the
reason it gives (`from_reason`):

- **not Python** and **an unparsable lock file** are properties of the tree.
- **no docker** and **no pytest** are properties of the *environment*, and they
  cannot honestly be guessed from the tree. In particular **a repository with no
  test suite is supported**: Attest installs `pytest` into the image itself and
  writes the test it runs, so "this project does not use pytest" is not a
  refusal. What refuses is pytest failing in the image that was built, which is
  what the bootstrap reports.

The check says *nothing* about whether a supported project will produce a
finding. It only refuses to pretend.
"""

from __future__ import annotations

import tomllib
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from attest.execution.container_images import _SKIP, LOCK_MANIFESTS, MAX_DEPTH
from attest.review.output_contract import SILENCE_MARKER

SUPPORT_POLICY_VERSION = "attest.support.v1"

# a tree is Python if it carries a .py file that is not vendored or generated
_PYTHON_SUFFIX = ".py"
# pytest is declared, not guessed: a config that names it, a dependency that
# pins it, or a tests directory holding a file pytest would collect
_PYTEST_CONFIG_FILES = ("pytest.ini", "tox.ini", "setup.cfg", "pyproject.toml")
_DEPENDENCY_FILES = (
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "requirements.txt",
    "requirements-dev.txt",
    "requirements-test.txt",
)


@dataclass(frozen=True)
class Unsupported:
    """One refusal: a stable code, and the sentence the user reads."""

    code: str
    reason: str

    @property
    def line(self) -> str:
        """The `[silent]` line, in the fixed shape every level's output has."""
        return f"{SILENCE_MARKER} {self.reason}"


NOT_PYTHON = Unsupported(
    "not-python",
    "unsupported: this repository has no Python source, and Attest reviews Python; "
    "nothing was read and nothing was spent.",
)
NO_PYTEST = Unsupported(
    "no-pytest",
    "unsupported: pytest could not be provided in the reproduction image, and every "
    "claim Attest makes is a pytest run on two revisions; nothing was verified.",
)
NO_DOCKER = Unsupported(
    "no-docker",
    "unsupported: docker is not available here, and Attest runs head code only inside a "
    "container; nothing was verified.",
)
UNREADABLE_LOCK = Unsupported(
    "unreadable-lock",
    "unsupported: this repository's dependency lock file cannot be parsed, so the "
    "reproduction environment cannot be built; nothing was read and nothing was spent.",
)

SUPPORT_CODES = (NOT_PYTHON.code, NO_PYTEST.code, NO_DOCKER.code, UNREADABLE_LOCK.code)


def _walk(tree: Path) -> Iterator[tuple[Path, Path]]:
    for current in tree.rglob("*"):
        relative = current.relative_to(tree)
        if len(relative.parts) > MAX_DEPTH + 1 or any(part in _SKIP for part in relative.parts):
            continue
        yield current, relative


def _has_python(tree: Path) -> bool:
    for current, _relative in _walk(tree):
        if current.is_file() and current.suffix == _PYTHON_SUFFIX:
            return True
    return False


def _declares_pytest(tree: Path) -> bool:
    for name in _PYTEST_CONFIG_FILES:
        path = tree / name
        if path.is_file():
            try:
                text = path.read_text(errors="replace")
            except OSError:
                continue
            if "pytest" in text:
                return True
    for name in _DEPENDENCY_FILES:
        path = tree / name
        if path.is_file():
            try:
                if "pytest" in path.read_text(errors="replace"):
                    return True
            except OSError:
                continue
    for current, relative in _walk(tree):
        if not current.is_file() or current.suffix != _PYTHON_SUFFIX:
            continue
        name = relative.name
        if name.startswith("test_") or name.endswith("_test.py") or "tests" in relative.parts:
            return True
    return False


def _lock_is_readable(tree: Path) -> bool:
    """Every lock file the image key digests must at least parse.

    Only the TOML ones are actually parsed -- the rest are checked for being
    readable text, because a format this product does not understand is not the
    same as a corrupt one.
    """
    for current, relative in _walk(tree):
        if not current.is_file() or relative.name not in LOCK_MANIFESTS:
            continue
        try:
            raw = current.read_bytes()
        except OSError:
            return False
        if relative.name in {"poetry.lock", "uv.lock", "pdm.lock", "Pipfile"}:
            try:
                tomllib.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, tomllib.TOMLDecodeError):
                return False
        else:
            try:
                raw.decode("utf-8")
            except UnicodeDecodeError:
                return False
    return True


def preflight(tree: Path) -> Unsupported | None:
    """The one reason this **tree** cannot be reviewed, decided before any spend.

    Only properties of the tree are decided here. Whether pytest and docker can
    actually be provided is a property of the environment and is answered by
    `from_reason` once the backend has tried.
    """
    if not _has_python(tree):
        return NOT_PYTHON
    if not _lock_is_readable(tree):
        return UNREADABLE_LOCK
    return None


def from_reason(reason: str) -> Unsupported | None:
    """The fixed refusal behind a backend or bootstrap reason, if it is one.

    The reason strings are the product's own (`select_backend`,
    `container_images._bootstrap_failure`); anything else is a real DEFER with
    its own sentence and is left alone.
    """
    if type(reason) is not str or not reason:
        return None
    lowered = reason.lower()
    if "docker not found" in lowered or "docker is not installed" in lowered:
        return NO_DOCKER
    if "environment bootstrap failed" in lowered and "pytest" in lowered:
        return NO_PYTEST
    return None


def declares_pytest(tree: Path) -> bool:
    """Does this tree carry a pytest suite of its own?

    **Not** a support condition — a repository with no tests is reviewed like
    any other, because the reproduction is generated and pytest is installed
    into the image. Exposed because the reports say how often it is true.
    """
    return _declares_pytest(tree)
