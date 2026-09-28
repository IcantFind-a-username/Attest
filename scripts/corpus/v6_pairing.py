"""Pair the shipped intent rule (`attest.intent.v5.1`) against the experimental
`attest.intent.v6` (D-252) on the same evidence, offline and free.

    forty     every frozen-probe replay record (`frozen_probe_replay.py run`): the
              observation is re-made under v5.1 and under v6 from the recorded test
              body and head-run details, on worktrees of the case's base and head,
              and the two verdicts stand side by side with every contract v6 found
    controls  every real-PR value line whose note carries its probe (D-241, the v4
              notes of batch 3): the replay body is rebuilt from the note, and the
              same pairing is made on the pull request's own base and head -- these
              are merged pull requests the owner adjudicated as true and not
              defects, so a v6 admission here is a false publication and is said so

    .venv/bin/python scripts/corpus/v6_pairing.py forty [--arm C]
    .venv/bin/python scripts/corpus/v6_pairing.py controls
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "corpus"))

from evidence_supply import _read_jsonl  # noqa: E402
from mutation_recall import WORK  # noqa: E402

from attest.certification.intent import (  # noqa: E402
    INTENT_POLICY_V6,
    INTENT_POLICY_VERSION,
    intent_verdict,
)
from attest.review.intent import RaiseOrigin, observe_intent  # noqa: E402
from attest.review.probe import Observation, ProbeSpec, replay_test_body  # noqa: E402

REPLAY = ROOT / "docs" / "acceptance" / "evidence" / "2026-09-15-frozen-probe-replay"
OUT = ROOT / "docs" / "acceptance" / "evidence" / "2026-09-15-v6-pairing"
EVIDENCE = ROOT / "docs" / "acceptance" / "evidence"
STUDIES = ROOT / "benchmarks" / "studies"
# every real-PR batch that produced a value line: (its ledgers, its study)
BATCHES = (
    (EVIDENCE / "2026-09-12-lines-on-real-prs" / "run-b", STUDIES / "e05-external-v1"),
    (EVIDENCE / "2026-09-13-lines-on-real-prs-batch2" / "run-c", STUDIES / "e05-external-v2"),
    (EVIDENCE / "2026-09-14-lines-on-real-prs-batch3" / "run-d", STUDIES / "e05-external-v3"),
)
CONTROLS = ROOT / ".attest" / "corpora" / "e05-controls"
POLICIES = (INTENT_POLICY_VERSION, INTENT_POLICY_V6)


def _git(repo: Path, *args: str) -> str:
    done = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if done.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {done.stderr.strip()[:200]}")
    return done.stdout


class _Trees:
    """Detached worktrees of one repository's base and head, removed on exit."""

    def __init__(self, repo: Path, base_sha: str, head_sha: str) -> None:
        self.repo = repo
        self.root = Path(tempfile.mkdtemp(prefix="v6-pairing-"))
        self.base = self.root / "base"
        self.head = self.root / "head"
        _git(repo, "worktree", "add", "-q", "--detach", str(self.base), base_sha)
        _git(repo, "worktree", "add", "-q", "--detach", str(self.head), head_sha)

    def close(self) -> None:
        for tree in (self.base, self.head):
            subprocess.run(["git", "-C", str(self.repo), "worktree", "remove", "--force",
                            str(tree)], capture_output=True)
        subprocess.run(["rm", "-rf", str(self.root)], capture_output=True)


def _origins(runs: list[dict]) -> list[tuple[RaiseOrigin, ...]]:
    out = []
    for run in runs:
        origins = []
        for o in run.get("raise_origins") or ():
            fields = dict(o)
            fields["values"] = tuple(fields.get("values") or ())
            fields["path"] = tuple(fields.get("path") or ())
            origins.append(RaiseOrigin(**fields))
        out.append(tuple(origins))
    return out


