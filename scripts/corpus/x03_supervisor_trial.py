"""Committed synthetic-only feasibility trial; never a product or corpus verdict."""

import json
import os
import subprocess
from pathlib import Path

from attest.benchmark.artifacts import sha256_bytes, write_canonical_json

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / ".attest/x03-supervisor-trial"
BUILDER = "python@sha256:94c362db08c5b38857943d31b10558ff1856e918605c474d205d72a534929d4e"


def main() -> None:
    WORK.mkdir(parents=True, exist_ok=False)
    env = dict(os.environ)
    source = ROOT / "scripts/corpus/git_query_supervisor.c"
    (WORK / source.name).write_bytes(source.read_bytes())
    (WORK / "Dockerfile").write_text(
        f"FROM {BUILDER}\nCOPY git_query_supervisor.c /supervisor.c\n"
        "RUN cc -std=c11 -O2 -Wall -Wextra -Werror /supervisor.c -lcrypto -o /supervisor\n"
    )
    with (WORK / "build.log").open("wb") as output:
        subprocess.run(["docker", "build", "-t", "attest-gq-prototype", str(WORK)],
                       env=env, stdout=output, stderr=subprocess.STDOUT, check=True, timeout=180)
    image = subprocess.check_output(
        ["docker", "image", "inspect", "--format", "{{.Id}}", "attest-gq-prototype"],
        env=env, text=True, timeout=30,
    ).strip()
    hashes = subprocess.check_output(
        ["docker", "run", "--rm", "--network=none", "--entrypoint=sha256sum", image,
         "/usr/local/bin/python3.10", "/bin/sh", "/usr/bin/git"],
        env=env, text=True, timeout=30,
    )
    digests = [line.split()[0] for line in hashes.splitlines()]
    probes = {
        "literal_query": "import subprocess\nsubprocess.run('git log --pretty=format:%ct --quiet -1 HEAD', shell=True, capture_output=True, text=True)\n",
        "different_shell_command": "import subprocess\nsubprocess.run('echo unauthorized', shell=True)\n",
        "direct_native_exec": "import os\nos.execv('/bin/sh', ['/bin/sh', '-c', 'echo unauthorized'])\n",
        "changed_environment": "import subprocess,os\nos.environ['ENV']='/tmp/injected'\nsubprocess.run('git log --pretty=format:%ct --quiet -1 HEAD',shell=True)\n",
    }
    record = {
        "code_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "driver_sha256": sha256_bytes(Path(__file__).read_bytes()),
        "supervisor_sha256": sha256_bytes(source.read_bytes()),
        "image": image, "executable_sha256": digests, "rows": [], "model_api_spend_usd": 0,
    }
    for name, text in probes.items():
        directory = WORK / name
        directory.mkdir()
        (directory / "probe.py").write_text(text)
        command = [
            "docker", "run", "--rm", "--network=none", "--read-only", "--user=65534:65534",
            "--cap-drop=ALL", "--security-opt=no-new-privileges", "--pids-limit=16",
            "--memory=256m", "--cpus=1", "--tmpfs=/tmp:rw,nosuid,nodev,noexec,size=16m",
            "--mount", f"type=bind,src={directory},dst=/attest/tree,readonly",
            "--workdir=/attest/tree", "--entrypoint=/usr/bin/env", image, "-i",
            "PATH=/usr/bin", "HOME=/tmp", "LANG=C.UTF-8", "PYTHONDONTWRITEBYTECODE=1",
            "/supervisor", *digests, "15", "--", "/usr/local/bin/python3.10", "-I",
            "/attest/tree/probe.py",
        ]
        run = subprocess.run(command, env=env, capture_output=True, timeout=30)
        (directory / "stdout.txt").write_bytes(run.stdout)
        (directory / "stderr.txt").write_bytes(run.stderr)
        record["rows"].append({"case": name, "exit_code": run.returncode,
                               "stdout_sha256": sha256_bytes(run.stdout),
                               "stderr_sha256": sha256_bytes(run.stderr)})
        write_canonical_json(WORK / "result.json", record)
        print(name, run.returncode, flush=True)
    print(json.dumps(record, sort_keys=True))


if __name__ == "__main__":
    main()
