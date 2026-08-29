"""End-to-end CLI runs on real repositories, with the proposer replayed.

No API key is used. The proposer is fed a payload built from what git history
says the real defect was, i.e. an ORACLE proposer that finds the true bug with
full K-sample consensus. That deliberately removes the model from the question
and asks the one the model cannot answer: given a perfect proposal on a real
diff in a real checkout, what does the evidence gate actually do?

The mirror run feeds an equally confident FALSE claim anchored on a real clean
commit, so the two paths can be compared under identical channel evidence.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

from realdata.corpus import Case, build_cases


def _run(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )


def stage_case(repo: Path, case: Case, dest: Path) -> Path:
    """Real checkout at the fixed commit, with the bug put back in the worktree.

    A worktree, not a clone: these repositories are partial (blob:none) clones,
    and a clone of a partial clone loses the promisor remote, so any blob not
    already local becomes unreadable.
    """
    if dest.exists():
        _run(["git", "worktree", "remove", "--force", str(dest)], cwd=repo)
        shutil.rmtree(dest, ignore_errors=True)
    base = case.fix_sha if case.label == "positive" else case.parent_sha
    out = _run(["git", "worktree", "add", "--quiet", "--detach", str(dest), base], cwd=repo)
    if out.returncode != 0:
        raise RuntimeError(out.stderr[:400])
    patch = dest / ".patch"
    patch.write_text(case.diff_text, encoding="utf-8")
    applied = _run(["git", "apply", str(patch)], cwd=dest)
    patch.unlink()
    if applied.returncode != 0:
        raise RuntimeError(f"git apply failed: {applied.stderr[:300]}")
    return dest


def payload_for(case: Case, line: int, claim: str, scenario: str, plan: str) -> str:
    return json.dumps(
        {
            "findings": [
                {
                    "claim": claim,
                    "anchor": {"file": case.path, "line": line},
                    "failure_scenario": scenario,
                    "falsification_plan": plan,
                }
            ]
        }
    )


def attest(args: list[str], repo: Path, venv: Path) -> subprocess.CompletedProcess[str]:
    return _run([str(venv / "bin" / "python"), "-m", "attest.cli.main", "--repo", str(repo), *args])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--venv", default=".venv")
    args = ap.parse_args()

    repo, work, venv = Path(args.repo), Path(args.work), Path(args.venv).resolve()
    work.mkdir(parents=True, exist_ok=True)
    cases = build_cases(repo, per_class=25)
    # prefer a fix whose message names a real runtime failure over a metadata tweak
    hard = re.compile(r"crash|traceback|exception|error|infinite|hang|corrupt", re.IGNORECASE)
    pos_all = [c for c in cases if c.label == "positive" and c.true_lines]
    pos = next((c for c in pos_all if hard.search(c.subject)), None) or next(iter(pos_all), None)
    neg = next((c for c in cases if c.label == "negative" and c.true_lines), None)
    if pos is None or neg is None:
        print("no suitable pair found in this repository", file=sys.stderr)
        raise SystemExit(1)

    for case, kind, claim in (
        (pos, "true-bug", "Defect a later commit had to fix: " + case_subject(pos)),
        (neg, "false-alarm", "This line dereferences a value that can be None at runtime."),
    ):
        tree = stage_case(repo, case, work / kind)
        pay = work / f"{kind}.json"
        pay.write_text(
            payload_for(
                case,
                case.true_lines[0],
                claim,
                "Reached on the code path this change introduces.",
                "Run the project's test suite against this revision and watch this line.",
            ),
            encoding="utf-8",
        )
        print(f"\n=== {kind}: {case.repo} {case.fix_sha[:8]} {case.path}:{case.true_lines[0]}")
        print(f"    history says: {case.subject}")
        res = attest(["review", "--mock", str(pay)], tree, venv)
        print(res.stdout.strip() or res.stderr.strip())

        cand = tree / ".attest" / "candidates.jsonl"
        if not cand.is_file():
            continue
        rows = [json.loads(x) for x in cand.read_text(encoding="utf-8").splitlines() if x.strip()]
        for row in rows:
            ver = attest(["verify", row["finding_id"], "--reproduced"], tree, venv)
            print("    after V (reproduced): " + ver.stdout.strip().replace("\n", "\n    "))


def case_subject(case: Case) -> str:
    return case.subject.rstrip(".")


if __name__ == "__main__":
    main()
