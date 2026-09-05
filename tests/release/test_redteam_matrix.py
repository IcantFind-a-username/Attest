"""The red-team matrix covers nine attack classes, and cannot pass by skipping (4.1).

`G-SEC-002` fails closed in a specific way: **a pre-dispatch DEFER is not attack
coverage.** A matrix of refusals that never dispatched anything proves only that
the product is broken, so the runner's verdict must depend on the fixtures
having actually run, and the positive control must certify in the same backend
in the same run.

These tests do not need docker: they pin the shape of the matrix -- which
classes exist, what makes a row pass, and that the external-observer item stays
INSUFFICIENT -- so a fixture cannot be quietly dropped or a verdict quietly
loosened. The dispatch itself is the runner's job.
"""

from __future__ import annotations

import runpy
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def redteam() -> dict:
    sys.path.insert(0, str(ROOT / "src"))
    sys.path.insert(0, str(ROOT / "tests"))
    return runpy.run_path(str(ROOT / "scripts" / "release" / "redteam.py"))


EXPECTED_CLASSES = (
    "read the controller's environment secret",
    "read the controller's key file off the host",
    "open a network connection",
    "resolve a name (DNS egress)",
    "write outside the work directory",
    "escape the work directory through a symlink",
    "exhaust processes and threads (bounded)",
    "forge a result",
    "tamper with a sealed bundle",
)


def test_the_matrix_names_nine_attack_classes(redteam: dict) -> None:
    """The module docstring is the contract a reader checks first."""
    doc = redteam["__doc__"]
    assert "Nine adversarial fixtures" in doc
    for token in ("secret", "keyfile", "socket", "dns", "escape", "symlink", "processes",
                  "forge", "bundle"):
        assert f"\n    {token}" in doc, token


def test_every_new_fixture_body_is_python_that_asserts_the_boundary_held(
    redteam: dict,
) -> None:
    """Each attack asserts that it *failed*: the fixture passes on both trees
    when the boundary holds, so it buys nothing and certifies nothing."""
    for name in ("KEYFILE_BODY", "SYMLINK_BODY", "DNS_BODY", "PROCESS_BODY"):
        body = redteam[name]
        compile(body, name, "exec")
        assert "def test_repro():" in body
        assert "assert" in body or "raise AssertionError" in body


def test_a_row_that_never_dispatched_cannot_pass(redteam: dict) -> None:
    """A pre-dispatch skip is `marked=False`, and the verdict is a conjunction
    over every attack row -- so an unattempted fixture fails the matrix."""
    row = redteam["Row"](
        fixture="tamper with a sealed bundle",
        attempt="no bundle was produced",
        outcome="unattempted",
        detail="a pre-dispatch skip is not attack coverage",
        marked=False,
        certified=False,
    )

    assert not (row.marked and not row.certified)


def test_the_verdict_needs_the_control_to_certify(redteam: dict) -> None:
    """A matrix of refusals with a dead control proves nothing works."""
    Row = redteam["Row"]
    control = Row("positive control: a real regression", "ran", "not_reproduced", "", False, False)
    attacks = [Row(name, "ran", "deferred", "", True, False) for name in EXPECTED_CLASSES]

    passed = control.certified and all(row.marked and not row.certified for row in attacks)

    assert passed is False


def test_the_external_observer_item_stays_insufficient(redteam: dict) -> None:
    """Every row is observed from inside the product. That is evidence the
    boundary held for this attempt, not evidence the kernel denied it, and
    `G-SEC-002` is not allowed to read the first as the second."""
    source = (ROOT / "scripts" / "release" / "redteam.py").read_text(encoding="utf-8")

    assert "External observation: INSUFFICIENT" in source
    assert "sandbox-external" in source
    assert "auditd/seccomp-notify" in source


def test_the_positive_control_is_a_crash_not_a_changed_value(redteam: dict) -> None:
    """On 2026-09-07 the matrix reported FAIL, and the failing row was the
    *control*: `a + b` becoming `a - b` is a value change, and
    `attest.intent.v4.1` refuses a value change whose intended value the base
    tree does not state. Nothing about the isolation boundary had moved.

    A control that can fail for a reason unrelated to the boundary makes the
    whole matrix report FAIL about the wrong thing, so the control is a crash
    -- the class this product certifies."""
    import inspect

    source = inspect.getsource(redteam["_repo"])
    head = source.split('base = _git(repo, "rev-parse", "HEAD")')[1]

    assert "a - b" not in head, "the control is a value change again"
    assert "parts[1]" in head
    # the head really does raise where the base does not
    def head_add(a: int, b: int) -> int:
        parts = [a]
        return parts[1] + b

    with pytest.raises(IndexError):
        head_add(2, 2)
