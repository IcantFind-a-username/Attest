"""Yellow (b) offline: how often does the null/Optional class speak, and about what?

D-151 builds the level; this runs it over the 79 units already on disk -- 11
forward pairs and 68 null controls -- and reports the three numbers the owner
asked for before it may ever be author-visible:

    the trigger rate, per population
    the premise verification pass rate, per premise
    the number of control units it would speak on (> 3% is not adopted)

    scan --population forward|controls|both --json <out> [--dry-run]

**Paid**, unlike yellow (a): one model call per unit that has a changed function
worth showing. Reserve in DEVSPEND.md first. `--dry-run` makes no call at all and
exercises the driver, the prompt and the checker over an empty hypothesis list.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "corpus"))

from driver_budget import DriverCap  # noqa: E402

from attest.github.presentation import nullability_line  # noqa: E402
from attest.review.impact import changed_functions  # noqa: E402
from attest.review.nullability import (  # noqa: E402
    HYPOTHESIS_MAX_TOKENS,
    HYPOTHESIS_SCHEMA,
    HYPOTHESIS_SYSTEM,
    NULLABILITY_POLICY_VERSION,
    PREMISES,
    hypotheses_from,
    notes_for_change,
    prompt_for,
)
from attest.review.proposer import ApiProvider  # noqa: E402

CORPORA = ROOT / ".attest" / "corpora"
RUNS = ROOT / "benchmarks" / "attest-v2" / "runs"
PAIRS = RUNS / "2026-09-05-forward-pairs.json"
CONTROLS = RUNS / "2026-09-05-g-null-001a-independent-population.json"

HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
MAX_TREE_FILES = 3_000
MAX_UNITS_PER_CALL = 5  # changed functions shown to the model in one prompt
MAX_FUNCTION_LINES = 120  # a function longer than this is not shown


def clone_of(repo: str) -> Path:
    direct = CORPORA / repo
    return direct if direct.is_dir() else CORPORA / "gnull" / repo


def git(repo: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=False
    )
    if done.returncode != 0:
        raise RuntimeError(done.stderr.strip()[:200] or "git failed")
    return done.stdout


def tree_sources(repo: Path, sha: str) -> dict[str, str]:
    listing = git(repo, "ls-tree", "-r", "--name-only", sha).splitlines()
    sources: dict[str, str] = {}
    for name in listing:
        if not name.endswith(".py") or len(sources) >= MAX_TREE_FILES:
            continue
        try:
            sources[name] = git(repo, "show", f"{sha}:{name}")
        except RuntimeError:
            continue
    return sources


def changed_lines(repo: Path, base: str, head: str) -> dict[str, set[int]]:
    diff = git(repo, "diff", "--unified=0", f"{base}..{head}", "--", "*.py")
    touched: dict[str, set[int]] = {}
    path = ""
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            path = line[6:]
            touched.setdefault(path, set())
            continue
        found = HUNK.match(line)
        if found and path:
            start = int(found.group(1))
            count = int(found.group(2) or 1)
            touched[path].update(range(start, start + max(count, 1)))
    return {p: lines for p, lines in touched.items() if lines}


def units(population: str) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    if population in {"forward", "both"}:
        document = json.loads(PAIRS.read_text(encoding="utf-8"))
        seen: set[tuple[str, str]] = set()
        for pair in document["pairs"]:
            if not pair.get("resolved"):
                continue
            key = (str(pair["repo"]), str(pair["head"]))
            if key in seen:
                continue
            seen.add(key)
            out.append(
                {
                    "population": "forward",
                    "repo": str(pair["repo"]),
                    "head": str(pair["head"]),
                    "base": str(pair["base"]),
                }
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


def _shown(sources: dict[str, str], touched: dict[str, set[int]], repo: Path, base: str):
    """The changed functions worth a prompt: existing at base, short enough."""
    shown: list[tuple[str, str, int, str]] = []
    for path, lines in sorted(touched.items()):
        head_source = sources.get(path)
        if head_source is None:
            continue
        try:
            base_source: str | None = git(repo, "show", f"{base}:{path}")
        except RuntimeError:
            base_source = None
        for changed in changed_functions(
            path=path, head_source=head_source, base_source=base_source, changed_lines=lines
        ):
            definition = changed.definition
            span = definition.end_line - definition.line + 1
            if span > MAX_FUNCTION_LINES:
                continue
            body = "\n".join(head_source.splitlines()[definition.line - 1 : definition.end_line])
            shown.append((path, definition.qualname, definition.line, body))
    shown.sort(key=lambda unit: (unit[0], unit[2]))
    return shown[:MAX_UNITS_PER_CALL]


def scan_unit(unit: dict[str, str], provider: Any | None) -> dict[str, object]:
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
    shown = _shown(sources, touched, repo, unit["base"])
    row.update({"ok": True, "functions_shown": len(shown)})
    if not shown:
        row.update({"hypotheses": 0, "notes": 0, "lines": [], "voided": [], "spend_usd": 0.0})
        return row
    if provider is None:
        payload: object = {"hypotheses": []}
        cost = 0.0
    else:
        result = provider.sample(
            system=HYPOTHESIS_SYSTEM,
            prompt=prompt_for(shown),
            schema=cast(dict[str, Any], HYPOTHESIS_SCHEMA),
            max_tokens=HYPOTHESIS_MAX_TOKENS,
        )
        try:
            payload = json.loads(result.text or "{}")
        except json.JSONDecodeError:
            payload = {}
        # sonnet-5 list price, the same basis the review path prices a sample at
        cost = result.input_tokens * 3e-6 + result.output_tokens * 15e-6
    hypotheses = hypotheses_from(payload)
    notes, voided = notes_for_change(sources, hypotheses)
    row.update(
        {
            "hypotheses": len(hypotheses),
            "notes": len(notes),
            "lines": [nullability_line(note) for note in notes],
            "voided": [
                {
                    "parameter": h.parameter,
                    "at": f"{h.path}:{h.access_line}",
                    "failed": [v.premise for v in verdicts if not v.holds],
                    "detail": next((v.detail for v in verdicts if not v.holds), ""),
                }
                for h, verdicts in voided
            ],
            "spend_usd": round(cost, 6),
        }
    )
    return row


def cmd_scan(args: argparse.Namespace) -> int:
    provider = None
    if not args.dry_run:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            print("no ANTHROPIC_API_KEY; use --dry-run", file=sys.stderr)
            return 2
        provider = ApiProvider(model=args.model)
    rows: list[dict[str, object]] = []
    # D-172: a unit's *maximum* is reserved before it starts. This level buys at
    # most one proposal per unit, so `--reserve` is that call's ceiling rather
    # than a per-review budget; the measured cost is ~$0.0013 a unit.
    cap = DriverCap(cap=args.cap, reservation_usd=args.reserve)
    for unit in units(args.population):
        refusal = cap.refusal(str(unit.get("head", ""))[:10])
        if refusal is not None:
            print(refusal, flush=True)
            break
        cap.start(str(unit.get("head", ""))[:10])
        row = scan_unit(unit, provider)
        cap.settle(float(row.get("spend_usd", 0.0) or 0.0))
        spent = cap.spent
        rows.append(row)
        print(
            f"{row['population']:8s} {row['repo']:>14s} {str(row['head'])[:10]} "
            f"shown={row.get('functions_shown', 0)} hyp={row.get('hypotheses', 0)} "
            f"notes={row.get('notes', 0)} ${spent:.4f}",
            flush=True,
        )
    payload: dict[str, object] = {
        "schema_version": "attest.nullability-scan.v1",
        "policy_version": NULLABILITY_POLICY_VERSION,
        "model": args.model if provider is not None else "none (dry run)",
        "generated": datetime.now(UTC).isoformat(),
        "population": args.population,
        "spend_usd": round(spent, 6),
        "rows": rows,
    }
    summary: dict[str, object] = {}
    for name in ("forward", "controls"):
        scanned = [r for r in rows if r["population"] == name and r["ok"]]
        if not scanned:
            continue
        triggered = [r for r in scanned if int(r.get("notes") or 0) > 0]
        failures: Counter[str] = Counter()
        hypotheses = sum(int(r.get("hypotheses") or 0) for r in scanned)
        for row in scanned:
            for void in cast(list[dict[str, Any]], row.get("voided") or []):
                for premise in void["failed"]:
                    failures[premise] += 1
        summary[name] = {
            "units_scanned": len(scanned),
            "units_failed": sum(1 for r in rows if r["population"] == name and not r["ok"]),
            "units_triggering": len(triggered),
            "trigger_rate": round(len(triggered) / len(scanned), 4),
            "hypotheses_total": hypotheses,
            "notes_total": sum(int(r.get("notes") or 0) for r in scanned),
            "premise_pass_rate": round(
                sum(int(r.get("notes") or 0) for r in scanned) / hypotheses, 4
            )
            if hypotheses
            else None,
            "first_failing_premise": {p: failures.get(p, 0) for p in PREMISES},
            "spend_usd": round(sum(float(r.get("spend_usd") or 0.0) for r in scanned), 6),
        }
    payload["summary"] = summary
    if args.json:
        args.json.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    for name, value in summary.items():
        assert isinstance(value, dict)
        print(
            f"{name}: {value['units_triggering']} of {value['units_scanned']} units trigger "
            f"({value['trigger_rate']:.1%}); {value['hypotheses_total']} hypotheses, "
            f"{value['notes_total']} survived all three premises "
            f"(pass rate {value['premise_pass_rate']}); "
            f"failed premises {value['first_failing_premise']}; ${value['spend_usd']:.4f}"
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    scan = sub.add_parser("scan")
    scan.add_argument("--population", choices=("forward", "controls", "both"), default="both")
    scan.add_argument("--json", type=Path)
    scan.add_argument("--model", default="claude-sonnet-5")
    scan.add_argument("--cap", type=float, default=5.0)
    scan.add_argument(
        "--reserve",
        type=float,
        default=0.05,
        help="the most one unit's single proposal call may cost; reserved before "
        "the unit starts and released to its actual cost afterwards",
    )
    scan.add_argument("--dry-run", action="store_true")
    scan.set_defaults(func=cmd_scan)
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
