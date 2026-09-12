"""The lines on real pull requests, re-rendered under the rules that followed the runs:
D-232, D-233, D-234 (work order PR 1 e) and D-235 (release/probe-hygiene).

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

D-235 adds, from `probe_hygiene_replay.py`'s evidence: a red line or a value
line whose probe would now be refused before execution, or whose differential
rests on a warning escalated to an exception, is **withdrawn** -- nothing stands
in its place, because what the next probe would have found is not knowable
offline; a surviving value line is re-rendered with object addresses dropped
(D-235 c); a surviving red line whose model claim does not pass the contract is
re-rendered with the receipt's own sentence, as `run_ci` would have shown it
(D-235 d).

Appends a section to the dated report rather than rewriting §1: the original
table is the record of what the run showed. Free: no model, no execution.

    .venv/bin/python scripts/acceptance/lines_after_rules.py --run ab \\
        --replay docs/acceptance/evidence/2026-09-13-d232-replay.json \\
        --hygiene docs/acceptance/evidence/2026-09-13-d235-replay.json \\
        --report docs/acceptance/2026-09-12-lines-on-real-prs.md
    .venv/bin/python scripts/acceptance/lines_after_rules.py --run c \\
        --replay docs/acceptance/evidence/2026-09-13-d232-replay.json \\
        --hygiene docs/acceptance/evidence/2026-09-13-d235-replay.json \\
        --report docs/acceptance/2026-09-13-lines-on-real-prs-batch2.md
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
from attest.review.output_contract import check, claim_line, receipt_sentence  # noqa: E402
from attest.review.value_note import (  # noqa: E402
    ValueNote,
    note_from,
    render,
    visible,
)

EVIDENCE = ROOT / "docs" / "acceptance" / "evidence" / "2026-09-12-lines-on-real-prs"
EVIDENCE_C = ROOT / "docs" / "acceptance" / "evidence" / "2026-09-13-lines-on-real-prs-batch2"
STUDIES = ROOT / "benchmarks" / "studies"
CORPORA = ROOT / ".attest" / "corpora"
SECTION_AB = "## 1b. The same lines under D-232, D-233, D-234 and D-235"
SECTION_C = "## 1b. The same lines under D-235"
# the heading this script wrote before D-235, replaced in place
OLD_SECTION_AB = "## 1b. The same lines under D-232, D-233 and D-234"
REPLAY_TEST_NODE = ".attest-repro/test_repro.py::test_attest_replay"
_RED = re.compile(
    r"^\[red\] (?P<path>\S+):(?P<line>\d+) — (?P<fact>.*) — receipt (?P<digest>[0-9a-f]{12})$"
)


def _read_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def _clone(repository: str, run_name: str) -> Path:
    name = repository.split("/")[-1].lower().lstrip("-")
    if "eight" in run_name:
        return CORPORA / "gnull" / name
    if "five" in run_name:
        return CORPORA / "e05v2" / name
    return CORPORA / name


def withdrawn_under_d235(hygiene: dict | None) -> dict[tuple[str, str], str]:
    """(unit, finding id) -> why, for every receipt or note D-235 withdraws."""
    if hygiene is None:
        return {}
    out: dict[tuple[str, str], str] = {}
    for row in hygiene["rows"]:
        if not row.get("withdrawn"):
            continue
        why = row.get("refusal") or row.get("warning") or row["after"]
        rule = "a" if row.get("refusal") else "b"
        out[(str(row["unit"]), str(row["finding_id"]))] = f"withdrawn under D-235 ({rule}): {why}"
    return out


def red_as_shown(line: str, verification: dict | None, evidence_class: str) -> str | None:
    """D-235 (d): the red line `run_ci` would have published. None when the line
    already passes the contract; otherwise the same coordinates and receipt with
    the receipt's own sentence in place of the model's claim."""
    if check(line):
        return None
    match = _RED.match(line)
    if match is None:
        return None
    label = "behavior change (intent to confirm): " if evidence_class == "behavior_change" else ""
    runs = verification or {}
    return claim_line(
        "red",
        path=match.group("path"),
        line=int(match.group("line")),
        fact=label
        + receipt_sentence(
            test_node=REPLAY_TEST_NODE,
            head_runs=len(runs.get("head_runs") or ()) or 3,
            base_runs=len(runs.get("base_runs") or ()) or 3,
        ),
        evidence=f"receipt {match.group('digest')}",
    )


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
        imports=str(probe.get("imports", "")),
        setup=str(probe.get("setup", "")),
    )


def after_lines(
    run: RunData,
    replay: dict,
    samples: dict[str, dict],
    withdrawn: dict[tuple[str, str], str] | None = None,
) -> list[dict]:
    moved = {(r["unit"], r["finding_id"]): r for r in replay["rows"] if r["after"] == "moved"}
    withdrawn = withdrawn or {}
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
        verifications = {
            str(r["finding_id"]): r for r in rows if r.get("kind") == "verification"
        }
        # red: every certified receipt the frame rule does not move and D-235
        # does not withdraw; a surviving claim over the contract is shown as
        # `run_ci` shows it (D-235 d)
        for item in entry.get("red", []):
            key = (unit_id, str(item.get("candidate_id")))
            if key in moved:
                continue
            if key in withdrawn:
                out.append(
                    {
                        "unit": unit_id,
                        "level": "red",
                        "before": item["line"],
                        "after": "",
                        "what": withdrawn[key],
                    }
                )
                continue
            shown = red_as_shown(
                item["line"], verifications.get(key[1]), str(item.get("evidence_class", ""))
            )
            out.append(
                {
                    "unit": unit_id,
                    "level": "red",
                    "before": item["line"],
                    "after": shown or item["line"],
                    "what": "unchanged"
                    if shown is None
                    else "re-rendered under D-235 (d): the model claim did not pass the "
                    "contract, so the receipt's own sentence is shown, as run_ci shows it",
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
        # D-235: a note whose probe is refused or whose differential rests on a
        # warning is withdrawn before the cap is applied
        for note in list(notes):
            key = (unit_id, note.candidate_id)
            if key in withdrawn:
                notes.remove(note)
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
                        "before": shown_before.get(note.candidate_id, red_line),
                        "after": "",
                        "what": withdrawn[key],
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
                        "what": _rerender_reason(before, render(note)),
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


def _rerender_reason(before: str, after: str) -> str:
    if before == after:
        return "unchanged"
    if " at 0x" in before and " at 0x" not in after:
        return "re-rendered under D-235 (c): the object address is dropped"
    return "re-rendered under D-234"


INTRO_AB = (
    "**Replayed 2026-09-13 from the committed ledgers, under the rules that followed the "
    "owner's reading of the six lines above.** D-232 reads a new rejection off the exception's "
    "*frame* rather than the statement that raised it, so a builtin raising on a line the change "
    "wrote is a behaviour change with unknown intent -- the drawer, and under D-218 a value line "
    "-- not a red receipt; D-233 withdraws yellow (a) where only a return annotation moved; D-234 "
    "renders a container value by the first element that differs; D-235 withdraws a line whose "
    "probe would now be refused before execution (a setup that reached for `warnings`, "
    "`sys.modules`, a mock, the environment, or assigned an attribute of an imported name) or "
    "whose differential rests on a warning escalated to an exception, drops object addresses "
    "from a rendered value, and shows a red line whose claim did not pass the contract as "
    "`run_ci` shows it. The table in §1 is what the run showed and stays as it is; this is what "
    "the same ledgers say now. Nothing was re-executed and no model was called."
)
INTRO_C = (
    "**Replayed 2026-09-13 from the committed ledgers, under D-235 -- the rules D-232, D-233 and "
    "D-234 were already in force for this run.** A line whose probe would now be refused before "
    "execution (a setup that reached for `warnings`, `sys.modules`, a mock, the environment, or "
    "assigned an attribute of an imported name), or whose differential rests on a warning "
    "escalated to an exception, is withdrawn: what the next probe would have found is not "
    "knowable offline and nothing stands in its place. A surviving value line drops object "
    "addresses; a surviving red line whose model claim did not pass the contract is shown as "
    "`run_ci` shows it, with the receipt's own sentence. The table in §1 is what the run showed "
    "and stays as it is; this is what the same ledgers say now. Nothing was re-executed and no "
    "model was called."
)


def section(
    named_rows: list[tuple[str, list[dict]]],
    replay: dict,
    *,
    heading: str,
    intro: str,
    hygiene: dict | None,
) -> str:
    before_kinds = Counter()
    after_kinds = Counter()
    lines = [heading, ""]
    lines.append(intro)
    lines.append("")
    lines.append(
        "| # | run | pull request | level before → after | "
        "the line, as it would be shown now | what moved it |"
    )
    lines.append("|---|---|---|---|---|---|")
    n = 0
    for name, rows in named_rows:
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
    withdrawn_here = sum(
        1 for _name, rows in named_rows for r in rows if "D-235" in r["what"] and not r["after"]
    )
    summary = (
        f"**Before: {sum(before_kinds.values())} lines** "
        f"({', '.join(f'{k} {v}' for k, v in sorted(before_kinds.items())) or 'none'}). "
        f"**After: {total_after} lines** "
        f"({', '.join(f'{k} {v}' for k, v in sorted(after_kinds.items())) or 'none'}). "
    )
    if heading == SECTION_AB:
        summary += (
            f"The D-232 replay itself: {replay['summary']['reproduced_rows']} reproduced rows over "
            f"{sum(replay['summary']['verification_rows_read'].values())} verification rows, "
            f"{replay['summary']['moved_to_the_drawer']} moved to the drawer "
            f"(both `python-attrs/attrs#1603`), {replay['summary']['kept_as_regression']} kept, "
            f"{replay['summary']['unchanged']} unchanged "
            f"([evidence](evidence/2026-09-13-d232-replay.json)). "
        )
    if hygiene is not None:
        h = hygiene["summary"]
        units = {name for name, _rows in named_rows}
        mine = [r for r in hygiene["rows"] if r["set"] in units]
        refused = [r for r in mine if r["refusal"]]
        warned = [r for r in mine if r["warning"] and not r["refusal"]]
        unread = [r for r in mine if not r["setup_recovered"]]
        summary += (
            f"The D-235 replay on these runs: {len(mine)} verification rows, "
            f"{len(refused)} probes that would now be refused before execution"
            + (
                " ("
                + ", ".join(
                    f"{k} {v}" for k, v in sorted(Counter(r["rule"] for r in refused).items())
                )
                + ")"
                if refused
                else ""
            )
            + f", {len(warned)} further differentials resting on a warning, {len(unread)} rows "
            f"with no test source to read the setup from (counted as unchanged); "
            f"**{withdrawn_here} lines withdrawn here** "
            f"([evidence](evidence/2026-09-13-d235-replay.json); all runs: "
            f"{len(h['receipts_withdrawn'])} receipts and {len(h['notes_withdrawn'])} notes "
            "withdrawn)."
        )
    lines.append(summary)
    lines.append("")
    lines.append(
        "The three empty columns of §1 are still the owner's; a line that changed level "
        "here is adjudicated as it is shown now, and a withdrawn line is not adjudicated at all."
    )
    lines.append("")
    return "\n".join(lines) + "\n"


def _load(run: RunData, study: str, trials: str, directory: Path) -> None:
    # the committed evidence directories hold only ledgers; trials and lines
    # files live in the study directories
    base = STUDIES / study
    run.trials = _read_jsonl(base / trials)
    run.lines = {
        row["unit_id"]: row for row in _read_jsonl(base / f"lines-{Path(trials).stem}.jsonl")
    }
    # the committed evidence keeps one ledger per clone as <name>-ledger.jsonl
    run.ledgers = [
        row for path in sorted(directory.glob("*-ledger.jsonl")) for row in _read_jsonl(path)
    ]


def _splice(report: Path, heading: str, text: str, *, replacing: tuple[str, ...] = ()) -> None:
    body = report.read_text(encoding="utf-8")
    for old_heading in (heading, *replacing):
        if old_heading in body:
            head, _sep, rest = body.partition(old_heading)
            _old, _sep2, tail = rest.partition("\n## 2. ")
            body = head + text + "\n## 2. " + tail
            break
    else:
        head, sep, tail = body.partition("## 2. ")
        body = head + text + sep + tail
    report.write_text(body, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replay", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--hygiene", default="", help="probe_hygiene_replay.py's evidence (D-235)")
    parser.add_argument("--run", choices=("ab", "c"), default="ab")
    parser.add_argument("--out-json", default="")
    args = parser.parse_args(argv)
    replay = json.loads(Path(args.replay).read_text(encoding="utf-8"))
    assert replay["rows"], "the replay carries no reproduced row: the input is empty"
    hygiene = json.loads(Path(args.hygiene).read_text(encoding="utf-8")) if args.hygiene else None
    if hygiene is not None:
        assert hygiene["rows"], "the hygiene replay carries no row: the input is empty"
    withdrawn = withdrawn_under_d235(hygiene)
    if args.run == "c":
        run_c = load_run(
            "run C (five libraries)",
            EVIDENCE_C / "run-c",
            "34660287636",
            "e05-external-v2",
            "trials.jsonl",
        )
        _load(run_c, "e05-external-v2", "trials.jsonl", EVIDENCE_C / "run-c")
        assert run_c.trials and run_c.ledgers, "no trials or ledgers read"
        samples_c = {
            r["unit_id"]: r for r in _read_jsonl(STUDIES / "e05-external-v2" / "sample.jsonl")
        }
        rows_c = after_lines(run_c, replay, samples_c, withdrawn)
        text = section(
            [("run C (five libraries)", rows_c)],
            replay,
            heading=SECTION_C,
            intro=INTRO_C,
            hygiene=hygiene,
        )
        _splice(Path(args.report), SECTION_C, text)
        if args.out_json:
            Path(args.out_json).write_text(
                json.dumps({"run_c": rows_c}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )
        print(text)
        return 0
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
    _load(run_a, "e04-prospective-v3", "trials-runner-only5.jsonl", EVIDENCE / "run-a")
    _load(run_b, "e05-external-v1", "trials.jsonl", EVIDENCE / "run-b")
    assert run_a.trials and run_b.trials and run_b.ledgers, "no trials or ledgers read"
    samples_a = {
        r["unit_id"]: r for r in _read_jsonl(STUDIES / "e04-prospective-v3" / "sample.jsonl")
    }
    samples_b = {r["unit_id"]: r for r in _read_jsonl(STUDIES / "e05-external-v1" / "sample.jsonl")}
    rows_a = after_lines(run_a, replay, samples_a, withdrawn)
    rows_b = after_lines(run_b, replay, samples_b, withdrawn)
    text = section(
        [("run A (the owner's five)", rows_a), ("run B (eight libraries)", rows_b)],
        replay,
        heading=SECTION_AB,
        intro=INTRO_AB,
        hygiene=hygiene,
    )
    _splice(Path(args.report), SECTION_AB, text, replacing=(OLD_SECTION_AB,))
    if args.out_json:
        Path(args.out_json).write_text(
            json.dumps({"run_a": rows_a, "run_b": rows_b}, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
