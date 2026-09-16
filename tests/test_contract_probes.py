"""D-254: contract probes in the product path, experimental and off by default.

With ``contract_probes`` on, a candidate's probe search first screens the probes the
fixed rule reads out of the base tree's own contracts about the definitions the change
touched -- free, no model call -- and asks the model only when none of them makes the
revisions differ. ``intent_policy`` names the rule the review certifies under. Neither is
a policy key: a reviewed repository cannot turn them on, and the factory setting is the
shipped behaviour exactly.

Everything below executes on real trees under the executor's guards.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from attest.certification.intent import INTENT_POLICY_V6, INTENT_POLICY_VERSION
from attest.review.budget import Budget
from attest.review.candidates import StoredCandidate
from attest.review.channels import ChannelPurchase
from attest.review.config import ReviewConfig, load_config, load_pricing, validate_review_config
from attest.review.contracts import MAX_CONTRACT_PROBES, contract_probes, find_contracts
from attest.review.executor import (
    EvidenceClass,
    ExecutionOutcome,
    ExecutorLimits,
    verify_candidate,
)
from attest.review.gate import GateResult
from attest.review.ledger import Ledger
from attest.review.proposer import ProviderResult
from attest.review.schema import Finding

DEFAULT_MODEL = str(load_pricing()["default_model"])

GEO_BASE = '''from typing import NamedTuple


class Point(NamedTuple):
    x: int
    y: int


def parse(text):
    a, b = text.split(",")
    return Point(int(a), int(b))
'''
GEO_HEAD = GEO_BASE.replace("return Point(int(a), int(b))", "return Point(int(a), int(b) + 1)")
# a head that changes behaviour only on an input no contract states
GEO_HEAD_ELSEWHERE = GEO_BASE.replace(
    "return Point(int(a), int(b))",
    'return Point(int(a), int(b) + (1 if text == "9,9" else 0))',
)
PARSE_LINE = 11  # `return Point(...)` on head

TESTS = '''import pytest

from geo import Point, parse


@pytest.mark.parametrize("text, x, y", [("1,2", 1, 2), ("3,4", 3, 4)])
def test_parse(text, x, y):
    assert parse(text) == Point(x, y)


def test_parse_with_a_fixture(sample_text):
    assert parse(sample_text) == Point(0, 0)


def test_parse_with_a_local_class():
    class Text(str):
        pass

    assert parse(Text("5,6")) == Point(5, 6)
'''


def run_git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), "-c", "user.email=contract@example.test",
         "-c", "user.name=contract-tests", "-c", "commit.gpgsign=false", *args],
        capture_output=True, text=True, check=True,
    )
    return completed.stdout.strip()


def two_revisions(tmp_path: Path, head: str) -> tuple[Path, str, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    run_git(repo, "init", "--initial-branch=main")
    (repo / "geo.py").write_text(GEO_BASE, encoding="utf-8")
    (repo / "tests").mkdir()
    (repo / "tests" / "test_geo.py").write_text(TESTS, encoding="utf-8")
    run_git(repo, "add", "--all")
    run_git(repo, "commit", "-m", "base")
    base_sha = run_git(repo, "rev-parse", "HEAD")
    (repo / "geo.py").write_text(head, encoding="utf-8")
    run_git(repo, "commit", "-am", "head")
    return repo, base_sha, run_git(repo, "rev-parse", "HEAD")


@pytest.mark.parametrize(
    "binding", ["from pretend import pytest", "import pytest\npytest = replacement"]
)
def test_parameter_decorator_requires_an_unrebound_framework_import(
    tmp_path: Path, binding: str,
) -> None:
    repo, _, _ = two_revisions(tmp_path, GEO_HEAD)
    (repo / "tests/test_geo.py").write_text(TESTS.replace("import pytest", binding))
    observed = find_contracts(
        base_tree=repo, head_tree=repo, anchored="geo.py", symbols=("parse",),
        pinned=("'Point(x=1, y=2)'",),
        test_source='from geo import parse\ndef test_probe():\n    _attest_value = parse("1,2")\n',
    )
    assert not contract_probes(repo, "geo.py", ("parse",)).probes
    assert observed and not any(c.admitted for c in observed)
    assert all("context" in c.reason for c in observed)


class CountingProvider:
    """Answers the probe question with one fixed probe, and counts every call."""

    def __init__(self, payload: dict[str, str] | None = None) -> None:
        self.payload = payload
        self.calls = 0

    def sample(self, system: str, prompt: str, schema: dict[str, Any], max_tokens: int, *,
               timeout_s: float | None = None) -> ProviderResult:
        del system, prompt, schema, max_tokens, timeout_s
        self.calls += 1
        if self.payload is None:
            raise AssertionError("the model was asked for a probe")
        return ProviderResult(text=json.dumps(self.payload), input_tokens=10, output_tokens=10)


def verify(repo: Path, base_sha: str, head_sha: str, provider: CountingProvider, **kwargs: Any):
    candidate = StoredCandidate(
        task_id="task-contract",
        finding=Finding(claim="parse returns the wrong point.", file="geo.py", line=PARSE_LINE,
                        failure_scenario="parse('1,2') no longer returns Point(1, 2).",
                        falsification_plan="Call parse on the tests' own input."),
        wealth=8.0, action="drawer", alpha=0.1,
    )
    gate = GateResult(finding=candidate.finding, wealth=8.0,
                      purchases=[ChannelPurchase("S", 2.0, "existing evidence")], decision=None)
    return verify_candidate(
        repo, candidate, gate, provider, Budget(limit_usd=1.0, model=DEFAULT_MODEL),
        ExecutorLimits(wall_timeout_s=90), base_sha=base_sha, head_sha=head_sha,
        probe_generation=True, **kwargs,
    )


# --- the rule -----------------------------------------------------------------------


def test_the_rule_reads_one_probe_per_row_and_names_what_it_cannot_build(tmp_path: Path) -> None:
    repo, _base, _head = two_revisions(tmp_path, GEO_HEAD)
    run_git(repo, "checkout", "-q", "HEAD~1")

    search = contract_probes(repo, "geo.py", ["parse"])

    assert [(p.kind, p.origin, p.spec.setup, p.spec.expression) for p in search.probes] == [
        ("parametrize_row", "tests/test_geo.py:8#0", "text = '1,2'", "parse(text)"),
        ("parametrize_row", "tests/test_geo.py:8#1", "text = '3,4'", "parse(text)"),
    ]
    assert all(p.spec.imports == "from geo import parse" for p in search.probes)
    reasons = dict(search.refused)
    # D-255 refused this for the call's own dependency; D-282 refuses it earlier, because
    # a fixture no conftest on the path defines is context the rule has not read at all
    assert reasons["tests/test_geo.py:12#0"] == (
        "test context: test_parse_with_a_fixture asks for 'sample_text', a fixture no "
        "conftest on the path defines: what it does is not read"
    )
    assert reasons["tests/test_geo.py:19#0"] == "'Text' is bound nowhere the rule reads"
    assert search.truncated == 0 and MAX_CONTRACT_PROBES == 8


# --- the product path ------------------------------------------------------------------


def test_a_contract_probe_certifies_under_v6_without_asking_the_model(tmp_path: Path) -> None:
    repo, base_sha, head_sha = two_revisions(tmp_path, GEO_HEAD)
    provider = CountingProvider(payload=None)

    run = verify(repo, base_sha, head_sha, provider, contract_probes=True,
                 intent_policy=INTENT_POLICY_V6)

    assert provider.calls == 0
    assert run.execution.outcome is ExecutionOutcome.REPRODUCED
    assert run.execution.evidence_class is EvidenceClass.REGRESSION_REPRODUCED
    probe = run.execution.probe
    assert probe is not None and probe.source == "contract"
    assert probe.origin == "tests/test_geo.py:8#0"
    assert run.execution.intent is not None
    assert run.execution.intent.policy_version == INTENT_POLICY_V6
    assert [c.admitted for c in run.execution.intent.contracts if c.input_bound] == [True]
    rows = Ledger(repo).entries()
    search = next(r for r in rows if r["kind"] == "contract_search")
    assert search["chosen"] == "tests/test_geo.py:8#0" and len(search["probes"]) == 2
    assert search["refused_count"] == 2
    observation = next(r for r in rows if r["kind"] == "probe_observation")
    assert observation["source"] == "contract" and observation["attempts"] == 0


def test_the_same_contract_probe_under_the_shipped_rule_is_the_drawer(tmp_path: Path) -> None:
    repo, base_sha, head_sha = two_revisions(tmp_path, GEO_HEAD)
    provider = CountingProvider(payload=None)

    run = verify(repo, base_sha, head_sha, provider, contract_probes=True)

    assert provider.calls == 0
    assert run.execution.probe is not None and run.execution.probe.source == "contract"
    assert run.execution.outcome is ExecutionOutcome.DEFERRED
    assert run.execution.intent is not None
    assert run.execution.intent.policy_version == INTENT_POLICY_VERSION
    assert "value change confirmed, intent unknown" in run.execution.reason


def test_no_contract_probe_that_differs_hands_the_search_to_the_model(tmp_path: Path) -> None:
    repo, base_sha, head_sha = two_revisions(tmp_path, GEO_HEAD_ELSEWHERE)
    provider = CountingProvider(
        payload={"imports": "from geo import parse", "setup": "", "expression": 'parse("9,9")'}
    )

    run = verify(repo, base_sha, head_sha, provider, contract_probes=True,
                 intent_policy=INTENT_POLICY_V6)

    assert provider.calls == 1
    probe = run.execution.probe
    assert probe is not None and probe.source == "model"
    assert probe.screened == 2
    search = next(r for r in Ledger(repo).entries() if r["kind"] == "contract_search")
    assert search["chosen"] == ""


def test_the_factory_setting_asks_the_model_first_and_runs_no_contract_search(
    tmp_path: Path,
) -> None:
    repo, base_sha, head_sha = two_revisions(tmp_path, GEO_HEAD)
    provider = CountingProvider(
        payload={"imports": "from geo import parse", "setup": "", "expression": 'parse("1,2")'}
    )

    run = verify(repo, base_sha, head_sha, provider)

    assert provider.calls == 1
    assert run.execution.probe is not None and run.execution.probe.source == "model"
    assert run.execution.contract_search is None
    assert run.execution.intent is not None
    assert run.execution.intent.policy_version == INTENT_POLICY_VERSION
    assert not any(r["kind"] == "contract_search" for r in Ledger(repo).entries())


# --- the switches ----------------------------------------------------------------------


def test_the_switches_default_off_and_are_not_policy_keys(tmp_path: Path) -> None:
    config = ReviewConfig()
    assert (config.contract_probes, config.intent_policy) == (False, INTENT_POLICY_VERSION)
    (tmp_path / ".attest.toml").write_text(
        'contract_probes = true\nintent_policy = "attest.intent.v6"\n', encoding="utf-8"
    )
    loaded = load_config(tmp_path)
    assert (loaded.contract_probes, loaded.intent_policy) == (False, INTENT_POLICY_VERSION)
    with pytest.raises(ValueError, match="intent_policy must be one of"):
        validate_review_config(ReviewConfig(intent_policy="attest.intent.v7"))
    with pytest.raises(ValueError, match="contract_probes must be a boolean"):
        validate_review_config(ReviewConfig(contract_probes="yes"))  # type: ignore[arg-type]
