"""Contract-binding correctness: four scenarios, traced from the contract search to the kernel.

Each scenario is a two-revision repository whose base tests state a contract in a shape the
reader must bind correctly or refuse, and one change the review is asked about. `trace` runs
the product's own path on it -- `verify_candidate` (the contract search when on, the model
probe otherwise, the 3x3 differential, the intent observation) and then
`attempt_certification` (receipt, kernel validation) -- and records, separately:

    reader      did the intent observer admit a contract, and with which bindings
    verdict     the intent rule's own verdict on the observation
    certified   did the kernel accept a receipt

    reassigned_after_assert   `text = "1,2"; assert norm(text) == Point(1, 2); text = "9,9"`:
                              the contract is about "1,2"; a reader that binds a name by its
                              last assignment in the function says it is about "9,9"
    receiver_mutated          `g = Grid(width=2); g.cache = {}; assert g.cell(Point(1, 2)) == ...`:
                              the contract is about a grid with a cache; a reader that binds the
                              receiver by its construction alone says it is about any Grid(width=2)
    unreachable_assert        `return` before the assertion: the suite never checks it
    legal_contract            the first shape on a change that breaks "1,2" itself: the contract
                              is bound at its assertion and must still be admitted (D-255)
    first_contract_masks_model  the selection diagnostic: the first contract probe makes the
                              revisions differ and cannot certify, while the model probe the search
                              would otherwise have asked for certifies

    .venv/bin/python scripts/corpus/binding_cases.py --policy attest.intent.v6 --out before.json

Executed on the host development adapter (the tests' own backend): the kernel and the intent rule
are the same code on either backend.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from attest.certification.intent import intent_verdict  # noqa: E402
from attest.review.budget import Budget  # noqa: E402
from attest.review.candidates import StoredCandidate  # noqa: E402
from attest.review.certify import (  # noqa: E402
    attempt_certification,
    certification_policy,
    certification_task,
)
from attest.review.channels import ChannelPurchase  # noqa: E402
from attest.review.config import load_pricing  # noqa: E402
from attest.review.executor import ExecutorLimits, verify_candidate  # noqa: E402
from attest.review.gate import GateResult  # noqa: E402
from attest.review.ledger import Ledger  # noqa: E402
from attest.review.proposer import ProviderResult  # noqa: E402
from attest.review.schema import Finding  # noqa: E402

GEO_BASE = '''from typing import NamedTuple


class Point(NamedTuple):
    x: int
    y: int


def norm(text):
    a, b = text.split(",")
    return Point(min(int(a), 1), min(int(b), 2))


class Grid:
    def __init__(self, width=1):
        self.width = width
        self.cache = None

    def cell(self, point):
        return Point(point.x * self.width, point.y)


def parse(text):
    a, b = text.split(",")
    return Point(int(a), int(b))


class Label:
    def __init__(self, text):
        self.text = text

    def __eq__(self, other):
        return isinstance(other, Label) and other.text == self.text

    def __repr__(self):
        return f"Label({self.text!r})"


def describe(n):
    """describe(9) returns 'nine'; a small n is described by its Label."""
    return Label(str(n)) if n < 5 else "nine"
'''

SCENARIOS: dict[str, dict[str, Any]] = {
    "reassigned_after_assert": {
        "head": ("return Point(min(int(a), 1), min(int(b), 2))",
                 "return Point(min(int(a), 1), min(int(b), 3))"),
        "tests": '''from geo import Point, norm


def test_norm():
    text = "1,2"
    assert norm(text) == Point(1, 2)
    text = "9,9"
    assert len(text) == 3
''',
        "probe": {"imports": "from geo import norm", "setup": "", "expression": 'norm("9,9")'},
    },
    "receiver_mutated": {
        "head": ("return Point(point.x * self.width, point.y)",
                 "return Point(point.x * self.width, point.y + (1 if self.cache is None else 0))"),
        "tests": '''from geo import Grid, Point


def test_cell_with_a_cache():
    g = Grid(width=2)
    g.cache = {}
    assert g.cell(Point(1, 2)) == Point(2, 2)
''',
        "probe": {"imports": "from geo import Grid, Point", "setup": "g = Grid(width=2)",
                  "expression": "g.cell(Point(1, 2))"},
    },
    "unreachable_assert": {
        "head": ("return Point(int(a), int(b))", "return Point(int(a), int(b) + 1)"),
        "tests": '''from geo import Point, parse


def test_parse_disabled():
    return
    assert parse("5,6") == Point(5, 6)
''',
        "probe": {"imports": "from geo import parse", "setup": "", "expression": 'parse("5,6")'},
    },
    # D-255's acceptance path: the same shape as `reassigned_after_assert`, on a change
    # that breaks the input the assertion states -- a legal contract, bound at its point
    "legal_contract": {
        "head": ("return Point(int(a), int(b))", "return Point(int(a), int(b) + 1)"),
        "tests": '''from geo import Point, parse


def test_parse():
    text = "1,2"
    assert parse(text) == Point(1, 2)
    text = "9,9"
    assert len(text) == 3
''',
        "probe": {"imports": "from geo import parse", "setup": "", "expression": 'parse("1,2")'},
    },
    "first_contract_masks_model": {
        "head": ('return Label(str(n)) if n < 5 else "nine"',
                 'return Label(str(n + 1)) if n < 5 else "nine"[:3]'),
        "tests": '''from geo import Label, describe


def test_describe_small():
    assert describe(1) == Label("1")
''',
        "probe": {"imports": "from geo import describe", "setup": "", "expression": "describe(9)"},
    },
}


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), "-c", "user.email=binding@example.test",
         "-c", "user.name=binding-cases", "-c", "commit.gpgsign=false", *args],
        capture_output=True, text=True, check=True,
    ).stdout.strip()


def build(name: str, root: Path) -> tuple[Path, str, str, int]:
    """The scenario's repository: (repo, base sha, head sha, the changed line on head)."""
    scenario = SCENARIOS[name]
    repo = root / name
    repo.mkdir(parents=True)
    _git(repo, "init", "--initial-branch=main")
    (repo / "geo.py").write_text(GEO_BASE, encoding="utf-8")
    (repo / "tests").mkdir()
    (repo / "tests" / "test_geo.py").write_text(scenario["tests"], encoding="utf-8")
    for relative, source in scenario.get("files", {}).items():
        target = repo / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source, encoding="utf-8")
    _git(repo, "add", "--all")
    _git(repo, "commit", "-m", "base")
    base = _git(repo, "rev-parse", "HEAD")
    old, new = scenario["head"]
    head_source = GEO_BASE.replace(old, new)
    assert head_source != GEO_BASE, name
    (repo / "geo.py").write_text(head_source, encoding="utf-8")
    _git(repo, "commit", "-am", "head")
    line = next(i for i, text in enumerate(head_source.splitlines(), 1) if new in text)
    return repo, base, _git(repo, "rev-parse", "HEAD"), line


