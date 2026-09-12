"""D-235 replay: every committed ledger, re-read under the probe-hygiene rules and the
warning rule, from the files already on disk (release/probe-hygiene, 2026-09-13).

Five ledger sets -- run A (the owner's two), run B (eight libraries, 24 units), run C
(five libraries, 20 units), and the two dispatches of the mutations-v1 recall run
(forty cases) -- and for every `verification` row three questions:

    (a) would `parse_probe` now refuse the probe's setup?  The setup is read back
        from the pytest longrepr the row carries (the replay's own source, or the
        recording run's), so the imports block is not available; a name the setup
        did not bind itself is treated as import-bound, which is what it was.
    (b) is any observed exception a Warning subclass -- on head, on base, or as
        the intent observation's rejection type -- so that the differential does
        not hold?
    (c)/(d) is the rendered line changed by the address rule or the red-line
        contract fallback?  Answered by `lines_after_rules.py`, which re-renders;
        this script decides what stands and what is withdrawn.

A row whose probe is refused under (a) or whose exception is a warning under (b)
**withdraws** what it produced: an accepted receipt, or a value note.  What the
next probe would have found is not knowable offline and is not guessed.  The
mutation recall is recomputed over the same forty with the withdrawn receipt out
of the numerator; the denominator does not move.  No execution, no model, $0.00.

    .venv/bin/python scripts/acceptance/probe_hygiene_replay.py \\
        --out docs/acceptance/evidence/2026-09-13-d235-replay.json \\
        --mutation-report docs/acceptance/2026-09-13-mutation-recall.md
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "corpus"))

from heldout_v2 import wilson  # noqa: E402
from mutation_recall import REPOSITORIES, classify  # noqa: E402

from attest.certification.intent import is_warning_type  # noqa: E402
from attest.review.probe import ProbeSpec, hygiene_refusal  # noqa: E402

EVIDENCE = ROOT / "docs" / "acceptance" / "evidence"
STUDIES = ROOT / "benchmarks" / "studies"
RUNS = "https://github.com/IcantFind-a-username/Attest/actions/runs"
SETS = {
    "run A (the owner's five)": {
        "ledgers": EVIDENCE / "2026-09-12-lines-on-real-prs" / "run-a",
        "study": "e04-prospective-v3",
        "trials": "trials-runner-only5.jsonl",
        "report": "2026-09-12-lines-on-real-prs.md",
    },
    "run B (eight libraries)": {
        "ledgers": EVIDENCE / "2026-09-12-lines-on-real-prs" / "run-b",
        "study": "e05-external-v1",
        "trials": "trials.jsonl",
        "report": "2026-09-12-lines-on-real-prs.md",
    },
    "run C (five libraries)": {
        "ledgers": EVIDENCE / "2026-09-13-lines-on-real-prs-batch2" / "run-c",
        "study": "e05-external-v2",
        "trials": "trials.jsonl",
        "report": "2026-09-13-lines-on-real-prs-batch2.md",
    },
    "mutations-v1-recall run 1": {
        "ledgers": EVIDENCE / "2026-09-13-mutation-recall" / "run-1",
        "study": "mutations-v1-recall",
        "trials": "trials.jsonl",
        "report": "2026-09-13-mutation-recall.md",
    },
    "mutations-v1-recall run 2": {
        "ledgers": EVIDENCE / "2026-09-13-mutation-recall" / "run-2",
        "study": "mutations-v1-recall",
        "trials": "trials.jsonl",
        "report": "2026-09-13-mutation-recall.md",
    },
}
MUTATION_SECTION = "## 1a. The same forty under D-235"
# the test function's source as pytest prints it: the def line, then the body
# indented eight spaces, up to the recorder's `try:` or the replay's call
_SOURCE = re.compile(
    r"def test_attest_(?:replay|probe)\(\):\n(?P<body>.*?)(?=\n[> ]\s*(?:try:|_attest_value =))",
    re.DOTALL,
)
_WITHDRAWN_FIELDS = ("set", "unit", "finding_id", "after", "refusal", "warning")
RULES = (
    ("warnings module", "uses the warnings module"),
    ("sys.modules", "touches sys.modules"),
    ("mock", "mocks"),
    ("attribute of an imported name", "assigns an attribute of the imported name"),
    ("recursion limit", "changes the recursion limit"),
    ("os.environ write", "writes os.environ"),
)


def _read_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def setup_from_evidence(row: dict) -> str | None:
    """The probe's setup statements, read back from the test source pytest printed
    in the longrepr of a head run or in a recording run's stdout; None when no run
    printed the source (a recording that died before pytest reported)."""
    texts = [str(row.get("evidence") or "")]
    for run in row.get("run_evidence") or ():
        texts.append(str(run.get("stdout_tail") or ""))
    for text in texts:
        match = _SOURCE.search(text)
        if match is None:
            continue
        lines = []
        for raw in match.group("body").splitlines():
            line = raw[1:] if raw.startswith(">") else raw
            lines.append(line[8:] if line.startswith("        ") else line.strip())
        return "\n".join(lines).strip("\n")
    return None


def free_roots(setup: str) -> list[str]:
    """Names the setup uses but does not bind: in a probe file those are the
    imports block's bindings (or builtins), which the ledger did not keep."""
    try:
        tree = ast.parse(setup)
    except SyntaxError:
        return []
    from attest.review.probe import _import_bindings, _local_bindings

    bound = set(_import_bindings(tree.body)) | _local_bindings(tree)
    used = {
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
    }
    import builtins

    return sorted(name for name in used - bound if not hasattr(builtins, name))


