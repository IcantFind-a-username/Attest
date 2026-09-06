"""G-SEC-002's missing row: a record of what the container did, written by the kernel.

Every row of the nine-class red-team matrix is observed **from inside the
product**. The harness dispatches an attack, the harness reads the result, and
the harness writes down that the boundary held. That is the one thing a security
claim may not do, and the matrix says so about itself: the external-observer item
stays `INSUFFICIENT`.

This is the attempt at the missing observer. It asks the Linux kernel's audit
subsystem to record the syscalls the container's processes make, runs the attack
fixtures, and then compares **the kernel's record** with **the harness's claim**.
Nothing attest writes is trusted; `attest` is not even imported by the comparison.

    observer probe   --json <out>              # can this host observe at all?
    sudo observer arm                          # install the rules, print the mark
    python scripts/release/redteam.py ...      # the matrix, **unprivileged**
    sudo observer collect --since <mark> --json <out>   # compare, then disarm

The three steps are separate because the privileges are opposite. Audit rules
need root; the matrix must **not** have it. Run as root, the product's own
containment guard refuses every fixture -- *"process containment unavailable for
privileged POSIX user"* -- because `RLIMIT_NPROC = 0` does not bind a privileged
uid, and a matrix of refusals observed by a kernel that saw no container is not
evidence of anything. The first attempt did exactly that and is on the record.

Why the audit subsystem and not a seccomp `SCMP_ACT_LOG` profile: adding a
seccomp profile means handing `docker run` a *different* security configuration
than the product uses, and a matrix taken under a different configuration
measures a different container. An audit rule is attached to the host kernel and
changes nothing about the container at all -- the product's argv is byte for byte
what it always is, and the observation happens beside it.

**What the observer can and cannot establish**, stated before any result:

* it can show that a syscall the harness says was **refused** either never
  reached the kernel or returned the error the harness reported;
* it can show that a syscall the harness never mentioned **did** happen;
* it **cannot** show that nothing else happened. Audit records what its rules
  match, and a rule set is a list of names someone chose.

Free: no model call, no network, no spend. Needs root on a Linux host with
`CONFIG_AUDIT` and an unlocked audit subsystem, which is why it lives beside
`red-team.yml` and not in the test suite.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

OBSERVER_SCHEMA_VERSION = "attest.external-observer.v1"

# The container's unprivileged uid, from `attest.execution.container_adapter`.
# It is written here as a literal on purpose: an observer that imports the thing
# it observes is not independent of it.
CONTAINER_UID = 65534

# The syscalls whose presence or absence the matrix's claims are about. Kept
# short: every rule costs the whole host a kernel record per matching call, and
# a rule set nobody can read is not evidence anybody can check.
WATCHED = ("connect", "socket", "openat", "execve", "clone", "unlink", "unlinkat")

AUDIT_KEY = "attest-observer"
# A second rule with **no uid filter** and one syscall, armed beside the first.
# It exists to tell three failures apart that a run of zero records cannot:
# the uid filter does not match the container, the rule set does not work at
# all, or the host's audit pipeline records nothing whatever the rule says.
AUDIT_KEY_ANY = "attest-observer-any"


@dataclass
class Step:
    name: str
    ok: bool
    detail: str = ""
    output: str = ""


@dataclass
class Probe:
    """Whether this host can observe at all, and precisely what stopped it."""

    platform: str
    kernel: str
    root: bool
    auditctl: str = ""
    ausearch: str = ""
    audit_status: str = ""
    audit_enabled: int | None = None
    audit_locked: bool = False
    docker: str = ""
    steps: list[Step] = field(default_factory=list)

    @property
    def feasible(self) -> bool:
        return (
            self.platform == "Linux"
            and self.root
            and bool(self.auditctl)
            and bool(self.ausearch)
            and bool(self.docker)
            and self.audit_enabled is not None
            and not self.audit_locked
        )

    def blocked_by(self) -> str:
        if self.platform != "Linux":
            return f"the audit subsystem is a Linux kernel facility; this host is {self.platform}"
        if not self.root:
            return "audit rules need root (CAP_AUDIT_CONTROL); this process is not root"
        if not self.auditctl or not self.ausearch:
            missing = " and ".join(
                name for name, found in (("auditctl", self.auditctl), ("ausearch", self.ausearch))
                if not found
            )
            return f"{missing} is not installed (apt-get install -y auditd)"
        if not self.docker:
            return "docker is not installed, so there is no container to observe"
        if self.audit_enabled is None:
            return f"the kernel reports no audit status: {self.audit_status[:200]}"
        if self.audit_locked:
            return "the audit subsystem is locked (enabled 2); rules cannot be added"
        return ""


def _run(*argv: str, check: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(list(argv), capture_output=True, text=True, check=check)


def probe() -> Probe:
    found = Probe(
        platform=platform.system(),
        kernel=platform.release(),
        root=hasattr(os, "geteuid") and os.geteuid() == 0,
        auditctl=shutil.which("auditctl") or "",
        ausearch=shutil.which("ausearch") or "",
        docker=shutil.which("docker") or "",
    )
    if found.auditctl and found.root:
        status = _run(found.auditctl, "-s")
        found.audit_status = (status.stdout + status.stderr).strip()
        for line in found.audit_status.splitlines():
            if line.startswith("enabled"):
                parts = line.split()
                if len(parts) > 1 and parts[1].isdigit():
                    found.audit_enabled = int(parts[1])
                    found.audit_locked = found.audit_enabled == 2
    return found


def install_rules(auditctl: str) -> Step:
    """One rule per architecture, filtered to the container's uid."""
    output: list[str] = []
    ok = True
    for arch in ("b64", "b32"):
        done = _run(
            auditctl,
            "-a",
            "always,exit",
            "-F",
            f"arch={arch}",
            "-F",
            f"uid={CONTAINER_UID}",
            "-S",
            ",".join(WATCHED),
            "-k",
            AUDIT_KEY,
        )
        output.append(f"[{arch}] rc={done.returncode} {(done.stdout + done.stderr).strip()[:200]}")
        # b32 is absent on an arm64 kernel and its failure is not the observer's
        ok = ok and (done.returncode == 0 or arch == "b32")
    return Step("install_rules", ok, f"uid={CONTAINER_UID} {','.join(WATCHED)}", "\n".join(output))


