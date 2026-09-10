"""D-191 held-out corpus rebuild: supported-interpreter cases for `G-RECALL-002`.

D-186 turned 9 of the 16 crash-class held-out cases into stated refusals, so the
gate's eligible-and-supported denominator fell to **7** and two of the four
receipts its number rested on came from a `pytest` tree the product can no longer
run. Seven cases cannot test a >=70% bar. This driver rebuilds the population
from the *same* held-out slice -- never the dev slice, never a re-split -- keeping
only instances whose own manifests declare an interpreter the product supports,
and it decides eligibility **before** anything is bought.

  screen   free, no docker. For every held-out instance whose upstream clone is
           present, read `setup.py` / `setup.cfg` / `pyproject.toml` at the
           instance's `base_commit` with `git show` and apply `project_python`'s
           own rule. Keep the instances whose declaration selects an interpreter
           inside 3.10-3.13; the rest are exactly D-186's refusal and are not
           bought.
  probe    free, docker only, no model call. Build the case, build the image the
           product itself would build for the *base* tree, and run a
           collect-only inside it under the product's own isolation flags. The
           collected file imports every top-level package the tree defines
           (D-213), so a project that will not import under the dependencies the
           image resolved is refused here rather than three paid container runs
           later. A case is **evaluable** when the image builds, the project
           imports and pytest collects at least one test.
  plan     write the corpus file from the probe results, recording each
           instance's commit.
  run      paid. One factory review per planned case (`--k 5 --budget 1.00`).
  table    the crash-class recall table with its Wilson interval.

Paid: `run` only. Reserve in DEVSPEND.md first.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "corpus"))
sys.path.insert(0, str(ROOT / "src"))

from driver_budget import DriverCap  # noqa: E402

CORPUS = ROOT / ".attest" / "corpora" / "swebench-verified"
WORK = ROOT / ".attest" / "corpora" / "swebench"
RESULTS = WORK / "results"
CASES = WORK / "cases"
UPSTREAM = WORK / "upstream"
SPLIT = ROOT / "benchmarks" / "attest-v2" / "splits" / "swebench-verified-v1.json"

# the corpus this driver owns, under .attest/corpora as AGENTS.md section 7 requires
CORPUS_DIR = ROOT / ".attest" / "corpora" / "heldout-supported-v1"
SCREEN = CORPUS_DIR / "screen.json"
PROBE = CORPUS_DIR / "probe.json"
PLAN = CORPUS_DIR / "plan.json"

MANIFEST_NAMES = ("setup.py", "setup.cfg", "pyproject.toml")
RESULTS_SUFFIX = ".v2"
K = 5
BUDGET = 1.00


def _instances() -> dict[str, dict]:
    rows = {}
    for line in (CORPUS / "instances.jsonl").read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        rows[row["instance_id"]] = row
    return rows


def _held_out() -> list[str]:
    return list(json.loads(SPLIT.read_text(encoding="utf-8"))["held_out"])


def _upstream_dir(repo: str) -> Path:
    return UPSTREAM / repo.replace("/", "__")


def _show(repo_dir: Path, sha: str, path: str) -> str | None:
    done = subprocess.run(
        ["git", "-C", str(repo_dir), "show", f"{sha}:{path}"], capture_output=True, text=True
    )
    return done.stdout if done.returncode == 0 else None


def cmd_screen(args: argparse.Namespace) -> int:
    """The declaration screen, verbatim from `project_python`'s rule."""
    from attest.execution.container_images import (
        _CLASSIFIER_RE,
        _REQUIRES_PYTHON_RE,
        AVAILABLE_PYTHONS,
        PRIMARY_PYTHON,
    )

    def select(texts: list[str]) -> tuple[str, str]:
        declared: list[int] = []
        lower: list[int] = []
        for text in texts:
            declared.extend(int(m) for m in _CLASSIFIER_RE.findall(text))
            lower.extend(int(m) for m in _REQUIRES_PYTHON_RE.findall(text))
        floor = max(lower) if lower else None
        ceiling = max(declared) if declared else None
        for version in AVAILABLE_PYTHONS:
            minor = int(version.split(".")[1])
            if ceiling is not None and minor > ceiling:
                continue
            if floor is not None and minor < floor:
                continue
            if ceiling is None and floor is None:
                continue
            reason = []
            if ceiling is not None:
                reason.append(f"classifiers up to 3.{ceiling}")
            if floor is not None:
                reason.append(f"declared floor >= 3.{floor}")
            return version, "; ".join(reason)
        if floor is not None or ceiling is not None:
            return PRIMARY_PYTHON, "declared range outside 3.10-3.13; primary"
        return PRIMARY_PYTHON, "no declaration found; primary"

    instances = _instances()
    rows = []
    absent: Counter[str] = Counter()
    for instance_id in _held_out():
        row = instances[instance_id]
        repo_dir = _upstream_dir(row["repo"])
        if not (repo_dir / ".git").is_dir():
            absent[row["repo"]] += 1
            continue
        texts = [
            text
            for name in MANIFEST_NAMES
            if (text := _show(repo_dir, row["base_commit"], name)) is not None
        ]
        version, reason = select(texts)
        rows.append(
            {
                "instance_id": instance_id,
                "repo": row["repo"],
                "base_commit": row["base_commit"],
                "created_at": row.get("created_at"),
                "difficulty": row.get("difficulty"),
                "python": version,
                "reason": reason,
                "manifests_read": len(texts),
                "supported": "outside" not in reason and "no declaration" not in reason,
            }
        )
    CORPUS_DIR.mkdir(parents=True, exist_ok=True)
    SCREEN.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    kept = [r for r in rows if r["supported"]]
    print(f"screened {len(rows)} held-out instances; not cloned: {dict(absent)}")
    print(f"declaration inside 3.10-3.13: {len(kept)}")
    for repo, n in Counter(r["repo"] for r in kept).most_common():
        print(f"  {n:4d}  {repo}")
    print(f"-> {SCREEN}")
    return 0


