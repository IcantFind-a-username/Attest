"""Every yellow and green line this repository has shown its own authors (phase 4).

Free and offline apart from one `gh` read per pull request: no model call, no
execution, $0.00.

D-174 merged in PR #12. From there to the tip, every `attest` self-review comment
on this repository's own pull requests is read and split by the marker the output
contract puts at the front of each line:

    [green]    the structural measure (D-133)
    [yellow]   yellow (a) impact scope (D-143/D-145), yellow (b) nullability
               (D-151) and yellow (b)'s propagation class (D-164) -- the three
               share one section and one cap of two, so a census has to read the
               HTML marker comment to tell them apart
    [red]      a certified finding
    [silent]   the one line a wholly silent review owes

Usage: .venv/bin/python scripts/acceptance/yellow_census.py [--json OUT]
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any

REPO = "IcantFind-a-username/Attest"
FIRST_PR = 12  # D-174 merged here; before it the yellow classes did not all exist

MARKER = re.compile(r"<!--\s*attest:(?P<kind>[a-z]+):", re.IGNORECASE)
LINE = re.compile(r"^\s*-?\s*\[(?P<level>green|yellow|red|silent|gate)\]\s*(?P<rest>.*)$")
# D-190 (merged in PR #15) put every refusal and every deferral on a contract
# line. Before it a deferred review posted bare prose with no level marker --
# exactly what mainline condition 7 forbids -- so the census counts those
# separately rather than as a silence, and the count is the adoption curve.
UNMARKED_DEFER = re.compile(r"^DEFER:\s", re.MULTILINE)


def _pulls() -> list[dict[str, Any]]:
    out = subprocess.run(
        ["gh", "pr", "list", "--repo", REPO, "--state", "all", "--limit", "100",
         "--json", "number,title,state,createdAt"],
        capture_output=True, text=True, check=True,
    )
    rows = [r for r in json.loads(out.stdout) if int(r["number"]) >= FIRST_PR]
    return sorted(rows, key=lambda r: int(r["number"]))


def _bodies(number: int) -> list[str]:
    """Every comment and review body the Action could have written."""
    out = subprocess.run(
        ["gh", "pr", "view", str(number), "--repo", REPO,
         "--json", "comments,reviews"],
        capture_output=True, text=True, check=False,
    )
    if out.returncode != 0:
        return []
    data = json.loads(out.stdout or "{}")
    bodies = [str(c.get("body") or "") for c in data.get("comments", [])]
    for review in data.get("reviews", []):
        bodies.append(str(review.get("body") or ""))
    # inline review comments live on a different endpoint
    api = subprocess.run(
        ["gh", "api", f"repos/{REPO}/pulls/{number}/comments", "--jq", ".[].body"],
        capture_output=True, text=True, check=False,
    )
    if api.returncode == 0:
        bodies.extend(line for line in api.stdout.splitlines() if line.strip())
    return [b for b in bodies if b.strip()]


def census() -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for pull in _pulls():
        number = int(pull["number"])
        counts = {"green": 0, "yellow_a": 0, "yellow_b": 0, "yellow_prop": 0,
                  "red": 0, "silent": 0, "unmarked_defer": 0}
        lines: list[dict[str, str]] = []
        # One note reaches an author twice -- once as an inline comment and once
        # in the summary body -- and that is one note, not two. The census
        # counts distinct lines per pull request, which is what an author reads.
        seen: set[tuple[str, str]] = set()
        for body in _bodies(number):
            if UNMARKED_DEFER.search(body):
                counts["unmarked_defer"] += 1
                lines.append({"level": "(none)", "class": "unmarked_defer",
                              "marker": "status",
                              "text": body.splitlines()[1][:400] if len(body.splitlines()) > 1
                                      else body[:400]})
            marker = MARKER.search(body)
            kind = marker.group("kind").lower() if marker else ""
            for raw in body.splitlines():
                match = LINE.match(raw)
                if not match:
                    continue
                level = match.group("level")
                if level == "yellow":
                    bucket = {"impact": "yellow_a", "nullability": "yellow_b",
                              "propagation": "yellow_prop"}.get(kind, "yellow_a")
                else:
                    bucket = level
                text = match.group("rest").strip()[:400]
                if (bucket, text) in seen:
                    continue
                seen.add((bucket, text))
                counts[bucket] = counts.get(bucket, 0) + 1
                lines.append({"level": level, "class": bucket, "marker": kind,
                              "text": text})
        rows.append({"pr": number, "title": str(pull["title"])[:80],
                     "state": str(pull["state"]), **counts, "lines": lines})
    return {"repository": REPO, "from_pull_request": FIRST_PR, "pull_requests": rows}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", default="")
    args = parser.parse_args()
    result = census()
    total = {"green": 0, "yellow_a": 0, "yellow_b": 0, "yellow_prop": 0, "red": 0,
             "silent": 0, "unmarked_defer": 0}
    for row in result["pull_requests"]:
        for key in total:
            total[key] += int(row.get(key, 0))
        print(f"#{row['pr']:<4} green={row['green']} yellow_a={row['yellow_a']} "
              f"yellow_b={row['yellow_b']} prop={row['yellow_prop']} red={row['red']} "
              f"silent={row['silent']} defer={row['unmarked_defer']}  {row['title'][:48]}")
    print()
    print("total:", total)
    result["totals"] = total
    if args.json:
        Path(args.json).write_text(json.dumps(result, indent=1, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
