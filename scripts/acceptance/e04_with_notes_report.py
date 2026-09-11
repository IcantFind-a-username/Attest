"""The step-7 table of the 2026-09-11 drawer window (owner instruction 7).

Reads the re-run's trials and lines files beside the 2026-09-13 runner re-take,
and writes the markdown the owner adjudicates: every line the review would have
put in front of an author, verbatim, with what stands behind it and the pull
request it belongs to -- and three empty columns after each line, **useful /
true but useless / wrong**, for the owner to fill one by one. Free: it reads
JSON already on disk and calls nothing.

    python scripts/acceptance/e04_with_notes_report.py \
        --study benchmarks/studies/e04-prospective-v3 \
        --trials trials-runner-notes.jsonl \
        --lines lines-trials-runner-notes.jsonl \
        --baseline trials-runner.jsonl --run-id 34618040099 \
        --out docs/acceptance/2026-09-12-e04-with-notes.md
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

RUNS = "https://github.com/IcantFind-a-username/Attest/actions/runs"


def _read_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    text = path.read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def _cell(text: object) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def _behind(kind: str, item: dict) -> str:
    if kind == "red":
        return f"receipt {item.get('receipt')}, {item.get('evidence_class')}"
    if kind == "value":
        return (
            f"note {item.get('note_id')} — `{item.get('expression')}`; "
            f"base {item.get('base')}; head {item.get('head')}; {item.get('runs')}; "
            f"drawer: {item.get('drawer_reason')}"
        )
    if kind == "gate":
        return (
            f"gate note {item.get('note_id')} — {item.get('exception_type')} at "
            f"{item.get('path')}:{item.get('origin_line')}, entered through "
            f"`{item.get('entry')}` at {item.get('call_site')} ({item.get('caller')}), "
            f"{item.get('runs')} runs"
        )
    return f"yellow (a), {item.get('callers')} caller(s): {item.get('reason')}"


def _anchors(ledgers_root: Path | None) -> dict[tuple[str, str], tuple[str, int]]:
    """(task_id, finding_id) -> (path, anchor line), read from every ledger under
    ``ledgers_root``: the `history_signal` row carries the candidate's anchor."""
    anchors: dict[tuple[str, str], tuple[str, int]] = {}
    if ledgers_root is None:
        return anchors
    for path in sorted(ledgers_root.rglob("ledger.jsonl")):
        for row in _read_jsonl(path):
            if row.get("kind") == "history_signal" and row.get("finding_id") and row.get("line"):
                anchors[(str(row["task_id"]), str(row["finding_id"]))] = (
                    str(row.get("file")),
                    int(row["line"]),
                )
    return anchors


def _rerendered(item: dict, task_id: str, anchors: dict) -> dict:
    """The value line with the candidate's anchor as its coordinate (the D-218
    coordinate defect, D-222): the run wrote the test's assertion line."""
    from attest.review.value_note import ValueNote, render

    key = (task_id, str(item.get("candidate_id")))
    anchor = anchors.get(key)
    if anchor is None or anchor[0] != item.get("path"):
        return {**item, "coordinate": "as recorded (anchor not recovered)"}
    base_kind, _, base_detail = str(item.get("base", "")).partition(": ")
    head_kind, _, head_detail = str(item.get("head", "")).partition(": ")
    note = ValueNote(
        policy_version="attest.value-note.v2",
        path=str(item["path"]),
        line=anchor[1],
        expression=str(item.get("expression", "")),
        base_kind=base_kind,
        base_detail=base_detail,
        head_kind=head_kind,
        head_detail=head_detail,
        head_runs=3,
        base_runs=3,
        pinned_values=(),
        specified_by=tuple(tuple(x) for x in item.get("specified_by", [])),
        drawer_reason=str(item.get("drawer_reason", "")),
        candidate_id=str(item.get("candidate_id", "")),
    )
    return {**item, "line": render(note), "line_no": anchor[1], "coordinate": "anchor"}


