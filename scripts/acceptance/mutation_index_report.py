"""The forty under D-245, case by case against the D-240 run (0.3.0 step 4).

Reads the downloaded artifact of a `mutation-recall.yml` dispatch -- its trials
file, lines file, ledgers and run log -- and, for every case, the class the
D-240 run gave (`trials-search-v3b.jsonl` and its committed ledgers) beside the
class it has now. For every case newly certified it reads, from the ledgers and
from the case's own rebuilt tree, whether the certifying probe used a literal
the D-245 hint offered, the boundary D-240 named, or a call site the tree index
resolved; for every case that lost a receipt it lays the two runs' context and
discovery figures side by side so jitter can be told from a squeezed context.
The boundary stratum is its own column and its own table. Free: JSON on disk
and `ast` over the case trees, no model.

    python scripts/acceptance/mutation_index_report.py \\
        --artifact <downloaded artifact dir> --run-id 34736200356 \\
        --trials trials-with-index.jsonl --baseline search-v3b \\
        --out docs/acceptance/2026-09-14-forty-with-index.md \\
        --facts docs/acceptance/evidence/2026-09-14-forty-with-index/facts.json
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "corpus"))
sys.path.insert(0, str(ROOT / "src"))

from heldout_v2 import wilson  # noqa: E402
from mutation_recall import REPOSITORIES, WORK, classify  # noqa: E402

from attest.review.boundary import changed_conditions  # noqa: E402
from attest.review.executor import (  # noqa: E402
    _changed_definitions,
    _changed_lines,
    _literal_arguments,
)
from attest.review.index import EXACT, tree_index  # noqa: E402
from attest.review.planner import show_file_at  # noqa: E402

RUNS = "https://github.com/IcantFind-a-username/Attest/actions/runs"
STUDY = ROOT / "benchmarks" / "studies" / "mutations-v1-recall"
EVIDENCE_BEFORE = ROOT / "docs" / "acceptance" / "evidence" / "2026-09-13-mutation-recall"
BEFORE_RUNS = ("34711985142", "34712819526")
MAX_CALLERS_SHOWN = 6


def _read_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def _cell(text: object) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ").replace("\r", " ")


def _code(text: object) -> str:
    text = str(text).replace("|", "\\|").replace("\n", " ").replace("`", "'")
    return f"`{text}`" if text else ""


def _codes(values: list[str], empty: str) -> str:
    return ", ".join(_code(x) for x in values) or empty


def _row(*cells: object) -> str:
    return "| " + " | ".join(str(c) for c in cells) + " |"


def _rule(count: int) -> str:
    return "|" + "---|" * count


# --------------------------------------------------------------------------- facts


def case_facts(rows: list[dict], trial: dict, lines_entry: dict) -> dict:
    """Everything one case's ledger rows say that the comparison reads."""
    klass, why = classify(rows, str(trial.get("deferred_reason") or ""))
    probes = [
        {
            "finding_id": r.get("finding_id"),
            "attempt": r.get("attempt_index"),
            "expression": r.get("expression") or "",
            "setup": r.get("setup") or "",
            "imports": r.get("imports") or "",
            "base_kind": r.get("observed_kind") or "",
            "base_detail": r.get("observed_detail") or "",
            "head_kind": r.get("head_kind") or "",
            "head_detail": r.get("head_detail") or "",
            "feedback_kind": r.get("feedback_kind") or "",
        }
        for r in rows
        if r.get("kind") == "probe_observation"
    ]
    for probe in probes:
        probe["differs"] = bool(probe["head_kind"]) and (
            (probe["head_kind"], probe["head_detail"])
            != (probe["base_kind"], probe["base_detail"])
        )
    plan: dict = {"callers": 0, "context_chars": 0, "diff_chars": 0, "omissions": [],
                  "context": {}}
    for r in rows:
        if r.get("kind") != "review_plan":
            continue
        for unit in r.get("units") or []:
            context = unit.get("context") or {}
            plan["callers"] += int(context.get("caller") or 0)
            plan["context_chars"] += int(unit.get("context_chars") or 0)
            plan["diff_chars"] += int(unit.get("diff_chars") or 0)
            plan["omissions"].extend(str(o) for o in unit.get("omissions") or [])
            for kind, count in context.items():
                plan["context"][kind] = plan["context"].get(kind, 0) + int(count or 0)
    coverage = next((r for r in rows if r.get("kind") == "proposal_coverage"), {})
    run = next((r for r in rows if r.get("kind") == "review_run"), {})
    samples = run.get("provider_samples") or []
    discovery = {
        "samples": len(samples),
        "input_tokens": sum(
            int(s.get("input_tokens") or 0)
            + int(s.get("cache_creation_input_tokens") or 0)
            + int(s.get("cache_read_input_tokens") or 0)
            for s in samples
        ),
        "output_tokens": sum(int(s.get("output_tokens") or 0) for s in samples),
        "truncated": sum(1 for s in samples if s.get("stop_reason") == "max_tokens"),
    }
    findings = {
        str(r.get("finding_id")): (str(r.get("file") or ""), int(r.get("line") or 0))
        for r in rows
        if r.get("kind") == "history_signal"
    }
    certified = [
        r for r in rows if r.get("kind") == "certification" and r.get("outcome") == "accepted"
    ]
    certified_finding = str(certified[0].get("finding_id")) if certified else ""
    certifying = None
    if certified_finding:
        mine = [p for p in probes if p["finding_id"] == certified_finding]
        differing = [p for p in mine if p["differs"]]
        certifying = (differing or mine or [None])[-1]
    return {
        "class": klass,
        "why": why,
        "spend": float(trial.get("spend_usd") or 0.0),
        "elapsed_s": float(trial.get("elapsed_s") or 0.0),
        "candidates": trial.get("candidates"),
        "eligible": trial.get("eligible"),
        "attempted": trial.get("attempted"),
        "lines": {k: len(v) for k, v in (lines_entry.get("lines") or {}).items() if v},
        "recordings": len(probes),
        "verifications": sum(1 for r in rows if r.get("kind") == "verification"),
        "probes": probes,
        "hit": any(p["differs"] for p in probes),
        "plan": plan,
        "coverage": {
            "units_read": coverage.get("units_read"),
            "units_planned": coverage.get("units_planned"),
            "budget_limited": bool(coverage.get("budget_limited")),
        },
        "discovery": discovery,
        "breakdown": run.get("spend_breakdown") or {},
        "findings": findings,
        "certified_finding": certified_finding,
        "certifying_probe": certifying,
    }