def _judge(
    *,
    trees: _Trees,
    path: str,
    changed_lines: tuple[int, ...],
    added_lines: tuple[int, ...] | None,
    test_body: str,
    head_runs: list[dict],
    changed_files: tuple[str, ...],
) -> dict:
    head_source = (trees.head / path).read_text(encoding="utf-8", errors="replace")
    base_source = (trees.base / path).read_text(encoding="utf-8", errors="replace")
    verdicts: dict = {}
    for policy in POLICIES:
        observed = observe_intent(
            path=path,
            changed_lines=changed_lines,
            added_lines=added_lines,
            head_source=head_source,
            base_source=base_source,
            test_source=test_body,
            head_origins=_origins(head_runs),
            head_failures=[str(r.get("failure_message") or "") for r in head_runs],
            head_failure_details=[str(r.get("failure_detail") or "") for r in head_runs],
            changed_files=changed_files,
            truncated=any(bool(r.get("raise_origins_truncated")) for r in head_runs),
            base_tree=trees.base,
            head_tree=trees.head,
            policy_version=policy,
        )
        if isinstance(observed, str):
            verdicts[policy] = {"verdict": f"not observable: {observed}", "publishes": False}
            continue
        verdict = intent_verdict(observed)
        entry: dict = {
            "verdict": verdict or "publishes",
            "publishes": verdict is None,
            "pinned": list(observed.pinned_values),
            "specified": [list(s) for s in observed.value_specified],
            "anchored_symbols": list(observed.anchored_symbols),
        }
        if policy == INTENT_POLICY_V6:
            entry["contracts"] = [asdict(c) for c in observed.contracts]
        verdicts[policy] = entry
    return verdicts


def _transition(verdicts: dict) -> str:
    old = verdicts[INTENT_POLICY_VERSION]["publishes"]
    new = verdicts[INTENT_POLICY_V6]["publishes"]
    if old and new:
        return "unchanged: publishes"
    if not old and not new:
        return "unchanged: drawer"
    return "gained" if new else "lost"