def marker(uid: int = CONTAINER_UID) -> Step:
    """A positive control for the rules themselves.

    A process at the container's uid that makes a watched syscall (`execve`).
    If the kernel does not record *this*, the rule set is not working and no
    conclusion may be drawn about the container; if it records this and not the
    container, the container is not running at the uid the rule filters on.
    Without it a run of zero records means nothing at all, and the first two
    runs of this observer are exactly that."""
    setpriv = shutil.which("setpriv")
    if setpriv is None:
        return Step("marker", False, "setpriv is not installed", "")
    done = _run(setpriv, f"--reuid={uid}", f"--regid={uid}", "--clear-groups", "/bin/true")
    return Step(
        "marker",
        done.returncode == 0,
        f"execve /bin/true as uid {uid}",
        (done.stdout + done.stderr)[:300],
    )


def rules_now(auditctl: str) -> str:
    done = _run(auditctl, "-l")
    return (done.stdout + done.stderr).strip()[:1200]


def install_unfiltered_rule(auditctl: str) -> Step:
    """`execve`, any uid: the broadest rule this observer will ever install."""
    done = _run(
        auditctl, "-a", "always,exit", "-F", "arch=b64", "-S", "execve", "-k", AUDIT_KEY_ANY
    )
    return Step(
        "install_unfiltered_rule",
        done.returncode == 0,
        "execve, no uid filter",
        (done.stdout + done.stderr)[:300],
    )


def raw_log_mentions(key: str) -> int:
    """How many lines of the raw audit log carry ``key`` -- ausearch not involved."""
    log = Path("/var/log/audit/audit.log")
    if not log.is_file():
        return -1
    try:
        with log.open("rb") as handle:
            return sum(1 for line in handle if key.encode() in line)
    except OSError:
        return -1


def remove_rules(auditctl: str) -> Step:
    done = _run(auditctl, "-D")
    return Step("remove_rules", done.returncode == 0, output=(done.stdout + done.stderr)[:400])


def collect(ausearch: str, since: str) -> tuple[list[dict[str, str]], str]:
    """Every audited syscall of the container's uid since ``since``, as records."""
    done = _run(ausearch, "-k", AUDIT_KEY, "-ts", since, "--format", "csv")
    if done.returncode not in (0, 1):  # 1 is ausearch's "no matches"
        return [], (done.stdout + done.stderr)[:800]
    rows: list[dict[str, str]] = []
    lines = [line for line in done.stdout.splitlines() if line.strip()]
    if not lines:
        return rows, ""
    header = [name.strip().strip('"').upper() for name in lines[0].split(",")]
    for line in lines[1:]:
        values = [value.strip().strip('"') for value in line.split(",")]
        if len(values) == len(header):
            rows.append(dict(zip(header, values, strict=True)))
    return rows, ""