def run_facts(
    trials_path: Path, lines_path: Path, ledger_of: dict[str, list[dict]]
) -> dict[str, dict]:
    sample = {r["unit_id"]: r for r in _read_jsonl(STUDY / "sample.jsonl")}
    trials = _read_jsonl(trials_path)
    assert trials, f"no trial in {trials_path}: the input is empty"
    lines = {r["unit_id"]: r for r in _read_jsonl(lines_path)}
    out: dict[str, dict] = {}
    for trial in trials:
        unit = str(trial["unit_id"])
        library = str(sample[unit]["library"])
        mine = [e for e in ledger_of.get(library, []) if e.get("task_id") == trial["task_id"]]
        out[unit] = case_facts(mine, trial, lines.get(unit, {}))
        out[unit]["task_id"] = trial["task_id"]
    return out


def before_facts(baseline: str) -> dict[str, dict]:
    ledgers = {
        library: _read_jsonl(EVIDENCE_BEFORE / baseline / f"{library}-ledger.jsonl")
        for library in REPOSITORIES
    }
    assert any(ledgers.values()), f"no ledger under {EVIDENCE_BEFORE / baseline}: input is empty"
    return run_facts(
        STUDY / f"trials-{baseline}.jsonl", STUDY / f"lines-trials-{baseline}.jsonl", ledgers
    )


def after_facts(artifact: Path, trials_name: str) -> dict[str, dict]:
    study_dir = artifact / "benchmarks" / "studies" / "mutations-v1-recall"
    clones = artifact / ".attest" / "corpora" / "mutations-v1-recall"
    ledgers = {
        library: _read_jsonl(clones / library / "repo" / ".attest" / "ledger.jsonl")
        for library in REPOSITORIES
    }
    assert any(ledgers.values()), "no ledger in the artifact: the input is empty"
    return run_facts(
        study_dir / trials_name, study_dir / f"lines-{Path(trials_name).stem}.jsonl", ledgers
    )


