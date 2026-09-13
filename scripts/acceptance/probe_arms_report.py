"""The A/B/C probe arms (D-246 step 5): three dispatches of the forty, read side by side.

Each arm's artifact carries its trials file (`trials-arm-<arm>.jsonl`), its lines
file and the eight ledgers. For every arm the script counts certified cases and
the boundary thirteen's, sums spend and the probe stage's share (D-243's
`spend_breakdown`), takes the median per-case wall clock, names every case the
cap or the budget refused, and applies the pre-registered default rule from
`DEVSPEND.md` (window 2026-09-14): cost per certified case decides; a dearer arm
needs at least three more certified cases than the cheaper one, each gained case
named with its mechanism; an arm whose median wall clock is more than twice A's
is never the default; two cases or fewer is jitter (AGENTS.md section 9). It prints
the tables the report template holds and never decides anything on its own --
the gained cases' mechanisms are read by a person from the ledgers.

    python scripts/acceptance/probe_arms_report.py \\
        --arm A=<artifact dir> --arm B=<artifact dir> --arm C=<artifact dir>
"""

from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "corpus"))
sys.path.insert(0, str(ROOT / "scripts" / "acceptance"))
sys.path.insert(0, str(ROOT / "src"))

from heldout_v2 import wilson  # noqa: E402
from mutation_index_report import _read_jsonl, driver_log, run_facts  # noqa: E402
from mutation_recall import REPOSITORIES  # noqa: E402

STUDY = ROOT / "benchmarks" / "studies" / "mutations-v1-recall"
GAIN_FOR_A_DEARER_DEFAULT = 3
WALL_CLOCK_CEILING = 2.0  # times A's median
JITTER = 2  # AGENTS.md section 9


def arm_facts(arm: str, artifact: Path) -> dict:
    trials = artifact / f"trials-arm-{arm}.jsonl"
    lines = artifact / f"lines-trials-arm-{arm}.jsonl"
    ledgers = {lib: _read_jsonl(artifact / f"{lib}-ledger.jsonl") for lib in REPOSITORIES}
    assert any(ledgers.values()), f"arm {arm}: no ledger under {artifact}; the input is empty"
    facts = run_facts(trials, lines, ledgers)
    rows = _read_jsonl(trials)
    sample = _read_jsonl(STUDY / "sample.jsonl")
    boundary = {r["unit_id"] for r in sample if r["stratum"] == "boundary"}
    certified = sorted(u for u, f in facts.items() if f["class"] == "certified")
    probe_spend = sum(
        float((f["breakdown"].get("probe") or {}).get("cost_usd") or 0.0) for f in facts.values()
    )
    log = driver_log(artifact)
    refused = [s["unit_id"] for s in log.get("skipped", []) if s.get("skipped") == "cap"]
    parameters = next((r.get("probe_call") for r in rows if r.get("probe_call")), {})
    return {
        "arm": arm,
        "run": len(facts),
        "certified": certified,
        "boundary_certified": sorted(u for u in certified if u in boundary),
        "spend": sum(f["spend"] for f in facts.values()),
        "probe_spend": probe_spend,
        "median_wall_s": statistics.median([f["elapsed_s"] for f in facts.values()] or [0.0]),
        "refused": refused,
        "parameters": parameters,
        "facts": facts,
    }


def tables(arms: dict[str, dict]) -> str:
    n = len(_read_jsonl(STUDY / "sample.jsonl"))
    out = [
        "| arm | the probe's call | cases run | certified of 40 | Wilson 95% | boundary certified "
        "of 13 | spend | probe stage | cost per certified case | median wall clock per case | "
        "refused by the cap |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for arm, f in sorted(arms.items()):
        k = len(f["certified"])
        low, high = wilson(k, n)
        p = f["parameters"]
        call = (f"`{p.get('model', '?')}`, thinking {p.get('thinking', '?')}"
                + (f" at effort {p['effort']}" if p.get("effort") else "")
                + f", {p.get('max_output_tokens', '?')} output tokens")
        per = f"${f['spend'] / k:.4f}" if k else "undefined (0 certified)"
        out.append(
            f"| **{arm}** | {call} | {f['run']} | **{k}** | [{low:.1%}, {high:.1%}] | "
            f"{len(f['boundary_certified'])} | ${f['spend']:.4f} | ${f['probe_spend']:.4f} | "
            f"{per} | {f['median_wall_s']:.0f} s | {', '.join(f['refused']) or 'none'} |"
        )
    out.append("")
    out.append("| arm | certified cases |")
    out.append("|---|---|")
    for arm, f in sorted(arms.items()):
        out.append(f"| {arm} | {', '.join(f'`{u}`' for u in f['certified']) or 'none'} |")
    if "A" in arms:
        a = set(arms["A"]["certified"])
        out.append("")
        out.append("| arm | gained against A | lost against A | net |")
        out.append("|---|---|---|---|")
        for arm, f in sorted(arms.items()):
            if arm == "A":
                continue
            mine = set(f["certified"])
            gained, lost = sorted(mine - a), sorted(a - mine)
            out.append(f"| {arm} | {', '.join(f'`{u}`' for u in gained) or 'none'} | "
                       f"{', '.join(f'`{u}`' for u in lost) or 'none'} | {len(mine) - len(a):+d} |")
    return "\n".join(out)


def rule(arms: dict[str, dict]) -> str:
    """The pre-registered rule applied to the numbers; the mechanism reading is
    a person's and is asked for, not asserted."""
    lines = []
    a = arms.get("A")
    ranked = sorted(
        (f for f in arms.values() if f["certified"]),
        key=lambda f: f["spend"] / len(f["certified"]),
    )
    if not ranked:
        return "- no arm certified a case; the rule chooses nothing."
    best = ranked[0]
    lines.append(
        f"- **cost per certified case**: best is arm {best['arm']} at "
        f"${best['spend'] / len(best['certified']):.4f}."
    )
    for f in sorted(arms.values(), key=lambda f: f["arm"]):
        if a is not None and f["arm"] != "A":
            gain = len(set(f["certified"]) - set(a["certified"]))
            net = len(f["certified"]) - len(a["certified"])
            wall = f["median_wall_s"] / a["median_wall_s"] if a["median_wall_s"] else 0.0
            verdict = []
            if abs(net) <= JITTER:
                verdict.append(f"net {net:+d} is inside the ±{JITTER} jitter: decides nothing")
            if f["spend"] > a["spend"] and gain < GAIN_FOR_A_DEARER_DEFAULT:
                verdict.append(
                    f"dearer than A and gains {gain} < {GAIN_FOR_A_DEARER_DEFAULT}: not the default"
                )
            if wall > WALL_CLOCK_CEILING:
                verdict.append(
                    f"median wall clock {wall:.1f}× A's > {WALL_CLOCK_CEILING}×: not the default"
                )
            if not verdict:
                verdict.append(
                    f"gains {gain} against A at {wall:.1f}× its wall clock; eligible if each "
                    "gained case's mechanism is named from the ledgers (a person's reading)"
                )
            lines.append(f"- **arm {f['arm']} against A**: " + "; ".join(verdict) + ".")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--arm", action="append", default=[], metavar="ARM=DIR",
                        help="an arm and its downloaded artifact directory, e.g. B=./arm-b")
    args = parser.parse_args(argv)
    arms: dict[str, dict] = {}
    for spec in args.arm:
        arm, _, directory = spec.partition("=")
        assert arm in ("A", "B", "C") and directory, f"bad --arm {spec!r}"
        arms[arm] = arm_facts(arm, Path(directory))
    assert arms, "no arm given"
    print(tables(arms))
    print()
    print(rule(arms))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