def cmd_probe(args: argparse.Namespace) -> int:
    found = probe()
    payload = {
        "schema_version": OBSERVER_SCHEMA_VERSION,
        "generated": datetime.now(UTC).isoformat(),
        "probe": asdict(found),
        "feasible": found.feasible,
        "blocked_by": found.blocked_by(),
    }
    if args.json:
        args.json.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=1, sort_keys=True))
    return 0 if found.feasible else 3


def cmd_arm(args: argparse.Namespace) -> int:
    """Install the rules and print the mark `collect` will search from."""
    found = probe()
    if not found.feasible:
        print(found.blocked_by(), file=sys.stderr)
        return 3
    mark = datetime.now().strftime("%H:%M:%S")
    step = install_rules(found.auditctl)
    broad = install_unfiltered_rule(found.auditctl)
    control = marker()
    payload = {
        "schema_version": OBSERVER_SCHEMA_VERSION,
        "probe": asdict(found),
        "armed": step.ok,
        "since": mark,
        "step": asdict(step),
        "marker": asdict(control),
        "unfiltered_rule": asdict(broad),
        "rules_after_arming": rules_now(found.auditctl),
    }
    if args.json:
        args.json.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(mark)
    return 0 if step.ok else 4


def cmd_collect(args: argparse.Namespace) -> int:
    """Read the kernel's record, compare it with the harness's, and disarm."""
    found = probe()
    if not found.feasible:
        print(found.blocked_by(), file=sys.stderr)
        return 3
    rules_before = rules_now(found.auditctl)
    unfiltered = _run(found.ausearch, "-k", AUDIT_KEY)
    any_uid = _run(found.ausearch, "-k", AUDIT_KEY_ANY)
    raw_key = raw_log_mentions(AUDIT_KEY)
    raw_any = raw_log_mentions(AUDIT_KEY_ANY)
    log = Path("/var/log/audit/audit.log")
    records, error = collect(found.ausearch, args.since)
    steps = [
        Step("collect", not error, f"{len(records)} kernel record(s)", error or ""),
        Step(
            "diagnostics",
            True,
            f"rules still loaded: {bool(rules_before and 'No rules' not in rules_before)}; "
            f"audit.log {log.stat().st_size if log.is_file() else 'absent'} bytes; "
            f"ausearch by key rc={unfiltered.returncode}, "
            f"{len(unfiltered.stdout.splitlines())} line(s); "
            f"ausearch for the no-uid rule rc={any_uid.returncode}, "
            f"{len(any_uid.stdout.splitlines())} line(s); "
            f"raw log lines carrying the keys: {raw_key} / {raw_any}",
            (rules_before + "\n" + (unfiltered.stdout + unfiltered.stderr)[:600])[:1400],
        ),
        remove_rules(found.auditctl),
    ]
    claim: dict[str, object] = {}
    if args.matrix and args.matrix.is_file():
        text = args.matrix.read_text(encoding="utf-8", errors="replace")
        claim = {
            "rows": text.count("\n| "),
            "says_certified": "certified" in text.lower(),
            "path": str(args.matrix),
        }
    syscalls: dict[str, int] = {}
    for record in records:
        name = record.get("SYSCALL") or record.get("SYSCALL_NAME") or "?"
        syscalls[name] = syscalls.get(name, 0) + 1
    network = [r for r in records if (r.get("SYSCALL") or "") in {"connect", "socket"}]
    succeeded = [r for r in network if (r.get("SUCCESS") or "").lower() == "yes"]
    observed = bool(records)
    payload = {
        "schema_version": OBSERVER_SCHEMA_VERSION,
        "generated": datetime.now(UTC).isoformat(),
        "probe": asdict(found),
        "feasible": True,
        "since": args.since,
        "watched": list(WATCHED),
        "container_uid": CONTAINER_UID,
        "steps": [asdict(step) for step in steps],
        "records": len(records),
        "syscalls": dict(sorted(syscalls.items())),
        "network_attempts": len(network),
        "network_attempts_that_succeeded": len(succeeded),
        "harness_claim": claim,
        "verdict": "OBSERVED" if observed else "NOTHING_RECORDED",
        "what_this_does_not_show": (
            "audit records what its rules match. This says nothing about syscalls "
            "outside the watched list, and a rule set is a list of names someone chose."
        ),
    }
    if args.json:
        args.json.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=1, sort_keys=True))
    return 0 if observed else 4