def _build_case(instance_id: str) -> Path:
    case = CASES / instance_id
    if not (case / "manifest.json").is_file():
        subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "corpus" / "swebench_pilot.py"),
                "build",
                instance_id,
                "--no-env",
            ],
            check=False,
        )
    return case


# --- the evaluability stub (D-213) -----------------------------------------
# The stub `probe` collects inside the base image. It used to be `assert True`,
# which asked only whether pytest collects; a tree whose own package will not
# import under the dependencies the image resolved passed that and was planned,
# bought, and lost three container runs later as `probe deferred on base`. It
# imports the project now, so that failure is a free refusal in this stage.

_STUB_SKIP_ROOTS = ("tests", "test", "testing")


def stub_packages(tree: Path) -> list[str]:
    """Top-level packages importable from the tree's own import roots.

    Directories with an ``__init__.py`` only: a bare module at the tree root is
    `setup.py` or `conftest.py` as often as it is the project, and a directory
    without one (`doc/`, `ci/`) is not importable at all. The tree's test roots
    are skipped -- the reproduction runs outside the test tree, and a test
    package that will not import says nothing about whether the project will.
    """
    from attest.review.executor import project_roots

    names: set[str] = set()
    for root in project_roots(tree):
        relative = root.replace("{tree}", "").lstrip("/")
        if relative.split("/")[-1] in _STUB_SKIP_ROOTS:
            continue
        directory = tree / relative if relative else tree
        if not directory.is_dir():
            continue
        for entry in sorted(directory.iterdir()):
            if entry.name.startswith((".", "_")) or entry.name in _STUB_SKIP_ROOTS:
                continue
            if entry.is_dir() and (entry / "__init__.py").is_file():
                names.add(entry.name)
    return sorted(names)


def probe_stub_source(tree: Path) -> str:
    """The stub written into the run directory, for this tree.

    A tree that defines no importable package gets the old stub and **says so**
    in its own source: an evaluable verdict that rests on an import check which
    imported nothing must not read like one that did (D-177).
    """
    packages = stub_packages(tree)
    if not packages:
        return (
            "# no top-level package was found in this tree, so this stub imports\n"
            "# nothing and answers only whether pytest collects here\n"
            "def test_attest_probe() -> None:\n"
            "    assert True\n"
        )
    imports = "".join(f"import {name}\n" for name in packages)
    return (
        f"{imports}\n"
        "\n"
        "def test_attest_probe() -> None:\n"
        f"    assert {tuple(packages)!r}\n"
    )


