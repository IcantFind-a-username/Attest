"""E-02 pilot driver over SWE-bench Verified (mainline §2 step 7, §3, §4).

Subcommands (no product code is touched; this is a measurement harness):

  build <instance_id> [--control test-only|docs-only]
      Clone the upstream repository (blobless) under .attest/corpora/swebench/,
      construct a realistic pull request in a dedicated worktree and a
      per-instance virtual environment:
        regression : base = base_commit + gold code patch ("fixed"),
                     head = base + revert of that patch  (the regression)
        test-only  : base = base_commit, head = base + gold test patch
        docs-only  : base = parent of the nearest docs-only commit at or
                     before base_commit, head = that commit
      The gold tests (hidden-truth.jsonl) are never applied to a regression
      head and never shown to the product.
  run <instance_id> [--control ...] --k 4 [--budget 0.25]
      Run the full product path (run_ci) against a loopback GitHub server
      with the real provider; every ledger row lands in the worktree.
  table
      Tabulate candidates / eligible / certified / control false publications
      / silence rate from the ledgers of every built case.

Paid: `run` calls the model. Reserve in DEVSPEND.md first.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / ".attest" / "corpora" / "swebench-verified"
WORK = ROOT / ".attest" / "corpora" / "swebench"
RESULTS = ROOT / ".attest" / "corpora" / "swebench" / "results"


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=check, capture_output=True, text=True
    )


def _instances() -> dict[str, dict]:
    rows = {}
    for line in (CORPUS / "instances.jsonl").read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        rows[row["instance_id"]] = row
    return rows


def _hidden(instance_id: str) -> dict:
    for line in (CORPUS / "hidden-truth.jsonl").read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row["instance_id"] == instance_id:
            return row
    raise KeyError(instance_id)


def _upstream(repo: str) -> Path:
    path = WORK / "upstream" / repo.replace("/", "__")
    if not (path / ".git").is_dir():
        path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                "git",
                "clone",
                "--filter=blob:none",
                "--no-checkout",
                f"https://github.com/{repo}.git",
                str(path),
            ],
            check=True,
        )
    return path


def _case_dir(instance_id: str, control: str | None) -> Path:
    return WORK / "cases" / (instance_id if control is None else f"{instance_id}--{control}")


def _apply(worktree: Path, patch_text: str, *, reverse: bool = False) -> None:
    args = ["apply", "--index", "--whitespace=nowarn"]
    if reverse:
        args.append("-R")
    subprocess.run(
        ["git", "-C", str(worktree), *args],
        input=patch_text,
        text=True,
        check=True,
        capture_output=True,
    )


def _commit(worktree: Path, message: str) -> str:
    _git(
        worktree,
        "-c",
        "user.email=pilot@example.invalid",
        "-c",
        "user.name=Pilot",
        "commit",
        "-qm",
        message,
        "--allow-empty",
    )
    return _git(worktree, "rev-parse", "HEAD").stdout.strip()


def _docs_only_commit(upstream: Path, base_commit: str) -> tuple[str, str] | None:
    """Nearest commit at/before base_commit touching only docs-like paths."""
    log = _git(upstream, "log", "--format=%H", "-n", "400", base_commit).stdout.split()
    for sha in log:
        files = _git(upstream, "show", "--format=", "--name-only", sha).stdout.split()
        if not files:
            continue
        if all(
            f.endswith((".rst", ".md", ".txt")) or f.startswith(("docs/", "doc/", "CHANGES"))
            for f in files
        ):
            parent = _git(upstream, "rev-parse", f"{sha}^").stdout.strip()
            return parent, sha
    return None


def _commit_generated_version_file(worktree: Path) -> None:
    """pytest's own tree imports ``_pytest._version``, a file setuptools_scm
    generates at install time; the executor runs from fresh worktrees that
    never see it, so the pilot commits a fixed one on both sides of the PR."""
    version_file = worktree / "src" / "_pytest" / "_version.py"
    if (worktree / "src" / "_pytest" / "__init__.py").exists() and not version_file.exists():
        # a large version: pytest's own tox.ini enforces `minversion` against it
        version_file.write_text('version = "99.0.0+pilot"\nversion_tuple = (99, 0, 0)\n')
        _git(worktree, "add", "-f", str(version_file))
        _commit(worktree, "pilot: commit the generated _pytest/_version.py")


# Interpreters this host can offer, newest first. CPython 3.8 is excluded: its
# eager platform.uname() shells out and trips the process guard (D-057).
AVAILABLE_PYTHONS = {
    (3, 11): "/Library/Frameworks/Python.framework/Versions/3.11/bin/python3.11",
    (3, 9): str(Path.home() / ".pyenv" / "versions" / "3.9.19" / "bin" / "python"),
}
_CLASSIFIER_RE = re.compile(r"Programming Language :: Python :: 3\.(\d+)")


def _project_python(worktree: Path) -> tuple[str, str]:
    """Interpreter by the project's own declaration, else the era fallback.

    Rule (owner 2026-09-02, item 3): the highest available interpreter whose
    minor version does not exceed the newest ``Programming Language :: Python
    :: 3.X`` classifier the project declares; a project declaring nothing this
    host can satisfy gets the oldest available interpreter (3.9).
    """
    declared: list[int] = []
    for name in ("setup.py", "setup.cfg", "pyproject.toml"):
        path = worktree / name
        if path.exists():
            declared.extend(
                int(m) for m in _CLASSIFIER_RE.findall(path.read_text(errors="replace"))
            )
    available = sorted(AVAILABLE_PYTHONS, reverse=True)
    if declared:
        newest = max(declared)
        for version in available:
            if version[1] <= newest:
                return AVAILABLE_PYTHONS[version], f"classifiers up to 3.{newest}"
        return AVAILABLE_PYTHONS[available[-1]], f"classifiers up to 3.{newest}; fallback"
    return AVAILABLE_PYTHONS[available[-1]], "no classifiers; era fallback"


def _make_env(case: Path, worktree: Path) -> Path:
    """Per-case virtualenv on the interpreter the project declares (or
    PILOT_PYTHON when set); the choice and its reason are recorded."""
    env_dir = case / "env"
    chosen, reason = _project_python(worktree)
    base_python = os.environ.get("PILOT_PYTHON", chosen)
    (case / "interpreter.json").write_text(
        json.dumps(
            {
                "python": base_python,
                "reason": reason if "PILOT_PYTHON" not in os.environ else "PILOT_PYTHON override",
            }
        )
        + "\n"
    )
    if not (env_dir / "bin" / "python").exists():
        subprocess.run([base_python, "-m", "venv", "--clear", str(env_dir)], check=True)
        py = env_dir / "bin" / "python"
        subprocess.run(
            [str(py), "-m", "pip", "install", "-q", "--upgrade", "pip", "pytest"], check=True
        )
        # best effort: the product must survive an un-installable project as a DEFER
        subprocess.run([str(py), "-m", "pip", "install", "-q", "-e", str(worktree)], check=False)
        # an editable install may regenerate tracked files (setuptools_scm rewrites
        # _version.py); the executor demands an immutable, clean tree
        _git(worktree, "checkout", "--", ".")
    return env_dir / "bin" / "python"


def cmd_build(args: argparse.Namespace) -> int:
    row = _instances()[args.instance_id]
    upstream = _upstream(row["repo"])
    case = _case_dir(args.instance_id, args.control)
    worktree = case / "repo"
    if worktree.exists():
        print(f"exists: {worktree}")
        return 0
    case.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, object] = {
        "instance_id": args.instance_id,
        "repo": row["repo"],
        "control": args.control,
    }
    if args.control == "docs-only":
        found = _docs_only_commit(upstream, row["base_commit"])
        if found is None:
            print("no docs-only commit found", file=sys.stderr)
            return 2
        parent, sha = found
        _git(upstream, "worktree", "add", "--detach", str(worktree), sha)
        manifest.update(base_sha=parent, head_sha=sha, shape="docs-only history commit")
    else:
        _git(upstream, "worktree", "add", "--detach", str(worktree), row["base_commit"])
        _commit_generated_version_file(worktree)
        if args.control == "test-only":
            base_sha = row["base_commit"]
            _apply(worktree, _hidden(args.instance_id)["test_patch"])
            head_sha = _commit(worktree, "test-only control: gold tests without the fix")
            manifest.update(base_sha=base_sha, head_sha=head_sha, shape="test-only control")
        else:
            _apply(worktree, row["patch"])
            base_sha = _commit(worktree, "fixed: base_commit + gold code patch")
            _apply(worktree, row["patch"], reverse=True)
            head_sha = _commit(worktree, "regression: revert the fix")
            manifest.update(
                base_sha=base_sha, head_sha=head_sha, shape="regression PR (revert of the gold fix)"
            )
    # the container backend (X-02) builds its own image from the tree; the
    # host virtualenv is only needed by the development adapter
    manifest["project_python"] = sys.executable if args.no_env else str(_make_env(case, worktree))
    (case / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    return 0


class Loopback:
    """A minimal GitHub stand-in: stores the status comment and reviews."""

    def __init__(self) -> None:
        self.status_bodies: list[str] = []
        self.reviews: list[dict] = []
        self._status: dict | None = None
        recorder = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args: object) -> None:
                pass

            def _respond(self) -> None:
                length = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(length) or b"null")
                if self.command == "GET":
                    response: object = [] if recorder._status is None else [recorder._status]
                elif self.path.endswith("/reviews"):
                    recorder.reviews.append(body)
                    response = {"id": 202}
                else:
                    recorder.status_bodies.append(str(body["body"]))
                    recorder._status = {"id": 101, "body": body["body"], "user": {"type": "Bot"}}
                    response = {"id": 101}
                encoded = json.dumps(response).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

            do_GET = do_POST = do_PATCH = _respond  # noqa: N815

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    @property
    def url(self) -> str:
        host, port = self.server.server_address
        return f"http://{host}:{port}"

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


def cmd_run(args: argparse.Namespace) -> int:
    sys.path.insert(0, str(ROOT / "src"))
    from attest.github.client import GitHubClient
    from attest.github.context import PullRequestContext
    from attest.review.ci import run_ci
    from attest.review.config import ReviewConfig
    from attest.review.executor import ExecutorLimits
    from attest.review.proposer import ApiProvider

    case = _case_dir(args.instance_id, args.control)
    manifest = json.loads((case / "manifest.json").read_text(encoding="utf-8"))
    worktree = case / "repo"
    os.environ["ATTEST_PROJECT_PYTHON"] = manifest["project_python"]
    config = ReviewConfig(
        k_samples=args.k,
        budget_usd=args.budget,
        tier0_commands=[],
        context_strategy=args.context_strategy,
        model=args.model,
    )
    github = Loopback()
    try:
        result = run_ci(
            worktree,
            PullRequestContext(
                repository=f"corpus/{case.name}",
                number=1,
                base_sha=manifest["base_sha"],
                head_sha=manifest["head_sha"],
                is_fork=False,
            ),
            GitHubClient("loopback", github.url),
            config,
            ApiProvider(config.model),
            verification_timeout_s=args.verification_timeout,
            limits=ExecutorLimits(wall_timeout_s=120.0),
        )
    finally:
        github.close()
    RESULTS.mkdir(parents=True, exist_ok=True)
    summary = {
        "case": case.name,
        "control": args.control,
        "model": config.model,  # every table names the model (owner, 2026-09-03e)
        "task_id": result.task_id,
        "candidate_count": result.candidate_count,
        "surfaced_count": result.surfaced_count,
        "deferred_reason": result.deferred_reason,
        "spend_usd": result.spend_usd,
        "reviews": github.reviews,
        "final_status": github.status_bodies[-1] if github.status_bodies else None,
    }
    (RESULTS / f"{case.name}{args.results_suffix}.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({k: v for k, v in summary.items() if k != "reviews"}, indent=2))
    return 0


def cmd_table(_args: argparse.Namespace) -> int:
    rows = []
    for path in sorted(RESULTS.glob("*.json")):
        summary = json.loads(path.read_text(encoding="utf-8"))
        case = _case_dir(summary["case"].split("--")[0], summary["control"])
        ledger = case / "repo" / ".attest" / "ledger.jsonl"
        entries = (
            [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]
            if ledger.exists()
            else []
        )
        task = summary["task_id"]
        mine = [e for e in entries if e.get("task_id") == task]
        eligible = sum(
            1
            for e in mine
            if e.get("kind") == "eligibility" and e.get("eligibility") == "regression"
        )
        ineligible = {}
        for e in mine:
            if e.get("kind") == "eligibility" and e.get("eligibility") != "regression":
                ineligible[e["eligibility"]] = ineligible.get(e["eligibility"], 0) + 1
        certified = sum(
            1 for e in mine if e.get("kind") == "certification" and e.get("outcome") == "accepted"
        )
        samples = [
            s
            for e in mine
            if e.get("kind") == "review_run"
            for s in (e.get("provider_samples") or [])
        ]
        # owner fix 2 (2026-09-03): "no text returned" is a failed sample, not
        # silence; only the model's own empty findings list abstains
        no_text = sum(1 for s in samples if s.get("recovery") == "no_text")
        abstained = sum(1 for s in samples if s.get("recovery") == "empty")
        verifications = [e for e in mine if e.get("kind") == "verification"]
        outcomes = {}
        for e in verifications:
            outcomes[e.get("outcome")] = outcomes.get(e.get("outcome"), 0) + 1
        reasons = sorted(
            {str(e.get("reason", ""))[:80] for e in verifications if e.get("outcome") == "deferred"}
        )
        rows.append(
            {
                "case": summary["case"],
                "control": summary["control"] or "-",
                "candidates": summary["candidate_count"],
                "eligible": eligible,
                "ineligible": ineligible,
                "certified": certified,
                "published": summary["surfaced_count"],
                "samples": len(samples),
                "no_text": no_text,
                "abstained": abstained,
                "verification": outcomes,
                "defer": summary["deferred_reason"],
                "spend": round(summary["spend_usd"], 4),
                "defer_reasons": reasons,
            }
        )
    defects = [r for r in rows if r["control"] == "-"]
    controls = [r for r in rows if r["control"] != "-"]
    print(json.dumps(rows, indent=2))
    print()
    print(
        "| population | n | candidates | eligible | certified | published | "
        "samples | no text returned | true abstentions | spend |"
    )
    print("|---|---|---|---|---|---|---|---|---|---|")
    for name, group in (("defects", defects), ("controls", controls)):
        if not group:
            continue
        print(
            f"| {name} | {len(group)} | {sum(r['candidates'] for r in group)} | "
            f"{sum(r['eligible'] for r in group)} | {sum(r['certified'] for r in group)} | "
            f"{sum(r['published'] for r in group)} | {sum(r['samples'] for r in group)} | "
            f"{sum(r['no_text'] for r in group)} | {sum(r['abstained'] for r in group)} | "
            f"${sum(r['spend'] for r in group):.4f} |"
        )
    if defects:
        silent = sum(1 for r in defects if r["published"] == 0)
        print(f"\nsilence rate on defects: {silent}/{len(defects)}")
        certified_defects = sum(1 for r in defects if r["certified"] > 0)
        published_defects = sum(1 for r in defects if r["published"] > 0)
        print(
            f"certified: {sum(r['certified'] for r in defects)} candidates on "
            f"{certified_defects}/{len(defects)} defects; published: "
            f"{sum(r['published'] for r in defects)} candidates on "
            f"{published_defects}/{len(defects)} defects"
        )
    if controls:
        false_publications = sum(r["published"] for r in controls)
        print(f"control false publications: {false_publications}/{len(controls)} cases")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build")
    b.add_argument("instance_id")
    b.add_argument("--control", choices=["test-only", "docs-only"], default=None)
    b.add_argument(
        "--no-env",
        action="store_true",
        help="skip the host virtualenv (container backend runs build their own image)",
    )
    b.set_defaults(func=cmd_build)
    r = sub.add_parser("run")
    r.add_argument("instance_id")
    r.add_argument("--control", choices=["test-only", "docs-only"], default=None)
    r.add_argument("--k", type=int, default=4)
    r.add_argument("--budget", type=float, default=0.25)
    r.add_argument("--verification-timeout", type=float, default=900.0)
    r.add_argument(
        "--model",
        default="",
        help="model id from pricing.toml; empty uses its default_model",
    )
    r.add_argument(
        "--context-strategy",
        choices=["r01", "package-cache"],
        default="r01",
        help="owner instruction 4 comparison arm; the default is unchanged",
    )
    r.add_argument(
        "--results-suffix",
        default="",
        help="suffix for the results file so both arms keep their summaries",
    )
    r.set_defaults(func=cmd_run)
    t = sub.add_parser("table")
    t.set_defaults(func=cmd_table)
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