class FixedProbe:
    """Answers the probe question with the scenario's one model probe, and counts calls."""

    def __init__(self, payload: dict[str, str]) -> None:
        self.payload = payload
        self.calls = 0

    def sample(self, system: str, prompt: str, schema: dict[str, Any], max_tokens: int, *,
               timeout_s: float | None = None) -> ProviderResult:
        del system, prompt, schema, max_tokens, timeout_s
        self.calls += 1
        return ProviderResult(text=json.dumps(self.payload), input_tokens=10, output_tokens=10)


def trace(name: str, *, policy: str, contract_probes: bool, root: Path) -> dict[str, Any]:
    repo, base, head, line = build(name, root)
    provider = FixedProbe(SCENARIOS[name]["probe"])
    candidate = StoredCandidate(
        task_id=f"binding-{name}",
        finding=Finding(claim="the changed line misbehaves.", file="geo.py", line=line,
                        failure_scenario="a caller sees another value.",
                        falsification_plan="call the changed function."),
        wealth=8.0, action="drawer", alpha=0.1,
    )
    gate = GateResult(finding=candidate.finding, wealth=8.0,
                      purchases=[ChannelPurchase("S", 2.0, "existing evidence")], decision=None)
    run = verify_candidate(
        repo, candidate, gate, provider,
        Budget(limit_usd=1.0, model=str(load_pricing()["default_model"])),
        ExecutorLimits(wall_timeout_s=90), base_sha=base, head_sha=head, probe_generation=True,
        contract_probes=contract_probes, intent_policy=policy,
    )
    execution = run.execution
    profile = next((r.executor_profile for r in execution.head_runs), "")
    cpolicy = certification_policy(3, profile, intent_policy_version=policy)
    task = certification_task(task_id=candidate.task_id, repository_id=name, merge_base_sha=base,
                              head_sha=head, diff_digest="0" * 64, policy_source_sha=base,
                              policy=cpolicy, review_policy_digest="0" * 64)
    attempt = attempt_certification(task, cpolicy, candidate, run, limits=ExecutorLimits())
    search = next((r for r in Ledger(repo).entries() if r.get("kind") == "contract_search"), None)
    intent = execution.intent
    return {
        "scenario": name,
        "policy": policy,
        "contract_probes": contract_probes,
        "model_calls": provider.calls,
        "contract_search": None if search is None else {
            "probes": [p["origin"] + " " + p["expression"] for p in search["probes"]],
            "refused": search["refused"], "chosen": search["chosen"]},
        "probe": None if execution.probe is None else {
            "source": execution.probe.source, "origin": execution.probe.origin,
            "setup": execution.probe.setup, "expression": execution.probe.expression},
        "outcome": execution.outcome.value,
        "evidence_class": execution.evidence_class.value,
        "reason": execution.reason,
        "reader": None if intent is None else [asdict(c) for c in intent.contracts],
        "reader_admitted": None if intent is None else any(c.admitted for c in intent.contracts),
        "verdict": None if intent is None else (intent_verdict(intent) or "publishes"),
        "certification": attempt.outcome,
        "certification_reason": attempt.reason,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--policy", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--scenarios", default=",".join(SCENARIOS))
    args = parser.parse_args(argv)
    results = []
    with tempfile.TemporaryDirectory(prefix="binding-cases-") as tmp:
        for name in args.scenarios.split(","):
            arms = [True, False] if name == "first_contract_masks_model" else [True]
            for on in arms:
                sub = Path(tmp) / f"{name}-{'contracts' if on else 'model'}"
                sub.mkdir()
                result = trace(name, policy=args.policy, contract_probes=on, root=sub)
                results.append(result)
                print(json.dumps({k: result[k] for k in (
                    "scenario", "contract_probes", "model_calls", "outcome", "reader_admitted",
                    "certification")} | {
                    "probe": (result["probe"] or {}).get("source"),
                    "verdict": str(result["verdict"])[:90]}, ensure_ascii=False), flush=True)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n",
                              encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
