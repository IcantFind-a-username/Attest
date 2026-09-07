"""What this product does not review, said in one line instead of a traceback.

Attest reviews Python repositories whose head code runs under `pytest` inside a
Linux container. Outside that it is unsupported, and the failure a user meets
matters: a stack trace out of a bootstrap, an exit code 2 in a pull-request
check, or a review that reads as "nothing found" are three wrong answers to
"this tool cannot look at your project". Each unsupported scenario therefore has
**one fixed sentence naming the reason**, printed as the `[silent]` line, and the
process exits **0**.

Two of the five are decided from the tree before anything is bought
(`preflight`), and three are decided by the backend or by a run and are
recognised from the reason it gives (`from_reason`):

- **not Python** and **an unparsable lock file** are properties of the tree.
- **no docker** and **no pytest** are properties of the *environment*, and they
  cannot honestly be guessed from the tree. In particular **a repository with no
  test suite is supported**: Attest installs `pytest` into the image itself and
  writes the test it runs, so "this project does not use pytest" is not a
  refusal. What refuses is pytest failing in the image that was built, which is
  what the bootstrap reports.
- **outside the interpreter range** is a property of the tree *and* of a run,
  which is why it is not in `preflight`: a project declaring less than 3.10
  often runs on 3.12 perfectly well, and only a reproduction that collected
  nothing turns the declaration into a refusal (D-186).

The check says *nothing* about whether a supported project will produce a
finding. It only refuses to pretend.
"""

from __future__ import annotations

import re
import tomllib
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

from attest.execution.container_images import (
    _SKIP,
    AVAILABLE_PYTHONS,
    LOCK_MANIFESTS,
    MAX_DEPTH,
    PRIMARY_PYTHON,
    project_python,
)
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
SUPPORTED_RANGE = f"{AVAILABLE_PYTHONS[-1]}-{AVAILABLE_PYTHONS[0]}"
OUTSIDE_INTERPRETER_RANGE = Unsupported(
    "interpreter-out-of-range",
    f"unsupported: this project declares Python outside {SUPPORTED_RANGE} and pytest "
    f"collected no test at all under the {PRIMARY_PYTHON} Attest fell back to, so the "
    "reproduction never ran; nothing was verified -- Attest can review this repository "
    f"once it runs on Python {AVAILABLE_PYTHONS[-1]} or newer.",
)

SUPPORT_CODES = (
    NOT_PYTHON.code,
    NO_PYTEST.code,
    NO_DOCKER.code,
    UNREADABLE_LOCK.code,
    OUTSIDE_INTERPRETER_RANGE.code,
)


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


# Which build step failed, as the builder itself names it. BuildKit prints the
# failing command once (`process "/bin/sh -c <cmd>" did not complete
# successfully`) and marks its Dockerfile line with `>>>`, while echoing every
# *neighbouring* line as plain context. A search over the whole reason therefore
# reads the successful `RUN pip install pytest` two lines above the failure and
# calls a project that will not install a missing pytest, which is the wrong
# sentence and the wrong next step (measured on `tenacity`, 2026-09-09).
_FAILED_COMMAND_RE = re.compile(r'process "(?:/bin/sh -c )?(.+?)" did not complete', re.S)
_MARKED_DOCKERFILE_LINE_RE = re.compile(r"^\s*\d+\s*\|\s*>>>\s*(.+)$", re.M)


def failed_build_step(reason: str) -> str | None:
    """The command a bootstrap failure actually died on, or None if the reason
    does not name one (a resolver error, a timeout, a daemon refusal)."""
    if type(reason) is not str or not reason:
        return None
    found = _FAILED_COMMAND_RE.search(reason)
    if found:
        return found.group(1).strip()
    marked = _MARKED_DOCKERFILE_LINE_RE.search(reason)
    return marked.group(1).strip() if marked else None


# --- a project the chosen interpreter cannot collect (D-186) ---------------
# D-162 narrowed the reproduction range to 3.10-3.13 and gave a project whose
# own declaration falls outside it the primary, 3.12, on the ground that "a
# project that cannot install on 3.10 is a bootstrap failure". A 2019-2022
# `pytest` tree installs there perfectly well and then cannot collect -- its
# assertion rewriter builds AST nodes 3.12 rejects -- so no bootstrap failure
# fires, the run produces no JUnit artifact at all, and the operator is shown
# `missing or malformed JUnit evidence`, which reads as a broken host (D-185).
#
# The refusal is decided by two facts, both of them counted rather than
# guessed, and it needs both:
#
# 1. **no test was collected**: the run produced no JUnit artifact, or a
#    collect-only run failed -- so nothing about the change was observed and
#    there is no evidence for any verdict to rest on;
# 2. **the interpreter was not the project's**: `project_python` fell back to
#    the primary *because the tree's own declaration lies outside the range*,
#    which is the one case where the reproduction runs a version the project
#    never claimed to support.
#
# Measured on the 16 held-out cases (2026-09-11, docker only, $0.00): condition
# 1 holds for exactly the 7 `pytest` trees that cannot be reviewed and for
# **none of the 7 whose probe collects**, and every one of the 7 also satisfies
# condition 2. The remaining two cases never get an image at all: they satisfy
# condition 2 alone, fail earlier at the image build, and keep their existing
# bootstrap sentence (D-175). Neither fact alone is the refusal: a project
# inside the range that fails to collect has an ordinary scaffolding problem,
# and a project outside it that collects fine is reviewed like any other.
_OUT_OF_RANGE_DECLARATION = "declared range outside"
INTERPRETER_RANGE_REASON = (
    f"reproduction interpreter outside the project's declared range: pytest collected "
    f"no test under python {PRIMARY_PYTHON}, and this project declares a range outside "
    f"{SUPPORTED_RANGE}"
)


