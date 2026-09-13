"""The index repair (D-246), free: the forty rebuilt trees under three retrieval
versions, and the regex-era caller snippets the repaired index does not give.

For every case of `mutations-v1-recall` the tree is checked out at its recorded
head and `plan_review` is run three times -- with the regex planner that D-245
replaced (the parent of `e75ac07`), with the D-245 index as it was measured on
2026-09-14 (`main` at `a16312a`), and with the working tree's repaired index --
and the caller snippets of each plan are counted. The index-level census of
the report script (`mutation_index_report.census`) is recomputed per finding
with the D-245 index and with the repaired one. Then every caller snippet the
regex planner put in a plan is looked up in the repaired index: a site the
index does not report is listed with its line for the reader to judge. No
model is called; nothing is bought.

    python scripts/acceptance/index_repair_census.py \\
        --facts docs/acceptance/evidence/2026-09-14-index-repair/census.json
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "corpus"))
sys.path.insert(0, str(ROOT / "scripts" / "acceptance"))

REGEX_REF = "e75ac07^"  # the planner before D-245
D245_REF = "a16312a"  # D-245 as measured on 2026-09-14
STUDY = ROOT / "benchmarks" / "studies" / "mutations-v1-recall"
EVIDENCE_D245 = ROOT / "docs" / "acceptance" / "evidence" / "2026-09-14-forty-with-index"
EVIDENCE_D240 = (
    ROOT / "docs" / "acceptance" / "evidence" / "2026-09-13-mutation-recall" / "search-v3b"
)


def _load_from_git(ref: str, path: str, name: str, workdir: Path, patch=None) -> ModuleType:
    text = subprocess.run(
        ["git", "-C", str(ROOT), "show", f"{ref}:{path}"], capture_output=True, text=True,
        check=True,
    ).stdout
    if patch is not None:
        text = patch(text)
    file = workdir / f"{name}.py"
    file.write_text(text, encoding="utf-8")
    spec = importlib.util.spec_from_file_location(name, file)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    ).stdout.strip()


def _callers_in_plan(plan) -> tuple[list[dict], list[str]]:
    callers = [
        {"unit": unit.unit_id, "symbol": s.symbol, "path": s.path, "start": s.start,
         "end": s.end, "text": s.text, "resolution": getattr(s, "resolution", "")}
        for unit in plan.units
        for s in unit.context
        if s.kind == "caller"
    ]
    return callers, [o for unit in plan.units for o in unit.omissions]


def _call_line(snippet: dict, def_re: re.Pattern[str]) -> tuple[int, str]:
    """The line the regex matched inside its window: the first line that
    carries `name(` and is not a definition."""
    name = re.escape(snippet["symbol"])
    pattern = re.compile(rf"(?<![\w.]){name}\s*\(|\.{name}\s*\(")
    for offset, line in enumerate(snippet["text"].splitlines()):
        if pattern.search(line) and not def_re.match("+" + line.strip()):
            return snippet["start"] + offset, line.strip()
    return snippet["start"], ""


def _index_census(index_module: ModuleType, repo: Path, findings: dict) -> dict[str, dict]:
    from attest.review.executor import _changed_definitions

    index = index_module.tree_index(repo)
    out: dict[str, dict] = {}
    for finding_id, (file, line) in findings.items():
        try:
            source = (repo / file).read_text(encoding="utf-8", errors="replace")
        except OSError:
            out[finding_id] = {"file": file, "line": line, "symbols": [], "exact": 0,
                               "attribute": 0, "sites": []}
            continue
        symbols = [n.rsplit(":", 1)[0] for n in _changed_definitions(source, [line])]
        module = index.module_of(file)
        sites = [s for name in symbols for s in index.callers_of(module, name)] if module else []
        out[finding_id] = {
            "file": file, "line": line, "symbols": symbols,
            "exact": sum(1 for s in sites if s.resolution == "exact"),
            "attribute": sum(1 for s in sites if s.resolution != "exact"),
            "sites": [{"path": s.path, "line": s.line, "resolution": s.resolution,
                       "name": s.name, "callee": s.callee} for s in sites],
        }
    return out


def run(workdir: Path) -> dict[str, dict]:
    from mutation_index_report import _read_jsonl, run_facts
    from mutation_recall import REPOSITORIES, WORK

    index_d245 = _load_from_git(D245_REF, "src/attest/review/index.py", "index_d245", workdir)
    planner_regex = _load_from_git(
        REGEX_REF, "src/attest/review/planner.py", "planner_regex", workdir
    )
    planner_d245 = _load_from_git(
        D245_REF, "src/attest/review/planner.py", "planner_d245", workdir,
        patch=lambda t: t.replace("from attest.review.index import TreeIndex, tree_index",
                                  "from index_d245 import TreeIndex, tree_index"),
    )
    import attest.review.index as index_repaired
    import attest.review.planner as planner_repaired
    from attest.review.diffs import git_diff

    def facts_of(evidence: Path, trials: str) -> dict[str, dict]:
        ledgers = {lib: _read_jsonl(evidence / f"{lib}-ledger.jsonl") for lib in REPOSITORIES}
        assert any(ledgers.values()), f"no ledger under {evidence}: the input is empty"
        return run_facts(STUDY / trials, STUDY / f"lines-{Path(trials).stem}.jsonl", ledgers)

    sample = _read_jsonl(STUDY / "sample.jsonl")
    assert sample, "the sample is empty"
    d245 = facts_of(EVIDENCE_D245, "trials-with-index.jsonl")
    d240 = facts_of(EVIDENCE_D240, "trials-search-v3b.jsonl")
    results: dict[str, dict] = {}
    for row in sample:
        unit = str(row["unit_id"])
        manifest = json.loads((WORK / "cases" / unit / "manifest.json").read_text("utf-8"))
        repo = Path(manifest["repo_path"])
        _git(repo, "checkout", "-q", "--", ".")
        _git(repo, "checkout", "-q", "--detach", manifest["head_sha"])
        diff = git_diff(repo, manifest["base_sha"])
        changed_paths = sorted(diff.hunks)
        plans: dict[str, dict] = {}
        for name, module in (
            ("regex", planner_regex), ("d245", planner_d245), ("repaired", planner_repaired)
        ):
            plan = module.plan_review(repo, diff, manifest["base_sha"])
            callers, omissions = _callers_in_plan(plan)
            plans[name] = {"callers": callers, "omissions": omissions,
                           "context_chars": sum(len(u.prompt_context()) for u in plan.units)}
        findings = d245[unit]["findings"]
        index = index_repaired.tree_index(repo)
        symbols = {c["symbol"] for c in plans["regex"]["callers"]}
        given: set[tuple[str, int, str]] = set()
        importers: set[str] = set()
        for path in changed_paths:
            module_name = index.module_of(path)
            if not module_name:
                continue
            importers.update(index.importers_of(module_name))
            for symbol in symbols:
                given.update(
                    (s.path, s.line, symbol) for s in index.callers_of(module_name, symbol)
                )
        regex_only = []
        for snippet in plans["regex"]["callers"]:
            line, text = _call_line(snippet, planner_regex._DEF_RE)
            if (snippet["path"], line, snippet["symbol"]) in given:
                continue
            at_line = [
                s for s in index.calls
                if s.path == snippet["path"] and s.line == line and s.name == snippet["symbol"]
            ]
            regex_only.append({
                "path": snippet["path"], "line": line, "symbol": snippet["symbol"], "text": text,
                "index_says": [{"callee": s.callee, "resolution": s.resolution} for s in at_line],
                "file_imports_changed_module": snippet["path"] in importers,
                "same_file": snippet["path"] in changed_paths,
            })
        results[unit] = {
            "stratum": row["stratum"],
            "changed_paths": changed_paths,
            "ledger_callers": {"d240_run": d240[unit]["plan"]["callers"],
                               "d245_run": d245[unit]["plan"]["callers"]},
            "plans": {k: {**v, "callers": [{kk: vv for kk, vv in c.items() if kk != "text"}
                                            for c in v["callers"]]}
                      for k, v in plans.items()},
            "census": {"d245": _index_census(index_d245, repo, findings),
                       "repaired": _index_census(index_repaired, repo, findings)},
            "regex_only": regex_only,
        }
        print(json.dumps({"unit": unit, **{k: len(v["callers"]) for k, v in plans.items()},
                          "regex_only": len(regex_only)}), flush=True)
    return results


def tables(results: dict[str, dict]) -> str:
    lines = [
        "| case | stratum | regex plan | D-245 plan | repaired plan | index D-245 exact / "
        "attribute | index repaired exact / attribute | omissions D-245 → repaired |",
        "|---|---|---|---|---|---|---|---|",
    ]
    totals = [0] * 7
    for unit, d in results.items():
        p = d["plans"]
        c1, c2 = d["census"]["d245"], d["census"]["repaired"]
        row = [len(p["regex"]["callers"]), len(p["d245"]["callers"]), len(p["repaired"]["callers"]),
               sum(c["exact"] for c in c1.values()), sum(c["attribute"] for c in c1.values()),
               sum(c["exact"] for c in c2.values()), sum(c["attribute"] for c in c2.values())]
        totals = [a + b for a, b in zip(totals, row, strict=True)]
        omissions = (f"{'; '.join(p['d245']['omissions']) or 'none'} → "
                     f"{'; '.join(p['repaired']['omissions']) or 'none'}")
        lines.append(f"| `{unit}` | {d['stratum']} | {row[0]} | {row[1]} | {row[2]} | "
                     f"{row[3]} / {row[4]} | {row[5]} / {row[6]} | {omissions} |")
    lines.append(f"| **the forty** | | **{totals[0]}** | **{totals[1]}** | **{totals[2]}** | "
                 f"**{totals[3]} / {totals[4]}** | **{totals[5]} / {totals[6]}** | |")
    lines += ["", "| # | case | site | symbol | the line | the repaired index at that line |",
              "|---|---|---|---|---|---|"]
    n = 0
    for unit, d in results.items():
        for x in d["regex_only"]:
            n += 1
            says = ", ".join(
                f"{s['resolution']}→`{s['callee'] or '?'}`" for s in x["index_says"]
            ) or "no call site"
            text = x["text"].replace("|", "\\|").replace("`", "'")
            lines.append(f"| {n} | `{unit}` | `{x['path']}:{x['line']}` | `{x['symbol']}` | "
                         f"`{text[:90]}` | {says}; file imports the changed module: "
                         f"{'yes' if x['file_imports_changed_module'] else 'no'}; "
                         f"same file: {'yes' if x['same_file'] else 'no'} |")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--facts", required=True)
    args = parser.parse_args(argv)
    with tempfile.TemporaryDirectory() as tmp:
        results = run(Path(tmp))
    facts = Path(args.facts)
    facts.parent.mkdir(parents=True, exist_ok=True)
    facts.write_text(json.dumps(results, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(tables(results))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