def refusal_for(setup: str, expression: str) -> str | None:
    imports = "\n".join(f"import {name}" for name in free_roots(setup))
    return hygiene_refusal(ProbeSpec(imports=imports, setup=setup, expression=expression))


def rule_of(refusal: str) -> str:
    for name, marker in RULES:
        if marker in refusal:
            return name
    return "other"


def warning_side(row: dict, probe: dict | None) -> str | None:
    """Which recorded exception is a Warning subclass, if any."""
    intent = row.get("intent") or {}
    if intent.get("new_rejection") and is_warning_type(str(intent.get("exception_type") or "")):
        return f"head raised {intent['exception_type']} on the exception's path"
    if probe is not None:
        if probe.get("head_kind") == "exception" and is_warning_type(str(probe.get("head_detail"))):
            return f"head raised {probe['head_detail']}"
        if probe.get("observed_kind") == "exception" and is_warning_type(
            str(probe.get("observed_detail"))
        ):
            return f"the merge base raised {probe['observed_detail']}"
    return None


def replay_set(name: str, spec: dict) -> list[dict]:
    rows_all: list[dict] = []
    for path in sorted(Path(spec["ledgers"]).glob("*-ledger.jsonl")):
        rows_all.extend(_read_jsonl(path))
    assert rows_all, f"{name}: no ledger rows read from {spec['ledgers']}"
    trials = _read_jsonl(STUDIES / spec["study"] / spec["trials"])
    unit_of_task = {str(t["task_id"]): str(t["unit_id"]) for t in trials}
    by_key: dict[tuple[str, str], dict] = {}
    for row in rows_all:
        key = (str(row.get("task_id")), str(row.get("finding_id")))
        kind = row.get("kind")
        if kind == "verification":
            by_key.setdefault(key, {})["verification"] = row
        elif kind == "probe_observation":
            by_key.setdefault(key, {})["probe"] = row
        elif kind == "certification" and row.get("outcome") == "accepted":
            by_key.setdefault(key, {})["certification"] = row
        elif kind == "value_observation_note":
            by_key.setdefault(key, {})["note"] = row
    out: list[dict] = []
    for (task_id, finding_id), parts in sorted(by_key.items()):
        verification = parts.get("verification")
        if verification is None:
            continue
        probe = parts.get("probe")
        setup = setup_from_evidence(verification)
        expression = str((probe or {}).get("expression") or "x")
        refusal = refusal_for(setup, expression) if setup is not None else None
        warning = warning_side(verification, probe)
        produced = (
            "receipt"
            if "certification" in parts
            else "note"
            if "note" in parts
            else "nothing author-visible"
        )
        if refusal is not None:
            after = "refused before execution (D-235 a)"
        elif warning is not None:
            after = "the differential does not hold (D-235 b)"
        else:
            after = "unchanged"
        out.append(
            {
                "set": name,
                "unit": unit_of_task.get(task_id, ""),
                "task_id": task_id,
                "finding_id": finding_id,
                "outcome": verification.get("outcome"),
                "evidence_class": verification.get("evidence_class"),
                "produced": produced,
                "receipt_digest": (parts.get("certification") or {}).get("receipt_digest", "")[:12],
                "note_id": (parts.get("note") or {}).get("note_id", ""),
                "setup_recovered": setup is not None,
                "setup": setup or "",
                "refusal": refusal or "",
                "rule": rule_of(refusal) if refusal else "",
                "warning": warning or "",
                "after": after,
                "withdrawn": after != "unchanged" and produced != "nothing author-visible",
                "runs_recorded": len(verification.get("run_evidence") or ()),
            }
        )
    return out


