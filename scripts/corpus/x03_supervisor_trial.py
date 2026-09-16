"""Committed synthetic-only feasibility trial; never a product or corpus verdict."""

import argparse
import json
import os
import subprocess
from pathlib import Path
from uuid import uuid4

from attest.benchmark.artifacts import sha256_bytes, write_canonical_json

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / ".attest/x03-supervisor-trial"
BUILDER = "python@sha256:94c362db08c5b38857943d31b10558ff1856e918605c474d205d72a534929d4e"


def run_container(
    arguments: list[str], env: dict[str, str], directory: Path,
) -> subprocess.CompletedProcess[bytes]:
    """Retain every attempt and remove its daemon-side container, even on timeout."""
    name = "attest-gq-" + uuid4().hex
    record: dict = {"container_name": name, "status": "started"}
    write_canonical_json(directory / "container.json", record)
    stdout, stderr = b"", b""
    try:
        result = subprocess.run(
            ["docker", "run", "--name", name, *arguments], env=env,
            capture_output=True, timeout=30,
        )
        stdout, stderr = result.stdout, result.stderr
        record.update(status="exited", exit_code=result.returncode)
    except (OSError, subprocess.TimeoutExpired) as exc:
        record["status"] = type(exc).__name__
        if isinstance(exc, subprocess.TimeoutExpired):
            stdout, stderr = exc.output or b"", exc.stderr or b""
        raise
    finally:
        # Cleanup is required even if saving the attempt's output fails.
        try:
            (directory / "stdout.txt").write_bytes(stdout[:65536])
            (directory / "stderr.txt").write_bytes(stderr[:65536])
            record["output_truncated"] = len(stdout) > 65536 or len(stderr) > 65536
            write_canonical_json(directory / "container.json", record)
        finally:
            try:
                cleanup = subprocess.run(
                    ["docker", "rm", "-f", name], env=env, capture_output=True, timeout=30,
                )
                record["cleanup_exit_code"] = cleanup.returncode
            except (OSError, subprocess.TimeoutExpired) as exc:
                record["cleanup_error"] = type(exc).__name__
                raise
            finally:
                write_canonical_json(directory / "container.json", record)
    if cleanup.returncode:
        raise RuntimeError("container cleanup unconfirmed; inspect container.json")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=WORK)
    work = parser.parse_args().output.resolve()
    work.relative_to(ROOT)
    work.mkdir(parents=True, exist_ok=False)
    env = dict(os.environ)
    source = ROOT / "scripts/corpus/git_query_supervisor.c"
    (work / source.name).write_bytes(source.read_bytes())
    (work / "Dockerfile").write_text(
        f"FROM {BUILDER}\nCOPY git_query_supervisor.c /supervisor.c\n"
        "RUN cc -std=c11 -O2 -Wall -Wextra -Werror /supervisor.c -lcrypto -o /supervisor\n"
    )
    with (work / "build.log").open("wb") as output:
        subprocess.run(["docker", "build", "-t", "attest-gq-prototype", str(work)],
                       env=env, stdout=output, stderr=subprocess.STDOUT, check=True, timeout=180)
    image = subprocess.check_output(
        ["docker", "image", "inspect", "--format", "{{.Id}}", "attest-gq-prototype"],
        env=env, text=True, timeout=30,
    ).strip()
    digest_directory = work / "executable-digests"
    digest_directory.mkdir()
    digest_run = run_container(
        ["--network=none", "--entrypoint=sha256sum", image,
         "/usr/local/bin/python3.10", "/bin/sh", "/usr/bin/git"], env, digest_directory,
    )
    digest_run.check_returncode()
    hashes = digest_run.stdout.decode()
    digests = [line.split()[0] for line in hashes.splitlines()]
    query = "git log --pretty=format:%ct --quiet -1 HEAD"
    probes = {
        "literal_query": (
            "import subprocess\n"
            f"subprocess.run({query!r}, shell=True, capture_output=True, text=True)\n"
        ),
        "different_shell_command": (
            "import subprocess\nsubprocess.run('echo unauthorized', shell=True)\n"
        ),
        "direct_native_exec": (
            "import os\nos.execv('/bin/sh', ['/bin/sh', '-c', 'echo unauthorized'])\n"
        ),
        "changed_environment": (
            "import subprocess,os\nos.environ['ENV']='/tmp/injected'\n"
            f"subprocess.run({query!r},shell=True)\n"
        ),
    }
    record = {
        "code_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "driver_sha256": sha256_bytes(Path(__file__).read_bytes()),
        "supervisor_sha256": sha256_bytes(source.read_bytes()),
        "image": image, "executable_sha256": digests, "rows": [], "model_api_spend_usd": 0,
    }
    for name, text in probes.items():
        directory = work / name
        directory.mkdir()
        (directory / "probe.py").write_text(text)
        command = [
            "--network=none", "--read-only", "--user=65534:65534",
            "--cap-drop=ALL", "--security-opt=no-new-privileges", "--pids-limit=16",
            "--memory=256m", "--cpus=1", "--tmpfs=/tmp:rw,nosuid,nodev,noexec,size=16m",
            "--mount", f"type=bind,src={directory},dst=/attest/tree,readonly",
            "--workdir=/attest/tree", "--entrypoint=/usr/bin/env", image, "-i",
            "PATH=/usr/bin", "HOME=/tmp", "LANG=C.UTF-8", "PYTHONDONTWRITEBYTECODE=1",
            "/supervisor", *digests, "15", "--", "/usr/local/bin/python3.10", "-I",
            "/attest/tree/probe.py",
        ]
        run = run_container(command, env, directory)
        record["rows"].append({
            "case": name, "exit_code": run.returncode,
            "stdout_sha256": sha256_bytes((directory / "stdout.txt").read_bytes()),
            "stderr_sha256": sha256_bytes((directory / "stderr.txt").read_bytes()),
        })
        write_canonical_json(work / "result.json", record)
        print(name, run.returncode, flush=True)
    print(json.dumps(record, sort_keys=True))


if __name__ == "__main__":
    main()