def cmd_forty(args: argparse.Namespace) -> int:
    records = _read_jsonl(REPLAY / f"replay-arm-{args.arm}.jsonl")
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for record in records:
        unit_id = record["unit_id"]
        row: dict = {"unit_id": unit_id, "stratum": record.get("stratum"),
                     "recorded": record.get("recorded", {}).get("class"),
                     "replay": record.get("outcome"), "replay_reason": record.get("reason", "")}
        intent = record.get("intent")
        if "skipped" in record or not intent or not record.get("test_body"):
            row["pairing"] = "not paired: " + str(record.get("skipped") or "no intent observation")
            rows.append(row)
            print(json.dumps({"unit_id": unit_id, "pairing": row["pairing"]}), flush=True)
            continue
        manifest = json.loads((WORK / "cases" / unit_id / "manifest.json").read_text())
        repo = Path(manifest["repo_path"])
        trees = _Trees(repo, manifest["base_sha"], manifest["head_sha"])
        try:
            verdicts = _judge(
                trees=trees, path=intent["path"],
                changed_lines=tuple(intent.get("changed_lines") or ()),
                added_lines=_added_lines(intent),
                test_body=record["test_body"], head_runs=record.get("head_runs") or [],
                changed_files=(intent["path"],),
            )
        finally:
            trees.close()
        row.update({"verdicts": verdicts, "pairing": _transition(verdicts)})
        # the re-made v5.1 verdict must agree with the replay's own reason
        replay_publishes = record.get("outcome") == "reproduced"
        row["v51_agrees_with_replay"] = (
            verdicts[INTENT_POLICY_VERSION]["publishes"] == replay_publishes
        )
        rows.append(row)
        print(json.dumps({"unit_id": unit_id, "pairing": row["pairing"],
                          "v6": verdicts[INTENT_POLICY_V6]["verdict"][:100],
                          "contracts": len(verdicts[INTENT_POLICY_V6].get("contracts", []))},
                         ensure_ascii=False), flush=True)
    (OUT / f"forty-arm-{args.arm}.json").write_text(
        json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    _summary(rows, "forty")
    return 0


def cmd_forty_static(args: argparse.Namespace) -> int:
    """The forty paired from the arm's own ledger, without re-executing anything:
    the frozen probe and its recorded base observation rebuild the replay body,
    the recorded intent observation supplies the hunk, and both rules judge the
    case's rebuilt trees. What the container replay adds is the fresh receipt;
    what this adds is the rule pairing today, at $0.00 and without a daemon."""
    from frozen_probe_replay import ARMS, frozen_probe
    from mutation_recall import STUDY, classify

    arm_dir = ARMS / f"arm-{args.arm}"
    trials = {r["unit_id"]: r for r in _read_jsonl(arm_dir / f"trials-arm-{args.arm}.jsonl")}
    ledgers: dict[str, list[dict]] = {}
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for row in _read_jsonl(STUDY / "sample.jsonl"):
        unit_id, library = str(row["unit_id"]), str(row["library"])
        site = (str(row["mutation"]["path"]), int(row["mutation"]["line"]))
        out: dict = {"unit_id": unit_id, "stratum": row["stratum"], "site": f"{site[0]}:{site[1]}"}
        trial = trials.get(unit_id)
        if trial is None:
            out["pairing"] = "not paired: no trial"
            rows.append(out)
            continue
        if library not in ledgers:
            ledgers[library] = _read_jsonl(arm_dir / f"{library}-ledger.jsonl")
        mine = [r for r in ledgers[library] if r.get("task_id") == trial["task_id"]]
        klass, why = classify(mine, str(trial.get("deferred_reason") or ""), site=site)
        out["recorded"] = {"class": klass, "reason": why[:200]}
        probe_row, reason = frozen_probe(mine)
        if probe_row is None:
            out["pairing"] = f"not paired: {reason}"
            rows.append(out)
            continue
        verification = next(
            (r for r in mine if r.get("kind") == "verification"
             and r.get("finding_id") == probe_row.get("finding_id")
             and isinstance(r.get("intent"), dict) and r["intent"].get("policy_version")),
            None,
        )
        if verification is None:
            out["pairing"] = "not paired: no intent observation for the frozen probe"
            rows.append(out)
            continue
        intent = verification["intent"]
        out["probe"] = probe_row.get("expression")
        if intent.get("new_rejection"):
            out["pairing"] = "not paired: a rejection row (the value rule never reads it)"
            rows.append(out)
            continue
        spec = ProbeSpec(imports=str(probe_row.get("imports") or ""),
                         setup=str(probe_row.get("setup") or ""),
                         expression=str(probe_row.get("expression") or ""))
        observation = Observation(kind=str(probe_row.get("observed_kind")),
                                  detail=str(probe_row.get("observed_detail")))
        body = replay_test_body(spec, observation)
        head_runs = _synthesised_head_runs(body, intent)
        manifest = json.loads((WORK / "cases" / unit_id / "manifest.json").read_text())
        trees = _Trees(Path(manifest["repo_path"]), manifest["base_sha"], manifest["head_sha"])
        try:
            verdicts = _judge(
                trees=trees, path=str(intent["path"]),
                changed_lines=tuple(intent.get("changed_lines") or ()),
                added_lines=_added_lines(intent),
                test_body=body, head_runs=head_runs, changed_files=(str(intent["path"]),),
            )
        finally:
            trees.close()
        out.update({"verdicts": verdicts, "pairing": _transition(verdicts)})
        recorded_publishes = klass == "certified"
        out["v51_now_vs_recorded"] = (
            "same" if verdicts[INTENT_POLICY_VERSION]["publishes"] == recorded_publishes
            else ("publishes now (D-249)" if verdicts[INTENT_POLICY_VERSION]["publishes"]
                  else "drawer now")
        )
        rows.append(out)
        print(json.dumps({"unit_id": unit_id, "recorded": klass,
                          "v51_now": out["v51_now_vs_recorded"], "pairing": out["pairing"],
                          "v6": verdicts[INTENT_POLICY_V6]["verdict"][:90],
                          "contracts": len(verdicts[INTENT_POLICY_V6].get("contracts", []))},
                         ensure_ascii=False), flush=True)
    (OUT / f"forty-static-arm-{args.arm}.json").write_text(
        json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    _summary(rows, "forty-static")
    return 0


def _synthesised_head_runs(body: str, intent: dict) -> list[dict]:
    """Three head runs as the recorded intent observation describes them: a value
    mismatch failed on the replay's assertion; a crash failed with the recorded
    exception from the recorded frame, which the frame rule then reads as it
    was read the first time."""
    if intent.get("value_mismatch"):
        assert_line = max(i + 1 for i, line in enumerate(body.splitlines())
                          if line.lstrip().startswith("assert "))
        longrepr = (f"    def test_attest_replay():\n>       assert ...\n"
                    f"E       AssertionError\n\n.attest-repro/test_repro.py:{assert_line}: "
                    "AssertionError")
        return [{"failure_message": "AssertionError", "failure_detail": longrepr,
                 "raise_origins": []} for _ in range(3)]
    exception = str(intent.get("exception_type") or "Exception")
    origins = []
    if int(intent.get("origin_line") or 0) > 0:
        origins.append({"line": int(intent["origin_line"]), "function": "",
                        "exception_type": exception, "message": "", "values": [],
                        "escaped": True, "path": list(intent.get("path_lines") or ())})
    return [{"failure_message": exception, "failure_detail": "", "raise_origins": origins}
            for _ in range(3)]


def _added_lines(intent: dict) -> tuple[int, ...] | None:
    """The lines the change wrote, as recorded: an empty record is a deletion
    that wrote nothing, and is not the same as no record at all (v4 and
    earlier), where the hunk range stands in."""
    if "added_lines" not in intent:
        return None
    return tuple(int(n) for n in intent.get("added_lines") or ())


def _summary(rows: list[dict], name: str) -> None:
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["pairing"]] = counts.get(r["pairing"], 0) + 1
    print(json.dumps({name: counts}, indent=2))


def cmd_controls(_args: argparse.Namespace) -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for batch_dir, study in BATCHES:
        trials = {r["task_id"]: r for f in study.glob("trials*.jsonl") for r in _read_jsonl(f)}
        sample = {r["unit_id"]: r for r in _read_jsonl(study / "sample.jsonl")}
        for ledger in sorted(batch_dir.glob("*-ledger.jsonl")):
            rows.extend(_control_rows(ledger, trials, sample))
    (OUT / "controls.json").write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n",
                                       encoding="utf-8")
    _summary(rows, "controls")
    return 0


