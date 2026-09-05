"""G-SEM-002 binding pilot (owner answer 2, 2026-09-03): the changed-line binding policy on
the held-out generated tests plus constructed adversarial tests, in the container backend.

For every held-out regression case with a generated test on record (the latest task's
reproduction under .attest/repro/<task>/<finding>/head-1/test_repro.py), the test is re-run
through execute_differential with the container adapter and the binding verdict is
recorded. Ten adversarial tests are constructed for the first ten regression cases with a
generated test: (a) a source-text test (reads the anchored file and asserts the base text,
never executing a changed line), (b) an unrelated known failure on both trees. The report is
the reject/allow matrix by class. No model call is made.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path("/Users/franz/Documents/Attest")
sys.path.insert(0, str(ROOT / "src"))
CASES = ROOT / ".attest" / "corpora" / "swebench" / "cases"
RESULTS = ROOT / ".attest" / "corpora" / "swebench" / "results"

from attest.execution.backends import select_backend  # noqa: E402
from attest.review.candidates import CandidateStore  # noqa: E402
from attest.review.executor import ExecutorLimits, ReproSpec, execute_differential  # noqa: E402
from attest.review.workdir import WORK_PREFIX, repo_key, work_parent  # noqa: E402


def latest_generated(case: Path, task_id: str) -> tuple[str, str, str] | None:
    """(finding_id, test source, anchored file) of the latest generated test for the task."""
    # D-138: the reproduction working directory left the repository tree. This
    # pilot reads what an *earlier* process wrote, and that process's session
    # directory is not this one's, so the legacy in-repo path is tried first and
    # every session root under the temporary directory after it.
    candidates = [case / "repo" / ".attest" / "repro" / task_id]
    key = repo_key(case / "repo")
    candidates += sorted(work_parent().glob(f"{WORK_PREFIX}-*/{key}/repro/{task_id}"))
    repro = next((path for path in candidates if path.is_dir()), None)
    if repro is None:
        return None
    store = CandidateStore(case / "repo")
    for finding_dir in sorted(repro.iterdir()):
        test = finding_dir / "head-1" / "test_repro.py"
        if not test.is_file():
            continue
        stored = store.latest(finding_dir.name, task_id)
        if stored is None:
            continue
        return finding_dir.name, test.read_text(encoding="utf-8"), stored.finding.file
    return None


def adversarial_source_text(anchored: str, base_text: str) -> str:
    return (
        "from pathlib import Path\n\n"
        "def test_repro():\n"
        f"    text = Path({anchored!r}).read_text(encoding='utf-8', errors='replace')\n"
        f"    assert text == {base_text!r}\n"
    )


ADVERSARIAL_UNRELATED = "def test_repro():\n    assert 1 == 2\n"


def main() -> int:
    rows = []
    adversarial_budget = 10
    for path in sorted(RESULTS.glob("*.heldout.json")):
        summary = json.loads(path.read_text())
        if summary["control"]:
            continue
        case = CASES / summary["case"]
        manifest = json.loads((case / "manifest.json").read_text())
        found = latest_generated(case, summary["task_id"])
        if found is None:
            rows.append({"case": summary["case"], "class": "no generated test", "verdict": "-"})
            continue
        finding_id, source, anchored = found
        repo = case / "repo"
        store = CandidateStore(repo)
        stored = store.latest(finding_id, summary["task_id"])
        backend = select_backend(repo, production=True)
        if backend.adapter is None:
            rows.append(
                {"case": summary["case"], "class": "backend unavailable", "verdict": backend.reason}
            )
            continue
        specs = [("generated", source)]
        if adversarial_budget > 0:
            base_text = subprocess.run(
                ["git", "-C", str(repo), "show", f"{manifest['base_sha']}:{anchored}"],
                capture_output=True,
                text=True,
            ).stdout
            specs.append(("adversarial: source text", adversarial_source_text(anchored, base_text)))
            specs.append(("adversarial: unrelated failure", ADVERSARIAL_UNRELATED))
            adversarial_budget -= 1
        for label, body in specs:
            result = execute_differential(
                repo,
                stored,
                ReproSpec(body),
                ExecutorLimits(wall_timeout_s=120.0),
                base_sha=manifest["base_sha"],
                head_sha=manifest["head_sha"],
                adapter=backend.adapter,
            )
            binding = result.binding
            rows.append(
                {
                    "case": summary["case"],
                    "class": label,
                    "outcome": result.outcome.value,
                    "evidence_class": result.evidence_class.value,
                    "reason": result.reason[:120],
                    "changed_lines": len(binding.changed_lines) if binding else None,
                    "executed_changed_lines": len(binding.executed_changed_lines)
                    if binding
                    else None,
                    "bound": bool(binding and binding.executed_changed_lines),
                }
            )
            print(json.dumps(rows[-1]), flush=True)
    out = ROOT / ".attest" / "corpora" / "swebench" / "results" / "binding-pilot.json"
    out.write_text(json.dumps(rows, indent=2))
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