def cmd_run(args: argparse.Namespace) -> int:
    found = probe()
    steps: list[Step] = []
    if not found.feasible:
        payload = {
            "schema_version": OBSERVER_SCHEMA_VERSION,
            "generated": datetime.now(UTC).isoformat(),
            "probe": asdict(found),
            "feasible": False,
            "blocked_by": found.blocked_by(),
            "verdict": "INSUFFICIENT",
        }
        if args.json:
            args.json.write_text(
                json.dumps(payload, indent=1, sort_keys=True) + "\n", encoding="utf-8"
            )
        print(json.dumps(payload, indent=1, sort_keys=True))
        return 3

    since = datetime.now().strftime("%H:%M:%S")
    steps.append(install_rules(found.auditctl))
    matrix_output = ""
    records: list[dict[str, str]] = []
    try:
        # the matrix, run exactly as `red-team.yml` runs it -- the observer
        # changes nothing about the product's own invocation
        done = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "release" / "redteam.py"), "--record",
             str(args.matrix)],
            capture_output=True,
            text=True,
            cwd=str(ROOT),
        )
        matrix_output = (done.stdout + done.stderr)[-4000:]
        steps.append(Step("matrix", done.returncode == 0, f"exit {done.returncode}"))
        records, error = collect(found.ausearch, since)
        steps.append(
            Step("collect", not error, f"{len(records)} kernel record(s)", error or "")
        )
    finally:
        steps.append(remove_rules(found.auditctl))

    syscalls: dict[str, int] = {}
    for record in records:
        name = record.get("SYSCALL") or record.get("SYSCALL_NAME") or "?"
        syscalls[name] = syscalls.get(name, 0) + 1
    # The comparison. `--network none` means a `connect` inside the container
    # cannot reach anything; what the kernel can say is whether the attempt was
    # made and what it returned, and whether anything the harness never
    # mentioned happened at the container's uid.
    connects = [r for r in records if (r.get("SYSCALL") or "") in {"connect", "socket"}]
    succeeded = [r for r in connects if (r.get("SUCCESS") or "").lower() == "yes"]
    payload = {
        "schema_version": OBSERVER_SCHEMA_VERSION,
        "generated": datetime.now(UTC).isoformat(),
        "probe": asdict(found),
        "feasible": True,
        "watched": list(WATCHED),
        "container_uid": CONTAINER_UID,
        "steps": [asdict(step) for step in steps],
        "records": len(records),
        "syscalls": dict(sorted(syscalls.items())),
        "network_attempts": len(connects),
        "network_attempts_that_succeeded": len(succeeded),
        "matrix_tail": matrix_output,
        "verdict": (
            "OBSERVED"
            if records and all(step.ok for step in steps if step.name != "remove_rules")
            else "INCONCLUSIVE"
        ),
        "what_this_does_not_show": (
            "audit records what its rules match. This says nothing about syscalls "
            "outside the watched list, and a rule set is a list of names someone chose."
        ),
    }
    if args.json:
        args.json.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in payload.items() if k != "matrix_tail"}, indent=1))
    return 0 if payload["verdict"] == "OBSERVED" else 4


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    probe_cmd = sub.add_parser("probe")
    probe_cmd.add_argument("--json", type=Path)
    probe_cmd.set_defaults(func=cmd_probe)
    run_cmd = sub.add_parser("run")
    run_cmd.add_argument("--json", type=Path)
    run_cmd.add_argument("--matrix", type=Path, default=Path("redteam-observed.md"))
    run_cmd.set_defaults(func=cmd_run)
    arm = sub.add_parser("arm")
    arm.add_argument("--json", type=Path)
    arm.set_defaults(func=cmd_arm)
    gather = sub.add_parser("collect")
    gather.add_argument("--since", required=True, help="the mark `arm` printed")
    gather.add_argument("--json", type=Path)
    gather.add_argument("--matrix", type=Path, default=None)
    gather.set_defaults(func=cmd_collect)
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
