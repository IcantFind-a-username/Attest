"""Forward pairs: the commit that *introduced* a defect, not the one that undid a fix.

The 2026-09-05b adjudication found that clause (c) is right on 7 of 8 forward
pairs and wrong on 4 of 4 reversed ones, for a reason no narrowing can repair:
undoing a ``fix:`` commit takes that fix's docstring, tests and changelog out in
the same diff, so the intent observer reads an author stating their intent. The
corpus policy that follows (D-135) says value-class recall numbers may only be
taken on **forward** pairs. This is the driver that builds them.

Given a repairing commit ``F``:

1. **the oracle** -- ``F``'s own test files, and the node ids of those files that
   *fail* on ``F^`` and *pass* on ``F``. No oracle, no pair;
2. **the boundary** -- search the first-parent chain back from ``F^`` for
   the first commit that **fails** the oracle whose own **parent passes** it.
   That commit is ``head``; its parent is ``base``. Where the oracle answers
   monotonically -- fails from the commit that introduced the defect until the
   fix -- that is the earliest failing commit; where it does not, it is the
   most recent boundary, which is still a commit that broke what its parent
   did. Both commits of the pair are probed; a tree in between that cannot run
   the oracle is skipped, not fatal;
3. **the pair** -- ``base`` is an ancestor of ``head``, the defect appears at
   ``head`` and is repaired later at ``F``. Time runs forwards, as it does in a
   pull request.

A commit whose boundary cannot be located -- the oracle never passes inside the
window, or the tree cannot run the oracle at all because the code it imports
does not exist yet -- is recorded ``unresolved`` with its reason and is not a
pair. That outcome is not a failure of the method: a defect born with the code
that carries it has no such boundary, and differential V could not certify it
anyway (D-063).

Free: git and pytest only, no model call, no product code, no spend.

Usage::

    python scripts/corpus/forward_pairs.py build --repo attest --limit 4
    python scripts/corpus/forward_pairs.py build --all --limit 3
    python scripts/corpus/forward_pairs.py table
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CORPORA = ROOT / ".attest" / "corpora"
OUT = ROOT / "benchmarks" / "attest-v2" / "runs" / "2026-09-05-forward-pairs.json"
SHARDS = ROOT / "benchmarks" / "attest-v2" / "runs" / "forward-pairs-shards"

# The eleven repositories the owner named: three of this account's, and the
# eight public clones `G-NULL-001a` already reads.
REPOS: dict[str, Path] = {
    "attest": CORPORA / "attest",
    "us-stock-helper": CORPORA / "us-stock-helper",
    "corum": CORPORA / "corum",
    **{
        name: CORPORA / "gnull" / name
        for name in (
            "click",
            "jinja",
            "itsdangerous",
            "attrs",
            "packaging",
            "python-dotenv",
            "more-itertools",
            "urllib3",
        )
    },
}

# Two interpreters are tried, in this order, and the first that can *run* the
# oracle at `F` is the one the whole bisect uses. The project venv carries this
# repository's own dependencies; the corpus venv carries the handful of pure
# Python packages the public clones' test suites import.
INTERPRETERS = (
    ROOT / ".venv" / "bin" / "python",
    CORPORA / ".venv-corpus" / "bin" / "python",
)

TEST_NAME = re.compile(r"(^|/)(test_[^/]+\.py|[^/]+_test\.py)$")
FIX_SUBJECT = re.compile(r"^(fix|bugfix)\b", re.I)
MAX_TEST_FILES = 3
MAX_NODES = 4  # oracle nodes carried through the bisect
MAX_BACK = 200  # first-parent commits listed behind `F^`
MAX_SCAN = 32  # of those, how far back the boundary search may reach
# Measured on the first 130 repairing commits of this corpus: every boundary the
# search found sat 1, 2, 11, 20 or 22 commits behind the fix, and no probe beyond
# 32 ever turned up a passing ancestor -- past that the oracle is failing because
# the code is *different*, not because this defect is present.
NEIGHBOUR_RADIUS = 2  # indices tried either side when a probe cannot be classified
PROBE_TIMEOUT_S = 300

PASS, FAIL, INDET = "pass", "fail", "indeterminate"


def git(repo: Path, *args: str, check: bool = True) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=False
    )
    if check and result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args[:3])}: {result.stderr.strip()[:200]}")
    return result.stdout


@dataclass
class Pair:
    repo: str
    fix: str
    fix_subject: str
    resolved: bool = False
    reason: str = ""
    head: str = ""
    head_subject: str = ""
    base: str = ""
    distance: int | None = None  # first-parent commits between `head` and `F^`
    test_files: list[str] = field(default_factory=list)
    nodes: list[str] = field(default_factory=list)
    interpreter: str = ""
    probes: int = 0
    trace: list[dict[str, object]] = field(default_factory=list)


# --------------------------------------------------------------------------- probes


def _project_root(tree: Path, test_file: str) -> Path:
    current = (tree / test_file).parent
    while current != tree and current != current.parent:
        if (current / "pyproject.toml").is_file() or (current / "setup.py").is_file():
            return current
        current = current.parent
    return tree


def _import_path(tree: Path, cwd: Path) -> list[str]:
    places = [str(cwd), str(cwd / "src"), str(tree), str(tree / "src")]
    seen: list[str] = []
    for place in places:
        if place not in seen and Path(place).is_dir():
            seen.append(place)
    return seen


def _pytest(
    tree: Path, interpreter: Path, test_file: str, nodes: list[str] | None = None
) -> tuple[set[str], int, str]:
    """(failed node ids, passed count, note) for one test file or a list of its
    nodes. An empty note means pytest ran and its summary was readable."""
    cwd = _project_root(tree, test_file)
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(_import_path(tree, cwd))
    env.pop("PYTEST_ADDOPTS", None)
    relative = os.path.relpath(tree / test_file, cwd)
    targets = [f"{relative}::{node}" for node in nodes] if nodes else [relative]
    try:
        completed = subprocess.run(
            [
                str(interpreter),
                "-m",
                "pytest",
                *targets,
                "-p",
                "no:cacheprovider",
                "-p",
                "no:randomly",
                "-o",
                "addopts=",
                "-q",
                "--tb=no",
                "-rf",
            ],
            capture_output=True,
            text=True,
            cwd=cwd,
            env=env,
            timeout=PROBE_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        return set(), 0, f"pytest exceeded {PROBE_TIMEOUT_S}s"
    text = completed.stdout + completed.stderr
    failed = {
        match.split("::", 1)[1]
        for match in re.findall(r"^FAILED (\S+)", text, flags=re.M)
        if "::" in match
    }
    errored = {
        match.split("::", 1)[1]
        for match in re.findall(r"^ERROR (\S+)", text, flags=re.M)
        if "::" in match
    }
    passed = sum(int(count) for count in re.findall(r"(\d+) passed", text))
    if errored or (not failed and passed == 0):
        tail = text.strip().splitlines()[-1][:160] if text.strip() else "no output"
        return set(), passed, tail
    return failed, passed, ""


def _classify(tree: Path, interpreter: Path, test_file: str, nodes: list[str]) -> tuple[str, str]:
    """Does this tree carry the defect the oracle names? ``fail`` yes, ``pass``
    no, ``indeterminate`` when the tree cannot answer."""
    failed, passed, note = _pytest(tree, interpreter, test_file, nodes)
    if note:
        return INDET, note
    if failed:
        return FAIL, f"{len(failed)} of {len(nodes)} failed"
    if passed >= len(nodes):
        return PASS, f"{passed} passed"
    return INDET, f"{passed} passed, {len(failed)} failed, {len(nodes)} expected"


class Tree:
    """One reusable detached worktree. Every checkout is forced, and the fix's
    own test bytes are re-written after it, so each probe sees exactly the
    historical tree plus today's oracle."""

    def __init__(self, repo: Path, fix: str, test_files: list[str]) -> None:
        self.repo = repo
        self.fix = fix
        self.test_files = test_files
        self.path = Path(tempfile.mkdtemp(prefix="forward-pair-"))
        git(repo, "worktree", "add", "--detach", "--force", str(self.path), fix)

    def at(self, sha: str) -> None:
        git(self.path, "checkout", "--detach", "--force", "-q", sha)
        for name in self.test_files:
            target = self.path / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(
                subprocess.run(
                    ["git", "-C", str(self.repo), "show", f"{self.fix}:{name}"],
                    capture_output=True,
                    check=True,
                ).stdout
            )

    def close(self) -> None:
        subprocess.run(
            ["git", "-C", str(self.repo), "worktree", "remove", "--force", str(self.path)],
            capture_output=True,
            check=False,
        )


