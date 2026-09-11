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
from attest.review.executor import (
    PROBE_RECORDINGS,
    EvidenceClass,
    ExecutionOutcome,
    ExecutorLimits,
    verify_candidate,
)
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


DEFAULT_TEST_SOURCE = "import mod\n\n\ndef test_total():\n    assert mod.total([1, 2, 3]) == 6\n"


def two_revisions(
    tmp_path: Path, base: str, head: str, test_source: str = DEFAULT_TEST_SOURCE
) -> tuple[Path, str, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    run_git(repo, "init", "--initial-branch=main")
    (repo / "mod.py").write_text(base, encoding="utf-8")
    (repo / "tests").mkdir()
    # the base tree states what the module returns, which the value-class rule
    # (D-132/D-134) requires before a changed value may be published
    (repo / "tests" / "test_mod.py").write_text(test_source, encoding="utf-8")
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
    kwargs.setdefault("probe_generation", True)
    return verify_candidate(
        repo,
        candidate,
        gate_for(candidate),
        provider,
        Budget(limit_usd=1.0, model=DEFAULT_MODEL),
        ExecutorLimits(wall_timeout_s=90),
        base_sha=base_sha,
        head_sha=head_sha,
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
    assert row["recordings"] == PROBE_RECORDINGS and row["attempts"] == 1


def test_the_same_value_on_both_revisions_is_silence(tmp_path: Path) -> None:
    """D-216 moved where this silence is decided, not whether it is one.

    The screening run on head answers it now, before the 3x3 differential is
    bought: head produces base's observation, so there is nothing to buy and the
    search asks for another probe. The provider here answers with the same probe
    every time, so all `MAX_MODEL_PROBES` see the same thing and the run ends
    saying so -- with the changed lines reached, which is the half of the old
    sentence that was missing."""
    from attest.review.executor import MAX_MODEL_PROBES

    repo, base_sha, head_sha = two_revisions(tmp_path, BASE_MODULE, HEAD_SAME_VALUE)

    run = verify(repo, base_sha, head_sha, ProbeProvider(PROBE))

    assert run.execution.outcome is ExecutionOutcome.DEFERRED
    assert f"{MAX_MODEL_PROBES} probes tried" in run.execution.reason
    assert "reached the changed lines and observed no difference" in run.execution.reason
    assert run.execution.evidence_class is EvidenceClass.NOT_REPRODUCED
    assert run.execution.base_runs == ()
    # the recordings still happened, and they are in the ledger
    row = next(r for r in Ledger(repo).entries() if r["kind"] == "verification")
    assert [e["side"] for e in row["run_evidence"]].count("screen") == MAX_MODEL_PROBES


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


# --- the recorder's own rules, without a container ---------------------------


def _result(stdout: str, *, executed: tuple[int, ...] = (12,)) -> Any:
    from attest.review.executor import ExecutionOutcome as Outcome
    from attest.review.executor import ExecutionResult

    return ExecutionResult(
        outcome=Outcome.REPRODUCED,
        reason="",
        exit_code=1,
        stdout=stdout,
        stderr="",
        elapsed_s=0.1,
        network_blocked=True,
        executed_lines=executed,
    )


def _observation_line(kind: str, detail: str) -> str:
    import base64 as b64

    payload = b64.b64encode(
        json.dumps({"detail": detail, "kind": kind}, sort_keys=True).encode()
    ).decode()
    return f"ATTEST-PROBE-OBSERVATION {payload}"


def test_the_recorder_demands_three_agreeing_observations() -> None:
    """D-148 raised this from two. `random_product` returns one of four tuples
    uniformly, so two recordings agree one time in four -- and did, on
    `more-itertools 2deea20ead`, whose replay then failed on base."""
    from attest.review.executor import PROBE_RECORDINGS, _record_on_base

    assert PROBE_RECORDINGS == 3
    calls: list[int] = []

    def run(index: int, body: str) -> Any:
        del body
        calls.append(index)
        return _result(_observation_line("value", "6"))

    recorded = _record_on_base(
        probe=ProbeSpec(**PROBE), reprobe=None, run=run, anchored="mod.py"
    )
    assert calls == [1, 2, 3]
    assert recorded.observation == Observation(kind="value", detail="6")
    assert recorded.attempts == 1


def test_a_recording_that_disagrees_with_itself_is_refused() -> None:
    from attest.review.executor import _record_on_base

    answers = iter(["6", "7", "6"])

    def run(index: int, body: str) -> Any:
        del index, body
        return _result(_observation_line("value", next(answers)))

    recorded = _record_on_base(
        probe=ProbeSpec(**PROBE), reprobe=None, run=run, anchored="mod.py"
    )
    assert recorded.observation is None
    assert "not stable on base" in recorded.reason
    assert "the merge base returned 6" in recorded.reason


def test_a_probe_that_touched_nothing_in_the_anchored_file_is_refused() -> None:
    from attest.review.executor import _record_on_base

    def run(index: int, body: str) -> Any:
        del index, body
        return _result(_observation_line("value", "6"), executed=())

    recorded = _record_on_base(
        probe=ProbeSpec(**PROBE), reprobe=None, run=run, anchored="mod.py"
    )
    assert recorded.observation is None
    assert "did not execute mod.py on base" in recorded.reason


UNCOLLECTABLE_PROBE = {
    "imports": "import mod\nimport a_module_that_does_not_exist",
    "setup": "items = [1, 2, 3]",
    "expression": "mod.total(items)",
}


def test_a_probe_that_defers_on_base_writes_its_output_to_the_ledger(
    tmp_path: Path,
) -> None:
    """D-213. `probe deferred on base` was the largest loss category of the
    2026-09-10 held-out run and the row carried no output at all, so the cause
    of each one had to be re-derived by hand. The recording phase's runs are
    evidence like any other run, and they carry a bounded tail of both streams.
    """
    repo, base_sha, head_sha = two_revisions(tmp_path, BASE_MODULE, HEAD_WRONG_VALUE)

    run = verify(repo, base_sha, head_sha, ProbeProvider(UNCOLLECTABLE_PROBE))

    assert run.execution.outcome is ExecutionOutcome.DEFERRED
    assert "probe deferred on base" in run.execution.reason
    row = next(
        entry
        for entry in reversed(Ledger(repo).entries())
        if entry["kind"] == "verification"
    )
    assert row["schema_version"] == "attest.verification.v2"
    recordings = [entry for entry in row["run_evidence"] if entry["side"] == "probe"]
    assert recordings, "the recording run is not in the row"
    assert recordings[0]["outcome"] == "deferred"
    assert all(len(entry["stdout_tail"]) <= 4_096 for entry in recordings)
    assert all(len(entry["stderr_tail"]) <= 4_096 for entry in recordings)
    # the cause is readable without re-running anything
    streams = recordings[0]["stdout_tail"] + recordings[0]["stderr_tail"]
    assert "a_module_that_does_not_exist" in streams


# --- D-215: which silence, and D-216: asking again --------------------------
#
# Six of the thirteen 2026-09-10 held-out cases that executed a probe at all
# ended as *the reproduction passed on head*, and nobody could say whether the
# probe had touched the change. That sentence is two different facts with two
# different repairs, and only one of them has one.

# base guards the empty list, head does not: the changed lines are inside
# `first`, and a probe that calls `total` never enters them.
TWO_FUNCTION_BASE = (
    "def total(items):\n"
    "    return sum(items)\n"
    "\n"
    "\n"
    "def first(items):\n"
    "    if not items:\n"
    "        return None\n"
    "    return items[0]\n"
)
TWO_FUNCTION_HEAD = (
    "def total(items):\n"
    "    return sum(items)\n"
    "\n"
    "\n"
    "def first(items):\n"
    "    return items[0]\n"
)
TWO_FUNCTION_TESTS = (
    "import mod\n\n\ndef test_first():\n    assert mod.first([1, 2, 3]) == 1\n"
)
# a reproduction that passes on head and never enters the changed function
MISSES_THE_CHANGE_TEST = {
    "test_body": "import mod\n\n\ndef test_repro():\n    assert mod.total([1, 2, 3]) == 6\n"
}
# and one that passes on head having executed the changed lines
REACHES_THE_CHANGE_TEST = {
    "test_body": "import mod\n\n\ndef test_repro():\n    assert mod.first([1, 2]) == 1\n"
}


def test_a_reproduction_that_never_touched_the_change_says_so(tmp_path: Path) -> None:
    """D-215's first RED. `did not reach` and `no difference` had one sentence
    between them, and they are not the same claim about the diff."""
    repo, base_sha, head_sha = two_revisions(
        tmp_path, TWO_FUNCTION_BASE, TWO_FUNCTION_HEAD, TWO_FUNCTION_TESTS
    )

    run = verify(
        repo,
        base_sha,
        head_sha,
        ProbeProvider(MISSES_THE_CHANGE_TEST),
        candidate=stored(line=6),
        probe_generation=False,
    )

    assert run.execution.outcome is ExecutionOutcome.NOT_REPRODUCED
    assert "did not reach the changed lines" in run.execution.reason
    assert run.execution.evidence_class is EvidenceClass.UNBOUND


def test_a_reproduction_that_touched_the_change_and_saw_nothing_says_that_instead(
    tmp_path: Path,
) -> None:
    """D-215's second RED, and the one that must not be swept into the first:
    here the run really is a silence *about the diff*, and no further probe
    would change that."""
    repo, base_sha, head_sha = two_revisions(
        tmp_path, TWO_FUNCTION_BASE, TWO_FUNCTION_HEAD, TWO_FUNCTION_TESTS
    )

    run = verify(
        repo,
        base_sha,
        head_sha,
        ProbeProvider(REACHES_THE_CHANGE_TEST),
        candidate=stored(line=6),
        probe_generation=False,
    )

    assert run.execution.outcome is ExecutionOutcome.NOT_REPRODUCED
    assert "reached the changed lines and observed no difference" in run.execution.reason
    assert run.execution.evidence_class is EvidenceClass.NOT_REPRODUCED


# D-216: one probe per candidate was the product until now. These three drive
# the search: the feedback reaches the second probe, the second probe finds what
# the first could not, and a search that gives up says what it bought.

MISSES_THE_CHANGE = {
    "imports": "import mod",
    "setup": "items = [1, 2, 3]",
    "expression": "mod.total(items)",
}
REACHES_THE_CHANGE = {"imports": "import mod", "setup": "", "expression": "mod.first([])"}


class PromptRecorder(ProbeProvider):
    """A `ProbeProvider` that keeps the user prompt of every call it answered."""

    def __init__(self, *payloads: dict[str, str]) -> None:
        super().__init__(*payloads)
        self.prompts: list[str] = []

    def sample(
        self,
        system: str,
        prompt: str,
        schema: dict[str, Any],
        max_tokens: int,
        *,
        timeout_s: float | None = None,
    ) -> ProviderResult:
        self.prompts.append(prompt)
        return super().sample(system, prompt, schema, max_tokens, timeout_s=timeout_s)


def test_what_the_last_probe_did_is_handed_to_the_next_one(tmp_path: Path) -> None:
    """D-216's first RED. Without this the loop is three independent guesses
    rather than a search, and three guesses at the same prompt are one guess."""
    repo, base_sha, head_sha = two_revisions(
        tmp_path, TWO_FUNCTION_BASE, TWO_FUNCTION_HEAD, TWO_FUNCTION_TESTS
    )
    provider = PromptRecorder(MISSES_THE_CHANGE, REACHES_THE_CHANGE)

    verify(repo, base_sha, head_sha, provider, candidate=stored(line=6))

    assert len(provider.prompts) >= 2
    feedback = provider.prompts[1]
    assert "mod.total(items)" in feedback  # what the last probe called
    assert "none of them is a changed line" in feedback
    assert "first:" in feedback  # the definition the diff changed, by name


def test_the_second_probe_certifies_what_the_first_could_not_see(
    tmp_path: Path,
) -> None:
    """D-216's second RED, and the whole point of the change: this differential
    was unreachable when a candidate got one probe."""
    repo, base_sha, head_sha = two_revisions(
        tmp_path, TWO_FUNCTION_BASE, TWO_FUNCTION_HEAD, TWO_FUNCTION_TESTS
    )
    provider = PromptRecorder(MISSES_THE_CHANGE, REACHES_THE_CHANGE)

    run = verify(repo, base_sha, head_sha, provider, candidate=stored(line=6))

    assert run.execution.outcome is ExecutionOutcome.REPRODUCED
    assert run.execution.evidence_class is EvidenceClass.REGRESSION_REPRODUCED
    observed = run.execution.probe
    assert observed is not None
    assert observed.expression == "mod.first([])"
    row = next(r for r in Ledger(repo).entries() if r["kind"] == "probe_observation")
    assert row["schema_version"] == "attest.probe-observation.v3"
    assert row["attempt_index"] == 2
    assert row["feedback_kind"] == "did-not-reach"
    # the head side of the screening run is recorded too: it is what a value
    # note would have to state, and it was nowhere before
    assert row["head_kind"] == "exception"


def test_a_search_that_gives_up_says_what_it_bought(tmp_path: Path) -> None:
    """D-216's third RED. `MAX_MODEL_PROBES` probes that all miss is a different
    report from one probe that missed, and the reader pays for the difference."""
    from attest.review.executor import MAX_MODEL_PROBES

    repo, base_sha, head_sha = two_revisions(
        tmp_path, TWO_FUNCTION_BASE, TWO_FUNCTION_HEAD, TWO_FUNCTION_TESTS
    )
    provider = PromptRecorder(MISSES_THE_CHANGE)

    run = verify(repo, base_sha, head_sha, provider, candidate=stored(line=6))

    assert run.execution.outcome is ExecutionOutcome.DEFERRED
    assert len(provider.prompts) == MAX_MODEL_PROBES
    assert f"{MAX_MODEL_PROBES} probes tried" in run.execution.reason
    assert "did not reach the changed lines" in run.execution.reason
    assert run.execution.evidence_class is EvidenceClass.UNBOUND


def test_neither_half_of_the_silence_names_a_coordinate(tmp_path: Path) -> None:
    """D-091 holds through D-215 and D-216: an uncertified candidate's file must
    not reach the author, and every reason in this module ends up in the status
    body of a silent run. The first draft of D-215 put the anchored path in it
    and `tests/test_ci_flow.py` caught it."""
    repo, base_sha, head_sha = two_revisions(
        tmp_path, TWO_FUNCTION_BASE, TWO_FUNCTION_HEAD, TWO_FUNCTION_TESTS
    )

    missed = verify(
        repo,
        base_sha,
        head_sha,
        ProbeProvider(MISSES_THE_CHANGE_TEST),
        candidate=stored(line=6),
        probe_generation=False,
    )
    searched = verify(
        repo, base_sha, head_sha, PromptRecorder(MISSES_THE_CHANGE), candidate=stored(line=6)
    )

    for reason in (missed.execution.reason, searched.execution.reason):
        assert "mod.py" not in reason
        assert "mod.total" not in reason  # nor the model's own expression


def test_a_screening_run_that_died_says_why_in_the_search_s_own_reason() -> None:
    """The release drill for a malicious same-repository change demands that the
    run's reason **name what head code reached for**. The first draft of D-216
    reported only counts, so `attempted a network connection` on the head
    revision became "could not be executed on the head revision" and the drill
    failed. Counts for the model's own probes, the product's own sentence for
    the guard."""
    from attest.review.executor import _choose_probe, _Recording, _Screen

    spec = ProbeSpec(**PROBE)
    recorded = _Recording(
        probe=spec, observation=Observation(kind="value", detail="6"), reason="", attempts=1
    )

    outcome = _choose_probe(
        model_probe=spec,
        reprobe=lambda feedback: spec,
        record=lambda chosen: recorded,
        screen_on_head=lambda chosen: _Screen(
            observation=None,
            executed_lines=(),
            deferred=True,
            reason="reproduction attempted a network connection",
        ),
        anchored="mod.py",
        changed_lines=(2,),
        head_source="def total(items):\n    return sum(items)\n",
    )

    assert isinstance(outcome, _Recording)
    assert "attempted a network connection" in outcome.reason
    assert "3 probes tried" in outcome.reason


def test_a_drawered_value_change_writes_its_note_to_the_ledger(tmp_path: Path) -> None:
    """D-218, end to end on the local review path. base raises where head
    returns, no base test states the type name, so v4.2 drawers it -- and the
    fact that drawer throws away is written down instead of lost."""
    from attest.review.output_contract import check

    repo, base_sha, head_sha = two_revisions(tmp_path, BASE_RAISES, HEAD_GUARDS)

    run = verify(
        repo, base_sha, head_sha, ProbeProvider(MEAN_PROBE), candidate=stored(line=2)
    )

    assert "value change confirmed, intent unknown" in run.execution.reason
    row = next(
        r for r in Ledger(repo).entries() if r["kind"] == "value_observation_note"
    )
    assert row["schema_version"] == "attest.value-observation-note.v1"
    assert row["expression"] == "mod.mean([])"
    assert (row["base_kind"], row["base_detail"]) == ("exception", "ZeroDivisionError")
    assert (row["head_kind"], row["head_detail"]) == ("value", "0.0")
    assert row["head_runs"] == 3 and row["base_runs"] == 3
    assert row["specified_by"] == []  # nothing in the tree pins it
    assert check(row["rendered"]).admitted
    assert "the merge base raised ZeroDivisionError and head returns 0.0" in row["rendered"]
    # and nothing was published: the row is the only place it exists
    assert not any(r["kind"] == "github_comment" for r in Ledger(repo).entries())


def test_a_certified_differential_writes_no_note(tmp_path: Path) -> None:
    """The note is about the drawer. A receipt says the thing outright and a
    second, quieter claim beside it would be noise."""
    repo, base_sha, head_sha = two_revisions(tmp_path, BASE_MODULE, HEAD_WRONG_VALUE)

    run = verify(repo, base_sha, head_sha, ProbeProvider(PROBE))

    assert run.execution.outcome is ExecutionOutcome.REPRODUCED
    assert not [r for r in Ledger(repo).entries() if r["kind"] == "value_observation_note"]


def test_a_recording_whose_third_observation_disagrees_is_refused() -> None:
    """Three recordings are bought (D-148) and all three must agree. Until this
    test the recorder compared only the first two, so a base that returned the
    same value twice and something else the third time was called stable --
    and the third recording, paid for, was never read."""
    from attest.review.executor import PROBE_RECORDINGS, _record_on_base

    assert PROBE_RECORDINGS == 3
    answers = iter(["6", "6", "7"])

    def run(index: int, body: str) -> Any:
        del index, body
        return _result(_observation_line("value", next(answers)))

    recorded = _record_on_base(
        probe=ProbeSpec(**PROBE), reprobe=None, run=run, anchored="mod.py"
    )
    assert recorded.observation is None
    assert "not stable on base" in recorded.reason
    assert "the merge base returned 6" in recorded.reason
    assert "then the merge base returned 7" in recorded.reason