def mutation_after(rows: list[dict]) -> dict:
    """The forty cases again: the class each had, and the class it has now."""
    sample = _read_jsonl(STUDIES / "mutations-v1-recall" / "sample.jsonl")
    trials = {
        r["unit_id"]: r for r in _read_jsonl(STUDIES / "mutations-v1-recall" / "trials.jsonl")
    }
    ledgers: dict[str, list[dict]] = {}
    for run in ("run-1", "run-2"):
        for library in REPOSITORIES:
            path = EVIDENCE / "2026-09-13-mutation-recall" / run / f"{library}-ledger.jsonl"
            ledgers.setdefault(library, []).extend(_read_jsonl(path))
    withdrawn = {
        (r["task_id"], r["finding_id"]): r
        for r in rows
        if r["set"].startswith("mutations") and r["withdrawn"]
    }
    cases = []
    for row in sample:
        unit = str(row["unit_id"])
        trial = trials.get(unit)
        if trial is None:
            cases.append({"case": unit, "before": "not run", "after": "not run", "why": ""})
            continue
        mine = [e for e in ledgers[str(row["library"])] if e.get("task_id") == trial["task_id"]]
        before, _why = classify(mine, str(trial.get("deferred_reason") or ""))
        hits = [
            withdrawn[(str(e["task_id"]), str(e["finding_id"]))]
            for e in mine
            if e.get("kind") == "verification"
            and (str(e["task_id"]), str(e["finding_id"])) in withdrawn
        ]
        after = before
        why = ""
        if before == "certified" and any(h["produced"] == "receipt" for h in hits):
            hit = next(h for h in hits if h["produced"] == "receipt")
            certified_rows = [
                e
                for e in mine
                if e.get("kind") == "certification" and e.get("outcome") == "accepted"
            ]
            standing = [
                e
                for e in certified_rows
                if (str(e["task_id"]), str(e["finding_id"])) not in withdrawn
            ]
            after = "certified" if standing else "no receipt: withdrawn under D-235"
            why = hit["refusal"] or hit["warning"]
        elif before == "value class" and any(h["produced"] == "note" for h in hits):
            hit = next(h for h in hits if h["produced"] == "note")
            after = "no receipt: value note withdrawn under D-235"
            why = hit["refusal"] or hit["warning"]
        cases.append({"case": unit, "before": before, "after": after, "why": why})
    n = len(sample)
    before_certified = sum(1 for c in cases if c["before"] == "certified")
    after_certified = sum(1 for c in cases if c["after"] == "certified")
    low_b, high_b = wilson(before_certified, n)
    low_a, high_a = wilson(after_certified, n)
    return {
        "denominator": n,
        "certified_before": before_certified,
        "certified_after": after_certified,
        "wilson_before": [round(low_b, 4), round(high_b, 4)],
        "wilson_after": [round(low_a, 4), round(high_a, 4)],
        "changed": [c for c in cases if c["before"] != c["after"]],
        "classes_after": dict(Counter(c["after"] for c in cases)),
    }