# --------------------------------------------------------------------------- build


def default_tip(repo: Path) -> str:
    """The clone's default branch. A corpus clone's ``HEAD`` is wherever the last
    run detached it, which is not the history this samples from."""
    for candidate in ("origin/HEAD", "origin/main", "origin/master", "main", "master", "HEAD"):
        probe = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "--verify", "--quiet", candidate],
            capture_output=True,
            check=False,
        )
        if probe.returncode == 0:
            return candidate
    return "HEAD"


def fix_commits(repo: Path, limit: int, subjects: str = "any") -> list[tuple[str, str]]:
    """Candidate repairing commits, newest first on the default branch: one that
    touches both a test file and a non-test Python file.

    ``subjects="fix"`` also demands a ``fix:`` subject. The default does not, and
    the reason is that the subject line turned out to carry no information the
    oracle does not already carry: **a commit that is not a repair produces no
    boundary**, because its own new test fails on every ancestor (the feature is
    absent there, not broken), and the search rejects it in two probes. Reading
    subjects only threw away the repairs whose authors did not say `fix`."""
    out = git(repo, "log", default_tip(repo), "--no-merges", "--min-parents=1", "--format=%H%x00%s")
    found: list[tuple[str, str]] = []
    for line in out.splitlines():
        sha, _, subject = line.partition("\0")
        if not sha or (subjects == "fix" and not FIX_SUBJECT.match(subject)):
            continue
        names = git(repo, "show", "--name-only", "--format=", "--diff-filter=AM", sha).splitlines()
        tests = [n for n in names if TEST_NAME.search(n)]
        code = [n for n in names if n.endswith(".py") and not TEST_NAME.search(n)]
        if tests and code:
            found.append((sha, subject))
        if len(found) >= limit:
            break
    return found


