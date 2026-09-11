"""e05-external-v1: select the 24 pull requests, read-only, before any unit runs.

Owner authorisation 4 of 2026-09-12. Eight public Python repositories -- the
`G-NULL-001a` clones, which build and import inside the product's container --
each contribute their three most recently merged pull requests that changed
the package itself (not only docs or tests), taken by `merged_at` descending,
skipping a pull request whose diff exceeds 2,000 changed lines. Units are
ordered round-robin across repositories in name order, as every stratum
before this one was, so a cost cap removes units evenly.

    head = the merge commit (what the default branch became when the pull
           request landed; a squash merge and a merge commit alike)
    base = that commit's first parent, i.e. the base branch as it stood
           the moment before -- merge-base(head, base branch at merge time)

`gh api` is used **read-only**; nothing is written to any repository. The
walk is recorded in `selection.json` beside `sample.jsonl`: every merged pull
request the walk looked at, kept or not, with the reason.

    .venv/bin/python scripts/corpus/e05_select.py --study e05-external-v1 \\
        --clones .attest/corpora/gnull
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from attest.benchmark import prospective  # noqa: E402

STUDIES = ROOT / "benchmarks" / "studies"
PER_REPOSITORY = 3
MAX_CHANGED_LINES = 2000
PAGES = 5  # 100 closed pull requests a page, newest updated first
NOT_PACKAGE_DIRS = frozenset(
    {"tests", "test", "testing", "docs", "doc", "examples", "benchmarks", "bench", "scripts", "ci"}
)
NOT_PACKAGE_FILES = frozenset({"setup.py", "conftest.py", "noxfile.py", "tasks.py"})


def _gh(*args: str) -> object:
    completed = subprocess.run(
        ["gh", "api", *args], capture_output=True, text=True, check=False
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip()[:200])
    return json.loads(completed.stdout or "null")


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    ).stdout.strip()


def is_package_source(path: str) -> bool:
    """A Python file of the package itself: not a test, not documentation, not
    packaging scaffolding, not hidden tooling."""
    if not path.endswith(".py") or path.startswith("."):
        return False
    parts = path.split("/")
    name = parts[-1]
    if name in NOT_PACKAGE_FILES or name.startswith("test_") or name.endswith("_test.py"):
        return False
    return not any(part in NOT_PACKAGE_DIRS for part in parts[:-1])


def _clone_name(repository: str) -> str:
    return repository.split("/")[-1].lower().lstrip("-")


def merged_pulls(repository: str) -> list[dict[str, object]]:
    """Closed pull requests, newest updated first, kept when merged, sorted by
    `merged_at` descending. Read-only."""
    found: list[dict[str, object]] = []
    for page in range(1, PAGES + 1):
        rows = _gh(
            f"repos/{repository}/pulls?state=closed&sort=updated&direction=desc"
            f"&per_page=100&page={page}"
        )
        if not isinstance(rows, list) or not rows:
            break
        found.extend(row for row in rows if isinstance(row, dict) and row.get("merged_at"))
        if len(rows) < 100:
            break
    found.sort(key=lambda row: str(row["merged_at"]), reverse=True)
    return found


def pull_files(repository: str, number: int) -> list[dict[str, object]]:
    files = _gh("--paginate", f"repos/{repository}/pulls/{number}/files?per_page=100")
    return files if isinstance(files, list) else []


def select(
    repository: str, clone: Path, *, fetch: bool = True
) -> tuple[list[prospective.TrafficUnit], list[dict[str, object]]]:
    """The repository's three qualifying units, and the walk that found them."""
    if fetch:
        subprocess.run(["git", "-C", str(clone), "fetch", "-q", "origin"], check=False)
    kept: list[prospective.TrafficUnit] = []
    walk: list[dict[str, object]] = []
    for pull in merged_pulls(repository):
        if len(kept) >= PER_REPOSITORY:
            break
        number = int(pull["number"])  # type: ignore[call-overload]
        title = str(pull.get("title", ""))
        entry: dict[str, object] = {
            "unit_id": f"{repository}#{number}",
            "merged_at": pull["merged_at"],
            "base_ref": (pull.get("base") or {}).get("ref"),  # type: ignore[union-attr]
            "title": title[:120],
        }
        files = pull_files(repository, number)
        paths = [str(f.get("filename", "")) for f in files]
        changed = sum(int(f.get("additions", 0)) + int(f.get("deletions", 0)) for f in files)  # type: ignore[call-overload]
        package = [p for p in paths if is_package_source(p)]
        entry.update(changed_files=len(paths), changed_lines=changed, package_files=len(package))
        if not package:
            entry["kept"] = False
            entry["reason"] = "no package source changed (docs, tests or scaffolding only)"
            walk.append(entry)
            continue
        if changed > MAX_CHANGED_LINES:
            entry["kept"] = False
            entry["reason"] = f"diff of {changed} changed lines exceeds {MAX_CHANGED_LINES}"
            walk.append(entry)
            continue
        merge_sha = str(pull.get("merge_commit_sha") or "")
        try:
            head = _git(clone, "rev-parse", "--verify", f"{merge_sha}^{{commit}}")
            base = _git(clone, "rev-parse", "--verify", f"{merge_sha}^1")
        except subprocess.CalledProcessError:
            entry["kept"] = False
            entry["reason"] = f"merge commit {merge_sha[:12]} is not in the clone"
            walk.append(entry)
            continue
        if head == base:
            entry["kept"] = False
            entry["reason"] = "empty diff"
            walk.append(entry)
            continue
        entry.update(kept=True, head_sha=head, base_sha=base)
        walk.append(entry)
        kept.append(
            prospective.TrafficUnit(
                unit_id=f"{repository}#{number}",
                repository=repository,
                head_sha=head,
                base_sha=base,
                subject=title[:120],
                stratum=prospective.classify_subject(title),
                changed_files=len(paths),
                pushed_at=str(pull["merged_at"]),
            )
        )
    return kept, walk


