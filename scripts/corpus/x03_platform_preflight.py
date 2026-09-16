"""Read kernel capabilities in the existing isolated image; never run corpus code."""

import argparse
import json
import os
import subprocess
from pathlib import Path

from attest.benchmark.artifacts import sha256_bytes, write_canonical_json

IMAGE = "python@sha256:68d914ec641a0b69267ce65184d000a2bc3a9ee2590ab702b82250ab2385735a"
PROBE = r'''
import ctypes, json, os, platform
from pathlib import Path
libc = ctypes.CDLL(None, use_errno=True)
architecture = platform.machine()
number = {"aarch64": 277, "x86_64": 317}.get(architecture)
sizes = (ctypes.c_ushort * 3)()
ctypes.set_errno(0)
seccomp = libc.syscall(number, 3, 0, ctypes.byref(sizes)) if number else -1
seccomp_errno = ctypes.get_errno()
ctypes.set_errno(0)
landlock = libc.syscall(444, None, 0, 1) if number else -1
landlock_errno = ctypes.get_errno()
child = os.fork()
if child == 0:
    os._exit(0 if libc.ptrace(0, 0, None, None) == 0 else 1)
_, status = os.waitpid(child, 0)
fields = {}
for line in Path("/proc/self/status").read_text().splitlines():
    key, _, value = line.partition(":")
    if key in {"NoNewPrivs", "Seccomp", "CapEff"}:
        fields[key] = value.strip()
print(json.dumps({"architecture": architecture, "kernel": platform.release(),
    "seccomp_notification_sizes_rc": seccomp, "seccomp_errno": seccomp_errno,
    "notification_sizes": list(sizes), "landlock_abi": landlock,
    "landlock_errno": landlock_errno, "ptrace_child_exit": os.waitstatus_to_exitcode(status),
    "process_status": fields}))
'''


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--docker-config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    env = {**os.environ, "DOCKER_CONFIG": str(args.docker_config.resolve())}
    env["DOCKER_HOST"] = subprocess.check_output(
        ["docker", "context", "inspect", "--format", "{{.Endpoints.docker.Host}}"],
        text=True, timeout=30,
    ).strip()
    command = [
        "docker", "run", "--rm", "--network=none", "--read-only", "--user=65534:65534",
        "--cap-drop=ALL", "--security-opt=no-new-privileges", "--pids-limit=16",
        "--memory=256m", "--cpus=1", "--tmpfs=/tmp:rw,nosuid,nodev,noexec,size=16m",
        "--entrypoint=python3", IMAGE, "-I", "-c", PROBE,
    ]
    run = subprocess.run(command, env=env, capture_output=True, text=True, timeout=30)
    (args.output / "stdout.txt").write_text(run.stdout)
    (args.output / "stderr.txt").write_text(run.stderr)
    record = {
        "code_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "driver_sha256": sha256_bytes(Path(__file__).read_bytes()), "image": IMAGE,
        "exit_code": run.returncode, "model_api_spend_usd": 0,
        "probe_sha256": sha256_bytes(PROBE.encode()),
        "capabilities": json.loads(run.stdout) if run.returncode == 0 else None,
    }
    write_canonical_json(args.output / "result.json", record)
    print(json.dumps(record, sort_keys=True))


if __name__ == "__main__":
    main()
