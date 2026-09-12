"""The 2026-09-12 table: every line on real pull requests, and where every
drawer observation went (work order PR 3 f).

Reads the artifacts of run A (`e04-shadow.yml`, the owner's own five pull
requests) and run B (`e05-external.yml`, 24 pull requests of eight public
libraries): the trials, the lines and -- this time -- the ledgers, and writes
the markdown the owner adjudicates. Free: JSON already on disk, no model call.

    python scripts/acceptance/lines_on_real_prs.py \\
        --run-a <dir> --run-a-id 34646556092 --run-a-trials trials-runner-only5.jsonl \\
        --run-b <dir> --run-b-id <id> --run-b-trials trials.jsonl \\
        --out docs/acceptance/2026-09-12-lines-on-real-prs.md

Each run directory is the downloaded artifact: `benchmarks/studies/<study>/`
holds the trials and lines files and `.attest/corpora/<name>/.attest/ledger.jsonl`
the ledgers. For run B a smoke trials file may sit beside the main one; it is
read for its ledger only and never counted.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from attest.certification.intent import (  # noqa: E402
    CONSTANT_CHANGE_LABEL,
    INTENT_STATED_LABEL,
    INTENT_UNKNOWN_LABEL,
    UNANCHORED_LABEL,
    VALUE_CHANGE_LABEL,
)
from attest.review.value_note import (  # noqa: E402
    NOTE_DRAWERS,
    ValueNote,
    admitted,
    anchored_in_tests,
)

RUNS = "https://github.com/IcantFind-a-username/Attest/actions/runs"
DRAWER_LABELS = (
    VALUE_CHANGE_LABEL,
    INTENT_UNKNOWN_LABEL,
    CONSTANT_CHANGE_LABEL,
    INTENT_STATED_LABEL,
    UNANCHORED_LABEL,
)


def _read_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def _cell(text: object) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


@dataclass
class Observation:
    """One drawer observation -- a behaviour-change verification that did not
    certify -- and where it went."""

    unit_id: str
    finding_id: str
    label: str
    reason: str
    fate: str  # one of FATES
    detail: str = ""
    rendered: str = ""


FATES = (
    "shown as a line",
    "note not written: drawer excluded by D-218 (intent stated / constant / unanchored)",
    "note not written: no head observation",
    "note not written: no probe recorded",
    "note written, filtered: anchored inside tests/",
    "note written, filtered: duplicate (path, expression)",
    "note written, filtered: contract refused the line",
    "note written, not in the lines file for an unread reason",
)


def _label_of(reason: str) -> str:
    for label in DRAWER_LABELS:
        if label in reason:
            return label
    return "(no drawer label in the reason)"


def _note_from_row(row: dict) -> ValueNote | None:
    try:
        return ValueNote(
            policy_version=str(row["policy_version"]),
            path=str(row["path"]),
            line=int(row["line"]),
            expression=str(row["expression"]),
            base_kind=str(row["base_kind"]),
            base_detail=str(row["base_detail"]),
            head_kind=str(row["head_kind"]),
            head_detail=str(row["head_detail"]),
            head_runs=int(row["head_runs"]),
            base_runs=int(row["base_runs"]),
            pinned_values=tuple(str(v) for v in row["pinned_values"]),
            specified_by=tuple((str(a), str(b)) for a, b in row["specified_by"]),
            drawer_reason=str(row["drawer_reason"]),
            candidate_id=str(row["candidate_id"]),
        )
    except (KeyError, TypeError, ValueError):
        return None


@dataclass
class RunData:
    name: str
    run_id: str
    study: str
    trials: list[dict]
    lines: dict[str, dict]
    ledgers: list[dict]
    skipped: list[dict] = field(default_factory=list)

    def rows_for(self, task_id: str) -> list[dict]:
        return [row for row in self.ledgers if row.get("task_id") == task_id]


def load_run(name: str, directory: Path, run_id: str, study: str, trials_name: str) -> RunData:
    base = directory / "benchmarks" / "studies" / study
    trials = _read_jsonl(base / trials_name)
    lines = {
        row["unit_id"]: row for row in _read_jsonl(base / f"lines-{Path(trials_name).stem}.jsonl")
    }
    ledgers: list[dict] = []
    for path in sorted((directory / ".attest" / "corpora").rglob("ledger.jsonl")):
        ledgers.extend(_read_jsonl(path))
    skipped: list[dict] = []
    log = directory / "shadow-run.log"
    if log.is_file():
        for line in log.read_text(encoding="utf-8").splitlines():
            if line.startswith("{") and '"skipped"' in line:
                try:
                    skipped.append(json.loads(line))
                except ValueError:
                    continue
    return RunData(name, run_id, study, trials, lines, ledgers, skipped)


def observations(run: RunData) -> list[Observation]:
    out: list[Observation] = []
    for trial in run.trials:
        task_id = str(trial["task_id"])
        unit_id = str(trial["unit_id"])
        rows = run.rows_for(task_id)
        notes = {str(r["finding_id"]): r for r in rows if r.get("kind") == "value_observation_note"}
        probes = {str(r["finding_id"]): r for r in rows if r.get("kind") == "probe_observation"}
        shown = {
            str(item.get("candidate_id"))
            for item in run.lines.get(unit_id, {}).get("lines", {}).get("value", [])
        }
        seen_keys: set[tuple[str, str]] = set()
        for row in rows:
            if row.get("kind") != "verification":
                continue
            if row.get("evidence_class") != "behavior_change" or row.get("outcome") == "reproduced":
                continue
            finding_id = str(row["finding_id"])
            reason = str(row.get("reason", ""))
            label = _label_of(reason)
            note_row = notes.get(finding_id)
            key = (
                (str(note_row.get("path")), str(note_row.get("expression")))
                if note_row is not None
                else None
            )
            if finding_id in shown:
                fate, detail = FATES[0], ""
            elif note_row is None:
                if not any(drawer in reason for drawer in NOTE_DRAWERS):
                    fate, detail = FATES[1], label
                elif finding_id not in probes:
                    fate, detail = FATES[3], ""
                elif not probes[finding_id].get("head_kind"):
                    fate, detail = FATES[2], "the probe was never screened on head"
                else:
                    fate, detail = (
                        FATES[3],
                        "no note row although the drawer and the head observation exist",
                    )
            else:
                note = _note_from_row(note_row)
                assert key is not None
                if note is not None and anchored_in_tests(note):
                    fate, detail = FATES[4], str(note_row.get("path"))
                elif key in seen_keys:
                    # D-222 rule (1): one note per (path, expression), the first
                    # kept -- so the second observation of the same call on the
                    # same file is the same fact, already shown once
                    fate, detail = FATES[5], f"{key[0]} / {key[1][:60]}"
                elif note is not None and not admitted(note).admitted:
                    fate, detail = FATES[6], admitted(note).reason
                else:
                    fate, detail = FATES[7], ""
            if key is not None:
                seen_keys.add(key)
            out.append(
                Observation(
                    unit_id=unit_id,
                    finding_id=finding_id,
                    label=label,
                    reason=reason,
                    fate=fate,
                    detail=detail,
                    rendered=str(note_row.get("rendered", "")) if note_row else "",
                )
            )
    return out


def _kinds(counts: dict[str, int]) -> str:
    return ", ".join(f"{k} {v}" for k, v in counts.items()) or "none"


def _behind(kind: str, item: dict) -> str:
    if kind == "red":
        return f"receipt {item.get('receipt')}, {item.get('evidence_class')}"
    if kind == "value":
        return (
            f"note {item.get('note_id')} — `{item.get('expression')}`; base {item.get('base')}; "
            f"head {item.get('head')}; {item.get('runs')}; drawer: {item.get('drawer_reason')}"
        )
    if kind == "gate":
        return (
            f"gate note {item.get('note_id')} — {item.get('exception_type')} at "
            f"{item.get('path')}:{item.get('origin_line')}, entered through `{item.get('entry')}` "
            f"at {item.get('call_site')} ({item.get('caller')}), {item.get('runs')} runs"
        )
    return f"yellow (a), {item.get('callers')} caller(s): {item.get('reason')}"


def _line_rows(run: RunData) -> list[tuple[str, str, str, str]]:
    rows = []
    for trial in run.trials:
        unit_id = str(trial["unit_id"])
        entry = run.lines.get(unit_id, {}).get("lines", {})
        for kind in ("red", "value", "gate", "impact"):
            for item in entry.get(kind, []):
                rows.append((unit_id, kind, str(item.get("line", "")), _behind(kind, item)))
    return rows


def _pr_table(run: RunData, obs: list[Observation]) -> list[str]:
    by_unit = Counter(o.unit_id for o in obs)
    out = [
        "| pull request | cand | elig | att | cert | drawers | red | value | gate | yellow (a) "
        "| units read | spend |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for trial in run.trials:
        unit_id = str(trial["unit_id"])
        entry = run.lines.get(unit_id, {}).get("lines", {})
        read = f"{trial.get('units_read')} of {trial.get('units_planned')}"
        if trial.get("budget_limited"):
            read += " (budget-limited)"
        out.append(
            f"| `{_cell(unit_id)}` | {trial.get('candidates')} | {trial.get('eligible')} | "
            f"{trial.get('attempted')} | {trial.get('certified')} | {by_unit.get(unit_id, 0)} | "
            f"{len(entry.get('red', []))} | {len(entry.get('value', []))} | "
            f"{len(entry.get('gate', []))} | {len(entry.get('impact', []))} | {read} | "
            f"${float(trial.get('spend_usd', 0.0)):.4f} |"
        )
    return out


def _summary(run: RunData, obs: list[Observation]) -> dict[str, object]:
    rows = _line_rows(run)
    units_with = {r[0] for r in rows}
    return {
        "units_run": len(run.trials),
        "units_with_a_line": len(units_with),
        "lines": len(rows),
        "lines_by_kind": dict(Counter(r[1] for r in rows)),
        "drawer_observations": len(obs),
        "fates": dict(Counter(o.fate for o in obs)),
        "spend": round(sum(float(t.get("spend_usd", 0.0)) for t in run.trials), 6),
        "candidates": sum(int(t.get("candidates", 0)) for t in run.trials),
        "eligible": sum(int(t.get("eligible", 0)) for t in run.trials),
        "attempted": sum(int(t.get("attempted", 0)) for t in run.trials),
        "certified": sum(int(t.get("certified", 0)) for t in run.trials),
    }


DEFAULT_TITLE = (
    "# Lines on real pull requests, 2026-09-12 — the owner's five and the eight "
    "libraries' twenty-four"
)
DEFAULT_INTRO = (
    "**Work order PR 3 f of the 2026-09-12 overnight window.** Two paid runs on the "
    "declared CI platform, both on the local review path — no GitHub client, nothing "
    "written to any repository — with `value_notes_visible` and `gate_notes_visible` on, "
    "`per_pr_budget_usd` $1.00, K=5, `linux-container-v1`. **This time the ledgers came "
    "back**, so every drawer observation that did not become a line is read to its "
    "reason rather than guessed at (D-225 could not)."
)


def build(
    run_a: RunData | None,
    run_b: RunData | None,
    *,
    title: str = DEFAULT_TITLE,
    intro: str = DEFAULT_INTRO,
    comparison_heading: str = "## 4. The owner's five against the libraries' twenty-four",
) -> str:
    runs = [run for run in (run_a, run_b) if run is not None]
    assert runs, "no run to report: the input is empty"
    obs = {run.name: observations(run) for run in runs}
    summaries = {run.name: _summary(run, obs[run.name]) for run in runs}
    out: list[str] = []
    out.append(title)
    out.append("")
    out.append(intro)
    out.append("")
    for run in runs:
        s = summaries[run.name]
        out.append(
            f"- **{run.name}** — run [`{run.run_id}`]({RUNS}/{run.run_id}), study `{run.study}`: "
            f"{s['units_run']} units run, {s['units_with_a_line']} with at least one line, "
            f"{s['lines']} lines ({_kinds(s['lines_by_kind'])}), "
            f"{s['drawer_observations']} drawer observations, ${s['spend']:.4f}."
        )
    out.append("")
    out.append(
        "**Wrong = 0 is the owner's to establish, not this report's.** Every line below has "
        "three empty columns."
    )
    out.append("")
    out.append("## 1. Every line, verbatim — the owner fills the last three columns")
    out.append("")
    out.append(
        "| # | run | pull request | level | the line, as it would have been shown | "
        "what stands behind it | useful | true but useless | wrong |"
    )
    out.append("|---|---|---|---|---|---|---|---|---|")
    n = 0
    for run in runs:
        for unit_id, kind, line, behind in _line_rows(run):
            n += 1
            out.append(
                f"| {n} | {run.name} | `{_cell(unit_id)}` | {kind} | {_cell(line)} | "
                f"{_cell(behind)} | | | |"
            )
    if n == 0:
        out.append("| — | — | — | — | *no line on any unit of either run* | — | | | |")
    out.append("")
    out.append("## 2. One row per pull request")
    out.append("")
    for run in runs:
        out.append(f"### {run.name}")
        out.append("")
        out.extend(_pr_table(run, obs[run.name]))
        refused = [s for s in run.skipped if s.get("skipped") == "cap"]
        unselected = [s for s in run.skipped if s.get("skipped") == "not selected"]
        other = [s for s in run.skipped if s.get("skipped") not in ("cap", "not selected")]
        out.append("")
        if refused:
            out.append(
                f"Refused by the cap, by name ({len(refused)}): "
                + ", ".join(f"`{s['unit_id']}`" for s in refused)
                + f". {refused[0].get('detail', '')}"
            )
        if unselected:
            out.append(
                f"Not selected by `--only` ({len(unselected)}): the rest of the frozen "
                "sample, recorded as such."
            )
        if other:
            out.append(
                "Skipped for another reason: "
                + "; ".join(f"`{s['unit_id']}`: {s.get('skipped')}" for s in other)
            )
        out.append("")
    out.append("## 3. Where every drawer observation went, read from the ledger")
    out.append("")
    out.append(
        "A drawer observation is a `verification` row of evidence class `behavior_change` whose "
        "outcome is not `reproduced`: the differential was real and the intent clause would not "
        "publish it. D-218 writes a value note only for the two drawers whose intent is "
        "*unreadable* (`value change confirmed, intent unknown` and `behavior change "
        "confirmed, intent unknown`); the drawer `intent stated in the change itself` means "
        "the author already said what they meant, and D-218 deliberately writes nothing for "
        "it. A written note is then shown only when "
        "it is not anchored inside `tests/`, is the first for its `(path, expression)`, and the "
        "contract admits the line (D-222)."
    )
    out.append("")
    out.append("| run | pull request | candidate | drawer | fate | detail |")
    out.append("|---|---|---|---|---|---|")
    for run in runs:
        for o in obs[run.name]:
            out.append(
                f"| {run.name} | `{_cell(o.unit_id)}` | `{o.finding_id}` | {_cell(o.label)} | "
                f"{_cell(o.fate)} | {_cell(o.detail)} |"
            )
    if not any(obs.values()):
        out.append("| — | — | — | *no drawer observation on any unit* | — | — |")
    out.append("")
    out.append("Fates, counted:")
    out.append("")
    for run in runs:
        for fate, count in sorted(summaries[run.name]["fates"].items()):  # type: ignore[union-attr]
            out.append(f"- {run.name}: **{count}** — {fate}")
    if not any(obs.values()):
        out.append("- none")
    out.append("")
    out.append(comparison_heading)
    out.append("")
    out.append("| | " + " | ".join(run.name for run in runs) + " |")
    out.append("|---|" + "---|" * len(runs))
    for key, label in (
        ("units_run", "units run"),
        ("candidates", "candidates"),
        ("eligible", "eligible"),
        ("attempted", "reproductions attempted"),
        ("certified", "certified"),
        ("drawer_observations", "drawer observations"),
        ("units_with_a_line", "pull requests with a line"),
        ("lines", "lines"),
        ("spend", "spend"),
    ):
        cells = []
        for run in runs:
            value = summaries[run.name][key]
            cells.append(f"${value:.4f}" if key == "spend" else str(value))
        out.append(f"| {label} | " + " | ".join(cells) + " |")
    out.append("")
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-a", default="")
    parser.add_argument("--run-a-id", default="")
    parser.add_argument("--run-a-trials", default="trials-runner-only5.jsonl")
    parser.add_argument("--run-a-study", default="e04-prospective-v3")
    parser.add_argument("--run-a-name", default="run A (the owner's five)")
    parser.add_argument("--run-b", default="")
    parser.add_argument("--run-b-id", default="")
    parser.add_argument("--run-b-trials", default="trials.jsonl")
    parser.add_argument("--run-b-study", default="e05-external-v1")
    parser.add_argument("--run-b-name", default="run B (eight libraries)")
    parser.add_argument("--title", default=DEFAULT_TITLE, help="the report's first line")
    parser.add_argument("--intro", default=DEFAULT_INTRO, help="the paragraph under it")
    parser.add_argument(
        "--comparison-heading", default="## 4. The owner's five against the libraries' twenty-four"
    )
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    if not args.run_a and not args.run_b:
        raise SystemExit("name at least one run directory (--run-a or --run-b)")
    run_a = (
        load_run(
            args.run_a_name, Path(args.run_a), args.run_a_id, args.run_a_study, args.run_a_trials
        )
        if args.run_a
        else None
    )
    run_b = (
        load_run(
            args.run_b_name, Path(args.run_b), args.run_b_id, args.run_b_study, args.run_b_trials
        )
        if args.run_b
        else None
    )
    text = build(
        run_a,
        run_b,
        title=args.title,
        intro=args.intro,
        comparison_heading=args.comparison_heading,
    )
    Path(args.out).write_text(text, encoding="utf-8")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