def build_pair(repo_name: str, repo: Path, fix: str, subject: str) -> Pair:
    pair = Pair(repo=repo_name, fix=fix, fix_subject=subject[:120])
    names = git(repo, "show", "--name-only", "--format=", "--diff-filter=AM", fix).splitlines()
    pair.test_files = [n for n in names if TEST_NAME.search(n)][:MAX_TEST_FILES]
    parent = git(repo, "rev-parse", f"{fix}^").strip()
    tree = Tree(repo, fix, pair.test_files)
    try:
        # 1. the oracle: nodes that fail on `F^` and pass on `F`
        oracle: tuple[str, list[str], Path] | None = None
        for test_file in pair.test_files:
            for interpreter in INTERPRETERS:
                if not interpreter.is_file():
                    continue
                tree.at(parent)
                head_failed, _, head_note = _pytest(tree.path, interpreter, test_file)
                pair.probes += 1
                if head_note or not head_failed:
                    pair.reason = f"{test_file}: F^ — {head_note or 'nothing fails'}"
                    continue
                tree.at(fix)
                base_failed, base_passed, base_note = _pytest(tree.path, interpreter, test_file)
                pair.probes += 1
                if base_note:
                    pair.reason = f"{test_file}: F — {base_note}"
                    continue
                nodes = sorted(head_failed - base_failed)[:MAX_NODES]
                if not nodes:
                    pair.reason = (
                        f"{test_file}: no node discriminates "
                        f"(F^ {len(head_failed)}F, F {len(base_failed)}F/{base_passed}P)"
                    )
                    continue
                oracle = (test_file, nodes, interpreter)
                break
            if oracle is not None:
                break
        if oracle is None:
            pair.reason = pair.reason or "no test file yields an oracle"
            return pair
        test_file, nodes, interpreter = oracle
        pair.nodes = nodes
        pair.interpreter = str(interpreter.relative_to(ROOT))

        # 2. the boundary scan over the first-parent chain behind `F^`
        chain = [
            line.strip()
            for line in git(
                repo, "rev-list", "--first-parent", f"--max-count={MAX_BACK}", parent
            ).splitlines()
            if line.strip()
        ]
        cache: dict[int, tuple[str, str]] = {}

        def probe(index: int) -> tuple[str, str]:
            if index in cache:
                return cache[index]
            tree.at(chain[index])
            verdict = _classify(tree.path, interpreter, test_file, nodes)
            pair.probes += 1
            pair.trace.append(
                {
                    "index": index,
                    "sha": chain[index][:10],
                    "verdict": verdict[0],
                    "note": verdict[1][:80],
                }
            )
            cache[index] = verdict
            return verdict

        verdict, note = probe(0)
        if verdict != FAIL:
            pair.reason = f"F^ does not carry the defect under the oracle: {verdict} ({note})"
            return pair

        def probe_near(index: int, floor: int, ceiling: int) -> tuple[int, str]:
            """The nearest index to ``index``, strictly inside ``(floor, ceiling)``,
            that answers pass or fail. A tree that cannot run today's oracle --
            because the code the test imports does not exist there yet -- is
            skipped, not fatal."""
            for offset in range(NEIGHBOUR_RADIUS + 1):
                for candidate in sorted({index - offset, index + offset}):
                    if floor < candidate < ceiling and candidate < len(chain):
                        answer, _ = probe(candidate)
                        if answer != INDET:
                            return candidate, answer
            return index, INDET

        # Doubling out from `F^` for any passing ancestor, then a bisect down to
        # the two adjacent commits. Doubling, because a defect born 60 commits
        # back is as interesting as one born 3 back and a linear walk cannot
        # reach it; a bisect, because only the two ends of the boundary have to
        # be probed, and **both of them are**: `head` is a commit seen failing
        # and `base` is its own parent, seen passing. Nothing is assumed about
        # the trees in between.
        low, high = 0, None
        step = 1
        while step < min(MAX_SCAN, len(chain)):
            index, verdict = probe_near(step, low, min(MAX_SCAN, len(chain)))
            if verdict == PASS:
                high = index
                break
            if verdict == FAIL:
                low = max(low, index)
            step *= 2
        if high is None:
            passes = sum(1 for verdict, _ in cache.values() if verdict == PASS)
            indeterminate = sum(1 for verdict, _ in cache.values() if verdict == INDET)
            pair.reason = (
                f"no passing ancestor within {min(MAX_SCAN, len(chain))} first-parent commits "
                f"({len(cache)} probed, {passes} pass, {indeterminate} indeterminate): the "
                "defect is older than the window, or it was born with the code that carries "
                "it and has no boundary"
            )
            return pair
        while high - low > 1:
            index, verdict = probe_near((low + high) // 2, low, high)
            if verdict == INDET:
                pair.reason = (
                    f"the boundary is between index {low} and {high} and no tree strictly "
                    "between them can run the oracle"
                )
                return pair
            if verdict == FAIL:
                low = index
            else:
                high = index
        # the two commits of the pair were both probed, and they are adjacent on
        # the first-parent chain: `base` is `head`'s own parent
        assert high - low == 1
        pair.head = chain[low]
        pair.base = chain[high]
        pair.head_subject = git(repo, "log", "-1", "--format=%s", pair.head).strip()[:120]
        pair.distance = low
        pair.resolved = True
        pair.reason = (
            f"{len(nodes)} oracle node(s) of {test_file} fail from {pair.head[:10]} onward "
            f"and pass at its parent {pair.base[:10]}"
        )
        return pair
    finally:
        tree.close()


def cmd_build(args: argparse.Namespace) -> int:
    names = list(REPOS) if args.all else [args.repo]
    out = Path(args.out) if args.out else OUT
    existing: list[dict[str, object]] = []
    if out.is_file():
        existing = list(json.loads(out.read_text(encoding="utf-8"))["pairs"])
    seen = {(str(row["repo"]), str(row["fix"])) for row in existing}
    for name in names:
        repo = REPOS[name]
        if not (repo / ".git").exists():
            print(f"{name}: no clone", file=sys.stderr)
            continue
        for fix, subject in fix_commits(repo, args.scan, args.subjects):
            if (name, fix) in seen:
                continue
            resolved_here = sum(
                1 for row in existing if row["repo"] == name and row.get("resolved")
            )
            if resolved_here >= args.limit:
                break
            pair = build_pair(name, repo, fix, subject)
            existing.append(asdict(pair))
            seen.add((name, fix))
            print(
                f"{name} {fix[:10]} {'PAIR' if pair.resolved else '----'} "
                f"{pair.head[:10] or '-'}<-{pair.base[:10] or '-'} "
                f"[{pair.probes} probes] {pair.reason[:90]}",
                flush=True,
            )
            _write(existing, out)
    _write(existing, out)
    return 0


def _write(pairs: list[dict[str, object]], out: Path = OUT) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "attest.forward-pairs.v1",
        "policy": "D-135: value-class recall is measured on forward pairs only",
        "max_back": MAX_BACK,
        "resolved": sum(1 for p in pairs if p.get("resolved")),
        "examined": len(pairs),
        "pairs": pairs,
    }
    out.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def cmd_merge(args: argparse.Namespace) -> int:
    pairs: list[dict[str, object]] = []
    for shard in sorted(SHARDS.glob("*.json")):
        pairs.extend(json.loads(shard.read_text(encoding="utf-8"))["pairs"])
    pairs.sort(key=lambda p: (str(p["repo"]), str(p["fix"])))
    _write(pairs)
    print(f"{sum(1 for p in pairs if p.get('resolved'))} resolved of {len(pairs)} -> {OUT}")
    return 0


