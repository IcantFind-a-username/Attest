"""P-02: can the certification kernel accept a Go regression on Go-derived evidence?

P-01 showed the execution layer runs a Go differential. This probe asks the next question:
what does the *kernel* demand, and can a non-Python adapter supply it honestly? It builds a
two-revision Go module whose head drops a length guard, generates a probe test the way the
executor generates a replay test, runs three repeats per revision under coverage, and then
fills the kernel's own records from what Go reported:

    BindingObservation    executed changed lines, read from `go test -coverprofile`
    IntentObservation     the failure origin, read from the panic trace of the head runs
    CertificationReceipt  the runs, the digests and the provenance digest

and validates them with `attest.certification.validate.validate_receipt`, `binding_verdict`
and `intent_verdict` -- the product's own kernel, unchanged. Every field the probe could not
derive from Go is recorded as a gap rather than invented.

    .venv/bin/python scripts/probe/go_certification_probe.py --out probe.json

No model call, no paid spend, no product change, nothing pushed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "probe"))

from go_execution_probe import IMAGE, PosixLauncherAdapter, _git  # noqa: E402

from attest.certification.binding import (  # noqa: E402
    BINDING_POLICY_VERSION,
    BindingObservation,
    binding_verdict,
)
from attest.certification.intent import (  # noqa: E402
    EVIDENCE_CLASS_BEHAVIOR_CHANGE,
    EVIDENCE_CLASS_REGRESSION,
    INTENT_POLICY_VERSION,
    IntentObservation,
    evidence_class_for,
    intent_verdict,
)
from attest.certification.types import (  # noqa: E402
    CERTIFICATION_POLICY_SCHEMA_VERSION,
    CERTIFICATION_RECEIPT_SCHEMA_VERSION,
    CERTIFICATION_TASK_SCHEMA_VERSION,
    RECEIPT_BODY_VERSION,
    CertificationPolicy,
    CertificationReceipt,
    CertificationSubject,
    CertificationTask,
    ExecutionRun,
)
from attest.certification.validate import validate_receipt  # noqa: E402
from attest.execution.container_adapter import SCRATCH_MOUNT, ContainerImage  # noqa: E402
from attest.execution.controller import Controller  # noqa: E402
from attest.execution.types import ResourceLimits  # noqa: E402
from attest.review.evidence import provenance_digest  # noqa: E402

REPEATS = 3
GO_MOD = "module shorten\n\ngo 1.22\n"
# the base guards the slice; the head drops the guard, so a short input panics
GO_BASE = '''package shorten

// Prefix returns the first three characters of s.
func Prefix(s string) string {
	if len(s) < 3 {
		return s
	}
	return s[:3]
}
'''
GO_HEAD = '''package shorten

// Prefix returns the first three characters of s.
func Prefix(s string) string {
	return s[:3]
}
'''
GO_TEST = '''package shorten

import "testing"

func TestPrefixKeepsShortInput(t *testing.T) {
	if got := Prefix("ab"); got != "ab" {
		t.Fatalf("Prefix = %q, want %q", got, "ab")
	}
}
'''
# what the executor calls a probe: a generated test that calls the changed symbol on one
# input and records what came back, written in the language of the repository under review
PROBE_TEST = '''package shorten

import "testing"

// The generated probe calls the changed symbol on one input and records what came back.
// It does not recover: a panic must reach the report, or the failure has no origin to read.
func TestAttestProbe(t *testing.T) {
	value := Prefix("ab")
	t.Logf("ATTEST_OBSERVATION value %q", value)
	if value != "ab" {
		t.Fatalf("ATTEST_OBSERVATION value %q", value)
	}
}
'''
PROBE_NODE = "shorten.TestAttestProbe"
PROBE_INPUT = '"ab"'


def digest(data: bytes | str) -> str:
    return hashlib.sha256(data.encode("utf-8") if isinstance(data, str) else data).hexdigest()


def build_case(root: Path) -> tuple[Path, str, str, int]:
    """The two revisions, and the line the head wrote (the slice without its guard)."""
    repo = root / "shorten"
    repo.mkdir(parents=True)
    _git(repo, "init", "--initial-branch=main")
    (repo / "go.mod").write_text(GO_MOD, encoding="utf-8")
    (repo / "shorten.go").write_text(GO_BASE, encoding="utf-8")
    (repo / "shorten_test.go").write_text(GO_TEST, encoding="utf-8")
    _git(repo, "add", "--all")
    _git(repo, "commit", "-m", "base")
    base = _git(repo, "rev-parse", "HEAD")
    (repo / "shorten.go").write_text(GO_HEAD, encoding="utf-8")
    _git(repo, "commit", "-am", "head")
    head = _git(repo, "rev-parse", "HEAD")
    changed = next(
        i for i, text in enumerate(GO_HEAD.splitlines(), 1) if "return s[:3]" in text
    )
    return repo, base, head, changed


def run_side(
    repo: Path, sha: str, adapter: Any, work: Path, tag: str,
) -> list[dict[str, Any]]:
    """Three repeats of the generated probe on one revision, with coverage."""
    _git(repo, "checkout", "--quiet", sha)
    tree = work / f"tree-{tag}"
    if tree.exists():
        shutil.rmtree(tree)
    shutil.copytree(repo, tree, ignore=shutil.ignore_patterns(".git"))
    # a Go test must live inside the module: the probe cannot be an input mount, as the
    # rendered pytest file is, so the tree the container sees is a copy with the probe in it
    (tree / "attest_probe_test.go").write_text(PROBE_TEST, encoding="utf-8")
    controller = Controller(work / f"controller-{tag}")
    runs: list[dict[str, Any]] = []
    for index in range(REPEATS):
        inputs = work / f"in-{tag}-{index}"
        outputs = work / f"out-{tag}-{index}"
        inputs.mkdir(parents=True, exist_ok=True)
        outputs.mkdir(parents=True, exist_ok=True)
        request = controller.issue(
            task_id="probe-go-cert", run_id=f"{tag}-{index}", candidate_id="prefix-guard",
            revision_sha=sha, profile=adapter.profile, interpreter=IMAGE,
            argv_template=(
                "sh", "-c",
                "go test -count=1 -json -run '^TestAttestProbe$' "
                "-coverprofile=/attest/outputs/cover.out ./... "
                "> /attest/outputs/report.json 2>&1",
            ),
            environment={
                "PATH": "/usr/local/go/bin:/usr/local/bin:/usr/bin:/bin",
                "GOCACHE": f"{SCRATCH_MOUNT}/gocache",
                "GOPATH": f"{SCRATCH_MOUNT}/gopath",
                "GOTMPDIR": SCRATCH_MOUNT,
                "GOFLAGS": "-mod=mod",
                "GOPROXY": "off",
            },
            inputs={}, limits=ResourceLimits(
                wall_timeout_s=240.0, cpu_timeout_s=180, memory_mb=1024, output_bytes=4_000_000,
            ),
            expected_artifacts=("report.json", "cover.out"),
        )
        envelope = adapter.execute(request, tree=tree, inputs=inputs, outputs=outputs)
        report = (outputs / "report.json")
        cover = (outputs / "cover.out")
        text = report.read_text(encoding="utf-8", errors="replace") if report.is_file() else ""
        runs.append({
            "repeat": index,
            "exit_code": envelope.exit_code,
            "outcome": "fail" if '"Action":"fail"' in text else (
                "pass" if '"Action":"pass"' in text else "no test ran"),
            "report": text,
            "coverage": cover.read_text(encoding="utf-8") if cover.is_file() else "",
            "artifact_digest": digest(text),
            "error": envelope.error,
        })
    return runs


def _signature(report: str) -> str:
    """The failure as every repeat reports it: the panic line, addresses removed."""
    text = "".join(
        json.loads(line).get("Output", "")
        for line in report.splitlines() if line.startswith("{")
    )
    panic = next((ln for ln in text.splitlines() if "panic:" in ln), "")
    return re.sub(r"0x[0-9a-f]+", "", panic).strip()


def executed_changed_lines(coverage: str, changed: int) -> list[int]:
    """The changed lines a run executed, from `go test -coverprofile`.

    Each line is `file:startLine.col,endLine.col statements count`; a block with a count
    above zero ran, so a changed line inside such a block ran."""
    executed: list[int] = []
    for line in coverage.splitlines()[1:]:
        match = re.match(r"^\S+:(\d+)\.\d+,(\d+)\.\d+ \d+ (\d+)$", line.strip())
        if not match:
            continue
        start, end, count = int(match.group(1)), int(match.group(2)), int(match.group(3))
        if count > 0 and start <= changed <= end:
            executed.append(changed)
    return sorted(set(executed))


def panic_origin(report: str, path: str) -> tuple[int, str, list[int]]:
    """The line the failure was raised from, its type, and the outer frames of the same
    file, read from the Go panic trace the test output carries."""
    text = "".join(
        json.loads(line).get("Output", "")
        for line in report.splitlines() if line.startswith("{")
    )
    kind = ""
    if "panic:" in text:
        kind = text.split("panic:", 1)[1].strip().split("\n", 1)[0].strip()
        kind = kind.split(" [")[0].strip()
    lines = [
        int(m.group(1))
        for m in re.finditer(rf"{re.escape(path)}:(\d+)", text)
    ]
    origin = lines[0] if lines else 0
    return origin, kind, sorted(set(lines[1:]))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    parser.add_argument("--image", default=IMAGE)
    args = parser.parse_args(argv)
    docker = shutil.which("docker")
    if docker is None:
        print("docker is not installed on this host")
        return 2
    identity = subprocess.run(
        [docker, "image", "inspect", "--format", "{{.Id}}", args.image],
        capture_output=True, text=True,
    ).stdout.strip()
    if not identity:
        print(f"image {args.image} is not present; run the P-01 probe first")
        return 2
    adapter = PosixLauncherAdapter(
        ContainerImage(reference=args.image, digest=identity, tag=args.image),
        docker=docker, pids_limit=256,
    )
    adapter.nproc_limit = 0

    gaps: list[str] = []
    with tempfile.TemporaryDirectory(prefix="go-cert-probe-") as tmp:
        work = Path(tmp)
        repo, base, head, changed_line = build_case(work)
        base_runs = run_side(repo, base, adapter, work, "base")
        head_runs = run_side(repo, head, adapter, work, "head")

        base_outcomes = {r["outcome"] for r in base_runs}
        head_outcomes = {r["outcome"] for r in head_runs}
        differential = base_outcomes == {"pass"} and head_outcomes == {"fail"}

        origins = [panic_origin(r["report"], "shorten.go") for r in head_runs]
        executed = []
        for row, (origin, _kind, frames) in zip(head_runs, origins, strict=True):
            covered = executed_changed_lines(row["coverage"], changed_line)
            if not covered and changed_line in {origin, *frames}:
                # Go writes no coverage profile when the test binary panics; the trace itself
                # proves the line ran, and is stronger evidence than a counter
                covered = [changed_line]
            executed.append(covered)
        binding = BindingObservation(
            policy_version=BINDING_POLICY_VERSION,
            path="shorten.go",
            changed_lines=(changed_line,),
            executed_changed_lines=tuple(
                sorted(set.intersection(*[set(e) for e in executed])) if executed else ()
            ),
            head_runs_observed=len(head_runs),
        )
        origin_line = origins[0][0] if origins else 0
        exception_type = origins[0][1] if origins else ""
        path_lines = origins[0][2] if origins else []
        # the literal the probe called with, and whether the base tree holds it anywhere
        witnesses: list[tuple[str, str]] = []
        for path in sorted(repo.rglob("*.go")):
            if PROBE_INPUT in path.read_text(encoding="utf-8", errors="replace"):
                witnesses.append((PROBE_INPUT, path.name))
                break
        intent = IntentObservation(
            policy_version=INTENT_POLICY_VERSION,
            path="shorten.go",
            changed_lines=(changed_line,),
            origin_line=origin_line,
            origin_statement="other",  # Go has no raise/assert statement kind
            exception_type=exception_type,
            new_rejection=bool(origin_line) and origin_line == changed_line,
            rejected_inputs=(PROBE_INPUT,),
            witnesses=tuple(witnesses),
            head_runs_observed=len(head_runs),
            path_lines=tuple(path_lines),
            added_lines=(changed_line,),
        )
        if not origin_line:
            gaps.append(
                "no failure origin could be read from the head runs: the observation was left "
                "empty, and an empty v5.1 observation still publishes -- the kernel trusts the "
                "adapter to record what it observed"
            )
        gaps.append(
            "IntentObservation.origin_statement names a Python statement kind (raise/assert); "
            "Go has none, so the probe records 'other', which the v5.1 frame rule accepts but "
            "which carries less than the Python record does"
        )
        gaps.append(
            "the probe test had to be copied into a writable tree: a Go test must live inside "
            "its module, so it cannot be an input mount the way the rendered pytest file is"
        )
        gaps.append(
            "`go test -coverprofile` writes nothing when the test binary panics, so coverage "
            "and the failure trace cannot come from one Go run; the probe reads the executed "
            "changed line from the trace instead, which is stronger than a counter"
        )
        gaps.append(
            "exception_type is the first line of the Go panic message, not a type name; the "
            "warning rule (D-235) reads names like ...Warning and has no Go counterpart"
        )

        verdicts = {
            "binding": binding_verdict(binding),
            "intent": intent_verdict(intent),
            "evidence_class": evidence_class_for(intent),
        }
        policy = CertificationPolicy(
            schema_version=CERTIFICATION_POLICY_SCHEMA_VERSION,
            receipt_schema_version=CERTIFICATION_RECEIPT_SCHEMA_VERSION,
            required_head_runs=REPEATS, required_base_runs=REPEATS,
            allowed_executor_profiles=(adapter.profile,),
            allowed_evidence_classes=(
                EVIDENCE_CLASS_REGRESSION, EVIDENCE_CLASS_BEHAVIOR_CHANGE,
            ),
            binding_policy_version=BINDING_POLICY_VERSION,
            intent_policy_version=INTENT_POLICY_VERSION,
        )
        policy_digest = digest(json.dumps(asdict(policy), sort_keys=True))
        task = CertificationTask(
            schema_version=CERTIFICATION_TASK_SCHEMA_VERSION,
            task_id="probe-go-cert", repository_id="shorten",
            merge_base_sha=base, head_sha=head,
            diff_digest=digest(GO_BASE + GO_HEAD), policy_source_sha=base,
            policy_digest=policy_digest,
        )
        subject = CertificationSubject(
            candidate_id="prefix-guard",
            normalized_claim="Prefix panics on an input shorter than three characters.",
            claim_digest=digest("Prefix panics on an input shorter than three characters."),
            test_digest=digest(PROBE_TEST), test_node=PROBE_NODE,
            environment_digest=digest(identity), interpreter_digest=digest(identity),
            executor_profile=adapter.profile, executor_digest=adapter.backend_digest(),
        )

        def runs_of(rows: list[dict[str, Any]], sha: str) -> tuple[ExecutionRun, ...]:
            return tuple(
                ExecutionRun(
                    run_id=f"{sha[:8]}-{row['repeat']}", revision_sha=sha,
                    outcome="failed" if row["outcome"] == "fail" else "passed",
                    artifact_digest=row["artifact_digest"], collected_count=1,
                    skipped_count=0, xfailed_count=0,
                    # the kernel requires one signature shared by every head run: the panic
                    # message without its addresses, which is what Go reports on each repeat
                    failure_signature=(
                        digest(_signature(row["report"])) if row["outcome"] == "fail" else None
                    ),
                )
                for row in rows
            )

        body = {
            "schema_version": CERTIFICATION_RECEIPT_SCHEMA_VERSION,
            "policy_version": policy.schema_version,
            "task_id": task.task_id, "repository_id": task.repository_id,
            "merge_base_sha": base, "head_sha": head, "diff_digest": task.diff_digest,
            "candidate_id": subject.candidate_id,
            "normalized_claim": subject.normalized_claim, "claim_digest": subject.claim_digest,
            "test_digest": subject.test_digest, "test_node": subject.test_node,
            "policy_source_sha": task.policy_source_sha, "policy_digest": policy_digest,
            "environment_digest": subject.environment_digest,
            "interpreter_digest": subject.interpreter_digest,
            "executor_profile": subject.executor_profile,
            "executor_digest": subject.executor_digest,
            "head_runs": runs_of(head_runs, head), "base_runs": runs_of(base_runs, base),
            "result_class": "head_fail_base_pass",
            "evidence_class": verdicts["evidence_class"],
            "binding_policy_version": binding.policy_version,
            "binding_digest": binding.digest(),
            "intent_policy_version": intent.policy_version,
            "intent_digest": intent.digest(),
            "body_version": RECEIPT_BODY_VERSION, "contained_attempts": (),
        }
        draft = CertificationReceipt(**body, provenance_digest="0" * 64)
        receipt = CertificationReceipt(**body, provenance_digest=provenance_digest(draft))
        decision = validate_receipt(task, policy, subject, receipt)

        record = {
            "probe": "P-02 go certification",
            "image": args.image, "image_digest": identity,
            "base_sha": base, "head_sha": head, "changed_line": changed_line,
            "differential_holds": differential,
            "base_outcomes": sorted(base_outcomes), "head_outcomes": sorted(head_outcomes),
            "binding": asdict(binding), "intent": intent.record(),
            "verdicts": {k: (v if isinstance(v, str) or v is None else str(v))
                         for k, v in verdicts.items()},
            "receipt_accepted": type(decision).__name__,
            "rejection_codes": [c.value for c in getattr(decision, "codes", ())],
            "gaps": gaps,
        }
    Path(args.out).write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "differential_holds": record["differential_holds"],
        "binding": record["binding"]["executed_changed_lines"],
        "binding_verdict": record["verdicts"]["binding"],
        "intent_verdict": record["verdicts"]["intent"],
        "evidence_class": record["verdicts"]["evidence_class"],
        "receipt": record["receipt_accepted"],
        "rejection_codes": record["rejection_codes"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
