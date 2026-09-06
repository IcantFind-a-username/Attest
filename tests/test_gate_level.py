"""The gate level, in shadow (D-137, `docs/design/gate-level.md`).

The design's RED, its false-positive control, and the two exclusions it names:

  ``::test_a_crash_on_an_input_a_pre_existing_caller_produces_is_a_gate_finding``
      an added ``widen`` raises ``IndexError``; an existing, not-added line of
      ``cli.py`` calls it; three runs agree; a pre-existing test of the same
      caller passes -- the observation would publish;
  ``::test_a_crash_reachable_only_from_a_caller_the_diff_added_is_not_a_gate_finding``
      the same tree, except the only call site is a line the diff itself added:
      the witness is ``direct`` and nothing publishes;
  ``::test_an_expected_value_assertion_never_publishes`` (§2.1);
  ``::test_a_raise_on_an_added_line_stays_a_deliberate_rejection`` (§2.3, D-102).

And the property the whole level rests on while it is in shadow:
``::test_a_would_publish_observation_reaches_no_author_visible_surface``.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from attest.review.diffs import parse_diff
from attest.review.gate_level import (
    DIRECT,
    GATE_POLICY_VERSION,
    THROUGH_CALLER,
    ControlRun,
    adjudicate,
    classify_origin,
    witness,
)
from attest.review.intent import RaiseOrigin

# ----------------------------------------------------------------- the fixture

CLI_BEFORE = (
    "import argparse\n"
    "\n"
    "\n"
    "def parse(argv: list[str]) -> str:\n"
    "    parser = argparse.ArgumentParser()\n"
    "    parser.add_argument('name')\n"
    "    return str(parser.parse_args(argv).name)\n"
    "\n"
    "\n"
    "def main(argv: list[str]) -> str:\n"
    "    argument = parse(argv)\n"
    "    return argument\n"
)
# the call to `widen` replaces the bare return, on a line the diff DID add;
# the call site itself is therefore added -- the false-positive control
CLI_AFTER_ADDED_CALL = CLI_BEFORE.replace(
    "    return argument\n", "    return widen(argument)\n"
).replace("import argparse\n", "import argparse\n\nfrom lib import widen\n")
# ... whereas here the caller already existed: `main` called `widen` before the
# change, and the change only adds `widen`'s body in lib.py
CLI_WITH_EXISTING_CALL = (
    "import argparse\n"
    "\n"
    "from lib import widen\n"
    "\n"
    "\n"
    "def parse(argv: list[str]) -> str:\n"
    "    parser = argparse.ArgumentParser()\n"
    "    parser.add_argument('name')\n"
    "    return str(parser.parse_args(argv).name)\n"
    "\n"
    "\n"
    "def main(argv: list[str]) -> str:\n"
    "    argument = parse(argv)\n"
    "    return widen(argument)\n"
)
LIB_NEW = "def widen(name: str) -> str:\n    return name.strip().casefold()[0]\n"
LIB_UNANNOTATED = "def widen(name):\n    return name.strip().casefold()[0]\n"
LIB_RAISES = (
    "def widen(name: str) -> str:\n"
    "    if not name:\n"
    "        raise ValueError('name must not be empty')\n"
    "    return name.strip().casefold()\n"
)
TESTS_EXISTING = (
    "from cli import main\n\n\ndef test_main_returns_the_argument():\n    assert main(['x'])\n"
)
# §3's control, already satisfied, so each case below turns on one thing only
PASSING_CONTROL = ControlRun("tests_cli.py", True, "passed")


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def _tree(
    root: Path, *, base_cli: str, head_cli: str, lib: str
) -> tuple[Path, str, dict[str, set[int]]]:
    """A head revision plus the added-line map of the change that made it, read
    from the real diff. That map is what §2.2 and §1(a) are both written
    against, so nothing here may approximate it."""
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "fixture@example.invalid")
    _git(root, "config", "user.name", "Fixture")
    (root / "cli.py").write_text(base_cli, encoding="utf-8")
    (root / "tests_cli.py").write_text(TESTS_EXISTING, encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "base")
    base = _git(root, "rev-parse", "HEAD")
    (root / "cli.py").write_text(head_cli, encoding="utf-8")
    (root / "lib.py").write_text(lib, encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "head")
    head = _git(root, "rev-parse", "HEAD")
    diff = parse_diff(_git(root, "diff", "-U0", base, head))
    return root, head, {path: set(lines) for path, lines in diff.added_lines.items()}


def _observe(
    repo: Path,
    head: str,
    added: dict[str, set[int]],
    *,
    lib: str,
    test_source: str,
    origins: tuple[RaiseOrigin, ...],
    runs: tuple[tuple[int, str], ...],
    control: ControlRun | None = PASSING_CONTROL,
):
    origin, reason = classify_origin(lib, added["lib.py"], origins)
    reach = witness(
        repo,
        head,
        path="lib.py",
        origin_line=origins[0].line if origins else 2,
        added=added,
        head_source=lib,
        test_source=test_source,
    )
    return adjudicate(
        path="lib.py",
        reachability=reach,
        origin=origin,
        origin_reason=reason,
        runs=runs,
        repeats=3,
        control=control,
    )


CRASH = RaiseOrigin(
    line=2,
    function="widen",
    exception_type="IndexError",
    message="string index out of range",
    values=(),
    escaped=True,
)
RUNS = ((2, "IndexError"),) * 3
THROUGH_CALLER_TEST = "from cli import main\n\n\ndef test_repro():\n    main([''])\n"
DIRECT_TEST = "from lib import widen\n\n\ndef test_repro():\n    widen('')\n"


# ------------------------------------------------------------------- the RED


def test_a_crash_on_an_input_a_pre_existing_caller_produces_is_a_gate_finding(tmp_path: Path):
    repo, head, added = _tree(
        tmp_path / "r",
        base_cli=CLI_WITH_EXISTING_CALL,
        head_cli=CLI_WITH_EXISTING_CALL,
        lib=LIB_NEW,
    )
    observation = _observe(
        repo,
        head,
        added,
        lib=LIB_NEW,
        test_source=THROUGH_CALLER_TEST,
        origins=(CRASH,),
        runs=RUNS,
    )
    assert observation.would_publish
    assert observation.policy_version == GATE_POLICY_VERSION
    assert observation.reachability.kind == THROUGH_CALLER
    assert observation.reachability.call_site is not None
    assert observation.reachability.call_site.path == "cli.py"
    # the three coordinates, and nothing beyond them
    assert observation.origin is not None
    assert observation.origin.exception_type == "IndexError"
    assert "no base revision to compare against" in observation.reason


def test_a_crash_reachable_only_from_a_caller_the_diff_added_is_not_a_gate_finding(tmp_path: Path):
    repo, head, added = _tree(
        tmp_path / "r", base_cli=CLI_BEFORE, head_cli=CLI_AFTER_ADDED_CALL, lib=LIB_NEW
    )
    observation = _observe(
        repo, head, added, lib=LIB_NEW, test_source=DIRECT_TEST, origins=(CRASH,), runs=RUNS
    )
    assert not observation.would_publish
    assert observation.reachability.kind == DIRECT
    assert observation.reachability.call_site is None
    assert "no call site" in observation.reason


def test_an_expected_value_assertion_never_publishes(tmp_path: Path):
    """§2.1: a reproduction that asserts ``f(x) == 7`` invents a specification.
    Its AssertionError is raised in the *test*, never in a frame of the anchored
    file, so there is no origin on an added line and nothing to publish."""
    repo, head, added = _tree(
        tmp_path / "r",
        base_cli=CLI_WITH_EXISTING_CALL,
        head_cli=CLI_WITH_EXISTING_CALL,
        lib=LIB_NEW,
    )
    observation = _observe(
        repo,
        head,
        added,
        lib=LIB_NEW,
        test_source="from cli import main\n\n\ndef test_repro():\n    assert main(['ab']) == 'z'\n",
        origins=(),
        runs=(),
    )
    assert not observation.would_publish
    assert observation.origin is None
    assert "no exception was raised" in observation.reason


def test_a_raise_on_an_added_line_stays_a_deliberate_rejection(tmp_path: Path):
    """§2.3 / D-102, unchanged: head refusing on purpose is not a gate finding."""
    repo, head, added = _tree(
        tmp_path / "r",
        base_cli=CLI_WITH_EXISTING_CALL,
        head_cli=CLI_WITH_EXISTING_CALL,
        lib=LIB_RAISES,
    )
    origin = RaiseOrigin(
        line=3,
        function="widen",
        exception_type="ValueError",
        message="name must not be empty",
        values=("",),
        escaped=True,
    )
    observation = _observe(
        repo,
        head,
        added,
        lib=LIB_RAISES,
        test_source=THROUGH_CALLER_TEST,
        origins=(origin,),
        runs=((3, "ValueError"),) * 3,
    )
    assert not observation.would_publish
    assert observation.origin is None
    assert "deliberate raise" in observation.reason


def test_an_unannotated_parameter_abstains(tmp_path: Path):
    """§1(b) is necessary and its recall cost is the decision, not an oversight."""
    repo, head, added = _tree(
        tmp_path / "r",
        base_cli=CLI_WITH_EXISTING_CALL,
        head_cli=CLI_WITH_EXISTING_CALL,
        lib=LIB_UNANNOTATED,
    )
    observation = _observe(
        repo,
        head,
        added,
        lib=LIB_UNANNOTATED,
        test_source=THROUGH_CALLER_TEST,
        origins=(CRASH,),
        runs=RUNS,
    )
    assert not observation.would_publish
    assert "unannotated parameter" in observation.reason


def test_disagreeing_runs_and_an_unproven_environment_each_stop_it(tmp_path: Path):
    """§3: the agreement rule is exact, and no passing control means no claim."""
    repo, head, added = _tree(
        tmp_path / "r",
        base_cli=CLI_WITH_EXISTING_CALL,
        head_cli=CLI_WITH_EXISTING_CALL,
        lib=LIB_NEW,
    )
    disagreeing = _observe(
        repo,
        head,
        added,
        lib=LIB_NEW,
        test_source=THROUGH_CALLER_TEST,
        origins=(CRASH,),
        runs=((2, "IndexError"), (2, "IndexError"), (2, "TypeError")),
    )
    assert not disagreeing.would_publish
    assert "disagree" in disagreeing.reason
    uncontrolled = _observe(
        repo,
        head,
        added,
        lib=LIB_NEW,
        test_source=THROUGH_CALLER_TEST,
        origins=(CRASH,),
        runs=RUNS,
        control=None,
    )
    assert not uncontrolled.would_publish
    assert "environment unproven" in uncontrolled.reason
    failed = _observe(
        repo,
        head,
        added,
        lib=LIB_NEW,
        test_source=THROUGH_CALLER_TEST,
        origins=(CRASH,),
        runs=RUNS,
        control=ControlRun("tests_cli.py", False, "pytest reported 1 failure(s)"),
    )
    assert not failed.would_publish
    assert "environment unproven" in failed.reason


def test_a_would_publish_observation_reaches_no_author_visible_surface(tmp_path: Path):
    """The property the level rests on while it is in shadow: the record says of
    itself that it is not author-visible, and it is not a `CertifiedFinding`."""
    repo, head, added = _tree(
        tmp_path / "r",
        base_cli=CLI_WITH_EXISTING_CALL,
        head_cli=CLI_WITH_EXISTING_CALL,
        lib=LIB_NEW,
    )
    observation = _observe(
        repo,
        head,
        added,
        lib=LIB_NEW,
        test_source=THROUGH_CALLER_TEST,
        origins=(CRASH,),
        runs=RUNS,
    )
    assert observation.would_publish
    row = observation.to_ledger_row("task", "finding")
    assert row["kind"] == "gate_shadow"
    assert row["author_visible"] is False
    from attest.certification.types import CertifiedFinding

    assert not isinstance(observation, CertifiedFinding)
    assert not hasattr(observation, "accepted_receipt")


def test_no_author_visible_module_can_reach_the_gate_level():
    """The cheapest guarantee that a shadow level stays shadow is that the code
    which writes to the author cannot import it. If this test ever has to be
    edited, the level is no longer in shadow and `G-NEWCODE-001` applies."""
    src = Path(__file__).parents[1] / "src" / "attest"
    author_visible = [
        src / "github" / "presentation.py",
        src / "github" / "client.py",
        src / "review" / "report.py",
        src / "review" / "structural.py",
        src / "review" / "ci.py",
        src / "certification" / "selection.py",
        src / "certification" / "types.py",
    ]
    offenders = [
        path.name for path in author_visible if "gate_level" in path.read_text(encoding="utf-8")
    ]
    assert offenders == []


def test_the_status_line_does_not_read_gate_rows():
    """A shadow row must not move a number the author is shown. `status_from_rows`
    dispatches on `kind`, and `gate_shadow` is not one of the kinds it reads."""
    from attest.review import status

    source = (Path(status.__file__)).read_text(encoding="utf-8")
    assert "gate_shadow" not in source


def test_a_caller_that_is_itself_a_test_is_graded_apart(tmp_path: Path) -> None:
    """D-166: the through-caller rule exists so that *something the change did
    not add* depends on the new code. A call site inside the change's own test
    satisfies the letter of that and not one word of its point, so it is its own
    grade -- reported separately, and never publishing.

    Owner item 2 of the 2026-09-06c handoff: 3 of the gate's 9 cumulative
    `through_caller` observations enter through a test rather than production
    code."""
    from attest.review.gate_level import THROUGH_CALLER, THROUGH_TEST_CALLER

    # the only call site of `widen` outside the added lines is in a test file
    only_a_test = (
        "from lib import widen\n\n\ndef test_widen_lowercases():\n    assert widen('A')\n"
    )
    repo = tmp_path / "t"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "fixture@example.invalid")
    _git(repo, "config", "user.name", "Fixture")
    (repo / "test_lib.py").write_text(only_a_test, encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "base")
    base = _git(repo, "rev-parse", "HEAD")
    (repo / "lib.py").write_text(LIB_NEW, encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "head")
    head = _git(repo, "rev-parse", "HEAD")
    diff = parse_diff(_git(repo, "diff", "-U0", base, head))
    added = {path: set(lines) for path, lines in diff.added_lines.items()}

    reach = witness(
        repo,
        head,
        path="lib.py",
        origin_line=2,
        added=added,
        head_source=LIB_NEW,
        test_source="from test_lib import test_widen_lowercases\n",
    )

    assert reach.call_site is not None
    assert reach.call_site.path == "test_lib.py"
    assert reach.kind == THROUGH_TEST_CALLER
    assert reach.kind != THROUGH_CALLER
    assert "which is a test" in reach.reason

    # and the grade never publishes: adjudication requires `through_caller` exactly
    observation = adjudicate(
        path="lib.py",
        reachability=reach,
        origin=CRASH,
        origin_reason="",
        runs=RUNS,
        repeats=3,
        control=PASSING_CONTROL,
    )
    assert observation.would_publish is False


# --- §1(a): a witness is a call that *resolves* to the anchored symbol --------

OTHER_WITH_ITS_OWN_WIDEN = (
    "def widen(name):\n"
    "    return name\n"
    "\n"
    "\n"
    "def use() -> str:\n"
    "    return widen('x')\n"
)


def test_a_call_of_another_modules_function_of_the_same_name_is_not_a_witness(
    tmp_path: Path,
) -> None:
    """RED. `other.py` defines its own `widen` and calls it; nothing in the tree
    imports `lib.widen`. A `grep`-shaped search reads that call as a caller of
    the new code and grades the candidate `through_caller` -- the one grade that
    is allowed to publish -- on a call that never reaches it."""
    repo, head, added = _tree(
        tmp_path / "repo",
        base_cli=CLI_BEFORE,
        head_cli=CLI_BEFORE,  # nothing calls `widen`
        lib=LIB_NEW,
    )
    (repo / "other.py").write_text(OTHER_WITH_ITS_OWN_WIDEN, encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "other")
    head = _git(repo, "rev-parse", "HEAD")

    reach = witness(
        repo,
        head,
        path="lib.py",
        origin_line=2,
        added=added,
        head_source=LIB_NEW,
        test_source=TESTS_EXISTING,
    )

    assert reach.call_site is None
    assert reach.kind != THROUGH_CALLER
    assert reach.admissible is False


def test_a_real_imported_call_site_is_still_a_witness(tmp_path: Path) -> None:
    """The retained positive: `from lib import widen` and a call of it in an
    unchanged line of `main` is exactly what the grade is for."""
    repo, head, added = _tree(
        tmp_path / "repo",
        base_cli=CLI_WITH_EXISTING_CALL,
        head_cli=CLI_WITH_EXISTING_CALL,
        lib=LIB_NEW,
    )

    reach = witness(
        repo,
        head,
        path="lib.py",
        origin_line=2,
        added=added,
        head_source=LIB_NEW,
        test_source=TESTS_EXISTING,
    )

    assert reach.call_site is not None
    assert reach.call_site.path == "cli.py"
    assert reach.kind == THROUGH_CALLER