def driver_log(artifact: Path) -> dict:
    """What the driver printed: the reservation, the cases it skipped, the cap summary."""
    out: dict = {"reservation": {}, "skipped": [], "unbought": [], "summary": ""}
    path = artifact / "recall-run.log"
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line.startswith("{"):
            if "cap" in line and "$" in line:
                out["summary"] = line
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if "reservation_usd" in row:
            out["reservation"] = row
        elif row.get("skipped"):
            out["skipped"].append(row)
        elif "unbought_units" in row:
            out["unbought"] = list(row["unbought_units"])
    return out


# --------------------------------------------------------------------------- the census


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    ).stdout.strip()


def census(unit_id: str, findings: dict[str, tuple[str, int]]) -> dict[str, dict]:
    """What the D-245 hint offered each finding of a case, recomputed on the case's
    own rebuilt tree with the executor's own helpers: the changed definitions,
    the literals the index found for them, the conditions D-240 named, and the
    call sites the index resolved."""
    manifest_path = WORK / "cases" / unit_id / "manifest.json"
    if not manifest_path.is_file():
        return {}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    repo = Path(manifest["repo_path"])
    _git(repo, "checkout", "-q", "--", ".")
    _git(repo, "checkout", "-q", "--detach", manifest["head_sha"])
    index = tree_index(repo)
    out: dict[str, dict] = {}
    for finding_id, (file, line) in findings.items():
        try:
            source = (repo / file).read_text(encoding="utf-8", errors="replace")
        except OSError:
            out[finding_id] = {"file": file, "line": line, "symbols": []}
            continue
        symbols = [n.rsplit(":", 1)[0] for n in _changed_definitions(source, [line])]
        entry: dict = {"file": file, "line": line, "symbols": symbols, "literals": [],
                       "conditions": [], "callers": [], "callers_exact": 0,
                       "callers_attribute": 0}
        if symbols:
            base_source = show_file_at(repo, manifest["base_sha"], file)
            if base_source is not None:
                changed = _changed_lines(repo, manifest["base_sha"], manifest["head_sha"], file)
                entry["conditions"] = list(changed_conditions(base_source, source, changed))
            entry["literals"] = _literal_arguments(repo, file, symbols)
            module = index.module_of(file)
            sites = []
            if module:
                sites = [s for name in symbols for s in index.callers_of(module, name)]
            entry["callers_exact"] = sum(1 for s in sites if s.resolution == EXACT)
            entry["callers_attribute"] = sum(1 for s in sites if s.resolution != EXACT)
            entry["callers"] = [
                {"path": s.path, "line": s.line, "resolution": s.resolution,
                 "literals": list(s.literals)}
                for s in sites[:MAX_CALLERS_SHOWN]
            ]
        out[finding_id] = entry
    return out


_NUMBER = re.compile(r"-?\d+(?:\.\d+)?")


def _variants(literal: str) -> list[str]:
    """The forms a probe may write the literal in: as rendered, with the other
    quote, and a keyword literal's bare value."""
    forms = [literal]
    if "=" in literal and not literal.startswith(("'", '"')):
        forms.append(literal.split("=", 1)[1])
    more = []
    for form in forms:
        if form.startswith("'") and form.endswith("'"):
            more.append('"' + form[1:-1] + '"')
        elif form.startswith('"') and form.endswith('"'):
            more.append("'" + form[1:-1] + "'")
    return forms + more


def _present(text: str, literal: str) -> bool:
    for form in _variants(literal):
        if not form:
            continue
        if _NUMBER.fullmatch(form):
            if re.search(rf"(?<![\w.]){re.escape(form)}(?![\w.])", text):
                return True
        elif form in text:
            return True
    return False


def hint_use(probe: dict | None, entry: dict | None) -> dict:
    """Which of the hint's literals and which of the named boundary's values the
    probe's text carries. A fact about the text; the reading is the report's."""
    if probe is None or not entry:
        return {"literals_used": [], "boundary_used": [], "text": ""}
    text = "\n".join((probe["imports"], probe["setup"], probe["expression"]))
    literals_used = [lit for lit in entry.get("literals", []) if _present(text, lit)]
    values = []
    for sentence in entry.get("conditions", []):
        values.extend(_NUMBER.findall(sentence))
    boundary_used = sorted({v for v in values if _present(text, v)})
    return {"literals_used": literals_used, "boundary_used": boundary_used, "text": text}