def interpreter_range_reason(tree: Path) -> str | None:
    """The stated reason for a tree the reproduction interpreter cannot collect.

    Answers only the *second* of the two conditions above -- whether the
    interpreter under which nothing collected is one this project never
    declared. The caller owns the first, because only the caller knows whether
    a test was collected.
    """
    try:
        _version, declaration = project_python(tree)
    except OSError:
        return None
    if not declaration.startswith(_OUT_OF_RANGE_DECLARATION):
        return None
    return INTERPRETER_RANGE_REASON


def from_reason(reason: str) -> Unsupported | None:
    """The fixed refusal behind a backend or bootstrap reason, if it is one.

    The reason strings are the product's own (`select_backend`,
    `container_images._bootstrap_failure`); anything else is a real DEFER with
    its own sentence and is left alone -- including a bootstrap failure whose
    cause is the project rather than the toolchain, which `failure-modes.md`
    already answers under *environment bootstrap failed*.
    """
    if type(reason) is not str or not reason:
        return None
    lowered = reason.lower()
    if "docker not found" in lowered or "docker is not installed" in lowered:
        return NO_DOCKER
    if INTERPRETER_RANGE_REASON.lower() in lowered:
        return OUTSIDE_INTERPRETER_RANGE
    if "environment bootstrap failed" not in lowered:
        return None
    step = failed_build_step(reason)
    if step is not None:
        # decided on the failing step alone; the echoed context cannot vote
        return NO_PYTEST if "pytest" in step.lower() else None
    return NO_PYTEST if "pytest" in lowered else None


def declares_pytest(tree: Path) -> bool:
    """Does this tree carry a pytest suite of its own?

    **Not** a support condition — a repository with no tests is reviewed like
    any other, because the reproduction is generated and pytest is installed
    into the image. Exposed because the reports say how often it is true.
    """
    return _declares_pytest(tree)


# --- what a failed provider call says (D-179) ------------------------------
# Every proposal call failing is one deferral with several causes, and only one
# of them is the product's problem. A 429 or a 529 means the operator's own API
# account is momentarily out of headroom: nothing was spent, nothing is wrong
# with the change, and re-running works. The general sentence said none of that.
PROVIDER_SAMPLES_FAILED = "all provider samples failed or were malformed"
PROVIDER_RATE_LIMITED = (
    "the model API refused every proposal for rate or capacity (HTTP 429/529); "
    "nothing was spent and nothing was reviewed -- re-run this job, or lower "
    "`samples` if it happens on every run"
)
PROVIDER_UNREACHABLE = (
    "the model API could not be reached from this runner (network or DNS); nothing "
    "was spent and nothing was reviewed -- check the runner's egress, then re-run "
    "this job"
)
_RATE_LIMIT_MARKERS = (
    "429",
    "529",
    "rate_limit",
    "rate limit",
    "overloaded",
    "too many requests",
)
_UNREACHABLE_MARKERS = (
    "apiconnectionerror",
    "connection error",
    "connectionerror",
    "connection refused",
    "connection reset",
    "network is unreachable",
    "name or service not known",
    "nodename nor servname",
    "temporary failure in name resolution",
    "failed to establish a new connection",
    "read timed out",
    "connect timeout",
    "connection timed out",
)


def _all_match(errors: Sequence[str], markers: Sequence[str]) -> bool:
    lowered = [str(error).lower() for error in errors]
    return bool(lowered) and all(
        any(marker in error for marker in markers) for error in lowered
    )


def provider_defer_reason(
    transport_errors: Sequence[str], sample_errors: Sequence[str]
) -> str:
    """The deferral sentence for a proposal stage where nothing came back.

    Two causes are the operator's environment rather than the change or the
    product, and each gets its own sentence and its own next step: the API
    refusing for rate or capacity, and the runner not reaching it at all.
    Everything else keeps the general sentence, because guessing a cause is
    worse than naming none.

    **Only transport errors are read** (independent review of 2026-09-09,
    finding 3). A malformed-answer failure embeds the model's own text, where
    `429` is an ordinary string in a review of retry code, and its reservation
    is *settled* rather than cancelled -- so classifying over it could assert
    both a wrong cause and `nothing was spent` when money was. Both sentences
    below are reachable only when **every** failure was a transport error,
    which is exactly the case in which nothing was charged.
    """
    if len(transport_errors) != len(sample_errors):
        return PROVIDER_SAMPLES_FAILED
    if _all_match(transport_errors, _RATE_LIMIT_MARKERS):
        return PROVIDER_RATE_LIMITED
    if _all_match(transport_errors, _UNREACHABLE_MARKERS):
        return PROVIDER_UNREACHABLE
    return PROVIDER_SAMPLES_FAILED
