"""Yellow (a) offline: how often does the impact level speak, and about what?

D-143 builds the level; this runs it over corpora that are already on disk and
reports the one number that decides whether it may ever be author-visible --
**the trigger rate** -- with five sampled lines a person can check by hand.

    scan --population forward|controls|both --json <out>

**Free.** No model, no container, no network: `git` reads two trees and `ast`
does the rest. Nothing here publishes anything.

The two populations answer different questions. The **forward pairs** are
defect-introducing commits, so a level meant to say "this change reaches
somewhere untested" ought to speak on some of them. The **null controls** are
ordinary old commits nobody had to fix, so the rate there is the level's noise
floor: yellow (a) claims no defect, but a level that fires on every commit is
not information.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from attest.github.presentation import impact_line  # noqa: E402
from attest.review.impact import (  # noqa: E402
    IMPACT_POLICY_VERSION,
    build_call_graph,
    changed_functions,
    notes_for_change,
)

CORPORA = ROOT / ".attest" / "corpora"
RUNS = ROOT / "benchmarks" / "attest-v2" / "runs"
PAIRS = RUNS / "2026-09-05-forward-pairs.json"
CONTROLS = RUNS / "2026-09-05-g-null-001a-independent-population.json"

HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
MAX_TREE_FILES = 3_000


def clone_of(repo: str) -> Path:
    direct = CORPORA / repo
    return direct if direct.is_dir() else CORPORA / "gnull" / repo


def git(repo: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=False
    )
    if done.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {done.stderr.strip()[:160]}")
    return done.stdout


def tree_sources(repo: Path, sha: str) -> dict[str, str]:
    """Every Python file of one revision, read in a single `git cat-file` pass."""
    names = [
        line.strip()
        for line in git(repo, "ls-tree", "-r", "--name-only", sha).splitlines()
        if line.strip().endswith(".py")
    ][:MAX_TREE_FILES]
    if not names:
        return {}
    request = "\n".join(f"{sha}:{name}" for name in names) + "\n"
    done = subprocess.run(
        ["git", "-C", str(repo), "cat-file", "--batch"],
        input=request.encode(),
        capture_output=True,
        check=False,
    )
    sources: dict[str, str] = {}
    data = done.stdout
    offset = 0
    for name in names:
        end = data.find(b"\n", offset)
        if end == -1:
            break
        header = data[offset:end].decode("utf-8", "replace").split()
        offset = end + 1
        if len(header) != 3 or header[1] != "blob":
            continue  # missing or non-blob: skipped, never guessed at
        size = int(header[2])
        sources[name] = data[offset : offset + size].decode("utf-8", "replace")
        offset += size + 1
    return sources


def changed_lines(repo: Path, base: str, head: str) -> dict[str, set[int]]:
    """Head-side line numbers the diff touched, per Python file."""
    text = git(repo, "diff", "--unified=0", "--no-color", base, head, "--", "*.py")
    out: dict[str, set[int]] = {}
    path: str | None = None
    for line in text.splitlines():
        if line.startswith("+++ b/"):
            path = line[6:].strip()
            if path == "/dev/null":
                path = None
            elif path is not None:
                out.setdefault(path, set())
            continue
        match = HUNK.match(line)
        if match is not None and path is not None:
            start = int(match.group(1))
            count = int(match.group(2) or 1)
            out[path].update(range(start, start + max(count, 1)))
    return {path: lines for path, lines in out.items() if lines}


def units(population: str) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    if population in {"forward", "both"}:
        document = json.loads(PAIRS.read_text(encoding="utf-8"))
        seen: set[tuple[str, str, str]] = set()
        for pair in document["pairs"]:
            if not pair.get("resolved"):
                continue
            key = (str(pair["repo"]), str(pair["head"]), str(pair["base"]))
            if key in seen:
                continue
            seen.add(key)
            out.append(
                {"population": "forward", "repo": key[0], "head": key[1], "base": key[2]}
            )
    if population in {"controls", "both"}:
        document = json.loads(CONTROLS.read_text(encoding="utf-8"))
        for control in document["controls"]:
            if not control.get("qualified"):
                continue
            out.append(
                {
                    "population": "controls",
                    "repo": str(control["repo"]),
                    "head": str(control["sha"]),
                    "base": str(control["base"]),
                }
            )
    return out


def scan_unit(unit: dict[str, str]) -> dict[str, object]:
    repo = clone_of(unit["repo"])
    row: dict[str, object] = {**unit, "ok": False}
    if not repo.is_dir():
        row["error"] = f"no clone at {repo}"
        return row
    try:
        touched = changed_lines(repo, unit["base"], unit["head"])
        sources = tree_sources(repo, unit["head"])
    except RuntimeError as error:
        row["error"] = str(error)[:160]
        return row
    graph = build_call_graph(sources)
    changed = []
    for path, lines in sorted(touched.items()):
        head_source = sources.get(path)
        if head_source is None:
            continue
        try:
            base_source: str | None = git(repo, "show", f"{unit['base']}:{path}")
        except RuntimeError:
            base_source = None  # added file: no counterpart, so no interface claim
        changed.extend(
            changed_functions(
                path=path,
                head_source=head_source,
                base_source=base_source,
                changed_lines=lines,
            )
        )
    notes = notes_for_change(graph, changed)
    row.update(
        {
            "ok": True,
            "files_changed": len(touched),
            "tree_files": len(sources),
            "changed_functions": len(changed),
            "interface_changes": sum(1 for c in changed if c.interface_changed),
            "notes": len(notes),
            "reasons": [note.reason for note in notes],
            "lines": [impact_line(note) for note in notes],
            "callers": [len(note.callers) for note in notes],
            "untested": [len(note.untested) for note in notes],
        }
    )
    return row


def cmd_scan(args: argparse.Namespace) -> int:
    rows = [scan_unit(unit) for unit in units(args.population)]
    payload: dict[str, object] = {
        "schema_version": "attest.impact-scan.v1",
        "policy_version": IMPACT_POLICY_VERSION,
        "generated": datetime.now(UTC).isoformat(),
        "population": args.population,
        "rows": rows,
    }
    summary: dict[str, object] = {}
    for name in ("forward", "controls"):
        scanned = [r for r in rows if r["population"] == name and r["ok"]]
        if not scanned:
            continue
        triggered = [r for r in scanned if int(r["notes"] or 0) > 0]
        reasons: Counter[str] = Counter()
        for row in scanned:
            reasons.update(list(row["reasons"]))  # type: ignore[arg-type]
        summary[name] = {
            "units_scanned": len(scanned),
            "units_failed": sum(
                1 for r in rows if r["population"] == name and not r["ok"]
            ),
            "units_triggering": len(triggered),
            "trigger_rate": round(len(triggered) / len(scanned), 4),
            "notes_total": sum(int(r["notes"] or 0) for r in scanned),
            "changed_functions_total": sum(int(r["changed_functions"] or 0) for r in scanned),
            "reasons": dict(reasons),
        }
    payload["summary"] = summary
    if args.json:
        args.json.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    for name, value in summary.items():
        assert isinstance(value, dict)
        print(
            f"{name}: {value['units_triggering']} of {value['units_scanned']} units trigger "
            f"({value['trigger_rate']:.1%}), {value['notes_total']} notes, "
            f"{value['units_failed']} unscannable; reasons {value['reasons']}"
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    scan = sub.add_parser("scan")
    scan.add_argument("--population", choices=("forward", "controls", "both"), default="both")
    scan.add_argument("--json", type=Path)
    scan.set_defaults(func=cmd_scan)
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
