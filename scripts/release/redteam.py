"""G-SEC-002 red-team matrix on the production isolation backend.

Nine adversarial fixtures, each dispatched for real against `linux-container-v1`
and each required to be **marked, never certified**:

    secret        head code reads a canary from the controller's environment
    keyfile       head code reads the controller's key file off the host
    socket        head code opens a network connection
    dns           head code resolves a name (egress that is not a TCP connect)
    escape        head code writes outside its work directory
    symlink       head code writes through a symlink that points out of it
    processes     head code exhausts processes and threads, bounded
    forge         an executor returns a result bound to another request's nonce
    bundle        a sealed evidence bundle is edited after the fact

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
import shutil
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

# 4.1, fixture 5: the controller's own key material sits on the host, outside
# every path the container is given. Head code goes looking for it by every
# route it has: the mount parents, the usual home directories, and the literal
# path the controller wrote it to.
KEYFILE_BODY = (
    "import os\n\n"
    "TARGETS = (\n"
    "    os.environ.get('ATTEST_CONTROLLER_KEY_PATH', '/nonexistent'),\n"
    "    '/attest/controller-key',\n"
    "    '/attest/inputs/../controller-key',\n"
    "    '/root/.attest/credentials',\n"
    "    '/home/runner/.attest/credentials',\n"
    "    '/proc/1/environ',\n"
    ")\n\n"
    "def test_repro():\n"
    "    found = []\n"
    "    for target in TARGETS:\n"
    "        try:\n"
    "            with open(target, 'rb') as handle:\n"
    "                blob = handle.read()\n"
    "        except OSError:\n"
    "            continue\n"
    "        if b'must-not-leak' in blob:\n"
    "            found.append(target)\n"
    "    assert found == [], found\n"
)

# 4.1, fixture 6: a symlink is the escape a plain open() does not get. The link
# is created inside the writable scratch, so creating it always succeeds; what
# must fail is the write that follows it out.
SYMLINK_BODY = (
    "import os\n"
    "import tempfile\n\n"
    "def test_repro():\n"
    "    escaped = 0\n"
    "    for target in ('/etc', '/attest/tree', '/'):\n"
    "        link = os.path.join(tempfile.gettempdir(), 'link-%s' % abs(hash(target)))\n"
    "        try:\n"
    "            os.symlink(target, link)\n"
    "        except OSError:\n"
    "            continue\n"
    "        try:\n"
    "            with open(os.path.join(link, 'symlinked.txt'), 'w') as handle:\n"
    "                handle.write('escaped')\n"
    "            escaped += 1\n"
    "        except OSError:\n"
    "            pass\n"
    "    assert escaped == 0, escaped\n"
)

# 4.1, fixture 7: DNS is egress the TCP-connect fixture does not cover -- a
# resolver reaches the network over UDP through a different path.
DNS_BODY = (
    "import socket\n\n"
    "def test_repro():\n"
    "    socket.setdefaulttimeout(3)\n"
    "    try:\n"
    "        answers = socket.getaddrinfo('example.com', 80)\n"
    "    except OSError:\n"
    "        return\n"
    "    raise AssertionError('resolved %r' % (answers[:1],))\n"
)

# 4.1, fixture 8: bounded process exhaustion. Bounded on purpose -- the point is
# that the boundary refuses, not that the runner is knocked over, so the fixture
# asks for a fixed number and stops.
PROCESS_BODY = (
    "import os\n"
    "import threading\n\n"
    "def _spin():\n"
    "    pass\n\n"
    "def test_repro():\n"
    "    forked = 0\n"
    "    for _ in range(64):\n"
    "        try:\n"
    "            pid = os.fork()\n"
    "        except OSError:\n"
    "            break\n"
    "        if pid == 0:\n"
    "            os._exit(0)\n"
    "        forked += 1\n"
    "    threaded = 0\n"
    "    for _ in range(64):\n"
    "        try:\n"
    "            worker = threading.Thread(target=_spin)\n"
    "            worker.start()\n"
    "        except RuntimeError:\n"
    "            break\n"
    "        threaded += 1\n"
    "    assert forked == 0 and threaded == 0, (forked, threaded)\n"
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
    """base: `add` is correct. head: `add` raises. A real regression.

    **The control must be a crash, not a changed value.** On 2026-09-07 the
    control was `a + b` becoming `a - b`, and it stopped certifying — not
    because anything about the isolation boundary had moved, but because
    `attest.intent.v4.1` refuses a *value* change whose intended value the base
    tree does not state. A matrix whose control fails for a reason unrelated to
    the boundary reports FAIL about the wrong thing. The crash class is the
    class this product certifies, so the control is one.
    """
    repo = root / "repo"
    repo.mkdir()
    _git(repo, "init", "--initial-branch=main")
    (repo / "mod.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    _git(repo, "add", "mod.py")
    _git(repo, "commit", "-m", "base")
    base = _git(repo, "rev-parse", "HEAD")
    (repo / "mod.py").write_text(
        "def add(a, b):\n    parts = [a]\n    return parts[1] + b\n", encoding="utf-8"
    )
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


def _bundle_row(root: Path) -> Row:
    """4.1, fixture 9: a sealed evidence bundle, edited after the fact.

    The bundle is what a reader verifies **offline**, without this process and
    without trusting it, so an edit to any byte it binds must be refused. The
    bundle is produced here rather than found: a fixture that skips when the
    checkout happens to hold no bundle is not attack coverage.

    No model call -- the proposal and the reproduction are both replayed from
    fixed payloads, and the certification is the real one.
    """
    from attest.certification.types import AcceptedReceipt
    from attest.review.config import ReviewConfig
    from attest.review.evidence import verify_bundle
    from attest.review.proposer import MockProvider
    from attest.review.run import run_review

    repo = root / "bundle-repo"
    repo.mkdir()
    _git(repo, "init", "--initial-branch=main")
    (repo / "calc.py").write_text(
        "def average(items):\n    if not items:\n        return 0\n"
        "    return sum(items) / len(items)\n",
        encoding="utf-8",
    )
    _git(repo, "add", "calc.py")
    _git(repo, "commit", "-m", "base")
    base = _git(repo, "rev-parse", "HEAD")
    (repo / "calc.py").write_text(
        "def average(items):\n    return sum(items) / len(items)\n", encoding="utf-8"
    )
    _git(repo, "commit", "-am", "head")

    proposal = json.dumps(
        {
            "findings": [
                {
                    "claim": "average() divides by zero when items is empty.",
                    "anchor": {"file": "calc.py", "line": 2},
                    "failure_scenario": "average([]) raises ZeroDivisionError",
                    "falsification_plan": "call average([]) and observe the exception",
                }
            ]
        }
    )
    repro = json.dumps(
        {
            "test_body": (
                "import runpy\n\n"
                "def test_average_handles_empty_input():\n"
                "    module = runpy.run_path('calc.py')\n"
                "    assert module['average']([]) == 0\n"
            )
        }
    )
    review = run_review(
        repo,
        base,
        ReviewConfig(probe_generation=False, k_samples=1, tier0_commands=[]),
        MockProvider([proposal, repro, repro, repro]),
        verify=True,
    )
    bundles = sorted((repo / ".attest" / "evidence").glob("**/manifest.json"))
    if not bundles:
        return Row(
            fixture="tamper with a sealed bundle",
            attempt=(
                "ran a local differential review to produce a bundle; none was written "
                f"({review.deferred_reason or 'no certification'})"
            ),
            outcome="unattempted",
            detail="a pre-dispatch skip is not attack coverage",
            marked=False,
            certified=False,
        )
    bundle = bundles[0].parent
    intact = verify_bundle(bundle)
    copy = root / "bundle-copy"
    shutil.copytree(bundle, copy)
    receipt = json.loads((copy / "receipt.json").read_text(encoding="utf-8"))
    receipt["claim"] = "a claim nobody certified"
    (copy / "receipt.json").write_text(json.dumps(receipt), encoding="utf-8")
    verdict = verify_bundle(copy)
    accepted = isinstance(verdict, AcceptedReceipt)
    reasons = "; ".join(getattr(verdict, "reasons", ()) or ()) or type(verdict).__name__
    return Row(
        fixture="tamper with a sealed bundle",
        attempt=(
            "produced a real sealed bundle from a local differential, verified it, then "
            "rewrote its receipt's claim and verified the copy again"
        ),
        outcome="ACCEPTED" if accepted else "rejected",
        detail=(
            reasons
            + (
                "; the intact bundle verified"
                if isinstance(intact, AcceptedReceipt)
                else "; INTACT BUNDLE ALSO FAILED"
            )
        ),
        marked=not accepted and isinstance(intact, AcceptedReceipt),
        certified=accepted,
    )


def matrix(root: Path) -> list[Row]:
    os.environ["ATTEST_CANARY_TOKEN"] = CANARY
    os.environ["CANARY_PLAIN"] = CANARY
    # the controller's key material, on the host and outside every path the
    # container is given. A fixture value, never a credential.
    key_path = root / "controller-key"
    key_path.write_text(f"attest-controller-key={CANARY}\n", encoding="utf-8")
    os.environ["ATTEST_CONTROLLER_KEY_PATH"] = str(key_path)
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

    keyfile = _run(repo, "keyfile", KEYFILE_BODY, adapter, base, head)
    key_leaked = any(CANARY in run.stdout + run.stderr for run in keyfile.head_runs)
    rows.append(
        Row(
            fixture="read the controller's key file off the host",
            attempt=(
                f"ran {len(keyfile.head_runs) or 1} head repeat(s) and opened six host paths, "
                "including the controller's real key path and /proc/1/environ"
            ),
            outcome=keyfile.outcome.value,
            detail=(
                "no path inside the container holds the key, so the test passes on both "
                "trees and buys nothing"
                if not key_leaked
                else "CONTROLLER KEY LEAKED"
            ),
            marked=not key_leaked and keyfile.outcome is not ExecutionOutcome.REPRODUCED,
            certified=keyfile.outcome is ExecutionOutcome.REPRODUCED,
        )
    )

    dns = _run(repo, "dns", DNS_BODY, adapter, base, head)
    rows.append(
        Row(
            fixture="resolve a name (DNS egress)",
            attempt=f"ran {len(dns.head_runs) or 1} head repeat(s) and called getaddrinfo()",
            outcome=dns.outcome.value,
            detail=dns.reason or "the resolver failed inside the container",
            marked=(
                dns.outcome is not ExecutionOutcome.REPRODUCED
                and dns.evidence_class is not EvidenceClass.REGRESSION_REPRODUCED
            ),
            certified=dns.outcome is ExecutionOutcome.REPRODUCED,
        )
    )

    symlink = _run(repo, "symlink", SYMLINK_BODY, adapter, base, head)
    symlinked = any(repo.rglob("symlinked.txt")) or (ROOT / "symlinked.txt").exists()
    rows.append(
        Row(
            fixture="escape the work directory through a symlink",
            attempt=(
                f"ran {len(symlink.head_runs) or 1} head repeat(s), created symlinks to /etc, "
                "/attest/tree and / and wrote through them"
            ),
            outcome=symlink.outcome.value,
            detail=symlink.reason + ("; FILE ON DISK" if symlinked else "; nothing on disk"),
            marked=symlink.outcome is not ExecutionOutcome.REPRODUCED and not symlinked,
            certified=symlink.outcome is ExecutionOutcome.REPRODUCED,
        )
    )

    processes = _run(repo, "processes", PROCESS_BODY, adapter, base, head)
    rows.append(
        Row(
            fixture="exhaust processes and threads (bounded)",
            attempt=(
                f"ran {len(processes.head_runs) or 1} head repeat(s) and asked for 64 forks "
                "and 64 threads"
            ),
            outcome=processes.outcome.value,
            detail=processes.reason or "the boundary refused before the fixture could assert",
            marked=processes.outcome is not ExecutionOutcome.REPRODUCED,
            certified=processes.outcome is ExecutionOutcome.REPRODUCED,
        )
    )

    rows.append(_forge_row(root))
    rows.append(_bundle_row(root))
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
            "**External observation: INSUFFICIENT, and this matrix does not change that.**",
            "`G-SEC-002` requires a *sandbox-external* supervisor or kernel observation",
            "proving OS denial or forced termination. Every row below is observed from",
            "**inside** the product -- the fixture's own return value, the reason the",
            "differential recorded, and whether a file appeared on the host. That is",
            "evidence the boundary held for this attempt; it is not evidence the kernel",
            "denied it, and the two are not the same claim. The gate stays open on that",
            "item until an auditd/seccomp-notify observer runs beside the container.",
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
        attempted = sum(1 for row in rows[1:] if row.outcome != "unattempted")
        lines += [
            "",
            f"**{'PASS' if passed else 'FAIL'}** — {len(attacks)} attack fixture(s), "
            f"{attempted} actually dispatched, 1 positive control.",
            "",
            "External observer: **INSUFFICIENT** (see above).",
            "",
        ]
        Path(args.record).write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"recorded -> {args.record}")
        print(json.dumps({"passed": passed, "rows": len(rows)}))

    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
