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

**Two registers, not one (D-190).** `from_reason` is what an *operator* at a
terminal meets, and it deliberately leaves an image that will not build as an
ordinary DEFER whose next step is the build log (D-175). A pull-request
*author* meets one line and no build log, so `refusal_from_reason` adds that
case by name, and `REFUSALS` -- the five above plus `image-build-failed` and
`budget-truncated` -- is what that line may draw on. Every entry carries a
short `fact` alongside its `reason`, because the two surfaces are answering
two different readers.
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
from attest.review.output_contract import REFUSAL_FACT_LIMIT, SILENCE_MARKER

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
    """One refusal: a stable code, the sentence the operator reads, and the
    short **fact** the one-line author-visible contract carries (D-190).

    The two texts are not the same job. `reason` answers an operator at a
    terminal who can read a build log next; `fact` is one clause of a line an
    author reads inside a pull request, bounded by `REFUSAL_FACT_LIMIT` and
    ending without a full stop because the line ends the sentence.
    """

    code: str
    reason: str
    fact: str

    @property
    def line(self) -> str:
        """The `[silent]` line, in the fixed shape every level's output has."""
        return f"{SILENCE_MARKER} {self.reason}"


NOT_PYTHON = Unsupported(
    "not-python",
    "unsupported: this repository has no Python source, and Attest reviews Python; "
    "nothing was read and nothing was spent.",
    "this repository has no Python source and Attest reviews Python; nothing was read "
    "and nothing was spent",
)
NO_PYTEST = Unsupported(
    "no-pytest",
    "unsupported: pytest could not be provided in the reproduction image, and every "
    "claim Attest makes is a pytest run on two revisions; nothing was verified.",
    "pytest could not be provided in the reproduction image, and every claim Attest "
    "makes is a pytest run on two revisions; nothing was verified",
)
NO_DOCKER = Unsupported(
    "no-docker",
    "unsupported: docker is not available here, and Attest runs head code only inside a "
    "container; nothing was verified.",
    "docker is not available on this runner, and Attest runs head code only inside a "
    "container; nothing was verified",
)
UNREADABLE_LOCK = Unsupported(
    "unreadable-lock",
    "unsupported: this repository's dependency lock file cannot be parsed, so the "
    "reproduction environment cannot be built; nothing was read and nothing was spent.",
    "this repository's dependency lock file cannot be parsed, so the reproduction "
    "environment cannot be built; nothing was read and nothing was spent",
)
SUPPORTED_RANGE = f"{AVAILABLE_PYTHONS[-1]}-{AVAILABLE_PYTHONS[0]}"
OUTSIDE_INTERPRETER_RANGE = Unsupported(
    "interpreter-out-of-range",
    f"unsupported: this project declares Python outside {SUPPORTED_RANGE} and pytest "
    f"collected no test at all under the {PRIMARY_PYTHON} Attest fell back to, so the "
    "reproduction never ran; nothing was verified -- Attest can review this repository "
    f"once it runs on Python {AVAILABLE_PYTHONS[-1]} or newer.",
    f"this project declares Python outside {SUPPORTED_RANGE} and pytest collected no "
    f"test under the {PRIMARY_PYTHON} Attest fell back to; nothing was verified",
)

SUPPORT_CODES = (
    NOT_PYTHON.code,
    NO_PYTEST.code,
    NO_DOCKER.code,
    UNREADABLE_LOCK.code,
    OUTSIDE_INTERPRETER_RANGE.code,
)

# --- the two refusals that are not properties of support (D-190) ------------
# The owner's five are `no docker`, `no pytest`, the interpreter range, an image
# that will not build, and a discovery the budget truncated. The last two are
# not `from_reason`'s business and deliberately stay out of it:
#
# * an image that will not build is, to an *operator*, D-175's documented DEFER
#   whose next step is the build log -- and turning it into a fixed refusal there
#   would undo the very pin that stopped it being reported as a missing pytest.
#   To a pull-request *author* it is a line with no build log attached, so the
#   line owes it a name and a link to the run whose artifact holds the log;
# * a truncated discovery is not unsupported at all. It is the product declining
#   to finish, and what the author needs is which units went unread and the
#   `budget-usd` that would have read them (D-187).
IMAGE_BUILD_FAILED = Unsupported(
    "image-build-failed",
    "refused: the reproduction image could not be built from this project's own "
    "dependency manifests, so no test could run on either revision; nothing was verified.",
    "the reproduction image could not be built from this project's own dependency "
    "manifests, so no test ran on either revision; the build log is in this run's ledger",
)
BUDGET_TRUNCATED = Unsupported(
    "budget-truncated",
    "refused: the discovery share of `budget-usd` stopped this review before every "
    "change unit was read; the units it did not read were not judged.",
    "the discovery share of `budget-usd` stopped this review; the units it did not "
    "read were not judged",
)