def _probe_one(instance_id: str, timeout_s: float) -> dict:
    """Build the product's own image for the base tree and collect in it.

    The base tree is copied out of the repository first: `workdir` (D-138) moves
    every bind-mount source out of the user's home for a reason, and a probe
    that mounted the worktree would be measuring Docker Desktop rather than the
    project.
    """
    from attest.execution.container_images import BootstrapFailed, ensure_image, project_python
    from attest.review.executor import RUN_DIR_NAME, project_roots
    from attest.review.workdir import work_parent

    case = _build_case(instance_id)
    manifest_path = case / "manifest.json"
    if not manifest_path.is_file():
        return {
            "instance_id": instance_id,
            "stage": "build",
            "ok": False,
            "reason": "case build failed",
        }
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    worktree = case / "repo"
    started = time.monotonic()
    staging = Path(tempfile.mkdtemp(prefix="attest-probe-", dir=work_parent()))
    try:
        base_sha = manifest["base_sha"]
        archive = subprocess.run(
            ["git", "-C", str(worktree), "archive", base_sha],
            capture_output=True,
            check=False,
        )
        if archive.returncode != 0:
            return {
                "instance_id": instance_id,
                "stage": "archive",
                "ok": False,
                "reason": archive.stderr.decode("utf-8", "replace")[-300:],
            }
        tree = staging / "tree"
        tree.mkdir()
        subprocess.run(["tar", "-x", "-C", str(tree)], input=archive.stdout, check=True)
        version, reason = project_python(tree)
        record = {
            "instance_id": instance_id,
            "repo": manifest["repo"],
            "base_commit": manifest.get("base_sha"),
            "head_commit": manifest.get("head_sha"),
            "upstream_base_commit": _instances()[instance_id]["base_commit"],
            "project_python": version,
            "project_python_reason": reason,
        }
        if "outside" in reason:
            record.update(stage="interpreter", ok=False, reason=reason)
            return record
        pins = None
        constraints_path = case / "constraints.txt"
        if constraints_path.is_file():
            pins = constraints_path.read_text(encoding="utf-8")
        record["constraints"] = "constraints.txt" if pins else "none"
        try:
            image = ensure_image(tree, remaining_s=timeout_s, constraints=pins)
        except BootstrapFailed as exc:
            record.update(stage="image", ok=False, reason=str(exc)[-400:])
            return record
        record.update(image=image.reference, image_cached=image.cached)
        # the exact shape the reproduction collects: a stub in the run directory,
        # `rootdir` and `confcutdir` pinned to the tree. That is what D-186's
        # fact (1) turns on -- a `pytest` tree whose own conftest will not load
        # under the chosen interpreter collects nothing here, before any model
        # is called -- and it is *not* the project's whole suite, which the
        # product never collects.
        #
        # D-213: the stub imports the tree's own packages, so this stage also
        # answers *will the project import in this image*, which is what the
        # `assert True` stub was blind to and what nine of the 2026-09-10 run's
        # cases actually died of.
        run_dir = tree / RUN_DIR_NAME
        run_dir.mkdir(exist_ok=True)
        packages = stub_packages(tree)
        record["stub_packages"] = packages
        (run_dir / "test_repro.py").write_text(probe_stub_source(tree), encoding="utf-8")
        collect = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "--network",
                "none",
                "--read-only",
                "--user",
                "65534:65534",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges",
                "--tmpfs",
                "/tmp:rw,nosuid,size=512m",
                "--mount",
                f"type=bind,src={tree},dst=/attest/tree,readonly",
                "--workdir",
                "/attest/tree",
                "--entrypoint",
                "/usr/bin/env",
                image.reference,
                "-i",
                "PATH=/usr/local/bin:/usr/bin:/bin",
                "HOME=/tmp",
                "TMPDIR=/tmp",
                # the reproduction's own environment, not a plainer one: without
                # `PYTEST_DISABLE_PLUGIN_AUTOLOAD` an incompatible pin pulled in
                # by a project's `requirements-dev.txt` fails at plugin import
                # and the probe reports a project the product reviews fine as
                # uncollectable (`psf__requests-5414`, which certifies, did
                # exactly that on the first draft of this probe)
                "PYTEST_DISABLE_PLUGIN_AUTOLOAD=1",
                "PYTHONSAFEPATH=1",
                "PYTHONDONTWRITEBYTECODE=1",
                "OPENBLAS_NUM_THREADS=1",
                "OMP_NUM_THREADS=1",
                "MKL_NUM_THREADS=1",
                "PYTHONPATH="
                + ":".join(
                    root.replace("{tree}", "/attest/tree") for root in project_roots(tree)
                ),
                "python3",
                "-m",
                "pytest",
                "-q",
                f"/attest/tree/{RUN_DIR_NAME}/test_repro.py",
                "--collect-only",
                "--rootdir",
                "/attest/tree",
                "--confcutdir",
                "/attest/tree",
                "-p",
                "no:cacheprovider",
            ],
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
        tail = (collect.stdout or "")[-4000:]
        collected = 0
        for line in reversed(tail.splitlines()):
            words = line.split()
            if len(words) >= 2 and words[1].startswith("test") and words[0].isdigit():
                collected = int(words[0])
                break
        record.update(
            stage="collect",
            exit_code=collect.returncode,
            collected=collected,
            ok=collected > 0,
            reason=""
            if collected > 0
            else f"exit {collect.returncode}: " + (collect.stdout or collect.stderr)[-300:],
            elapsed_s=round(time.monotonic() - started, 1),
        )
        return record
    except subprocess.TimeoutExpired:
        return {
            "instance_id": instance_id,
            "stage": "collect",
            "ok": False,
            "reason": f"collect exceeded {timeout_s:.0f}s",
        }
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def cmd_probe(args: argparse.Namespace) -> int:
    rows = json.loads(SCREEN.read_text(encoding="utf-8"))
    kept = [r for r in rows if r["supported"]]
    if args.repo:
        wanted = set(args.repo.split(","))
        kept = [r for r in kept if r["repo"] in wanted]
    done = {}
    if PROBE.is_file():
        done = {r["instance_id"]: r for r in json.loads(PROBE.read_text(encoding="utf-8"))}
    evaluable = sum(1 for r in done.values() if r.get("ok"))
    for row in kept:
        if evaluable >= args.target:
            print(f"target {args.target} evaluable cases reached; stopping")
            break
        if row["instance_id"] in done and not args.rebuild:
            continue
        print(f"probe {row['instance_id']}", flush=True)
        record = _probe_one(row["instance_id"], args.timeout)
        done[record["instance_id"]] = record
        if record.get("ok"):
            evaluable += 1
        print(
            f"  {'EVALUABLE' if record.get('ok') else 'no'} "
            f"({record.get('stage')}) {str(record.get('reason'))[:160]}",
            flush=True,
        )
        CORPUS_DIR.mkdir(parents=True, exist_ok=True)
        PROBE.write_text(
            json.dumps(sorted(done.values(), key=lambda r: r["instance_id"]), indent=2) + "\n",
            encoding="utf-8",
        )
    print(f"\nevaluable: {evaluable} of {len(done)} probed")
    for stage, n in Counter(
        r.get("stage") for r in done.values() if not r.get("ok")
    ).most_common():
        print(f"  refused at {stage}: {n}")
    return 0