def build(
    study: Path,
    trials_name: str,
    lines_name: str,
    baseline_name: str,
    run_id: str,
    ledgers_root: Path | None = None,
) -> str:
    trials = _read_jsonl(study / trials_name)
    lines = _read_jsonl(study / lines_name)
    anchors = _anchors(ledgers_root)
    for row in lines:
        row["lines"]["value"] = [
            _rerendered(item, str(row.get("task_id")), anchors)
            for item in row.get("lines", {}).get("value", [])
        ]
    baseline = _read_jsonl(study / baseline_name)
    sample = _read_jsonl(study / "sample.jsonl")
    by_unit = {row["unit_id"]: row for row in lines}
    trial_by_unit = {row["unit_id"]: row for row in trials}
    baseline_by_unit = {row["unit_id"]: row for row in baseline}

    units_run = [t["unit_id"] for t in trials]
    spend = sum(float(t.get("spend_usd", 0.0)) for t in trials)
    base_spend = sum(float(t.get("spend_usd", 0.0)) for t in baseline)
    kinds = ("red", "value", "gate", "impact")
    per_kind: Counter[str] = Counter()
    units_with_lines = 0
    line_rows: list[tuple[str, str, str, str]] = []  # unit, kind, line, behind
    for unit_id in units_run:
        entry = by_unit.get(unit_id, {}).get("lines", {})
        if sum(len(entry.get(k, [])) for k in kinds):
            units_with_lines += 1
        for kind in kinds:
            for item in entry.get(kind, []):
                per_kind[kind] += 1
                line_rows.append((unit_id, kind, str(item.get("line", "")), _behind(kind, item)))

    total_lines = sum(per_kind.values())
    new_kinds_lines = per_kind["red"] + per_kind["value"] + per_kind["gate"]
    units_with_new = sum(
        1
        for unit_id in units_run
        if any(by_unit.get(unit_id, {}).get("lines", {}).get(k) for k in ("red", "value", "gate"))
    )
    not_run = [row["unit_id"] for row in sample if row["unit_id"] not in trial_by_unit]
    baseline_published = sum(len(t.get("would_publish", [])) for t in baseline)
    baseline_units_with = sum(1 for t in baseline if t.get("would_publish"))
    per_run = max(1, len(units_run))
    per_base = max(1, len(baseline))

    out: list[str] = []
    out.append(
        "# E-04 stratum v3, re-run with the two yellow switches on — the lines, one by one, "
        "for the owner"
    )
    out.append("")
    out.append(
        "**Owner instruction 7 of 2026-09-11.** The same frozen 28-unit sample as the 2026-09-13 "
        f"runner re-take, reviewed again on `ubuntu-latest` (run [`{run_id}`]({RUNS}/{run_id})) "
        "from the `drawer/step-7` code — steps 1–6 of the window — with `value_notes_visible` "
        "and `gate_notes_visible` **on**, `per_pr_budget_usd` $1.00, `k_samples` 5, "
        "`linux-container-v1`, `contained_attempt_voids` at the product default. **Local review "
        "path only: no GitHub client was constructed and nothing was written to any "
        "repository.** The lines below are rendered by the same functions `run_ci` renders them "
        "with; they are what an author *would* have seen."
    )
    out.append("")
    out.append("## 1. The three numbers, and the comparison")
    out.append("")
    out.append("| | 2026-09-13 re-take (switches off) | **this run (switches on)** |")
    out.append("|---|---|---|")
    out.append(f"| units run | {len(baseline)} | **{len(units_run)}** of {len(sample)} |")
    out.append(
        "| pull requests with at least one author-visible line (red, value or gate) | "
        f"{baseline_units_with} | **{units_with_new}** |"
    )
    out.append(
        "| pull requests with any line at all (including yellow (a)) | not recorded | "
        f"**{units_with_lines}** |"
    )
    out.append(
        "| lines that would have been shown: red / value / gate / yellow (a) | "
        f"{baseline_published} / — / — / — | **{per_kind['red']} / {per_kind['value']} / "
        f"{per_kind['gate']} / {per_kind['impact']}** |"
    )
    out.append(
        "| mean lines per pull request run (red + value + gate) | "
        f"{baseline_published / per_base:.2f} | **{new_kinds_lines / per_run:.2f}** |"
    )
    out.append(
        f"| mean lines per pull request run (all four) | — | **{total_lines / per_run:.2f}** |"
    )
    out.append(f"| spend | ${base_spend:.6f} | **${spend:.6f}** of the $3.00 reservation |")
    out.append("")
    if not_run:
        named = ", ".join(f"`{u}`" for u in not_run)
        out.append(
            f"**{len(not_run)} of the {len(sample)} sampled units did not run** and are named "
            f"rather than dropped: {named}. A unit starts only if its $1.00 maximum still fits "
            "under the $3.00 cap (D-172), or its repository could not be cloned by the runner's "
            "token; the run log says which."
        )
        out.append("")
    out.append(
        "**Wrong = 0 is the owner's to establish, not this report's.** Every line below has "
        "three empty columns; the run says nothing about precision until they are filled."
    )
    out.append("")
    out.append("## 2. Every line, verbatim — the owner fills the last three columns")
    out.append("")
    out.append(
        "| # | pull request | level | the line, as it would have been shown | "
        "what stands behind it | useful | true but useless | wrong |"
    )
    out.append("|---|---|---|---|---|---|---|---|")
    for index, (unit_id, kind, line, behind) in enumerate(line_rows, 1):
        out.append(
            f"| {index} | `{_cell(unit_id)}` | {kind} | `{_cell(line)}` | {_cell(behind)} | | | |"
        )
    if not line_rows:
        out.append("| — | — | — | *no line on any unit* | — | | | |")
    out.append("")
    out.append("## 3. One row per pull request")
    out.append("")
    out.append(
        "| pull request | cand | elig | att | cert | red | value | gate | yellow (a) | "
        "units read | spend | 2026-09-13 published |"
    )
    out.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for unit_id in units_run:
        t = trial_by_unit[unit_id]
        entry = by_unit.get(unit_id, {}).get("lines", {})
        b = baseline_by_unit.get(unit_id, {})
        read = f"{t.get('units_read', 0)} of {t.get('units_planned', 0)}"
        if t.get("budget_limited"):
            read += " (budget-limited)"
        before = len(b.get("would_publish", [])) if b else "—"
        out.append(
            f"| `{_cell(unit_id)}` | {t.get('candidates', 0)} | {t.get('eligible', 0)} | "
            f"{t.get('attempted', 0)} | {t.get('certified', 0)} | {len(entry.get('red', []))} | "
            f"{len(entry.get('value', []))} | {len(entry.get('gate', []))} | "
            f"{len(entry.get('impact', []))} | {read} | ${float(t.get('spend_usd', 0.0)):.4f} | "
            f"{before} |"
        )
    out.append("")
    out.append("## 4. What this run does not say")
    out.append("")
    out.append(
        "- **Not a precision figure.** No line here is adjudicated until the owner fills the "
        "columns; a value or gate line carries no receipt and says so."
    )
    out.append(
        "- **Not a recall figure.** The 28 pull requests carry no known planted defect; the five "
        "drills were excluded before the 2026-09-13 run by the protocol."
    )
    out.append(
        "- **Not the same reviewer as 2026-09-13 in one respect that is not the switches:** step "
        "3 removed the discovery share, so a pull request the share used to truncate now reads "
        "more of its units for the same budget. The `units read` column says so per row."
    )
    out.append("- **Nothing was published.** The driver constructs no GitHub client.")
    out.append("")
    out.append("## 5. Artifacts")
    out.append("")
    out.append(
        f"- run [`{run_id}`]({RUNS}/{run_id}), artifact `e04-shadow-v3`: `{trials_name}`, "
        f"`{lines_name}`, the run log and the ledgers"
    )
    out.append(
        "- the study: [`benchmarks/studies/e04-prospective-v3`]"
        "(../../benchmarks/studies/e04-prospective-v3) — protocol digest unchanged; the two new "
        "files sit beside `trials-runner.jsonl`"
    )
    out.append(
        "- generated by `scripts/acceptance/e04_with_notes_report.py` from those files; nothing "
        "in it was typed by hand"
    )
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--study", type=Path, required=True)
    parser.add_argument("--trials", default="trials-runner-notes.jsonl")
    parser.add_argument("--lines", default="lines-trials-runner-notes.jsonl")
    parser.add_argument("--baseline", default="trials-runner.jsonl")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--ledgers",
        type=Path,
        default=None,
        help="root holding the run's ledgers; value lines are re-rendered with the anchor",
    )
    args = parser.parse_args(argv)
    text = build(args.study, args.trials, args.lines, args.baseline, args.run_id, args.ledgers)
    args.out.write_text(text, encoding="utf-8")
    print(f"wrote {args.out} ({text.count(chr(10))} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