def mutation_section(result: dict, rows: list[dict]) -> str:
    n = result["denominator"]
    lines = [MUTATION_SECTION, ""]
    lines.append(
        "**Replayed on 2026-09-13 from the committed ledgers of both dispatches, under the "
        "probe-hygiene rules and the warning rule (D-235).** A case whose certifying probe would "
        "now be refused before execution -- its setup reached for the interpreter or replaced "
        "part of the tree -- loses its receipt: what the next probe would have found cannot be "
        "known offline and is not guessed. The table in §1 is what the run showed; this is what "
        "the same ledgers say now. The denominator is forty either way."
    )
    lines.append("")
    lines.append("| | before | after D-235 |")
    lines.append("|---|---|---|")
    lines.append(
        f"| certified | **{result['certified_before']}** | **{result['certified_after']}** |"
    )
    lines.append(
        f"| point estimate | {result['certified_before'] / n:.1%} | "
        f"**{result['certified_after'] / n:.1%}** |"
    )
    lines.append(
        f"| Wilson 95% | [{result['wilson_before'][0]:.1%}, {result['wilson_before'][1]:.1%}] | "
        f"**[{result['wilson_after'][0]:.1%}, {result['wilson_after'][1]:.1%}]** |"
    )
    lines.append("")
    if result["changed"]:
        lines.append("| case | before | after | why |")
        lines.append("|---|---|---|---|")
        for c in result["changed"]:
            why = c["why"].replace("|", "\\|")
            lines.append(f"| `{c['case']}` | {c['before']} | **{c['after']}** | {why} |")
        lines.append("")
    mutation_rows = [r for r in rows if r["set"].startswith("mutations")]
    refused = [r for r in mutation_rows if r["refusal"]]
    warned = [r for r in mutation_rows if r["warning"] and not r["refusal"]]
    unread = [r for r in mutation_rows if not r["setup_recovered"]]
    by_rule = ", ".join(
        f"{k} {v}" for k, v in sorted(Counter(r["rule"] for r in refused).items())
    ) or "none"
    classes = ", ".join(
        f"{v} {k}" for k, v in sorted(result["classes_after"].items(), key=lambda kv: -kv[1])
    )
    lines.append(
        f"Over the run's **{len(mutation_rows)} verification rows**: **{len(refused)}** probes "
        f"would be refused before execution ({by_rule}), **{len(warned)}** differentials rest "
        f"on a warning, **{len(unread)}** rows carry no test source to read the setup from "
        "(recordings that died before pytest reported) and are counted as unchanged. Classes "
        f"after: {classes} ([evidence](evidence/2026-09-13-d235-replay.json))."
    )
    lines.append("")
    return "\n".join(lines) + "\n"


def splice(report: Path, section_title: str, text: str) -> None:
    body = report.read_text(encoding="utf-8")
    if section_title in body:
        head, _sep, rest = body.partition(section_title)
        _old, sep2, tail = rest.partition("\n## 2. ")
        body = head + text + sep2 + tail
    else:
        head, sep, tail = body.partition("## 2. ")
        body = head + text + sep + tail
    report.write_text(body, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    parser.add_argument("--mutation-report", default="")
    args = parser.parse_args(argv)
    rows: list[dict] = []
    for name, spec in SETS.items():
        rows.extend(replay_set(name, spec))
    assert rows, "no verification row read from any ledger: the input is empty"
    mutation = mutation_after(rows)
    refused = [r for r in rows if r["refusal"]]
    warned = [r for r in rows if r["warning"] and not r["refusal"]]
    summary = {
        "verification_rows_read": dict(Counter(r["set"] for r in rows)),
        "setup_recovered": sum(1 for r in rows if r["setup_recovered"]),
        "setup_not_recovered": sum(1 for r in rows if not r["setup_recovered"]),
        "refused_before_execution": len(refused),
        "refused_by_rule": dict(Counter(r["rule"] for r in refused)),
        "warning_differentials": len(warned),
        "receipts_withdrawn": [
            {k: r[k] for k in (*_WITHDRAWN_FIELDS, "receipt_digest")}
            for r in rows
            if r["withdrawn"] and r["produced"] == "receipt"
        ],
        "notes_withdrawn": [
            {k: r[k] for k in (*_WITHDRAWN_FIELDS, "note_id")}
            for r in rows
            if r["withdrawn"] and r["produced"] == "note"
        ],
        "mutation_recall": mutation,
    }
    Path(args.out).write_text(
        json.dumps({"summary": summary, "rows": rows}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    if args.mutation_report:
        splice(Path(args.mutation_report), MUTATION_SECTION, mutation_section(mutation, rows))
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
