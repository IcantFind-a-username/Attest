"""A named re-run of some of the forty, reported against the original run (0.3.0 step 1).

Reads the downloaded artifact of a `mutation-recall.yml` dispatch that ran with
`only` -- its own trials file, lines file and ledgers -- and, for every case it
ran, the class the original run gave (from the committed trials and ledgers)
beside the class it has now. The recall over forty is recomputed with the re-run
cases' new classes in place of their old ones; the denominator does not move,
and a case the re-run did not name keeps its original class. Appends a section
to the dated report. Free: JSON on disk, no model.

    python scripts/acceptance/mutation_rerun_report.py \\
        --artifact <downloaded artifact dir> --run-id <id> \\
        --trials trials-rerun-env.jsonl \\
        --title "The eight environment cases, re-run after D-236" \\
        --report docs/acceptance/2026-09-13-mutation-recall.md
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "corpus"))
sys.path.insert(0, str(ROOT / "src"))

from heldout_v2 import wilson  # noqa: E402
from mutation_recall import REPOSITORIES, classify  # noqa: E402

RUNS = "https://github.com/IcantFind-a-username/Attest/actions/runs"
STUDY = ROOT / "benchmarks" / "studies" / "mutations-v1-recall"
EVIDENCE = ROOT / "docs" / "acceptance" / "evidence" / "2026-09-13-mutation-recall"
# D-235 withdrew this case's receipt on replay; the baseline counts it as no receipt
WITHDRAWN_BEFORE = {"packaging-none_guard-13--forward": "no receipt: withdrawn under D-235"}


def _read_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def _cell(text: object) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def original_classes() -> dict[str, tuple[str, str]]:
    """Every case's class in the original run, from the committed evidence."""
    trials = {r["unit_id"]: r for r in _read_jsonl(STUDY / "trials.jsonl")}
    ledgers: dict[str, list[dict]] = {}
    for run in ("run-1", "run-2"):
        for library in REPOSITORIES:
            rows = _read_jsonl(EVIDENCE / run / f"{library}-ledger.jsonl")
            ledgers.setdefault(library, []).extend(rows)
    out: dict[str, tuple[str, str]] = {}
    for row in _read_jsonl(STUDY / "sample.jsonl"):
        unit = str(row["unit_id"])
        trial = trials.get(unit)
        if trial is None:
            out[unit] = ("not run", "")
            continue
        mine = [e for e in ledgers[str(row["library"])] if e.get("task_id") == trial["task_id"]]
        klass, why = classify(mine, str(trial.get("deferred_reason") or ""))
        if unit in WITHDRAWN_BEFORE:
            klass, why = WITHDRAWN_BEFORE[unit], why
        out[unit] = (klass, why)
    return out


def rerun_classes(artifact: Path, trials_name: str) -> dict[str, dict]:
    study_dir = artifact / "benchmarks" / "studies" / "mutations-v1-recall"
    trials = _read_jsonl(study_dir / trials_name)
    assert trials, f"the re-run wrote no trial to {trials_name}: the input is empty"
    lines_path = study_dir / f"lines-{Path(trials_name).stem}.jsonl"
    lines = {r["unit_id"]: r for r in _read_jsonl(lines_path)}
    sample = {r["unit_id"]: r for r in _read_jsonl(STUDY / "sample.jsonl")}
    ledgers: dict[str, list[dict]] = {}
    for library in REPOSITORIES:
        clone = artifact / ".attest" / "corpora" / "mutations-v1-recall" / library / "repo"
        path = clone / ".attest" / "ledger.jsonl"
        ledgers[library] = _read_jsonl(path)
    assert any(ledgers.values()), "no ledger in the artifact: the input is empty"
    out: dict[str, dict] = {}
    for trial in trials:
        unit = str(trial["unit_id"])
        library = str(sample[unit]["library"])
        mine = [e for e in ledgers[library] if e.get("task_id") == trial["task_id"]]
        klass, why = classify(mine, str(trial.get("deferred_reason") or ""))
        entry = lines.get(unit, {}).get("lines", {})
        probes = [e for e in mine if e.get("kind") == "probe_observation"]
        out[unit] = {
            "class": klass,
            "why": why,
            "spend": float(trial.get("spend_usd") or 0.0),
            "lines": {k: len(v) for k, v in entry.items() if v},
            "recordings": len(probes),
            "verifications": sum(1 for e in mine if e.get("kind") == "verification"),
        }
    return out


def section(
    title: str, run_id: str, before: dict[str, tuple[str, str]], after: dict[str, dict]
) -> str:
    n = len(before)
    certified_before = sum(1 for k, _w in before.values() if k == "certified")
    merged = {
        unit: (after[unit]["class"] if unit in after else klass)
        for unit, (klass, _w) in before.items()
    }
    certified_after = sum(1 for k in merged.values() if k == "certified")
    recorded = sum(1 for a in after.values() if a["recordings"] > 0)
    low_b, high_b = wilson(certified_before, n)
    low_a, high_a = wilson(certified_after, n)
    spend = sum(a["spend"] for a in after.values())
    out = [f"## 1b. {title}", ""]
    out.append(
        f"**Run [`{run_id}`]({RUNS}/{run_id}), `mutation-recall.yml` with `only` naming the "
        f"{len(after)} cases below, code from `main` after D-236 and D-237, ${spend:.4f}.** The "
        f"denominator is forty; a case not named keeps its class from the original run and the "
        f"D-235 replay. **{recorded} of {len(after)} cases now record a probe on the merge base** "
        f"(none did before)."
    )
    out.append("")
    out.append("| | before | after the re-run |")
    out.append("|---|---|---|")
    out.append(f"| certified | **{certified_before}** | **{certified_after}** |")
    out.append(f"| point estimate | {certified_before / n:.1%} | **{certified_after / n:.1%}** |")
    out.append(f"| Wilson 95% | [{low_b:.1%}, {high_b:.1%}] | **[{low_a:.1%}, {high_a:.1%}]** |")
    out.append("")
    out.append("| case | before | after | recordings | verifications | lines | why now | spend |")
    out.append("|---|---|---|---|---|---|---|---|")
    for unit, a in after.items():
        klass_before = before.get(unit, ("not in the sample", ""))[0]
        shown = ", ".join(f"{k} {v}" for k, v in a["lines"].items()) or "none"
        out.append(
            f"| `{unit}` | {klass_before} | **{a['class']}** | {a['recordings']} | "
            f"{a['verifications']} | {shown} | {_cell(a['why'][:160])} | ${a['spend']:.4f} |"
        )
    out.append("")
    return "\n".join(out) + "\n"


def splice(report: Path, heading_prefix: str, text: str) -> None:
    body = report.read_text(encoding="utf-8")
    if heading_prefix in body:
        head, _sep, rest = body.partition(heading_prefix)
        _old, sep2, tail = rest.partition("\n## 2. ")
        body = head + text + sep2 + tail
    else:
        head, sep, tail = body.partition("## 2. ")
        body = head + text + sep + tail
    report.write_text(body, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--trials", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--report", required=True)
    args = parser.parse_args(argv)
    before = original_classes()
    after = rerun_classes(Path(args.artifact), args.trials)
    text = section(args.title, args.run_id, before, after)
    splice(Path(args.report), f"## 1b. {args.title}", text)
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