def cmd_plan(_args: argparse.Namespace) -> int:
    probed = json.loads(PROBE.read_text(encoding="utf-8"))
    cases = [
        {
            "instance_id": r["instance_id"],
            "repo": r["repo"],
            "upstream_base_commit": r["upstream_base_commit"],
            "case_base_sha": r["base_commit"],
            "case_head_sha": r["head_commit"],
            "project_python": r["project_python"],
            "project_python_reason": r["project_python_reason"],
            "collected_on_base": r["collected"],
        }
        for r in probed
        if r.get("ok")
    ]
    # Order, fixed here and before any spend: round robin over repositories,
    # each repository's cases by id. The run has a cumulative cap and may stop
    # part way; in plain id order the cap would drop whole repositories off the
    # alphabet's end, and which repositories a sample contains would then be a
    # function of how much the earlier cases happened to cost.
    by_repo: dict[str, list[dict]] = {}
    for case in sorted(cases, key=lambda c: c["instance_id"]):
        by_repo.setdefault(case["repo"], []).append(case)
    ordered: list[dict] = []
    for index in range(max((len(v) for v in by_repo.values()), default=0)):
        for repo in sorted(by_repo):
            if index < len(by_repo[repo]):
                ordered.append(by_repo[repo][index])
    plan = {
        "schema_version": "attest.heldout-supported.v1",
        "decision": "D-191",
        "slice": "held_out",
        "split": str(SPLIT.relative_to(ROOT)),
        "rule": (
            "held-out instances whose own manifests at base_commit select an interpreter "
            "inside 3.10-3.13 (project_python), and whose base tree both builds the "
            "product's image and collects at least one test in it; decided by a free "
            "docker-only probe before any paid run"
        ),
        "order": (
            "round robin over repositories, each repository's cases by instance id; "
            "fixed before the run so a cumulative cap that stops the run early "
            "removes cases evenly rather than removing whole repositories"
        ),
        "k": K,
        "budget_usd": BUDGET,
        "cases": ordered,
    }
    PLAN.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    print(f"{len(cases)} evaluable cases -> {PLAN}")
    for repo, n in Counter(c["repo"] for c in cases).most_common():
        print(f"  {n:4d}  {repo}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    pilot = ROOT / "scripts" / "corpus" / "swebench_pilot.py"
    env = dict(os.environ)
    if args.code:
        env["PYTHONPATH"] = str(Path(args.code) / "src")
        sha = subprocess.run(
            ["git", "-C", args.code, "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
        ).stdout.strip()
        print(f"product code from {args.code} ({sha})", flush=True)
    cap = None if args.cap is None else DriverCap(cap=args.cap, reservation_usd=args.budget)
    only = set(args.only.split(",")) if args.only else None
    for case in plan["cases"]:
        instance_id = case["instance_id"]
        if only is not None and instance_id not in only:
            continue
        result_path = RESULTS / f"{instance_id}{args.results_suffix}.json"
        if result_path.is_file() and not args.rerun:
            continue
        if cap is not None:
            refusal = cap.refusal(instance_id)
            if refusal is not None:
                print(refusal, flush=True)
                break
            cap.start(instance_id)
        print(f"run {instance_id}", flush=True)
        # D-214: the era pins for this case reach the product's image build
        # through the one variable `ensure_image` reads. Set per case and never
        # in a product path.
        case_env = dict(env)
        pins = CASES / instance_id / "constraints.txt"
        if pins.is_file():
            case_env["ATTEST_PIP_CONSTRAINT"] = str(pins)
        else:
            case_env.pop("ATTEST_PIP_CONSTRAINT", None)
        subprocess.run(
            [
                sys.executable,
                str(pilot),
                "run",
                instance_id,
                "--k",
                str(args.k),
                "--budget",
                f"{args.budget:.2f}",
                "--verification-timeout",
                "900",
                "--results-suffix",
                args.results_suffix,
            ],
            check=False,
            env=case_env,
        )
        actual = (
            float(json.loads(result_path.read_text()).get("spend_usd", 0.0))
            if result_path.is_file()
            else None
        )
        if cap is not None:
            cap.settle(actual)
    return 0


def wilson(successes: int, trials: int, z: float = 1.959963985) -> tuple[float, float]:
    """The Wilson score interval. Public because `heldout_compare` calls it:
    the same arithmetic in two files is two things to keep in step (green,
    on PR #31, `attest.structural.duplicate-implementation.v2`)."""
    if trials == 0:
        return (0.0, 1.0)
    p = successes / trials
    denominator = 1 + z * z / trials
    centre = (p + z * z / (2 * trials)) / denominator
    half = z * math.sqrt(p * (1 - p) / trials + z * z / (4 * trials * trials)) / denominator
    return (max(0.0, centre - half), min(1.0, centre + half))


def cmd_table(args: argparse.Namespace) -> int:
    """The crash-class table, denominated the way D-158 requires.

    A case is classified by **what its own run observed**, never in advance:

      refused          a stated refusal before any evidence could exist -- the
                       interpreter range, an image that will not build, a host
                       without docker. Neither a miss nor a detection.
      value class      the run reached `value change confirmed, intent unknown`:
                       behaviour changed, nothing was raised, and the intent
                       clause refused because the base tree does not say what the
                       value should be. Excluded from the crash denominator, and
                       not a value-class recall figure either -- this corpus is
                       reversed by construction (D-158).
      crash class      everything else that reached a verdict. This is the
                       denominator `G-RECALL-002` is read over; `certified` is
                       the numerator.
    """
    from attest.certification.intent import VALUE_CHANGE_LABEL
    from attest.review.status import categorise_failure

    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    rows = []
    for case in plan["cases"]:
        instance_id = case["instance_id"]
        path = RESULTS / f"{instance_id}{args.results_suffix}.json"
        if not path.is_file():
            rows.append({"case": instance_id, "class": "not run"})
            continue
        summary = json.loads(path.read_text(encoding="utf-8"))
        ledger_path = CASES / summary["case"] / "repo" / ".attest" / "ledger.jsonl"
        ledger = [
            json.loads(line)
            for line in ledger_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        mine = [e for e in ledger if e.get("task_id") == summary["task_id"]]
        certified = [
            e for e in mine if e.get("kind") == "certification" and e.get("outcome") == "accepted"
        ]
        verifications = [e for e in mine if e.get("kind") == "verification"]
        reasons = [str(e.get("reason", "")) for e in mine if e.get("reason")]
        deferred = str(summary.get("deferred_reason") or "")
        blob = " || ".join([*reasons, deferred])
        refusal = None
        for marker, name in (
            ("outside the project's declared range", "refused: interpreter"),
            ("environment bootstrap failed", "refused: image"),
            ("isolation backend unavailable", "refused: executor"),
        ):
            if marker in blob:
                refusal = name
                break
        if certified:
            klass = "crash class, certified"
        elif refusal is not None:
            klass = refusal
        elif VALUE_CHANGE_LABEL in blob:
            klass = "value class"
        else:
            klass = "crash class, no receipt"
        failures = [
            str(e.get("reason", "")) for e in verifications if e.get("outcome") != "reproduced"
        ]
        rows.append(
            {
                "case": instance_id,
                "class": klass,
                "candidates": summary["candidate_count"],
                "published": summary["surfaced_count"],
                "certified": len(certified),
                "certified_ids": [e.get("finding_id") for e in certified],
                "attempts": len(verifications),
                "failures": dict(
                    Counter(
                        "unfaithful test" if "passed on head" in r else categorise_failure(r)
                        for r in failures
                    )
                ),
                "spend": summary["spend_usd"],
            }
        )
    print(json.dumps(rows, indent=2))
    counts = Counter(r["class"] for r in rows)
    ran = [r for r in rows if r["class"] != "not run"]
    crash = [r for r in ran if r["class"].startswith("crash class")]
    certified = [r for r in crash if r["certified"]]
    low, high = wilson(len(certified), len(crash))
    print("\nclass counts:")
    for name, n in counts.most_common():
        print(f"  {n:4d}  {name}")
    print(
        f"\ncrash-class denominator (eligible and supported): {len(crash)}"
        f"\ncertified: {len(certified)}"
        f"\npoint estimate: {(len(certified) / len(crash) if crash else 0):.3f}"
        f"\nWilson 95%: [{low:.3f}, {high:.3f}]"
        f"\nspend: ${sum(r.get('spend', 0.0) for r in ran):.6f} over {len(ran)} reviews"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    s = sub.add_parser("screen")
    s.set_defaults(func=cmd_screen)
    p = sub.add_parser("probe")
    p.add_argument("--target", type=int, default=30)
    p.add_argument("--timeout", type=float, default=1200.0)
    p.add_argument("--repo", default="")
    p.add_argument("--rebuild", action="store_true")
    p.set_defaults(func=cmd_probe)
    n = sub.add_parser("plan")
    n.set_defaults(func=cmd_plan)
    r = sub.add_parser("run")
    r.add_argument("--k", type=int, default=K)
    r.add_argument("--budget", type=float, default=BUDGET)
    r.add_argument("--cap", type=float, default=None)
    r.add_argument("--code", default="")
    r.add_argument("--only", default="")
    r.add_argument("--rerun", action="store_true")
    r.add_argument("--results-suffix", default=RESULTS_SUFFIX)
    r.set_defaults(func=cmd_run)
    t = sub.add_parser("table")
    t.add_argument("--results-suffix", default=RESULTS_SUFFIX)
    t.set_defaults(func=cmd_table)
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
