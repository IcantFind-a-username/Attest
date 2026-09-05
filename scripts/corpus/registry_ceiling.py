"""Free ceiling estimator for the registry witness (docs/design/gate-reachability-registry.md).

**Not the witness, and not the gate level.** A name-based *upper bound*: for
every recorded new-code candidate that has no call site outside the added lines,
ask whether its symbol is *registered* anywhere in the head tree under one of
the four adapters the design names -- argparse, click, an HTTP route, a pytest
fixture. Name matching over-counts (a same-named symbol in another module
counts), which is what a ceiling should do.

It runs over both recorded populations -- E-04 stratum v2's 224 new-code
candidates and the 53 replay bundles -- and over one positive control, the
`attest 2878d4012e` case the owner named, which it must find or the scan means
nothing. Free: `git show` and `git grep` only, no model call, no spend.

    python scripts/corpus/registry_ceiling.py
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CORPORA = REPO / ".attest" / "corpora"
WITNESS = REPO / "docs" / "acceptance" / "evidence" / "2026-09-05-gate-witness.json"
REPLAY = REPO / "docs" / "acceptance" / "evidence" / "2026-09-05-gate-replay.json"
OUT = REPO / "docs" / "acceptance" / "evidence" / "2026-09-05-registry-ceiling.json"

CLONES = {
    "us-stock-helper": CORPORA / "us-stock-helper",
    "corum": CORPORA / "corum",
    "attest": CORPORA / "attest",
}


def show(clone: Path, sha: str, path: str) -> str:
    out = subprocess.run(
        ["git", "-C", str(clone), "show", f"{sha}:{path}"],
        capture_output=True,
        text=True,
        check=False,
    )
    return out.stdout if out.returncode == 0 else ""


def grep(clone: Path, sha: str, pattern: str) -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(clone), "grep", "-n", "-E", pattern, sha, "--", "*.py"],
        capture_output=True,
        text=True,
        check=False,
    )
    return out.stdout.splitlines() if out.returncode in (0, 1) else []


def decorators_of(source: str, symbol: str) -> list[str]:
    """The decorator lines immediately above `def symbol` / `async def symbol`."""
    lines = source.splitlines()
    found: list[str] = []
    definition = re.compile(rf"^\s*(async\s+)?def\s+{re.escape(symbol)}\s*\(")
    for index, line in enumerate(lines):
        if not definition.match(line):
            continue
        cursor = index - 1
        while cursor >= 0:
            stripped = lines[cursor].strip()
            if stripped.startswith("@"):
                found.append(stripped)
                cursor -= 1
                continue
            if not stripped or stripped.startswith("#"):
                cursor -= 1
                continue
            break
    return found


ADAPTERS = {
    # decorator shapes, matched at the definition site
    "click": re.compile(r"@(\w+\.)?(command|group)\b"),
    "http": re.compile(r"@(\w+\.)?(route|get|post|put|patch|delete|websocket)\b"),
    "fixture": re.compile(r"@(pytest\.)?fixture\b"),
}


def registry_hit(clone: Path, sha: str, symbol: str, path: str) -> tuple[str, str] | None:
    source = show(clone, sha, path)
    for decorator in decorators_of(source, symbol):
        for name, pattern in ADAPTERS.items():
            if pattern.search(decorator):
                return name, decorator[:70]
    # argparse and explicit registration tables: the symbol used as a *value*
    escaped = re.escape(symbol)
    shapes = [
        ("argparse", rf"set_defaults\([^)]*func\s*=\s*{escaped}\b"),
        ("argparse", rf"(type|action)\s*=\s*{escaped}\b"),
        ("click", rf"add_command\(\s*{escaped}\b"),
        ("http", rf"add_(url_rule|api_route|route)\([^)]*{escaped}\b"),
        ("table", rf"[\[\{{,:]\s*{escaped}\s*[,\}}\]\)]"),
    ]
    for name, shape in shapes:
        for line in grep(clone, sha, shape):
            body = line.split(":", 2)[-1]
            if re.search(rf"^\s*(async\s+)?def\s+{escaped}\b", body):
                continue
            return name, body.strip()[:70]
    return None


def positive_control() -> tuple[bool, str]:
    """The scan must find `attest 2878d4012e`: head 506aae1a13, `cmd_run`,
    registered at `run.set_defaults(func=cmd_run)`. A scan that misses it is
    not measuring what this document says it measures."""
    hit = registry_hit(CLONES["attest"], "506aae1a13", "cmd_run", "scripts/corpus/heldout_run.py")
    return hit is not None, "" if hit is None else f"{hit[0]}: {hit[1]}"


def scan(rows: list[dict], *, clone_of, sha_of, symbol_key="symbol", site_key="call_site"):
    """Rows a registry witness would newly admit, and why."""
    gained: list[dict[str, object]] = []
    considered = 0
    for row in rows:
        if row.get(site_key):
            continue  # already witnessed by (a)
        if not row.get(symbol_key):
            continue  # the recorded candidate names no symbol; nothing to look up
        considered += 1
        hit = registry_hit(clone_of(row), sha_of(row), str(row[symbol_key]), str(row["path"]))
        if hit is None:
            continue
        adapter, evidence = hit
        gained.append(
            {
                "symbol": row[symbol_key],
                "path": row["path"],
                "annotated": row.get("annotated"),
                "documented": row.get("documented"),
                "adapter": adapter,
                "evidence": evidence,
            }
        )
    return considered, gained


def main() -> int:
    found, detail = positive_control()
    verdict = f"FOUND {detail}" if found else "MISSED"
    print(f"positive control (attest 2878d4012e / cmd_run): {verdict}")
    if not found:
        print("the scan cannot be trusted; not reporting a ceiling", file=sys.stderr)
        return 2

    candidates = json.loads(WITNESS.read_text(encoding="utf-8"))["rows"]
    considered, gained = scan(
        candidates,
        clone_of=lambda row: CLONES[row["repo"]],
        sha_of=lambda row: str(row["unit_id"]).split("@")[-1],
    )
    replay = json.loads(REPLAY.read_text(encoding="utf-8"))["rows"]

    def replay_clone(row: dict) -> Path:
        direct = CORPORA / str(row["clone"])
        return direct if direct.is_dir() else CORPORA / "gnull" / str(row["clone"])

    replay_considered, replay_gained = scan(
        replay, clone_of=replay_clone, sha_of=lambda row: str(row["head"])
    )

    print(
        f"E-04 stratum v2 : {len(candidates)} candidates, "
        f"{sum(1 for r in candidates if r['call_site'])} with a call site today, "
        f"{considered} scanned, newly admitted {len(gained)}"
    )
    print(
        f"replay bundles  : {len(replay)} rows, "
        f"{sum(1 for r in replay if r.get('call_site'))} with a call site today, "
        f"{replay_considered} scanned, newly admitted {len(replay_gained)}"
    )
    for row in gained + replay_gained:
        print(f"  {row['adapter']:<9} {str(row['symbol']):<32} {row['evidence']}")

    payload = {
        "schema_version": "attest.registry-ceiling.v1",
        "positive_control": detail,
        "adapters": ["argparse", "click", "http", "fixture"],
        "candidates": {
            "rows": len(candidates),
            "with_call_site": sum(1 for r in candidates if r["call_site"]),
            "scanned": considered,
            "newly_admitted": len(gained),
            "per_adapter": dict(Counter(str(row["adapter"]) for row in gained)),
            "detail": gained,
        },
        "replay": {
            "rows": len(replay),
            "with_call_site": sum(1 for r in replay if r.get("call_site")),
            "scanned": replay_considered,
            "newly_admitted": len(replay_gained),
            "per_adapter": dict(Counter(str(row["adapter"]) for row in replay_gained)),
            "detail": replay_gained,
        },
    }
    Path(sys.argv[1] if len(sys.argv) > 1 else OUT).write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
