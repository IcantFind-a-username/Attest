"""Reproduction by probe and record/replay (D-146), end to end on real trees.

The owner's three REDs are the first three tests: a probe whose recorded value
differs on head makes a differential; the same value is silence; a probe that
raises on base records the **exception type** as the expectation. All three fail
on the previous implementation, which had no probe path at all.

The fourth is the property that motivates the whole design:
`test_a_replay_can_never_fail_on_base_as_well`. D-140's wall was 20 of 31
answered candidates ending in *unfaithful generated test: fails on base as
well*; here the expectation is what base itself produced, so that outcome is
structurally unreachable, and the branch that would report it says in its own
words that reaching it is a bug rather than evidence.

Everything below executes: two git revisions, two worktrees, real `pytest` runs
under the executor's guards. No provider is asked for anything but a probe.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from attest.review.budget import Budget
from attest.review.candidates import StoredCandidate
from attest.review.channels import ChannelPurchase
from attest.review.config import load_pricing
from attest.review.executor import EvidenceClass, ExecutionOutcome, ExecutorLimits, verify_candidate
from attest.review.gate import GateResult
from attest.review.ledger import Ledger
from attest.review.probe import (
    Observation,
    ProbeSpec,
    parse_observation,
    parse_probe,
    probe_test_body,
    replay_test_body,
)
from attest.review.proposer import ProviderResult
from attest.review.schema import Finding

DEFAULT_MODEL = str(load_pricing()["default_model"])

# base returns the sum; three heads: one that returns something else, one that
# is identical in behaviour, and one that raises where base returned.
BASE_MODULE = "def total(items):\n    return sum(items)\n"
HEAD_WRONG_VALUE = "def total(items):\n    return sum(items) - 1\n"
HEAD_SAME_VALUE = "def total(items):\n    # a comment, and nothing else\n    return sum(items)\n"
# base raises on an empty list; head returns 0.0 -- the recording direction that
# matters, because base's *exception type* is the expectation
BASE_RAISES = "def mean(items):\n    return sum(items) / len(items)\n"
HEAD_GUARDS = (
    "def mean(items):\n    if not items:\n        return 0.0\n    return sum(items) / len(items)\n"
)

PROBE = {"imports": "import mod", "setup": "items = [1, 2, 3]", "expression": "mod.total(items)"}
MEAN_PROBE = {"imports": "import mod", "setup": "", "expression": "mod.mean([])"}
# a probe that never enters the anchored file: it computes its own answer
DETACHED_PROBE = {"imports": "import mod", "setup": "", "expression": "sum([1, 2, 3])"}


def run_git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "-c",
            "user.email=probe@example.test",
            "-c",
            "user.name=probe-tests",
            "-c",
            "commit.gpgsign=false",
            *args,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return completed.stdout.strip()


def two_revisions(tmp_path: Path, base: str, head: str) -> tuple[Path, str, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    run_git(repo, "init", "--initial-branch=main")
    (repo / "mod.py").write_text(base, encoding="utf-8")
    (repo / "tests").mkdir()
    # the base tree states what the module returns, which the value-class rule
    # (D-132/D-134) requires before a changed value may be published
    (repo / "tests" / "test_mod.py").write_text(
        "import mod\n\n\ndef test_total():\n    assert mod.total([1, 2, 3]) == 6\n",
        encoding="utf-8",
    )
    run_git(repo, "add", "--all")
    run_git(repo, "commit", "-m", "base")
    base_sha = run_git(repo, "rev-parse", "HEAD")
    (repo / "mod.py").write_text(head, encoding="utf-8")
    run_git(repo, "commit", "-am", "head")
    head_sha = run_git(repo, "rev-parse", "HEAD")
    return repo, base_sha, head_sha


class ProbeProvider:
    """Answers the probe question and nothing else."""

    def __init__(self, *payloads: dict[str, str]) -> None:
        self.payloads = list(payloads)
        self.systems: list[str] = []

    def sample(
        self,
        system: str,
        prompt: str,
        schema: dict[str, Any],
        max_tokens: int,
        *,
        timeout_s: float | None = None,
    ) -> ProviderResult:
        del prompt, schema, max_tokens, timeout_s
        self.systems.append(system)
        payload = self.payloads.pop(0) if len(self.payloads) > 1 else self.payloads[0]
        return ProviderResult(text=json.dumps(payload), input_tokens=10, output_tokens=10)


def stored(file: str = "mod.py", line: int = 2) -> StoredCandidate:
    return StoredCandidate(
        task_id="task-probe",
        finding=Finding(
            claim="The total is off by one.",
            file=file,
            line=line,
            failure_scenario="total([1, 2, 3]) no longer returns 6.",
            falsification_plan="Call total on a small list.",
        ),
        wealth=8.0,
        action="drawer",
        alpha=0.1,
    )


def gate_for(candidate: StoredCandidate) -> GateResult:
    return GateResult(
        finding=candidate.finding,
        wealth=candidate.wealth,
        purchases=[ChannelPurchase("S", 2.0, "existing evidence")],
        decision=None,
    )


def verify(repo: Path, base_sha: str, head_sha: str, provider: ProbeProvider, **kwargs: Any):
    candidate = kwargs.pop("candidate", None) or stored()
    return verify_candidate(
        repo,
        candidate,
        gate_for(candidate),
        provider,
        Budget(limit_usd=1.0, model=DEFAULT_MODEL),
        ExecutorLimits(wall_timeout_s=90),
        base_sha=base_sha,
        head_sha=head_sha,
        probe_generation=True,
        **kwargs,
    )


# --- the owner's three ------------------------------------------------------


def test_a_value_recorded_on_base_and_different_on_head_is_a_differential(
    tmp_path: Path,
) -> None:
    repo, base_sha, head_sha = two_revisions(tmp_path, BASE_MODULE, HEAD_WRONG_VALUE)
    provider = ProbeProvider(PROBE)

    run = verify(repo, base_sha, head_sha, provider)

    assert run.execution.outcome is ExecutionOutcome.REPRODUCED
    assert run.execution.evidence_class is EvidenceClass.REGRESSION_REPRODUCED
    assert [len(run.execution.head_runs), len(run.execution.base_runs)] == [3, 3]
    observed = run.execution.probe
    assert observed is not None
    assert (observed.kind, observed.detail) == ("value", "6")
    assert observed.expression == "mod.total(items)"
    # the assertion in the bundled test is base's own observation, verbatim
    assert run.spec is not None
    assert "assert _attest_value == 6" in run.spec.test_body
    assert "no model wrote this expectation" in run.spec.test_body
    row = next(r for r in Ledger(repo).entries() if r["kind"] == "probe_observation")
    assert (row["observed_kind"], row["observed_detail"]) == ("value", "6")
    assert row["recordings"] == 2 and row["attempts"] == 1


def test_the_same_value_on_both_revisions_is_silence(tmp_path: Path) -> None:
    repo, base_sha, head_sha = two_revisions(tmp_path, BASE_MODULE, HEAD_SAME_VALUE)

    run = verify(repo, base_sha, head_sha, ProbeProvider(PROBE))

    assert run.execution.outcome is ExecutionOutcome.NOT_REPRODUCED
    assert run.execution.reason == "pytest passed on head in 3/3 runs; base not executed"
    assert run.execution.base_runs == ()
    assert run.execution.probe is not None  # the recording still happened


def test_an_exception_on_base_is_recorded_as_the_expectation(tmp_path: Path) -> None:
    """base raises, head returns: the recorded expectation is the exception's
    type name, and the replay is the thing that notices head stopped raising."""

    repo, base_sha, head_sha = two_revisions(tmp_path, BASE_RAISES, HEAD_GUARDS)
    candidate = stored(line=2)

    run = verify(repo, base_sha, head_sha, ProbeProvider(MEAN_PROBE), candidate=candidate)

    observed = run.execution.probe
    assert observed is not None
    assert (observed.kind, observed.detail) == ("exception", "ZeroDivisionError")
    assert run.spec is not None
    assert "assert _attest_raised == 'ZeroDivisionError'" in run.spec.test_body
    # the differential itself holds: head fails every run, base passes every run
    assert [r.outcome for r in run.execution.head_runs] == [ExecutionOutcome.REPRODUCED] * 3
    assert [r.outcome for r in run.execution.base_runs] == [ExecutionOutcome.NOT_REPRODUCED] * 3
    # what that is *worth* is the unchanged intent rule's call, not this module's:
    # base raising and head not raising pins the type name as a string, and no
    # base test in this fixture states it, so v4.1 drawers it as a value change
    assert "value change confirmed, intent unknown" in run.execution.reason


# --- the property the design exists for -------------------------------------


def test_a_replay_can_never_fail_on_base_as_well(tmp_path: Path) -> None:
    """D-140's wall, closed by construction.

    Whatever base does with the probe's expression becomes the expectation, so
    the base runs of the replay assert what base just did. The legacy verdict
    string must not appear on this path at all.
    """
    cases = (
        (BASE_MODULE, HEAD_WRONG_VALUE, PROBE),
        (BASE_MODULE, HEAD_SAME_VALUE, PROBE),
        (BASE_RAISES, HEAD_GUARDS, MEAN_PROBE),
    )
    for index, (base, head, probe) in enumerate(cases):
        root = tmp_path / f"case{index}"
        root.mkdir()
        repo, base_sha, head_sha = two_revisions(root, base, head)
        run = verify(repo, base_sha, head_sha, ProbeProvider(probe))
        assert "fails on base as well" not in run.execution.reason


def test_a_probe_that_does_not_reach_the_anchored_file_records_nothing(tmp_path: Path) -> None:
    """The guard that refuses D-140's classes H and O: a probe that computes its
    own answer, or calls a signature only head has, never enters the code under
    review, so what it recorded is not about the diff."""

    repo, base_sha, head_sha = two_revisions(tmp_path, BASE_MODULE, HEAD_WRONG_VALUE)

    run = verify(repo, base_sha, head_sha, ProbeProvider(DETACHED_PROBE))

    assert run.execution.outcome is ExecutionOutcome.DEFERRED
    assert "did not execute mod.py on base" in run.execution.reason
    assert run.execution.evidence_class is EvidenceClass.UNFAITHFUL
    assert run.execution.head_runs == () and run.execution.base_runs == ()


def test_an_unstable_observation_on_base_is_refused(tmp_path: Path) -> None:
    """Two recordings, and they must agree. A clock, an address in a `repr`, an
    iteration order: any of them would make the replay fail on base for a reason
    that has nothing to do with the change."""

    # a fresh process each run, so a module-level counter would restart at zero;
    # the clock is the thing that actually differs between two recordings
    unstable = "import time\n\n\ndef total(items):\n    return sum(items) + time.time_ns()\n"
    repo, base_sha, head_sha = two_revisions(tmp_path, unstable, unstable + "# head\n")

    run = verify(repo, base_sha, head_sha, ProbeProvider(PROBE))

    assert run.execution.outcome is ExecutionOutcome.DEFERRED
    assert "not stable on base" in run.execution.reason
    assert "the merge base returned" in run.execution.reason


# --- the pure parts, without execution ---------------------------------------


def test_the_probe_schema_refuses_anything_that_is_not_one_call() -> None:
    for payload, fragment in (
        ({"imports": "", "setup": "", "expression": "x = 1"}, "single Python expression"),
        ({"imports": "def f(): pass", "setup": "", "expression": "f()"}, "not an import"),
        ({"imports": "", "setup": "if True", "expression": "1"}, "setup does not parse"),
        ({"imports": "", "setup": "", "expression": ""}, "no expression"),
        ({"test_body": "assert False"}, "does not match the probe schema"),
    ):
        with pytest.raises(Exception) as caught:  # noqa: B017 - the message is the assertion
            parse_probe(json.dumps(payload))
        assert fragment in str(caught.value)


def test_a_probe_body_reports_its_observation_on_both_streams() -> None:
    body = probe_test_body(ProbeSpec(**PROBE))
    assert "print('ATTEST-PROBE-OBSERVATION " in body
    assert "raise AssertionError('ATTEST-PROBE-OBSERVATION " in body
    namespace: dict[str, Any] = {}
    exec(compile(body.replace("import mod", "mod = None"), "<probe>", "exec"), namespace)
    with pytest.raises(AssertionError) as caught:
        namespace["test_attest_probe"]()
    observed = parse_observation(str(caught.value))
    assert observed == Observation(kind="exception", detail="AttributeError")


def test_a_replay_body_asserts_the_recording_and_carries_no_prose() -> None:
    body = replay_test_body(ProbeSpec(**PROBE), Observation(kind="value", detail="6"))
    assert "assert _attest_value == 6" in body  # the int, not the string "6"
    assert "ATTEST-PROBE-OBSERVATION" not in body
    assert body.count("def test_") == 1

    # a value whose repr is not a literal falls back to comparing the repr
    opaque = replay_test_body(ProbeSpec(**PROBE), Observation(kind="value", detail="<Row id=3>"))
    assert "assert repr(_attest_value) == '<Row id=3>'" in opaque

    # and a recorded exception compares the type name
    raised = replay_test_body(
        ProbeSpec(**PROBE), Observation(kind="exception", detail="KeyError")
    )
    assert "assert _attest_raised == 'KeyError'" in raised
