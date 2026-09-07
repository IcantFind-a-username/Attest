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
    OUTSIDE_INTERPRETER_RANGE,
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
    for refusal in (
        NOT_PYTHON,
        NO_PYTEST,
        NO_DOCKER,
        UNREADABLE_LOCK,
        OUTSIDE_INTERPRETER_RANGE,
    ):
        assert refusal.line.startswith(SILENCE_MARKER)
        assert "\n" not in refusal.line
        assert refusal.line.startswith(f"{SILENCE_MARKER} unsupported: ")
        assert "nothing was " in refusal.line
        assert refusal.code in support.SUPPORT_CODES


# The tenacity clone of the 2026-09-09 release-readiness acceptance: an outside
# repository whose image build fails at `pip install <project>`. Docker echoes
# the whole Dockerfile around the failing step, so the log tail quotes the
# *successful* `RUN pip install pytest` line -- and a substring search for
# "pytest" then reports the wrong cause and sends the operator to the wrong fix.
_TENACITY_BOOTSTRAP_TAIL = (
    "environment bootstrap failed (python 3.13, roots ['.']): Dockerfile:5\n"
    "--------------------\n"
    "   3 |     RUN pip install pytest\n"
    "   4 |     COPY tree /attest/build\n"
    "   5 | >>> RUN pip install /attest/build\n"
    "   6 |     RUN rm -rf /attest/build\n"
    "--------------------\n"
    'ERROR: failed to solve: process "/bin/sh -c pip install /attest/build" '
    "did not complete successfully: exit code: 1\n"
)


def test_a_project_that_will_not_install_is_not_reported_as_a_missing_pytest() -> None:
    """The failing step is the project, not pytest. `failure-modes.md` already
    carries the right row for it -- `environment bootstrap failed …`, "the
    project's manifests do not install on a slim image" -- so the refusal must
    not overwrite it with a sentence about pytest."""
    assert from_reason(_TENACITY_BOOTSTRAP_TAIL) is None


def test_pytest_itself_failing_to_install_is_still_told_so() -> None:
    """The other side of the same line: when the step that failed *is* the
    pytest install, the fixed pytest sentence is still what the operator gets."""
    reason = (
        "environment bootstrap failed (python 3.11, roots ['.']): Dockerfile:3\n"
        "   3 | >>> RUN pip install pytest\n"
        'ERROR: failed to solve: process "/bin/sh -c pip install pytest" '
        "did not complete successfully: exit code: 1\n"
    )
    assert from_reason(reason) == NO_PYTEST


# --- what a rate-limited provider says (D-179) -----------------------------
# Failure drill 5 of the 2026-09-09 acceptance: every proposal call answers
# HTTP 429. Before this, the whole review deferred with `all provider samples
# failed or were malformed` -- a sentence that reads like a defect in the
# product and offers nothing to do. Nothing was spent, and re-running works.


def test_a_rate_limited_provider_says_so_and_what_to_do() -> None:
    from attest.review.support import provider_defer_reason

    errors = [
        "sample 0: RuntimeError: Error code: 429 - {'type': 'error', 'error': "
        "{'type': 'rate_limit_error', 'message': 'Number of request tokens has "
        "exceeded your per-minute rate limit'}}",
        "sample 1: RuntimeError: Error code: 429 - {'type': 'rate_limit_error'}",
    ]

    reason = provider_defer_reason(errors, errors)

    assert "429" in reason
    assert "rate" in reason.lower()
    assert "nothing was spent" in reason
    assert "re-run" in reason


def test_an_overloaded_provider_is_the_same_category() -> None:
    from attest.review.support import provider_defer_reason

    errors = ["sample 0: Error code: 529 - overloaded_error"]
    reason = provider_defer_reason(errors, errors)
    assert "re-run" in reason


def test_an_ordinary_provider_failure_keeps_the_general_sentence() -> None:
    from attest.review.support import PROVIDER_SAMPLES_FAILED, provider_defer_reason

    assert provider_defer_reason([], []) == PROVIDER_SAMPLES_FAILED
    other = ["sample 0: ValueError: bad schema"]
    assert provider_defer_reason(other, other) == PROVIDER_SAMPLES_FAILED


def test_a_zero_budget_says_which_input_to_change() -> None:
    """Failure drill 4 of the 2026-09-09 acceptance. `budget-usd: "0.00"` in a
    workflow produced `budget must be a finite positive number` and exit 2 --
    true, and it names neither the input nor a value that would work."""
    from attest.review.config import ReviewConfig

    with pytest.raises(ValueError) as raised:
        ReviewConfig(budget_usd=0.0)

    message = str(raised.value)
    assert "budget-usd" in message
    assert "--budget" in message