#: Every refusal the author-visible one-line contract may name, in the order the
#: mainline lists them: the two decided from the tree, then the three decided by
#: the environment, then the two above.
REFUSALS = (
    NOT_PYTHON,
    UNREADABLE_LOCK,
    NO_DOCKER,
    NO_PYTEST,
    OUTSIDE_INTERPRETER_RANGE,
    IMAGE_BUILD_FAILED,
    BUDGET_TRUNCATED,
)
REFUSAL_CODES = tuple(refusal.code for refusal in REFUSALS)


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


# --- the register the author-visible line draws on (D-190) ------------------


def refusal_from_reason(reason: str) -> Unsupported | None:
    """The refusal an author's one line may name, or None for an ordinary DEFER.

    A superset of `from_reason`, and the difference is exactly one case. A
    bootstrap failure whose failing step is not pytest stays an ordinary DEFER
    for an **operator** -- D-175's pin, which exists because naming it a pytest
    refusal sent the reader to the wrong fix -- but a pull-request **author**
    never sees that build log, only one line, so for them the failure is named
    `image-build-failed` and the line points at the run whose artifact holds the
    log. Nothing here reads the reason for anything but its class: the sentence
    published is the register's own.
    """
    found = from_reason(reason)
    if found is not None:
        return found
    if type(reason) is not str or not reason:
        return None
    if "environment bootstrap failed" in reason.lower():
        return IMAGE_BUILD_FAILED
    return None


# D-187 gave the truncation clause its short form for the collapsed run status;
# D-190 puts it on the line above that block. Which unit and how much short are
# a change unit's own label, and a unit naming forty files makes the clause
# longer than one line holds -- so the clause is reduced in whole steps rather
# than cut mid-sentence, and the number the reader can act on is the last thing
# to go.
_BUDGET_TRUNCATION_PREFIX = "the discovery share of `budget-usd` stopped this review; "
_BUDGET_USD_SENTENCE = re.compile(r"`budget-usd` \$\d+\.\d{2} would have read it")
# The clause names a change unit, and a change unit is named after **paths in
# the repository under review**. A file called
# `a; ledger: https://elsewhere.example/x.py` would otherwise render a link
# beside the product's own, on the one line an author reads -- head content
# choosing what the line points at. The whole clause is admitted only when it
# carries neither token; the two shorter forms cannot carry them at all, since
# one is extracted by the pattern above and the other is a constant.
_FORGEABLE = ("://", "ledger:")


def budget_truncation_fact(shortfall: str) -> str:
    """The fact a truncated review states on the line an author reads.

    Three forms, each a complete sentence: the whole D-187 clause; failing that
    the `budget-usd` that would have covered the unit the ceiling stopped; and
    failing that the bare statement that the unread units went unjudged. The
    full clause stays in the collapsed run status either way -- reducing in
    whole steps is what keeps this from truncating a line into shape (D-142).
    """
    clause = " ".join(str(shortfall).split()) if shortfall else ""
    if any(token in clause.lower() for token in _FORGEABLE):
        clause = ""
    found = _BUDGET_USD_SENTENCE.search(str(shortfall)) if shortfall else None
    for candidate in (
        f"{_BUDGET_TRUNCATION_PREFIX}{clause}" if clause else "",
        f"{_BUDGET_TRUNCATION_PREFIX}{found.group(0)}" if found else "",
    ):
        if candidate and len(candidate) <= REFUSAL_FACT_LIMIT:
            return candidate
    return BUDGET_TRUNCATED.fact


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