def _control_rows(ledger: Path, trials: dict, sample: dict) -> list[dict]:
    """The pairing for every value note of one ledger: rebuilt from the note's
    own probe (D-241) when it carries one, named as not paired otherwise."""
    library = ledger.name.replace("-ledger.jsonl", "")
    entries = _read_jsonl(ledger)
    rows: list[dict] = []
    for note in (e for e in entries if e.get("kind") == "value_observation_note"):
        row: dict = {"library": library, "batch": ledger.parent.parent.name,
                     "note": note.get("note_id"), "path": note.get("path"),
                     "line": note.get("line"), "expression": note.get("expression"),
                     "pinned": note.get("pinned_values")}
        trial = trials.get(note.get("task_id"))
        unit = sample.get(trial["unit_id"]) if trial else None
        row["pull_request"] = trial["unit_id"] if trial else "?"
        if not note.get("pinned_values"):
            row["pairing"] = "not paired: a rejection row (the value rule never reads it)"
            rows.append(row)
            continue
        if not note.get("imports") and not note.get("setup"):
            row["pairing"] = "not paired: the note carries no probe (before D-241)"
            rows.append(row)
            continue
        if unit is None:
            row["pairing"] = "not paired: no sample row for the task"
            rows.append(row)
            continue
        verification = next(
            (e for e in entries if e.get("kind") == "verification"
             and e.get("finding_id") == note.get("finding_id")
             and e.get("task_id") == note.get("task_id")),
            None,
        )
        intent = (verification or {}).get("intent") or {}
        spec = ProbeSpec(imports=str(note.get("imports") or ""),
                         setup=str(note.get("setup") or ""),
                         expression=str(note.get("expression") or ""))
        observation = Observation(kind=str(note.get("base_kind")),
                                  detail=str(note.get("base_detail")))
        body = replay_test_body(spec, observation)
        assert_line = max(i + 1 for i, line in enumerate(body.splitlines())
                          if line.lstrip().startswith("assert "))
        longrepr = (f"    def test_attest_replay():\n>       assert ...\n"
                    f"E       AssertionError\n\n.attest-repro/test_repro.py:{assert_line}: "
                    "AssertionError")
        head_runs = [{"failure_message": "AssertionError", "failure_detail": longrepr,
                      "raise_origins": []} for _ in range(3)]
        repo = CONTROLS / library / "repo"
        if not (repo / ".git").is_dir():
            repo = WORK / library / "repo"  # the eight libraries the forty also use
        trees = _Trees(repo, unit["base_sha"], unit["head_sha"])
        try:
            changed = tuple(intent.get("changed_lines") or ())
            changed_files = tuple(
                line.strip()
                for line in _git(repo, "diff", "--name-only", unit["base_sha"],
                                 unit["head_sha"]).splitlines()
                if line.strip()
            ) or (str(note["path"]),)
            verdicts = _judge(
                trees=trees, path=str(note["path"]), changed_lines=changed,
                added_lines=_added_lines(intent),
                test_body=body, head_runs=head_runs, changed_files=changed_files,
            )
        finally:
            trees.close()
        row.update({"verdicts": verdicts, "pairing": _transition(verdicts)})
        rows.append(row)
        print(json.dumps({"pull_request": row["pull_request"], "note": row["note"],
                          "pairing": row["pairing"],
                          "v6": verdicts[INTENT_POLICY_V6]["verdict"][:100]},
                         ensure_ascii=False), flush=True)
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    f = sub.add_parser("forty")
    f.add_argument("--arm", default="C")
    f.set_defaults(func=cmd_forty)
    fs = sub.add_parser("forty-static")
    fs.add_argument("--arm", default="C")
    fs.set_defaults(func=cmd_forty_static)
    sub.add_parser("controls").set_defaults(func=cmd_controls)
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
