"""P-01: how much of the execution path is bound to Python? Run a Go differential through it.

The certification kernel and the execution protocol are language-neutral by construction
(`src/attest/certification/*` imports only the standard library; `ExecutionRequest` names an
image, an argv and mounts). What is not known is how much of the *executor* is: this probe
finds out by running a real parent/head differential of a Go module through the product's own
`Controller` and `ContainerAdapter`, changing nothing under `src/` and recording every place a
Python assumption has to be worked around.

    .venv/bin/python scripts/probe/go_execution_probe.py --out probe.json

It builds a two-revision Go module whose head introduces an off-by-one, runs the module's own
test three times per revision in a read-only, network-none container, and reports the outcome
each side produced. It buys nothing, calls no model, and writes only to `--out` and a
temporary directory.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from attest.execution.container_adapter import (  # noqa: E402
    SCRATCH_MOUNT,
    ContainerAdapter,
    ContainerImage,
)
from attest.execution.controller import Controller  # noqa: E402
from attest.execution.types import ResourceLimits  # noqa: E402

IMAGE = "golang:1.22-alpine"
GO_MOD = "module calc\n\ngo 1.22\n"
GO_BASE = '''package calc

// Sum adds the numbers of a slice.
func Sum(values []int) int {
	total := 0
	for _, v := range values {
		total += v
	}
	return total
}
'''
GO_HEAD = GO_BASE.replace("for _, v := range values {", "for _, v := range values[1:] {")
GO_TEST = '''package calc

import "testing"

func TestSum(t *testing.T) {
	if got := Sum([]int{1, 2, 3}); got != 6 {
		t.Fatalf("Sum = %d, want 6", got)
	}
}
'''


class PosixLauncherAdapter(ContainerAdapter):
    """The product adapter with one substitution, recorded as a finding.

    `ContainerAdapter` prepends `NPROC_LAUNCHER_ARGV`, which is `python3 -I -c …`: the
    launcher that sets RLIMIT_NPROC=0 before the job execs is written in Python, so every
    image must ship an interpreter whatever the repository under review is written in. The
    same guarantee is one line of `sh`, which every base image has."""

    nproc_limit = 0  # 0 means: do not set RLIMIT_NPROC at all

    def command(self, request: Any, *, tree: Path, inputs: Path, outputs: Path) -> list[str]:
        argv = super().command(request, tree=tree, inputs=inputs, outputs=outputs)
        start = argv.index("python3", argv.index(self.image.reference))
        job = argv[start + 3 + 1:]  # python3 -I -c <launcher> <job...>
        argv = [
            # the scratch and /tmp mounts are not executable: an interpreted test never
            # runs a file it just built, a compiled one always does
            a.replace("rw,nosuid,", "rw,exec,nosuid,")
            if a.startswith(("/attest/scratch:", "/tmp:")) else a
            for a in argv
        ]
        limit = self.nproc_limit
        guard = (
            f'ulimit -u {limit} 2>/dev/null || true; exec "$0" "$@"' if limit
            else 'exec "$0" "$@"'
        )
        return [*argv[:start], "sh", "-c", guard, *job]


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), "-c", "user.email=probe@example.test",
         "-c", "user.name=probe", "-c", "commit.gpgsign=false", *args],
        capture_output=True, text=True, check=True,
    ).stdout.strip()


def build_case(root: Path) -> tuple[Path, str, str]:
    repo = root / "calc"
    repo.mkdir(parents=True)
    _git(repo, "init", "--initial-branch=main")
    (repo / "go.mod").write_text(GO_MOD, encoding="utf-8")
    (repo / "calc.go").write_text(GO_BASE, encoding="utf-8")
    (repo / "calc_test.go").write_text(GO_TEST, encoding="utf-8")
    _git(repo, "add", "--all")
    _git(repo, "commit", "-m", "base")
    base = _git(repo, "rev-parse", "HEAD")
    (repo / "calc.go").write_text(GO_HEAD, encoding="utf-8")
    _git(repo, "commit", "-am", "head")
    return repo, base, _git(repo, "rev-parse", "HEAD")


def outcome_of(stdout: str) -> tuple[str, int, list[str]]:
    """What `go test -json` reported: the action of each test, as an outcome would read it."""
    actions, failed, names = [], 0, []
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get("Test") and event.get("Action") in ("pass", "fail", "skip"):
            actions.append(event["Action"])
            names.append(f"{event.get('Package', '')}.{event['Test']}")
            failed += event["Action"] == "fail"
    if not actions:
        return "no test ran", failed, names
    return ("fail" if failed else "pass"), failed, sorted(set(names))


def run_side(
    repo: Path, sha: str, adapter: ContainerAdapter, work: Path, repeats: int,
) -> list[dict[str, Any]]:
    _git(repo, "checkout", "--quiet", sha)
    controller = Controller(work / f"controller-{sha[:8]}")
    runs: list[dict[str, Any]] = []
    for index in range(repeats):
        inputs = work / f"in-{sha[:8]}-{index}"
        outputs = work / f"out-{sha[:8]}-{index}"
        inputs.mkdir(parents=True, exist_ok=True)
        outputs.mkdir(parents=True, exist_ok=True)
        request = controller.issue(
            task_id="probe-go", run_id=f"r{index}", candidate_id="calc-sum",
            revision_sha=sha, profile=adapter.profile, interpreter=IMAGE,
            argv_template=(
                "sh", "-c",
                "go test -count=1 -json ./... > /attest/outputs/report.json 2>&1",
            ),
            environment={
                # the adapter's fixed PATH is written for a Python image; Go lives elsewhere
                "PATH": "/usr/local/go/bin:/usr/local/bin:/usr/bin:/bin",
                "GOCACHE": f"{SCRATCH_MOUNT}/gocache",
                "GOPATH": f"{SCRATCH_MOUNT}/gopath",
                "GOTMPDIR": SCRATCH_MOUNT,
                "GOFLAGS": "-mod=mod",
                "GOPROXY": "off",
            },
            inputs={}, limits=ResourceLimits(
                wall_timeout_s=180.0, cpu_timeout_s=120, memory_mb=1024, output_bytes=4_000_000,
            ),
            expected_artifacts=("report.json",),
        )
        envelope = adapter.execute(request, tree=repo, inputs=inputs, outputs=outputs)
        report = outputs / "report.json"
        stdout = report.read_text(encoding="utf-8", errors="replace") if report.is_file() else ""
        action, failed, names = outcome_of(stdout)
        runs.append({
            "repeat": index, "exit_code": envelope.exit_code, "timed_out": envelope.timed_out,
            "outcome": action, "failed_tests": failed, "tests": names,
            "error": envelope.error,
            "artifacts": [a.name for a in envelope.artifacts],
            "report_head": stdout[:300],
        })
    return runs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--image", default=IMAGE)
    parser.add_argument("--nproc", type=int, default=0,
                        help="RLIMIT_NPROC for the job; 0 leaves it unset")
    parser.add_argument("--pids", type=int, default=256,
                        help="the container pid limit (the product default is 16)")
    args = parser.parse_args(argv)

    docker = shutil.which("docker")
    if docker is None:
        print("docker is not installed on this host")
        return 2
    pull = subprocess.run([docker, "pull", args.image], capture_output=True, text=True)
    if pull.returncode != 0:
        print(f"could not pull {args.image}: {pull.stderr.strip()[:200]}")
        return 2
    identity = subprocess.run(
        [docker, "image", "inspect", "--format", "{{.Id}}", args.image],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    image = ContainerImage(reference=args.image, digest=identity, tag=args.image)
    adapter = PosixLauncherAdapter(image, docker=docker, pids_limit=args.pids)
    adapter.nproc_limit = args.nproc

    findings: list[str] = [
        "the isolation launcher NPROC_LAUNCHER_ARGV is `python3 -I -c …`, so the product "
        "adapter needs a Python interpreter in every image; this probe substitutes one line "
        "of `sh` for the same RLIMIT_NPROC guarantee",
        "ExecutionResultEnvelope carries no stdout: a job reports through declared artifacts "
        "in the outputs mount, so each language needs its own report file and parser "
        "(pytest writes junit.xml; this probe redirects `go test -json`)",
        "ContainerAdapter.interpreter_identity runs `python3 -c` in the image, so identity "
        "for a non-Python image has to come from somewhere else (this probe uses the image id)",
        "CONTAINER_PATH is /usr/local/bin:/usr/bin:/bin, written for a Python image; the Go "
        "toolchain is at /usr/local/go/bin, so the probe overrides PATH through the request",
        "the scratch and /tmp tmpfs mounts are not executable, so a compiled test binary "
        "cannot be run from them; the probe adds `exec` to both",
        "the isolation profile assumes a job that never forks: RLIMIT_NPROC near zero and "
        "DEFAULT_PIDS_LIMIT = 16. A compiled language forks a compiler and the Go runtime "
        "creates one OS thread per core, so both bounds had to be raised for the job to run "
        "at all (this probe: no RLIMIT_NPROC, pid limit 256)",
    ]
    with tempfile.TemporaryDirectory(prefix="go-probe-") as tmp:
        work = Path(tmp)
        repo, base, head = build_case(work)
        record: dict[str, Any] = {
            "probe": "P-01 go execution", "image": args.image, "image_digest": identity,
            "repeats": args.repeats, "base_sha": base, "head_sha": head,
        }
        record["base"] = run_side(repo, base, adapter, work, args.repeats)
        record["head"] = run_side(repo, head, adapter, work, args.repeats)
    base_outcomes = {r["outcome"] for r in record["base"]}
    head_outcomes = {r["outcome"] for r in record["head"]}
    record["differential"] = {
        "base": sorted(base_outcomes), "head": sorted(head_outcomes),
        "holds": base_outcomes == {"pass"} and head_outcomes == {"fail"},
    }
    record["findings"] = findings
    Path(args.out).write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "base": sorted(base_outcomes), "head": sorted(head_outcomes),
        "holds": record["differential"]["holds"],
        "exit_codes": [r["exit_code"] for r in record["base"] + record["head"]],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
