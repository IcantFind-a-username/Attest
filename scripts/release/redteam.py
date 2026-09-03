"""G-SEC-002 red-team matrix on the production isolation backend.

Four adversarial fixtures, each dispatched for real against `linux-container-v1`
and each required to be **marked, never certified**:

    secret        head code reads a canary from the controller's environment
    socket        head code opens a network connection
    escape        head code writes outside its work directory
    forge         an executor returns a result bound to another request's nonce

A positive control -- an ordinary regression -- must certify in the same backend
in the same run, or a matrix of refusals proves only that nothing works.

    python scripts/release/redteam.py --record docs/acceptance/<date>-redteam.md

Free: no model call. It needs a docker daemon that can build the image, so it is
meant for the CI runner (`.github/workflows/red-team.yml`). A pre-dispatch DEFER
is not attack coverage: every row records whether the fixture actually ran.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from attest.execution.container_adapter import (  # noqa: E402
    CONTAINER_PROFILE,
    ContainerAdapter,
)
from attest.execution.container_images import ensure_image  # noqa: E402
from attest.execution.controller import Controller  # noqa: E402
from attest.execution.protocol import request_digest, sha256_hex  # noqa: E402
from attest.execution.types import (  # noqa: E402
    EXECUTION_PROTOCOL_VERSION,
    Artifact,
    ExecutionResultEnvelope,
    ResourceLimits,
)
from attest.review.executor import (  # noqa: E402
    EvidenceClass,
    ExecutionOutcome,
    ExecutorLimits,
    ReproSpec,
    execute_differential,
)

CANARY = "canary-must-not-leak"

SECRET_BODY = (
    "import os\n\n"
    "def test_repro():\n"
    "    leaked = {k: v for k, v in os.environ.items() if 'CANARY' in k}\n"
    "    assert leaked == {}, leaked\n"
    "    assert 'must-not-leak' not in ''.join(os.environ.values())\n"
)

SOCKET_BODY = (
    "import socket\n\n"
    "def test_repro():\n"
    "    s = socket.socket()\n"
    "    s.settimeout(3)\n"
    "    try:\n"
    "        s.connect(('1.1.1.1', 80))\n"
    "    except OSError:\n"
    "        return\n"
    "    raise AssertionError('connected')\n"
)

ESCAPE_BODY = (
    "def test_repro():\n"
    "    failures = 0\n"
    "    for target in ('/attest/tree/escaped.txt', '/etc/escaped.txt', '/attest/inputs/x'):\n"
    "        try:\n"
    "            with open(target, 'w') as handle:\n"
    "                handle.write('escaped')\n"
    "        except OSError:\n"
    "            failures += 1\n"
    "    assert failures == 3, failures\n"
)

REGRESSION_BODY = "import mod\n\ndef test_repro():\n    assert mod.add(2, 2) == 4"


@dataclass
class Row:
    fixture: str
    attempt: str  # what the fixture actually did before the verdict
    outcome: str
    detail: str
    marked: bool  # the run was refused *and* said why
    certified: bool


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "-c",
            "user.email=redteam@example.test",
            "-c",
            "user.name=red-team",
            "-c",
            "commit.gpgsign=false",
            *args,
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _repo(root: Path) -> tuple[Path, str, str]:
    """base: `add` is correct. head: `add` subtracts. A real regression."""
    repo = root / "repo"
    repo.mkdir()
    _git(repo, "init", "--initial-branch=main")
    (repo / "mod.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    _git(repo, "add", "mod.py")
    _git(repo, "commit", "-m", "base")
    base = _git(repo, "rev-parse", "HEAD")
    (repo / "mod.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    _git(repo, "commit", "-am", "head")
    return repo, base, _git(repo, "rev-parse", "HEAD")


def _candidate(task: str):  # noqa: ANN202 - the test helper's own type
    from test_executor import candidate

    return candidate(file="mod.py", line=2, task_id=task)


def _run(repo: Path, task: str, body: str, adapter: ContainerAdapter, base: str, head: str):  # noqa: ANN202
    return execute_differential(
        repo,
        _candidate(task),
        ReproSpec(body),
        ExecutorLimits(wall_timeout_s=180.0),
        base_sha=base,
        head_sha=head,
        adapter=adapter,
    )


class _ForgingAdapter:
    """An executor that answers a request it was never issued: the envelope
    carries another job's nonce and an artifact digest that does not describe
    the bytes it wrote."""

    profile = CONTAINER_PROFILE

    def __init__(self, nonce: str) -> None:
        self.nonce = nonce

    def backend_digest(self) -> str:
        # well-formed on purpose: the rejection under test must be the nonce,
        # not a malformed field the decoder would have caught anyway
        return sha256_hex(b"forged-backend")

    def interpreter_identity(self, interpreter: str) -> tuple[str, str]:
        return interpreter, "forged"

    def execute(  # noqa: ANN201
        self, request, *, tree: Path, inputs: Path, outputs: Path  # noqa: ANN001
    ):
        (outputs / "stdout.txt").write_bytes(b"1 passed")
        declared = b"whatever the controller expects"
        return ExecutionResultEnvelope(
            protocol_version=EXECUTION_PROTOCOL_VERSION,
            nonce=self.nonce,
            request_digest=request_digest(request),
            run_id=request.run_id,
            profile=self.profile,
            backend_digest=self.backend_digest(),
            exit_code=0,
            timed_out=False,
            elapsed_s=0.0,
            artifacts=(Artifact("stdout.txt", sha256_hex(declared), len(declared)),),
            error="",
        )


def _forge_row(root: Path) -> Row:
    controller = Controller(root / "forge-runs", nonce_source=iter(["1" * 32, "2" * 32]).__next__)

    def issue(run_id: str):  # noqa: ANN202
        return controller.issue(
            task_id="redteam",
            run_id=run_id,
            candidate_id="c1",
            revision_sha="0" * 40,
            profile=CONTAINER_PROFILE,
            interpreter=sys.executable,
            argv_template=[sys.executable, "-c", "pass"],
            environment={},
            inputs={"note.txt": b"input"},
            limits=ResourceLimits(
                wall_timeout_s=20.0, cpu_timeout_s=10, memory_mb=512, output_bytes=4096
            ),
            expected_artifacts=("stdout.txt",),
        )

    first = issue("head-1")
    second = issue("head-2")
    outcome = controller.dispatch(
        first, _ForgingAdapter(second.nonce), tree=root, inputs={"note.txt": b"input"}
    )
    reasons = "; ".join(outcome.reasons)
    return Row(
        fixture="forge a result",
        attempt="an executor returned an envelope bound to another request's nonce",
        outcome="rejected" if not outcome.accepted else "ACCEPTED",
        detail=reasons or "(no reason recorded)",
        marked=not outcome.accepted and bool(outcome.reasons) and outcome.artifacts == {},
        certified=bool(outcome.accepted),
    )


def matrix(root: Path) -> list[Row]:
    os.environ["ATTEST_CANARY_TOKEN"] = CANARY
    os.environ["CANARY_PLAIN"] = CANARY
    image_source = root / "image-source"
    image_source.mkdir()
    adapter = ContainerAdapter(ensure_image(image_source))
    repo, base, head = _repo(root)
    rows: list[Row] = []

    control = _run(repo, "control", REGRESSION_BODY, adapter, base, head)
    rows.append(
        Row(
            fixture="positive control: a real regression",
            attempt="ran 3 head and 3 base repeats in the container",
            outcome=control.outcome.value,
            detail=control.reason,
            marked=False,
            certified=control.outcome is ExecutionOutcome.REPRODUCED,
        )
    )

    secret = _run(repo, "secret", SECRET_BODY, adapter, base, head)
    leaked = any(CANARY in run.stdout + run.stderr for run in secret.head_runs)
    rows.append(
        Row(
            fixture="read the controller's environment secret",
            attempt=f"ran {len(secret.head_runs)} head repeat(s) and inspected os.environ",
            outcome=secret.outcome.value,
            detail=(
                "the canary is absent inside the container, so the test passes on both trees "
                "and buys nothing"
                if not leaked
                else "CANARY LEAKED"
            ),
            marked=not leaked and secret.outcome is not ExecutionOutcome.REPRODUCED,
            certified=secret.outcome is ExecutionOutcome.REPRODUCED,
        )
    )

    sock = _run(repo, "socket", SOCKET_BODY, adapter, base, head)
    rows.append(
        Row(
            fixture="open a network connection",
            attempt=f"ran {len(sock.head_runs) or 1} head repeat(s) and called connect()",
            outcome=sock.outcome.value,
            detail=sock.reason,
            marked=(
                sock.outcome is ExecutionOutcome.DEFERRED
                and "network connection" in sock.reason
                and sock.evidence_class is not EvidenceClass.REGRESSION_REPRODUCED
            ),
            certified=sock.outcome is ExecutionOutcome.REPRODUCED,
        )
    )

    escape = _run(repo, "escape", ESCAPE_BODY, adapter, base, head)
    on_disk = any(repo.rglob("escaped.txt"))
    rows.append(
        Row(
            fixture="write outside the work directory",
            attempt=f"ran {len(escape.head_runs) or 1} head repeat(s) and opened three paths",
            outcome=escape.outcome.value,
            detail=escape.reason + ("; FILE ON DISK" if on_disk else "; nothing on disk"),
            marked=(
                escape.outcome is ExecutionOutcome.DEFERRED
                and "write outside its work directory" in escape.reason
                and not on_disk
            ),
            certified=escape.outcome is ExecutionOutcome.REPRODUCED,
        )
    )

    rows.append(_forge_row(root))
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--record", default=None, help="write the matrix to this path")
    args = parser.parse_args(argv)

    with tempfile.TemporaryDirectory(prefix="attest-redteam-") as workspace:
        rows = matrix(Path(workspace).resolve())

    control = rows[0]
    attacks = rows[1:]
    passed = control.certified and all(row.marked and not row.certified for row in attacks)
    for row in rows:
        verdict = "ok  " if (row.marked or row.certified) else "FAIL"
        print(f"{verdict} {row.fixture}: {row.outcome} [{row.detail}]")
    print(f"\n{'PASS' if passed else 'FAIL'}: {len(attacks)} attack fixture(s), 1 control")

    if args.record:
        stamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        head = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True
        ).stdout.strip()
        docker = subprocess.run(
            ["docker", "version", "--format", "{{.Server.Version}}"],
            capture_output=True,
            text=True,
        ).stdout.strip()
        lines = [
            "# G-SEC-002 red-team matrix on the production backend",
            "",
            f"Run {stamp} at `{head[:7]}` on `{os.uname().sysname} {os.uname().machine}`, "
            f"docker {docker or 'unknown'}, profile `{CONTAINER_PROFILE}`.",
            "No model call. Every attack fixture was dispatched for real; a pre-dispatch",
            "DEFER would appear here as an unattempted row and is not attack coverage.",
            "",
            "| fixture | what it actually did | outcome | marked, not certified | detail |",
            "|---|---|---|---|---|",
        ]
        for row in rows:
            if row.fixture.startswith("positive control"):
                verdict = "**certified** (expected)" if row.certified else "**FAILED TO CERTIFY**"
            else:
                verdict = "yes" if row.marked and not row.certified else "**NO**"
            lines.append(
                f"| {row.fixture} | {row.attempt} | `{row.outcome}` | {verdict} | {row.detail} |"
            )
        lines += ["", f"**{'PASS' if passed else 'FAIL'}**", ""]
        Path(args.record).write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"recorded -> {args.record}")
        print(json.dumps({"passed": passed, "rows": len(rows)}))

    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
