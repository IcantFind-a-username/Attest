"""e05-external-v2: the free evaluability probe over the candidate population.

Owner authorisation 2 of 2026-09-13. Before the second batch of external pull
requests is selected, every candidate repository is asked one thing the paid run
would otherwise pay to learn: **does its default-branch tip build into the
product's own reproduction image, and does its top-level package import inside
that image?** The probe is the held-out corpus's (`heldout_v2.py`, D-186/D-213):
the tree is archived out of the clone, `ensure_image` builds the image the
reproduction would run in, and pytest collects a stub that imports the tree's
own packages, in the same container shape the reproduction uses. No model, no
network for the tree, $0.00.

The population of the study is the first `keep` candidates, in the owner's
order, whose probe passes; the rest are recorded with their reason. The protocol
is frozen only after this file exists, so the selection rule reads the probe
and the probe never reads an outcome.

    python scripts/corpus/e05_probe.py --study e05-external-v2 --clones .attest/corpora/e05v2
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "corpus"))

from heldout_v2 import probe_stub_source, stub_packages  # noqa: E402

STUDIES = ROOT / "benchmarks" / "studies"


def _clone_name(repository: str) -> str:
    return repository.split("/")[-1].lower().lstrip("-")


def probe_tree(worktree: Path, sha: str, *, timeout_s: float) -> dict[str, object]:
    """Build the product's image for the tree at ``sha`` and import its packages in it."""
    from attest.execution.container_images import BootstrapFailed, ensure_image, project_python
    from attest.review.executor import RUN_DIR_NAME, project_roots
    from attest.review.workdir import work_parent

    started = time.monotonic()
    staging = Path(tempfile.mkdtemp(prefix="attest-e05-probe-", dir=work_parent()))
    record: dict[str, object] = {"sha": sha}
    try:
        archive = subprocess.run(
            ["git", "-C", str(worktree), "archive", sha], capture_output=True, check=False
        )
        if archive.returncode != 0:
            record.update(stage="archive", ok=False,
                          reason=archive.stderr.decode("utf-8", "replace")[-300:])
            return record
        tree = staging / "tree"
        tree.mkdir()
        subprocess.run(["tar", "-x", "-C", str(tree)], input=archive.stdout, check=True)
        version, reason = project_python(tree)
        record.update(project_python=version, project_python_reason=reason)
        if "outside" in reason:
            record.update(stage="interpreter", ok=False, reason=reason)
            return record
        try:
            image = ensure_image(tree, remaining_s=timeout_s)
        except BootstrapFailed as exc:
            record.update(stage="image", ok=False, reason=str(exc)[-400:])
            return record
        record.update(image=image.reference, image_cached=image.cached)
        run_dir = tree / RUN_DIR_NAME
        run_dir.mkdir(exist_ok=True)
        packages = stub_packages(tree)
        record["stub_packages"] = packages
        (run_dir / "test_repro.py").write_text(probe_stub_source(tree), encoding="utf-8")
        collect = subprocess.run(
            [
                "docker", "run", "--rm", "--network", "none", "--read-only",
                "--user", "65534:65534", "--cap-drop", "ALL",
                "--security-opt", "no-new-privileges",
                "--tmpfs", "/tmp:rw,nosuid,size=512m",
                "--mount", f"type=bind,src={tree},dst=/attest/tree,readonly",
                "--workdir", "/attest/tree", "--entrypoint", "/usr/bin/env",
                image.reference,
                "-i", "PATH=/usr/local/bin:/usr/bin:/bin", "HOME=/tmp", "TMPDIR=/tmp",
                "PYTEST_DISABLE_PLUGIN_AUTOLOAD=1", "PYTHONSAFEPATH=1",
                "PYTHONDONTWRITEBYTECODE=1", "OPENBLAS_NUM_THREADS=1", "OMP_NUM_THREADS=1",
                "MKL_NUM_THREADS=1",
                "PYTHONPATH=" + ":".join(
                    root.replace("{tree}", "/attest/tree") for root in project_roots(tree)
                ),
                "python3", "-m", "pytest", "-q", f"/attest/tree/{RUN_DIR_NAME}/test_repro.py",
                "--collect-only", "--rootdir", "/attest/tree", "--confcutdir", "/attest/tree",
                "-p", "no:cacheprovider",
            ],
            capture_output=True, text=True, timeout=timeout_s,
        )
        tail = (collect.stdout or "")[-4000:]
        collected = 0
        for line in reversed(tail.splitlines()):
            words = line.split()
            if len(words) >= 2 and words[1].startswith("test") and words[0].isdigit():
                collected = int(words[0])
                break
        record.update(
            stage="collect", exit_code=collect.returncode, collected=collected,
            ok=collected > 0 and bool(packages),
            reason="" if collected > 0 and packages else (
                "no top-level package to import" if not packages
                else f"exit {collect.returncode}: " + (collect.stdout or collect.stderr)[-300:]
            ),
            elapsed_s=round(time.monotonic() - started, 1),
        )
        return record
    except subprocess.TimeoutExpired:
        record.update(stage="collect", ok=False, reason=f"collect exceeded {timeout_s:.0f}s")
        return record
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study", default="e05-external-v2")
    parser.add_argument("--clones", default=str(ROOT / ".attest" / "corpora" / "e05v2"))
    parser.add_argument("--timeout", type=float, default=1200.0)
    args = parser.parse_args(argv)
    study = STUDIES / args.study
    candidates = json.loads((study / "candidates.json").read_text(encoding="utf-8"))
    keep = int(candidates.get("keep", 6))
    rows: list[dict[str, object]] = []
    kept: list[str] = []
    for repository in candidates["candidates"]:
        clone = Path(args.clones) / _clone_name(repository)
        row: dict[str, object] = {"repository": repository}
        if not (clone / ".git").is_dir():
            row.update(ok=False, stage="clone", reason=f"no clone at {clone}")
        else:
            tip = subprocess.run(
                ["git", "-C", str(clone), "rev-parse", "HEAD"], capture_output=True, text=True
            ).stdout.strip()
            row.update(probe_tree(clone, tip, timeout_s=args.timeout))
        if row.get("ok") and len(kept) < keep:
            kept.append(repository)
            row["kept"] = True
        else:
            row["kept"] = False
            if row.get("ok"):
                row["reason"] = f"passed, but the first {keep} passing candidates were already kept"
        rows.append(row)
        print(json.dumps(row), flush=True)
    payload = {
        "recorded_at": datetime.now(UTC).isoformat(),
        "keep": keep,
        "population": kept,
        "probe": rows,
    }
    (study / "probe.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"kept {len(kept)} of {len(rows)} candidates -> {study / 'probe.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