def test_a_runner_with_no_network_says_so_and_what_to_do() -> None:
    """Failure drill 1 of the same acceptance: the runner cannot reach the model
    API at all. It is not a rate limit and it is not a malformed sample."""
    from attest.review.support import PROVIDER_UNREACHABLE, provider_defer_reason

    errors = [
        "sample 0: APIConnectionError: Connection error.",
        "sample 1: ConnectionError: [Errno 8] nodename nor servname provided",
    ]

    assert provider_defer_reason(errors, errors) == PROVIDER_UNREACHABLE
    assert "network" in PROVIDER_UNREACHABLE
    assert "nothing was spent" in PROVIDER_UNREACHABLE


def test_the_five_failure_modes_each_have_their_own_copy_and_a_next_step() -> None:
    """One assertion over all five drills of the 2026-09-09 acceptance.

    The property is not "a message exists". It is that **no two of the five say
    the same thing**, that none of them is the generic sentence, and that each
    tells the reader what to do — because a failure whose copy is shared with
    another failure sends half its readers to the wrong fix.
    """
    from pathlib import Path

    from attest.review.config import ReviewConfig
    from attest.review.output_contract import silence_line
    from attest.review.support import (
        NO_DOCKER,
        PROVIDER_RATE_LIMITED,
        PROVIDER_SAMPLES_FAILED,
        PROVIDER_UNREACHABLE,
    )

    entrypoint = Path(__file__).resolve().parents[1] / "scripts" / "action-entrypoint.sh"
    missing_key = entrypoint.read_text(encoding="utf-8")
    try:
        ReviewConfig(budget_usd=0.0)
    except ValueError as error:
        zero_budget = str(error)
    else:  # pragma: no cover - the validator must reject it
        raise AssertionError("a zero budget must be refused")

    messages = {
        "no network": PROVIDER_UNREACHABLE,
        "rate limited": PROVIDER_RATE_LIMITED,
        "no docker": NO_DOCKER.reason,
        "zero budget": zero_budget,
        "executor unavailable": silence_line(
            units_read=1,
            units_planned=1,
            spend_usd=0.0,
            elapsed_s=1.0,
            executor_unavailable="process containment unavailable for privileged POSIX user",
            unverified=2,
        ),
    }

    # 1. five distinct sentences, and none of them is the generic one
    assert len(set(messages.values())) == len(messages)
    for name, message in messages.items():
        assert PROVIDER_SAMPLES_FAILED not in message, name
        assert "nothing met an adjudicator's bar" not in message, name

    # 2. each names something the reader can do or check
    actionable = {
        "no network": "egress",
        "rate limited": "re-run",
        "no docker": "container",
        "zero budget": "budget-usd",
        "executor unavailable": "not verified",
    }
    for name, needle in actionable.items():
        assert needle in messages[name], f"{name}: {messages[name]!r}"

    # 3. the missing-credential message is the entrypoint's, and it names the
    #    secret, where to create it, and that nothing has happened yet
    for needle in (
        "ANTHROPIC_API_KEY",
        "settings/secrets/actions/new",
        "Nothing was sent anywhere",
    ):
        assert needle in missing_key

    # 4. the fork skip says it happened before credentials, and claims nothing
    #    about the code
    fork = "fork pull request skipped before credentials or head-code execution"
    assert fork in missing_key
    assert "no problems" not in missing_key


def test_a_malformed_answer_is_never_reported_as_a_rate_limit() -> None:
    """Independent review of 2026-09-09, finding 3. A malformed-answer failure
    embeds up to 500 characters of the model's **own text**, and the reservation
    for it is *settled*, not cancelled. Classifying over that text means a review
    of retry/backoff code — where `429` is a perfectly ordinary string — could be
    told the API rate-limited it and that nothing was spent. Both false.
    Classification reads transport errors only."""
    from attest.review.support import PROVIDER_SAMPLES_FAILED, provider_defer_reason

    malformed = [
        'sample 0: all findings malformed; raw="the retry policy handles 429 by backing off"',
        'sample 1: all findings malformed; raw="429 and 529 are both retried"',
    ]

    assert provider_defer_reason([], malformed) == PROVIDER_SAMPLES_FAILED


def test_a_rate_limit_is_only_claimed_when_every_sample_failed_in_transport() -> None:
    """`nothing was spent` is true of a cancelled reservation and false of a
    settled one, so the sentence is only reachable when every failure is a
    transport error."""
    from attest.review.support import PROVIDER_RATE_LIMITED, provider_defer_reason

    transport = ["sample 0: RuntimeError: Error code: 429", "sample 1: RuntimeError: 429"]

    assert provider_defer_reason(transport, transport) == PROVIDER_RATE_LIMITED


