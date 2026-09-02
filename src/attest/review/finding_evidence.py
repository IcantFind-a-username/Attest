"""What an author can run (owner item 7, 2026-09-03): a verified finding is
presented as its test -- the exact reproduction bytes, the one-line pytest
command with the node id, the head/base run summaries, the logs, the bundle
path and the offline verification command -- read from the sealed evidence
bundle the certification wrote. Pure file reads; no execution, no model.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

MAX_LOG_CHARS = 6_000


@dataclass(frozen=True)
class RunSummary:
    run_id: str
    outcome: str  # "failed" | "passed"
    exit_code: int | None
    log: str  # bounded stdout tail


@dataclass(frozen=True)
class FindingEvidence:
    candidate_id: str
    test_source: str
    test_node: str
    command: str
    head_runs: tuple[RunSummary, ...]
    base_runs: tuple[RunSummary, ...]
    bundle_path: str
    verify_command: str
    executor_profile: str = ""
    image: str = ""
    extra: dict[str, str] = field(default_factory=dict)

    def summary(self) -> str:
        head = sum(1 for run in self.head_runs if run.outcome == "failed")
        base = sum(1 for run in self.base_runs if run.outcome == "passed")
        return f"head FAIL {head}/{len(self.head_runs)}, base PASS {base}/{len(self.base_runs)}"


def _bounded(text: str) -> str:
    if len(text) <= MAX_LOG_CHARS:
        return text
    return "[...truncated...]\n" + text[-MAX_LOG_CHARS:]


def _runs(bundle: Path, run_ids: list[str]) -> tuple[RunSummary, ...]:
    out = []
    for run_id in run_ids:
        record_path = bundle / "runs" / run_id / "run.json"
        try:
            record = json.loads(record_path.read_bytes())
            log = (bundle / "runs" / run_id / "stdout.txt").read_text(
                encoding="utf-8", errors="replace"
            )
        except (OSError, ValueError):
            continue
        out.append(
            RunSummary(
                run_id=run_id,
                outcome=str(record.get("outcome", "")),
                exit_code=record.get("exit_code"),
                log=_bounded(log),
            )
        )
    return tuple(out)


def evidence_from_bundle(bundle: Path, *, repo: Path | None = None) -> FindingEvidence | None:
    """The runnable presentation of one accepted bundle; None when unreadable."""
    try:
        receipt = json.loads((bundle / "receipt.json").read_bytes())
        source = (bundle / "test_repro.py").read_text(encoding="utf-8")
    except (OSError, ValueError):
        return None
    node = str(receipt.get("test_node") or "test_repro.py")
    head_ids = [str(run["run_id"]) for run in receipt.get("head_runs", [])]
    base_ids = [str(run["run_id"]) for run in receipt.get("base_runs", [])]
    shown = bundle
    if repo is not None:
        try:
            shown = bundle.relative_to(repo)
        except ValueError:
            shown = bundle
    profile = str(receipt.get("executor_profile") or "")
    return FindingEvidence(
        candidate_id=str(receipt.get("candidate_id") or ""),
        test_source=source,
        test_node=node,
        command=f"pytest -q {node}",
        head_runs=_runs(bundle, head_ids),
        base_runs=_runs(bundle, base_ids),
        bundle_path=str(shown),
        verify_command=f"attest verify --bundle {shown} --require-seal",
        executor_profile=profile,
    )


def render_markdown(evidence: FindingEvidence) -> str:
    """The GitHub-flavoured block appended to a verified finding."""
    head = "\n".join(
        f"- {run.run_id}: {run.outcome} (exit {run.exit_code})" for run in evidence.head_runs
    )
    base = "\n".join(
        f"- {run.run_id}: {run.outcome} (exit {run.exit_code})" for run in evidence.base_runs
    )
    logs = "\n\n".join(
        f"**{run.run_id}**\n\n```text\n{run.log}\n```"
        for run in (*evidence.head_runs, *evidence.base_runs)
        if run.log.strip()
    )
    return (
        "Run it yourself: save the test as `test_repro.py` in the repository root and run\n\n"
        f"```bash\n{evidence.command}\n```\n\n"
        f"```python\n{evidence.test_source.rstrip()}\n```\n\n"
        f"Runs: {evidence.summary()}\n\nhead:\n{head}\n\nbase (merge-base):\n{base}\n\n"
        f"<details>\n<summary>Full logs</summary>\n\n{logs}\n\n</details>\n\n"
        f"Evidence bundle: `{evidence.bundle_path}` — verify offline with "
        f"`{evidence.verify_command}`."
    )


def render_text(evidence: FindingEvidence, indent: str = "     ") -> str:
    """The terminal block for the CLI report."""
    lines = [
        f"{indent}run it:      {evidence.command}",
        f"{indent}test:",
    ]
    lines.extend(f"{indent}  {line}" for line in evidence.test_source.rstrip().splitlines())
    lines.append(f"{indent}runs:        {evidence.summary()}")
    lines.append(f"{indent}bundle:      {evidence.bundle_path}")
    lines.append(f"{indent}verify:      {evidence.verify_command}")
    return "\n".join(lines)