def cmd_table(args: argparse.Namespace) -> int:
    """The list, one row per resolved pair, and the count that matters: two fix
    commits can converge on the same boundary, and reviewing that pair twice
    buys nothing, so `distinct` is what a review run is sized against."""
    payload = json.loads(OUT.read_text(encoding="utf-8"))
    pairs = [p for p in payload["pairs"] if p.get("resolved")]
    print("| # | repo | head | base | distance | the defect the oracle names |")
    print("|---|---|---|---|---|---|")
    for index, pair in enumerate(sorted(pairs, key=lambda p: (p["repo"], p["fix"])), start=1):
        print(
            f"| {index} | `{pair['repo']}` | `{str(pair['head'])[:10]}` | "
            f"`{str(pair['base'])[:10]}` | {pair['distance']} | {pair['fix_subject']} |"
        )
    distinct = {(p["repo"], p["head"], p["base"]) for p in pairs}
    print(
        f"\n{len(pairs)} resolved of {payload['examined']} examined; "
        f"{len(distinct)} distinct (repo, head, base) pairs"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build")
    b.add_argument("--repo", choices=sorted(REPOS))
    b.add_argument("--all", action="store_true")
    b.add_argument("--limit", type=int, default=3, help="resolved pairs wanted per repository")
    b.add_argument("--scan", type=int, default=12, help="fix commits examined per repository")
    b.add_argument("--out", default=None, help="write here instead of the merged file")
    b.add_argument(
        "--subjects",
        choices=("any", "fix"),
        default="any",
        help="which commits may be repairs; the oracle decides either way",
    )
    b.set_defaults(func=cmd_build)
    m = sub.add_parser("merge", help="fold per-repository shards into the one list")
    m.set_defaults(func=cmd_merge)
    t = sub.add_parser("table")
    t.set_defaults(func=cmd_table)
    args = parser.parse_args(argv)
    if args.command == "build" and not args.all and not args.repo:
        parser.error("build needs --repo or --all")
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