def test_a_mixed_run_keeps_the_general_sentence() -> None:
    from attest.review.support import PROVIDER_SAMPLES_FAILED, provider_defer_reason

    transport = ["sample 0: RuntimeError: Error code: 429"]
    everything = [*transport, 'sample 1: all findings malformed; raw="..."']

    assert provider_defer_reason(transport, everything) == PROVIDER_SAMPLES_FAILED


# --- a project the reproduction interpreter cannot collect (D-186) ----------
# D-185, found by the 2026-09-10 K=5 run and repaired here. D-162 set the
# reproduction range to 3.10-3.13 and gives a project declaring less than that
# the primary, 3.12. A 2019-2022 `pytest` tree installs on 3.12 and then cannot
# collect -- its assertion rewriter compiles AST nodes 3.12 rejects -- so there
# is no bootstrap failure to catch, the run writes no JUnit artifact, and the
# operator reads `missing or malformed JUnit evidence: ValueError: no JUnit
# artifact`: a sentence about a broken host, for a project that is simply
# outside the range.
#
# The container measurement behind this (2026-09-11, docker only, $0.00): on
# the base tree of `pytest-dev__pytest-7324`, in the image the product builds
# for it, one product-written probe ends
#
#   File ".../src/_pytest/assertion/rewrite.py", line 358, in _rewrite_test
#     co = compile(tree, fn_, "exec", dont_inherit=True)
#   TypeError: required field "lineno" missing from alias
#
# with exit code 1 and no artifact. The test below reproduces that *observable*
# without docker: a tree declaring 3.8/3.9 whose collection dies before pytest
# can write its report.
_DIES_DURING_COLLECTION = "import os\n\nos._exit(2)\n\ndef test_repro():\n    assert True\n"


def _tree_declaring_python(path: Path, *, classifiers: tuple[str, ...]) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    listed = ", ".join(f'"Programming Language :: Python :: {each}"' for each in classifiers)
    (path / "pyproject.toml").write_text(
        f'[project]\nname = "old"\nversion = "0"\nclassifiers = [{listed}]\n',
        encoding="utf-8",
    )
    (path / "mod.py").write_text("x = 1\n", encoding="utf-8")
    return path


def _collection_that_never_reports(tmp_path: Path, *, classifiers: tuple[str, ...]) -> str:
    """The deferral reason for a run that collected nothing in such a tree."""
    from attest.review.candidates import StoredCandidate
    from attest.review.executor import ExecutorLimits, ReproSpec, execute_repro
    from attest.review.schema import Finding

    tree = _tree_declaring_python(tmp_path / "tree", classifiers=classifiers)
    stored = StoredCandidate(
        task_id="task-185",
        finding=Finding(
            claim="The boundary check accepts an invalid value.",
            file="mod.py",
            line=1,
            failure_scenario="Passing -1 reaches the unsafe branch.",
            falsification_plan="Call validate(-1) and assert that it is rejected.",
        ),
        wealth=8.0,
        action="drawer",
        alpha=0.1,
    )
    result = execute_repro(
        tmp_path,
        stored,
        ReproSpec(_DIES_DURING_COLLECTION),
        ExecutorLimits(),
        tree=tree,
        run_label="probe-1",
    )
    assert result.exit_code not in (0, 1), result.reason
    return result.reason


def test_a_project_outside_the_interpreter_range_is_told_so_not_shown_a_missing_artifact(
    tmp_path: Path,
) -> None:
    """D-185's path, end to end: the reproduction runs an interpreter this
    project never declared, collects nothing, and must say *that* rather than
    report its own missing evidence as if the host were broken."""
    reason = _collection_that_never_reports(tmp_path, classifiers=("3.8", "3.9"))

    assert from_reason(reason) == OUTSIDE_INTERPRETER_RANGE
    # the cause comes first and the evidence follows it in brackets: a reader
    # that truncates, or matches on the head of the reason, sees the cause --
    # and the ledger still records what was actually seen
    assert reason.startswith("reproduction interpreter outside the project's declared range")
    assert "no JUnit artifact" in reason
    # what the operator reads says nothing about a missing artifact
    assert "JUnit" not in OUTSIDE_INTERPRETER_RANGE.line


def test_a_project_inside_the_range_that_will_not_collect_keeps_its_ordinary_defer(
    tmp_path: Path,
) -> None:
    """The other side of the conjunction, and the reason it is a conjunction: a
    tree the product *can* run is not refused for a collection failure. That is
    a scaffolding problem about one generated test, D-114 asks the generator
    again, and calling it "unsupported" would silence a whole review for it."""
    reason = _collection_that_never_reports(tmp_path, classifiers=("3.11", "3.12"))

    assert from_reason(reason) is None
    assert "JUnit" in reason
