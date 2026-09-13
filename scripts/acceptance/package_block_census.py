"""Does the shared package block's bound bind on real traffic? (D-246, step 4; free)

For every pull request of the three natural-traffic batches (`e05-external-v1`,
`-v2`, `-v3`, 68 in all) the clone is checked out at the pull request's head
and `package_block_report` is called on every file a review would have built
the block on -- the discovery anchor (the first planned unit's first file) and
the anchored file of every candidate that reached verification, read from the
committed ledgers -- and the report says whether the 120k bound cut anything,
which files it cut, and whether any of them imports the changed module. The
block is built here offline because no measured run built one: the shipped
`context_strategy` is `r01`. No model is called; nothing is bought.

    python scripts/acceptance/package_block_census.py \\
        --facts docs/acceptance/evidence/2026-09-14-index-repair/package-block.json
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from attest.review.index import tree_index  # noqa: E402
from attest.review.planner import MAX_PACKAGE_BLOCK_CHARS, package_block_report  # noqa: E402

STUDIES = ROOT / "benchmarks" / "studies"
EVIDENCE = ROOT / "docs" / "acceptance" / "evidence"
BATCHES = (
    ("e05-external-v1", "gnull", EVIDENCE / "2026-09-12-lines-on-real-prs" / "run-b"),
    ("e05-external-v2", "e05v2", EVIDENCE / "2026-09-13-lines-on-real-prs-batch2" / "run-c"),
    ("e05-external-v3", "e05v3", EVIDENCE / "2026-09-14-lines-on-real-prs-batch3" / "run-d"),
)


def _read_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def _clone_name(repository: str) -> str:
    return repository.split("/")[-1].lower().lstrip("-")


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    ).stdout.strip()


def anchors_of(rows: list[dict]) -> tuple[str, list[str]]:
    """The discovery anchor and the verified candidates' anchored files, from
    one task's ledger rows."""
    plan = next((r for r in rows if r.get("kind") == "review_plan"), None)
    discovery = ""
    if plan and plan.get("units"):
        files = plan["units"][0].get("files") or []
        discovery = str(files[0]) if files else ""
    signals = {
        str(r.get("finding_id")): str(r.get("file") or "")
        for r in rows
        if r.get("kind") == "history_signal"
    }
    verified = sorted(
        {
            signals[str(r.get("finding_id"))]
            for r in rows
            if r.get("kind") == "verification" and str(r.get("finding_id")) in signals
        }
    )
    return discovery, [f for f in verified if f]


def run() -> list[dict]:
    out: list[dict] = []
    for study, corpus, evidence in BATCHES:
        sample = _read_jsonl(STUDIES / study / "sample.jsonl")
        trials = {r["unit_id"]: r for r in _read_jsonl(STUDIES / study / "trials.jsonl")}
        assert sample and trials, f"{study}: the sample or the trials file is empty"
        ledgers: dict[str, list[dict]] = {}
        for row in sample:
            unit = str(row["unit_id"])
            name = _clone_name(str(row["repository"]))
            if name not in ledgers:
                ledgers[name] = _read_jsonl(evidence / f"{name}-ledger.jsonl")
                assert ledgers[name], f"{evidence / name}-ledger.jsonl is empty"
            trial = trials.get(unit)
            rows = [
                r for r in ledgers[name] if trial and r.get("task_id") == trial.get("task_id")
            ]
            discovery, verified = anchors_of(rows)
            repo = ROOT / ".attest" / "corpora" / corpus / name
            _git(repo, "checkout", "-q", "--", ".")
            _git(repo, "checkout", "-q", "--detach", str(row["head_sha"]))
            index = tree_index(repo)
            blocks = []
            for anchor in sorted({a for a in [discovery, *verified] if a}):
                if not (repo / anchor).is_file():
                    blocks.append({"anchor": anchor, "missing": True})
                    continue
                report = package_block_report(repo, anchor)
                module = index.module_of(anchor)
                importers = set(index.importers_of(module)) if module else set()
                blocks.append({
                    "anchor": anchor,
                    "role": "discovery" if anchor == discovery else "verification",
                    "chars": report.chars,
                    "files_kept": len(report.files),
                    "omitted": list(report.omitted),
                    "omitted_importing_the_changed_module": sorted(
                        f for f in report.omitted if f in importers
                    ),
                })
            out.append({
                "study": study,
                "unit_id": unit,
                "repository": row["repository"],
                "head_sha": row["head_sha"],
                "task_id": trial.get("task_id") if trial else "",
                "discovery_anchor": discovery,
                "verified_anchors": verified,
                "blocks": blocks,
                "bound_hit": any(b.get("omitted") for b in blocks),
            })
            print(json.dumps({"unit": unit, "anchors": len(blocks),
                              "bound_hit": out[-1]["bound_hit"],
                              "max_chars": max((b.get("chars", 0) for b in blocks), default=0)}),
                  flush=True)
    return out


def table(results: list[dict]) -> str:
    lines = [
        f"| pull request | batch | anchored files (discovery, verified) | largest block, chars "
        f"(bound {MAX_PACKAGE_BLOCK_CHARS:,}) | bound hit | files cut | cut files that import "
        "the changed module |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in results:
        blocks = [b for b in r["blocks"] if not b.get("missing")]
        largest = max((b["chars"] for b in blocks), default=0)
        cut = sorted({f for b in blocks for f in b["omitted"]})
        importing = sorted({f for b in blocks for f in b["omitted_importing_the_changed_module"]})
        anchors = ", ".join(f"`{b['anchor']}`" for b in r["blocks"]) or "none"
        cut_cell = "—"
        if cut:
            sources = sum(1 for f in cut if "test" not in f.lower())
            cut_cell = f"{len(cut)} ({sources} source, {len(cut) - sources} test)"
        lines.append(
            f"| `{r['unit_id']}` | {r['study'].removeprefix('e05-external-')} | {anchors} | "
            f"{largest:,} | {'**yes**' if r['bound_hit'] else 'no'} | {cut_cell} | "
            f"{', '.join(f'`{f}`' for f in importing) or '—'} |"
        )
    hit = sum(1 for r in results if r["bound_hit"])
    importing_any = sum(
        1 for r in results
        if any(b.get("omitted_importing_the_changed_module") for b in r["blocks"])
    )
    lines.append(
        f"| **{len(results)} pull requests** | | | | **{hit} hit the bound** | | "
        f"**{importing_any} cut an importer** |"
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--facts", required=True)
    args = parser.parse_args(argv)
    results = run()
    facts = Path(args.facts)
    facts.parent.mkdir(parents=True, exist_ok=True)
    facts.write_text(json.dumps(results, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(table(results))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