# --------------------------------------------------------------------------- the report


def _arrow(before: object, after: object) -> str:
    return f"{before} → **{after}**" if before != after else f"{before} → {after}"


def _lines_cell(lines: dict) -> str:
    return ", ".join(f"{k} {v}" for k, v in lines.items()) or "none"


def _probe_text(probe: dict | None, limit: int) -> str:
    if probe is None:
        return "no probe recorded"
    return f"{probe['setup']} ⏎ {probe['expression']}"[:limit]


def _read(facts: dict[str, dict], units: list[str], units_of: str) -> str:
    coverage = facts.get(units_of, {}).get("coverage", {})
    limited = " (budget-limited)" if coverage.get("budget_limited") else ""
    return f"{coverage.get('units_read')} of {coverage.get('units_planned')}{limited}"


def _hits(facts: dict[str, dict], units: list[str]) -> int:
    return sum(1 for u in units if facts.get(u, {}).get("hit"))


def _recorded(facts: dict[str, dict], units: list[str]) -> int:
    return sum(1 for u in units if facts.get(u, {}).get("recordings", 0) > 0)


def build(
    run_id: str, before: dict[str, dict], after: dict[str, dict], log: dict, trials_name: str,
    baseline: str, code: str,
) -> tuple[str, dict]:
    sample = _read_jsonl(STUDY / "sample.jsonl")
    order = [str(r["unit_id"]) for r in sample]
    stratum = {str(r["unit_id"]): str(r["stratum"]) for r in sample}
    n = len(sample)
    boundary = [u for u in order if stratum[u] == "boundary"]
    strata = Counter(stratum.values())

    def klass(facts: dict[str, dict], unit: str) -> str:
        return facts[unit]["class"] if unit in facts else "not run"

    def count(facts: dict[str, dict], units: list[str], name: str) -> int:
        return sum(1 for u in units if klass(facts, u) == name)

    def drawers(facts: dict[str, dict], units: list[str]) -> int:
        return sum(1 for u in units if klass(facts, u).startswith("drawer"))

    def spent(facts: dict[str, dict], units: list[str]) -> float:
        return sum(facts[u]["spend"] for u in units if u in facts)

    cert_b, cert_a = count(before, order, "certified"), count(after, order, "certified")
    bcert_b, bcert_a = count(before, boundary, "certified"), count(after, boundary, "certified")
    low_b, high_b = wilson(cert_b, n)
    low_a, high_a = wilson(cert_a, n)
    gained = [
        u for u in order if klass(after, u) == "certified" and klass(before, u) != "certified"
    ]
    lost = [
        u for u in order if klass(after, u) != "certified" and klass(before, u) == "certified"
    ]
    spend_a, spend_b = spent(after, order), spent(before, order)
    reservation = log.get("reservation") or {}
    reserved = float(reservation.get("reservation_usd") or 0)
    history = reservation.get("history_cases", "?")
    refused = [s["unit_id"] for s in log.get("skipped", []) if s.get("skipped") == "cap"]
    not_run = [s["unit_id"] for s in log.get("skipped", []) if s.get("skipped") != "cap"]

    # the census over every case that ran, on the rebuilt trees
    census_of: dict[str, dict] = {}
    for unit in order:
        if unit in after:
            census_of[unit] = census(unit, after[unit]["findings"])

    def probe_use(unit: str) -> tuple[dict, dict | None]:
        facts = after[unit]
        probe = facts["certifying_probe"]
        if probe is None:
            # the last probe that made the revisions differ, else the last probe
            differing = [p for p in facts["probes"] if p["differs"]]
            probe = (differing or facts["probes"] or [None])[-1]
        entry = census_of.get(unit, {}).get(str(probe["finding_id"])) if probe else None
        return hint_use(probe, entry), probe

    def named(units: list[str]) -> str:
        return f" ({', '.join(f'`{u}`' for u in units)})" if units else ""

    out: list[str] = []
    out.append(
        "# The forty under D-245, 2026-09-14 — the tree index, case by case against the 12 of 40"
    )
    out.append("")
    out.append(
        f"**0.3.0 step 4, the owner instruction of 2026-09-14.** Run [`{run_id}`]"
        f"({RUNS}/{run_id}), `mutation-recall.yml` over all {n} cases into `{trials_name}`, "
        f"{code}, $1.00 per case, K=5, `linux-container-v1`, both yellow switches on, the local "
        "review path -- no GitHub client, nothing written anywhere. **The same forty as every "
        "run before it: the code changed and the corpus did not.** The reservation that admitted "
        f"each case was the D-244 p95: **${reserved:.4f}** from {history} trials of history, "
        f"under the $1.00 ceiling and the $5.00 cap; **{len(refused)} case(s) refused by the "
        f"cap**{named(refused)}, {len(not_run)} not run for another reason{named(not_run)}. "
        f"**${spend_a:.4f} in all.** Compared case by case with the D-240 run "
        f"(`trials-{baseline}.jsonl`, runs [`{BEFORE_RUNS[0]}`]({RUNS}/{BEFORE_RUNS[0]}) and "
        f"[`{BEFORE_RUNS[1]}`]({RUNS}/{BEFORE_RUNS[1]}), ${spend_b:.4f}, §1e of the "
        "[2026-09-13 report](2026-09-13-mutation-recall.md)). The denominator is forty whatever "
        "the cap or the runner did; a case not run keeps its latest class."
    )
    out.append("")
    out.append("## 1. The number, and the boundary thirteen in their own column")
    out.append("")
    out.append(
        "AGENTS.md §9: one re-run of a forty-case corpus moves about ±2 cases on its own, so the "
        "net count is reported beside the gained and lost lists and a change is attributed only "
        "case by case (§3, §4)."
    )
    out.append("")
    out.append(_row("", "D-240 run (before)", "D-245 run (after)", "boundary, of 13 (before)",
                    "boundary, of 13 (after)"))
    out.append(_rule(5))
    out.append(_row("certified", f"**{cert_b}**", f"**{cert_a}**", f"**{bcert_b}**",
                    f"**{bcert_a}**"))
    out.append(_row("point estimate", f"{cert_b / n:.1%}", f"**{cert_a / n:.1%}**",
                    f"{bcert_b / len(boundary):.1%}", f"**{bcert_a / len(boundary):.1%}**"))
    out.append(_row("Wilson 95%", f"[{low_b:.1%}, {high_b:.1%}]",
                    f"**[{low_a:.1%}, {high_a:.1%}]**", "—", "—"))
    for name in ("value class", "no receipt", "no reproduction attempted"):
        out.append(_row(name, count(before, order, name), count(after, order, name),
                        count(before, boundary, name), count(after, boundary, name)))
    out.append(_row("drawer (D-232 or a statement)", drawers(before, order), drawers(after, order),
                    drawers(before, boundary), drawers(after, boundary)))
    out.append(_row("record a probe on the merge base", _recorded(before, order),
                    _recorded(after, order), _recorded(before, boundary),
                    _recorded(after, boundary)))
    out.append(_row("a probe made the two revisions differ", _hits(before, order),
                    _hits(after, order), _hits(before, boundary), _hits(after, boundary)))
    out.append(_row("spend", f"${spend_b:.4f}", f"${spend_a:.4f}",
                    f"${spent(before, boundary):.4f}", f"${spent(after, boundary):.4f}"))
    out.append("")
    other_strata = ", ".join(
        f"`{name}` {count(before, [u for u in order if stratum[u] == name], 'certified')} → "
        f"{count(after, [u for u in order if stratum[u] == name], 'certified')} of {strata[name]}"
        for name in sorted(strata) if name != "boundary"
    )
    out.append(
        f"Cases newly certified: **{len(gained)}**{named(gained)}; cases that lost a receipt: "
        f"**{len(lost)}**{named(lost)}; net {cert_a - cert_b:+d}. Cases, never candidates: an "
        "extra receipt inside a case already certified counts for nothing here. The other two "
        f"strata: {other_strata}."
    )
    out.append("")

    out.append("## 2. Every case, against the 12 of 40")
    out.append("")
    out.append(
        "`boundary` marks the thirteen of that stratum. *before* is the case's class in the "
        "D-240 run; *after* its class now; *recordings* is how many probes recorded on the merge "
        "base; *why now* is the wording that decided the class."
    )
    out.append("")
    out.append(_row("case", "boundary", "before", "after", "recordings", "verifications",
                    "lines", "why now", "spend"))
    out.append(_rule(9))
    for unit in order:
        b = klass(before, unit)
        flag = "✓" if stratum[unit] == "boundary" else ""
        a = after.get(unit)
        if a is None:
            reason = next((s for s in log.get("skipped", []) if s.get("unit_id") == unit), {})
            out.append(_row(f"`{unit}`", flag, b, f"**not run: {reason.get('skipped', 'absent')}**",
                            "—", "—", "—", _cell(reason.get("detail", ""))[:120], "—"))
            continue
        mark = "**" if a["class"] != b else ""
        out.append(_row(f"`{unit}`", flag, b, f"{mark}{a['class']}{mark}", a["recordings"],
                        a["verifications"], _lines_cell(a["lines"]), _cell(a["why"][:160]),
                        f"${a['spend']:.4f}"))
    out.append("")

    out.append("## 3. The cases newly certified: what the probe used")
    out.append("")
    out.append(
        "For each case that certifies now and did not in the D-240 run, read from the run's "
        "ledger and from the case's own tree rebuilt locally at the same site: the literals the "
        "D-245 hint offered for the changed definitions (the executor's own `_literal_arguments` "
        "on the head tree), the boundary D-240 named, the probe whose recording certified, "
        "whether that probe's text carries one of the offered literals or one of the named "
        "values, the call sites the index resolved for the changed symbols (`exact` through an "
        "import binding, `attribute` on an untyped receiver whose file imports the module), and "
        "how many caller snippets the planner put in the discovery context before and after. A "
        "literal in the probe's text is a fact about the text, not proof of where the model got "
        "it; the reading is below the table."
    )
    out.append("")
    if not gained:
        out.append("No case was newly certified.")
    else:
        out.append(_row("case", "stratum", "literals the hint offered", "the boundary D-240 named",
                        "the certifying probe", "offered literal in the probe",
                        "named value in the probe", "index call sites (exact / attribute)",
                        "caller snippets in the plan (before → after)"))
        out.append(_rule(9))
        for unit in gained:
            use, probe = probe_use(unit)
            entry = census_of.get(unit, {}).get(str(probe["finding_id"])) if probe else None
            entry = entry or {}
            callers_before = before.get(unit, {}).get("plan", {}).get("callers", "—")
            out.append(_row(
                f"`{unit}`", stratum[unit], _codes(entry.get("literals", []), "none"),
                _cell(" ".join(entry.get("conditions", [])) or "none"),
                _code(_probe_text(probe, 220)), _codes(use["literals_used"], "no"),
                _codes(use["boundary_used"], "no"),
                f"{entry.get('callers_exact', 0)} / {entry.get('callers_attribute', 0)}",
                _arrow(callers_before, after[unit]["plan"]["callers"]),
            ))
        out.append("")
        for unit in gained:
            _use, probe = probe_use(unit)
            entry = census_of.get(unit, {}).get(str(probe["finding_id"])) if probe else None
            if not entry or not entry.get("callers"):
                continue
            sites = "; ".join(
                f"`{c['path']}:{c['line']}` ({c['resolution'].lower()}"
                + (f", literals {_codes(c['literals'], '')}" if c["literals"] else "")
                + ")"
                for c in entry["callers"]
            )
            out.append(
                f"- `{unit}`: the index's call sites for {_codes(entry['symbols'], '')} -- {sites}."
            )
        out.append("")
    out.append("<!-- reading: gained -->")
    out.append("")

    out.append("## 4. The cases that lost a receipt: jitter, or a squeezed context")
    out.append("")
    out.append(
        "For each case certified in the D-240 run and not now, the two runs' figures side by "
        "side: the discovery context the planner built (characters, caller snippets, what it "
        "omitted), whether discovery read every unit under the budget, how many candidates were "
        "proposed and eligible, how many probes recorded and whether any made the revisions "
        "differ, and the spend. A context that grew or an omission that appeared is the mark of "
        "a squeezed context; the same figures with a different outcome is the search's and "
        "discovery's own variance, the ±2 of AGENTS.md §9. The reading is below the table."
    )
    out.append("")
    if not lost:
        out.append("No case lost a receipt.")
    else:
        out.append(_row("case", "stratum", "before → after", "why now",
                        "context chars (before → after)", "caller snippets (before → after)",
                        "omissions (before → after)", "discovery read (before → after)",
                        "candidates / eligible (before → after)",
                        "probes recorded, differing (before → after)",
                        "discovery input tokens (before → after)", "spend (before → after)"))
        out.append(_rule(12))
        for unit in lost:
            b, a = before[unit], after[unit]
            out.append(_row(
                f"`{unit}`", stratum[unit], f"certified → **{a['class']}**",
                _cell(a["why"][:140]),
                _arrow(b["plan"]["context_chars"], a["plan"]["context_chars"]),
                _arrow(b["plan"]["callers"], a["plan"]["callers"]),
                f"{_cell('; '.join(b['plan']['omissions']) or 'none')} → "
                f"{_cell('; '.join(a['plan']['omissions']) or 'none')}",
                f"{_read(before, order, unit)} → {_read(after, order, unit)}",
                f"{b['candidates']} / {b['eligible']} → {a['candidates']} / {a['eligible']}",
                f"{b['recordings']}, {sum(1 for p in b['probes'] if p['differs'])} → "
                f"{a['recordings']}, {sum(1 for p in a['probes'] if p['differs'])}",
                f"{b['discovery']['input_tokens']} → {a['discovery']['input_tokens']}",
                f"${b['spend']:.4f} → ${a['spend']:.4f}",
            ))
        out.append("")
        for unit in lost:
            b, a = before[unit], after[unit]
            now = "; ".join(
                _code(_probe_text(p, 160)) + f" (base {p['base_kind']}, head "
                + (p["head_kind"] or "not run") + ")"
                for p in a["probes"]
            ) or "none recorded"
            out.append(
                f"- `{unit}`: the probe that certified before -- "
                f"{_code(_probe_text(b['certifying_probe'], 200))}; the probes now -- {now}."
            )
        out.append("")
    out.append("<!-- reading: lost -->")
    out.append("")

    out.append("## 5. The boundary thirteen")
    out.append("")
    out.append(
        "The stratum D-245 was expected to move most: a `>=`/`>` swap changes behaviour on one "
        "input, and the literals hint names the inputs the tree already passes. *boundary hit* "
        "is §1f's reading -- a probe whose head observation differs from its base observation "
        "found the input; *offered literal in a probe* and *named value in a probe* are read "
        "over every probe the case recorded, not only the certifying one."
    )
    out.append("")
    out.append(_row("case", "before", "after", "boundary hit (before → after)",
                    "literals the hint offered", "offered literal in a probe",
                    "named value in a probe", "why now"))
    out.append(_rule(8))
    summary: Counter = Counter()
    for unit in boundary:
        b = klass(before, unit)
        a = after.get(unit)
        if a is None:
            out.append(_row(f"`{unit}`", b, "**not run**", "—", "—", "—", "—", "—"))
            continue
        entries = census_of.get(unit, {})
        offered: list[str] = []
        used_lits: list[str] = []
        used_vals: list[str] = []
        for probe in a["probes"]:
            entry = entries.get(str(probe["finding_id"]))
            if not entry:
                continue
            offered.extend(x for x in entry.get("literals", []) if x not in offered)
            use = hint_use(probe, entry)
            used_lits.extend(x for x in use["literals_used"] if x not in used_lits)
            used_vals.extend(x for x in use["boundary_used"] if x not in used_vals)
        if not a["probes"]:
            for entry in entries.values():
                offered.extend(x for x in entry.get("literals", []) if x not in offered)
        summary["offered"] += bool(offered)
        summary["literal used"] += bool(used_lits)
        summary["value used"] += bool(used_vals)
        summary["hit"] += bool(a["hit"])
        mark = "**" if a["class"] != b else ""
        hit_before = "yes" if before.get(unit, {}).get("hit") else "no"
        out.append(_row(
            f"`{unit}`", b, f"{mark}{a['class']}{mark}",
            f"{hit_before} → {'yes' if a['hit'] else 'no'}", _codes(offered, "none"),
            _codes(used_lits, "no"), _codes(used_vals, "no"), _cell(a["why"][:140]),
        ))
    out.append("")
    out.append(_row("", "cases"))
    out.append(_rule(2))
    out.append(_row("the hint offered at least one literal", f"{summary['offered']} of 13"))
    out.append(_row("a probe carried an offered literal", f"{summary['literal used']} of 13"))
    out.append(_row("a probe carried a value the moved condition named",
                    f"{summary['value used']} of 13"))
    out.append(_row("a probe made the two revisions differ",
                    f"{summary['hit']} of 13 ({_hits(before, boundary)} before)"))
    out.append(_row("certified", f"{bcert_a} of 13 ({bcert_b} before)"))
    out.append("")
    out.append("<!-- reading: boundary -->")
    out.append("")

    out.append("## 6. Spend, and the reservation that admitted each case")
    out.append("")
    spends = sorted(f["spend"] for f in after.values())
    out.append(_row("", ""))
    out.append(_rule(2))
    out.append(_row("cases run", f"{len(after)} of {n}"))
    out.append(_row(f"reservation per case (D-244 p95 of the most recent {history} trials)",
                    f"${reserved:.4f} (ceiling ${float(reservation.get('ceiling_usd') or 1):.2f})"))
    out.append(_row("refused by the $5.00 cap", len(refused)))
    out.append(_row("spend, all cases", f"${spend_a:.4f} (D-240 run: ${spend_b:.4f})"))
    if spends:
        largest = max(after, key=lambda u: after[u]["spend"])
        out.append(_row("per case: mean, median, largest",
                        f"${spend_a / len(spends):.4f}, ${spends[len(spends) // 2]:.4f}, "
                        f"${spends[-1]:.4f} (`{largest}`)"))
        out.append(_row("cases above the reservation", sum(1 for s in spends if s > reserved)))
    stage_cost: Counter = Counter()
    for f in after.values():
        for stage, entry in (f.get("breakdown") or {}).items():
            stage_cost[stage] += float(entry.get("cost_usd") or 0.0)
    if stage_cost:
        out.append(_row("by stage (D-243)", ", ".join(
            f"{stage} ${cost:.4f}" for stage, cost in sorted(stage_cost.items()))))
    if log.get("summary"):
        out.append(_row("the driver's cap summary", _cell(log["summary"])))
    out.append("")

    out.append("## 7. What is and is not claimed")
    out.append("")
    out.append("<!-- reading: claims -->")
    out.append("")

    facts = {
        "run_id": run_id,
        "trials": trials_name,
        "baseline": baseline,
        "reservation": reservation,
        "refused": refused,
        "not_run": not_run,
        "certified_before": cert_b,
        "certified_after": cert_a,
        "boundary_certified_before": bcert_b,
        "boundary_certified_after": bcert_a,
        "gained": gained,
        "lost": lost,
        "spend_before": round(spend_b, 6),
        "spend_after": round(spend_a, 6),
        "cases": {
            unit: {
                "stratum": stratum[unit],
                "before": {k: v for k, v in before.get(unit, {}).items() if k != "breakdown"},
                "after": dict(after.get(unit, {})),
                "census": census_of.get(unit, {}),
                "hint_use": probe_use(unit)[0] if unit in after else {},
            }
            for unit in order
        },
    }
    return "\n".join(out).rstrip("\n") + "\n", facts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--artifact", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--trials", default="trials-with-index.jsonl")
    parser.add_argument("--baseline", default="search-v3b",
                        help="the evidence directory and trials suffix of the run compared against")
    parser.add_argument("--code", default="the code of `main` at `a16312a` (D-245: the tree index, "
                        "the package block by import distance, the literals hint)")
    parser.add_argument("--out", required=True)
    parser.add_argument("--facts", default="")
    args = parser.parse_args(argv)
    artifact = Path(args.artifact)
    before = before_facts(args.baseline)
    after = after_facts(artifact, args.trials)
    text, facts = build(
        args.run_id, before, after, driver_log(artifact), args.trials, args.baseline, args.code
    )
    Path(args.out).write_text(text, encoding="utf-8")
    if args.facts:
        Path(args.facts).parent.mkdir(parents=True, exist_ok=True)
        Path(args.facts).write_text(json.dumps(facts, indent=1, ensure_ascii=False) + "\n",
                                    encoding="utf-8")
    print(json.dumps({k: v for k, v in facts.items() if k != "cases"}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
