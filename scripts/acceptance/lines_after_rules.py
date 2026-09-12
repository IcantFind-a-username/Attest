"""The 2026-09-12 lines, re-rendered under D-232, D-233 and D-234 (work order PR 1 e).

Reads the same artifacts `lines_on_real_prs.py` read -- run A's and run B's
trials, lines files and ledgers, now committed under
`docs/acceptance/evidence/2026-09-12-lines-on-real-prs/` -- plus the D-232
replay, and writes the table of what each of the six lines becomes:

- a red line whose receipt the frame rule moves to the drawer becomes, under
  D-218, a value note when the probe recorded a head observation; the note is
  built from the ledger's `probe_observation` and `history_signal` rows exactly
  as `verify_candidate` would build it, and rendered under D-234;
- a value line is re-rendered under D-234 from its ledger row;
- a yellow (a) line is recomputed from the two trees of the local read-only
  clone at the unit's head, under D-233;
- gate lines are unchanged (none were shown).

Appends a section to the dated report rather than rewriting §1: the original
table is the record of what the run showed. Free: no model, no execution.

    .venv/bin/python scripts/acceptance/lines_after_rules.py \\
        --replay docs/acceptance/evidence/2026-09-13-d232-replay.json \\
        --report docs/acceptance/2026-09-12-lines-on-real-prs.md
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "acceptance"))

from lines_on_real_prs import RunData, _cell, _note_from_row, load_run  # noqa: E402

from attest.certification.intent import (  # noqa: E402
    INTENT_UNKNOWN_LABEL,
    INTENT_UNKNOWN_LABEL_ZH,
    IntentObservation,
)
from attest.github.presentation import YELLOW_MAX_COMMENTS, impact_line  # noqa: E402
from attest.review.ci import impact_notes  # noqa: E402
from attest.review.value_note import (  # noqa: E402
    ValueNote,
    note_from,
    render,
    visible,
)

EVIDENCE = ROOT / "docs" / "acceptance" / "evidence" / "2026-09-12-lines-on-real-prs"
STUDIES = ROOT / "benchmarks" / "studies"
CORPORA = ROOT / ".attest" / "corpora"
SECTION = "## 1b. The same lines under D-232, D-233 and D-234"


def _read_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def _clone(repository: str, run_name: str) -> Path:
    name = repository.split("/")[-1].lower().lstrip("-")
    return (CORPORA / "gnull" / name) if "eight" in run_name else (CORPORA / name)


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)


def _intent_from_row(raw: dict) -> IntentObservation:
    record = dict(raw)
    record["changed_lines"] = tuple(record.get("changed_lines", ()))
    record["rejected_inputs"] = tuple(record.get("rejected_inputs", ()))
    record["witnesses"] = tuple((str(a), str(b)) for a, b in record.get("witnesses", ()))
    for key in ("value_specified", "value_respecified"):
        record[key] = tuple((str(a), str(b)) for a, b in record.get(key, ()))
    for key in (
        "pinned_values",
        "asserted_constants",
        "anchored_symbols",
        "path_lines",
        "added_lines",
    ):
        if key in record:
            record[key] = tuple(record[key])
    record["intent_evidence"] = tuple(
        (str(a), str(b)) for a, b in record.get("intent_evidence", ())
    )
    return IntentObservation(**record)


def moved_note(rows: list[dict], verification: dict, replay_row: dict) -> ValueNote | None:
    """The value note D-218 would write for a receipt D-232 moves to the drawer,
    built the way `verify_candidate` builds it from the same ledger rows."""
    finding_id = str(verification["finding_id"])
    probe = next(
        (
            r
            for r in rows
            if r.get("kind") == "probe_observation" and r.get("finding_id") == finding_id
        ),
        None,
    )
    signal = next(
        (
            r
            for r in rows
            if r.get("kind") == "history_signal" and r.get("finding_id") == finding_id
        ),
        None,
    )
    if probe is None or signal is None:
        return None
    intent = _intent_from_row(verification["intent"])
    reason = f"intent: {INTENT_UNKNOWN_LABEL}: {replay_row['why']} ({INTENT_UNKNOWN_LABEL_ZH})"
    return note_from(
        intent=intent,
        expression=str(probe.get("expression", "")),
        base_kind=str(probe.get("observed_kind", "")),
        base_detail=str(probe.get("observed_detail", "")),
        head_kind=str(probe.get("head_kind", "")),
        head_detail=str(probe.get("head_detail", "")),
        head_runs=len(verification.get("head_runs", [])) or 3,
        base_runs=len(verification.get("base_runs", [])) or 3,
        reason=reason,
        candidate_id=finding_id,
        anchor_line=int(signal.get("line", 0) or 0),
    )


def after_lines(run: RunData, replay: dict, samples: dict[str, dict]) -> list[dict]:
    moved = {(r["unit"], r["finding_id"]): r for r in replay["rows"] if r["after"] == "moved"}
    out: list[dict] = []
    for trial in run.trials:
        unit_id = str(trial["unit_id"])
        task_id = str(trial["task_id"])
        rows = run.rows_for(task_id)
        entry = run.lines.get(unit_id, {}).get("lines", {})
        certified = {
            str(r["finding_id"])
            for r in rows
            if r.get("kind") == "certification" and r.get("outcome") == "accepted"
        }
        # red: every certified receipt the frame rule does not move
        for item in entry.get("red", []):
            key = (unit_id, str(item.get("candidate_id")))
            if key in moved:
                continue
            out.append(
                {
                    "unit": unit_id,
                    "level": "red",
                    "before": item["line"],
                    "after": item["line"],
                    "what": "unchanged",
                }
            )
        # value: the notes the ledger holds, plus one for every moved receipt
        notes: list[ValueNote] = []
        for r in rows:
            if r.get("kind") == "value_observation_note":
                note = _note_from_row(r)
                if note is not None:
                    notes.append(note)
        for r in rows:
            if r.get("kind") != "verification" or r.get("outcome") != "reproduced":
                continue
            key = (unit_id, str(r["finding_id"]))
            if key in moved and str(r["finding_id"]) in certified:
                note = moved_note(rows, r, moved[key])
                if note is not None:
                    notes.append(note)
        shown_before = {
            str(item.get("candidate_id")): item["line"] for item in entry.get("value", [])
        }
        # D-233 first: yellow (a) recomputed at the unit's head in the local clone
        impact_after: list[str] = []
        sample = samples.get(unit_id)
        if sample is not None:
            repo = _clone(str(sample["repository"]), run.name)
            if (repo / ".git").is_dir():
                was = _git(repo, "rev-parse", "HEAD").stdout.strip()
                if (
                    _git(repo, "checkout", "-q", "--detach", str(sample["head_sha"])).returncode
                    == 0
                ):
                    try:
                        impact_after = [
                            impact_line(n)
                            for n in impact_notes(
                                repo=repo,
                                base_sha=str(sample["base_sha"]),
                                head_sha=str(sample["head_sha"]),
                            )
                        ]
                    finally:
                        _git(repo, "checkout", "-q", "--detach", was)
        for item in entry.get("impact", []):
            out.append(
                {
                    "unit": unit_id,
                    "level": "impact",
                    "before": item["line"],
                    "after": "",
                    "what": "withdrawn by D-233: the return annotation moved and nothing else",
                }
            )
        for line in impact_after:
            out.append(
                {
                    "unit": unit_id,
                    "level": "impact",
                    "before": "",
                    "after": line,
                    "what": "new under D-233",
                }
            )
        # the value lines share yellow's cap of two after (a), as run_ci applies it
        room = max(0, YELLOW_MAX_COMMENTS - len(impact_after))
        for note in visible(notes)[:room]:
            before = shown_before.get(note.candidate_id, "")
            if (unit_id, note.candidate_id) in moved:
                red_line = next(
                    (
                        i["line"]
                        for i in entry.get("red", [])
                        if str(i.get("candidate_id")) == note.candidate_id
                    ),
                    "",
                )
                out.append(
                    {
                        "unit": unit_id,
                        "level": "value",
                        "before": red_line,
                        "after": render(note),
                        "what": (
                            "was red; D-232 moves the receipt to the drawer and D-218 "
                            "writes the note"
                        ),
                    }
                )
            else:
                out.append(
                    {
                        "unit": unit_id,
                        "level": "value",
                        "before": before,
                        "after": render(note),
                        "what": "re-rendered under D-234"
                        if before != render(note)
                        else "unchanged",
                    }
                )
        for item in entry.get("gate", []):
            out.append(
                {
                    "unit": unit_id,
                    "level": "gate",
                    "before": item["line"],
                    "after": item["line"],
                    "what": "unchanged",
                }
            )
    return out


def section(rows_a: list[dict], rows_b: list[dict], replay: dict) -> str:
    before_kinds = Counter()
    after_kinds = Counter()
    lines = [SECTION, ""]
    lines.append(
        "**Replayed 2026-09-13 from the committed ledgers, under the three rules that "
        "followed the owner's reading of the six lines above.** D-232 reads a new rejection "
        "off the exception's *frame* rather than the statement that raised it, so a builtin "
        "raising on a line the change wrote is a behaviour change with unknown intent -- the "
        "drawer, and under D-218 a value line -- not a red receipt; D-233 withdraws yellow (a) "
        "where only a return annotation moved; D-234 renders a container value by the first "
        "element that differs. The table in §1 is what the run showed and stays as it is; "
        "this is what the same ledgers say now. Nothing was re-executed and no model was called."
    )
    lines.append("")
    lines.append(
        "| # | run | pull request | level before → after | "
        "the line, as it would be shown now | what moved it |"
    )
    lines.append("|---|---|---|---|---|---|")
    n = 0
    for name, rows in (("run A (the owner's five)", rows_a), ("run B (eight libraries)", rows_b)):
        for r in rows:
            n += 1
            if r["before"]:
                before_kinds[
                    r["level"]
                    if r["what"] == "unchanged" or "re-rendered" in r["what"]
                    else ("red" if "was red" in r["what"] else r["level"])
                ] += 1
            if r["after"]:
                after_kinds[r["level"]] += 1
            level = (
                "red → value"
                if "was red" in r["what"]
                else f"{r['level']} → (none)"
                if not r["after"]
                else f"(none) → {r['level']}"
                if not r["before"]
                else r["level"]
            )
            shown = r["after"] or f"*withdrawn* — was: {r['before']}"
            cells = f"`{_cell(r['unit'])}` | {level} | {_cell(shown)} | {_cell(r['what'])}"
            lines.append(
                f"| {n} | {name} | {cells} |"
            )
    lines.append("")
    total_after = sum(after_kinds.values())
    lines.append(
        f"**Before: {sum(before_kinds.values())} lines** "
        f"({', '.join(f'{k} {v}' for k, v in sorted(before_kinds.items())) or 'none'}). "
        f"**After: {total_after} lines** "
        f"({', '.join(f'{k} {v}' for k, v in sorted(after_kinds.items())) or 'none'}). "
        f"The D-232 replay itself: {replay['summary']['reproduced_rows']} reproduced rows over "
        f"{sum(replay['summary']['verification_rows_read'].values())} verification rows, "
        f"{replay['summary']['moved_to_the_drawer']} moved to the drawer "
        f"(both `python-attrs/attrs#1603`), {replay['summary']['kept_as_regression']} kept, "
        f"{replay['summary']['unchanged']} unchanged "
        f"([evidence](evidence/2026-09-13-d232-replay.json))."
    )
    lines.append("")
    lines.append(
        "The three empty columns of §1 are still the owner's; a line that changed level "
        "here is adjudicated as it is shown now, and a withdrawn line is not adjudicated at all."
    )
    lines.append("")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replay", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--out-json", default="")
    args = parser.parse_args(argv)
    replay = json.loads(Path(args.replay).read_text(encoding="utf-8"))
    assert replay["rows"], "the replay carries no reproduced row: the input is empty"
    run_a = load_run(
        "run A (the owner's five)",
        EVIDENCE / "run-a",
        "34646556092",
        "e04-prospective-v3",
        "trials-runner-only5.jsonl",
    )
    run_b = load_run(
        "run B (eight libraries)",
        EVIDENCE / "run-b",
        "34650336318",
        "e05-external-v1",
        "trials.jsonl",
    )
    # the committed evidence directories hold only ledgers; trials and lines
    # files live in the study directories
    for run, study, trials, directory in (
        (run_a, "e04-prospective-v3", "trials-runner-only5.jsonl", EVIDENCE / "run-a"),
        (run_b, "e05-external-v1", "trials.jsonl", EVIDENCE / "run-b"),
    ):
        base = STUDIES / study
        run.trials = _read_jsonl(base / trials)
        run.lines = {
            row["unit_id"]: row for row in _read_jsonl(base / f"lines-{Path(trials).stem}.jsonl")
        }
        # the committed evidence keeps one ledger per clone as <name>-ledger.jsonl
        run.ledgers = [
            row for path in sorted(directory.glob("*-ledger.jsonl")) for row in _read_jsonl(path)
        ]
    assert run_a.trials and run_b.trials and run_b.ledgers, "no trials or ledgers read"
    samples_a = {
        r["unit_id"]: r for r in _read_jsonl(STUDIES / "e04-prospective-v3" / "sample.jsonl")
    }
    samples_b = {r["unit_id"]: r for r in _read_jsonl(STUDIES / "e05-external-v1" / "sample.jsonl")}
    rows_a = after_lines(run_a, replay, samples_a)
    rows_b = after_lines(run_b, replay, samples_b)
    text = section(rows_a, rows_b, replay)
    report = Path(args.report)
    body = report.read_text(encoding="utf-8")
    if SECTION in body:
        head, _sep, rest = body.partition(SECTION)
        _old, _sep2, tail = rest.partition("\n## 2. ")
        body = head + text + "\n## 2. " + tail
    else:
        head, sep, tail = body.partition("## 2. ")
        body = head + text + sep + tail
    report.write_text(body, encoding="utf-8")
    if args.out_json:
        Path(args.out_json).write_text(
            json.dumps({"run_a": rows_a, "run_b": rows_b}, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