def round_robin(
    per_repo: dict[str, list[prospective.TrafficUnit]], limit: int
) -> list[prospective.TrafficUnit]:
    units: list[prospective.TrafficUnit] = []
    index = 0
    while len(units) < limit and any(index < len(g) for g in per_repo.values()):
        for name in sorted(per_repo):
            if len(units) >= limit:
                break
            group = per_repo[name]
            if index < len(group):
                units.append(group[index])
        index += 1
    return units


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study", default="e05-external-v1")
    parser.add_argument("--clones", default=str(ROOT / ".attest" / "corpora"))
    parser.add_argument("--no-fetch", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="print, record nothing")
    args = parser.parse_args(argv)
    study = STUDIES / args.study
    raw = json.loads((study / "preregistration.json").read_text(encoding="utf-8"))
    per_repo: dict[str, list[prospective.TrafficUnit]] = {}
    walks: dict[str, list[dict[str, object]]] = {}
    for repository in raw["population"]:
        clone = Path(args.clones) / _clone_name(repository)
        if not (clone / ".git").is_dir():
            print(f"skip {repository}: no clone at {clone}", file=sys.stderr)
            continue
        kept, walk = select(repository, clone, fetch=not args.no_fetch)
        per_repo[repository] = kept
        walks[repository] = walk
        print(f"{repository}: {len(kept)} kept of {len(walk)} walked", file=sys.stderr)
    target = int(raw.get("target_units", 0)) or sum(len(group) for group in per_repo.values())
    units = round_robin(per_repo, target)
    if args.dry_run:
        for unit in units:
            print(json.dumps(unit.__dict__))
        return 0
    recorded_at = datetime.now(UTC).isoformat()
    rows = prospective.record_sample(study, units, recorded_at=recorded_at)
    (study / "selection.json").write_text(
        json.dumps(
            {
                "recorded_at": recorded_at,
                "rule": raw.get("unit"),
                "per_repository": PER_REPOSITORY,
                "max_changed_lines": MAX_CHANGED_LINES,
                "walk": walks,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"{len(units)} units selected, {len(rows)} newly recorded -> {study / 'sample.jsonl'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
