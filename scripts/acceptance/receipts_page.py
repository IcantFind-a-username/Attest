"""docs/receipts.md and the README's adjudicated numbers, from the lines-on-real-PRs
reports (work order PR 3 a of the 2026-09-13 window).

Reads every `docs/acceptance/*lines-on-real-prs*.md` report: its §1 table -- one
row per author-visible line, with the three columns the owner fills by hand
(useful / true but not actionable / wrong) -- and its per-pull-request table, so
the page can say how many pull requests were reviewed and how many carried a
line. Where a report carries a §1b (the same lines re-rendered under a later
rule), §1b's lines are the ones counted and shown, with §1's adjudication
carried over by receipt or note id; a line §1b withdrew is not counted.

Writes `docs/receipts.md` -- every line verbatim, its pull request, its level,
its receipt or note id and the owner's verdict, "pending" where the columns are
still empty -- and rewrites the block between the two markers in `README.md`
with the four numbers: pull requests reviewed, pull requests with a line, lines,
and the verdict distribution. The README never carries a number a person typed.

    python scripts/acceptance/receipts_page.py
    python scripts/acceptance/receipts_page.py --check   # exit 1 if README or receipts.md is stale
"""

from __future__ import annotations

import argparse
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ACCEPTANCE = ROOT / "docs" / "acceptance"
RECEIPTS = ROOT / "docs" / "receipts.md"
README = ROOT / "README.md"
BEGIN = "<!-- receipts:begin -->"
END = "<!-- receipts:end -->"
PULL = re.compile(r"^([\w.-]+/[\w.-]+)#(\d+)$")
EVIDENCE_ID = re.compile(r"(?:receipt|note) ([0-9a-f]{12})")
LEVEL_WORDS = {
    "red": "red",
    "value": "yellow (value)",
    "impact": "yellow (a)",
    "gate": "yellow (gate)",
}
# the owner's own repositories are reviewed too (run A); they are not "open-source
# libraries this project does not own" and are counted apart in the README sentence
OWN_PREFIX = "IcantFind-a-username/"


@dataclass
class Line:
    report: str
    run: str
    pull_request: str
    level: str
    text: str
    evidence_id: str
    useful: str = ""
    true_but_useless: str = ""
    wrong: str = ""
    withdrawn: bool = False

    @property
    def verdict(self) -> str:
        marks = [(self.useful, "useful"), (self.true_but_useless, "true but not actionable"),
                 (self.wrong, "wrong")]
        chosen = [name for cell, name in marks if cell.strip()]
        if len(chosen) > 1:
            return "inconsistent: " + " and ".join(chosen)
        return chosen[0] if chosen else "pending"


@dataclass
class Report:
    path: Path
    lines: list[Line] = field(default_factory=list)
    pull_requests: set[str] = field(default_factory=set)
    with_a_line: set[str] = field(default_factory=set)


def _escape(text: str) -> str:
    return text.replace("|", "\\|")


def _cells(row: str) -> list[str]:
    body = row.strip()
    if body.startswith("|"):
        body = body[1:]
    if body.endswith("|"):
        body = body[:-1]
    # a cell may hold an escaped pipe
    parts = re.split(r"(?<!\\)\|", body)
    return [p.replace("\\|", "|").strip() for p in parts]


def _section(text: str, heading: str) -> str:
    start = text.find(heading)
    if start < 0:
        return ""
    rest = text[start + len(heading):]
    stop = re.search(r"^## ", rest, re.MULTILINE)
    return rest if stop is None else rest[: stop.start()]


def _table_rows(section: str) -> list[list[str]]:
    rows = []
    for raw in section.splitlines():
        if raw.startswith("|") and not raw.startswith("|---"):
            cells = _cells(raw)
            if cells and cells[0] not in ("#", "pull request", ""):
                rows.append(cells)
    return rows


def parse_report(path: Path) -> Report:
    text = path.read_text(encoding="utf-8")
    report = Report(path=path)
    one = _section(text, "## 1. ")
    adjudicated: list[Line] = []
    for cells in _table_rows(one):
        if len(cells) < 9 or cells[1] == "—":
            continue
        _n, run, pull, level, line_text, _behind, useful, tbu, wrong = cells[:9]
        found = EVIDENCE_ID.search(line_text) or EVIDENCE_ID.search(_behind)
        adjudicated.append(Line(
            report=path.name, run=run, pull_request=pull.strip("`"), level=level, text=line_text,
            evidence_id=found.group(1) if found else "",
            useful=useful, true_but_useless=tbu, wrong=wrong,
        ))
    by_id = {line.evidence_id: line for line in adjudicated if line.evidence_id}
    by_pull_level = {(line.pull_request, line.level, line.text): line for line in adjudicated}
    one_b = _section(text, "## 1b. ")
    if one_b:
        for cells in _table_rows(one_b):
            if len(cells) < 6:
                continue
            _n, run, pull, level, line_text, what = cells[:6]
            pull = pull.strip("`")
            withdrawn = line_text.startswith("*withdrawn*")
            after_level = level.split("→")[-1].strip() if "→" in level else level.strip()
            after_level = after_level.strip("() ")
            if after_level == "none":
                withdrawn = True
            match = EVIDENCE_ID.search(line_text)
            evidence_id = match.group(1) if match else ""
            # carry the owner's verdict across a re-rendering by id, else by text
            source = by_id.get(evidence_id) if evidence_id else None
            if source is None:
                for (p, _level, txt), candidate in by_pull_level.items():
                    if p == pull and txt.split(" — ")[0] == line_text.split(" — ")[0]:
                        source = candidate
                        break
            # a line that changed level (red → value) is adjudicated as shown now:
            # a verdict typed against the red wording does not carry to the yellow one
            carried = source if source is not None and source.level == after_level else None
            report.lines.append(Line(
                report=path.name, run=run, pull_request=pull, level=after_level, text=line_text,
                evidence_id=evidence_id, withdrawn=withdrawn,
                useful=carried.useful if carried else "",
                true_but_useless=carried.true_but_useless if carried else "",
                wrong=carried.wrong if carried else "",
            ))
    else:
        report.lines = adjudicated
    two = _section(text, "## 2. ")
    for cells in _table_rows(two):
        if len(cells) < 12:
            continue
        pull = cells[0].strip("`")
        if not PULL.match(pull):
            continue
        report.pull_requests.add(pull)
    for line in report.lines:
        if not line.withdrawn:
            report.with_a_line.add(line.pull_request)
    return report


def build(reports: list[Report]) -> tuple[str, str, dict[str, object]]:
    shown = [line for r in reports for line in r.lines if not line.withdrawn]
    every_pull = set().union(*(r.pull_requests for r in reports)) if reports else set()
    pulls = {p for p in every_pull if not p.startswith(OWN_PREFIX)}
    own = every_pull - pulls
    with_a_line = set().union(*(r.with_a_line for r in reports)) if reports else set()
    repositories = {p.split("#")[0] for p in pulls}
    verdicts = Counter(line.verdict for line in shown)
    numbers = {
        "pull_requests": len(pulls),
        "libraries": len(repositories),
        "own_pull_requests": len(own),
        "pull_requests_with_a_line": len(with_a_line),
        "lines": len(shown),
        "useful": verdicts.get("useful", 0),
        "true_but_not_actionable": verdicts.get("true but not actionable", 0),
        "wrong": verdicts.get("wrong", 0),
        "pending": verdicts.get("pending", 0),
        "inconsistent": sum(v for k, v in verdicts.items() if k.startswith("inconsistent")),
    }
    page = [
        "# Every line attest has said on a real pull request, and what the owner made of it",
        "",
    ]
    page.append(
        f"**{numbers['pull_requests']} merged pull requests of {numbers['libraries']} "
        f"open-source Python libraries reviewed; {numbers['pull_requests_with_a_line']} carried a "
        f"line; {numbers['lines']} lines in all.** The owner adjudicated each by hand: "
        f"**{numbers['useful']} useful, {numbers['true_but_not_actionable']} true but not "
        f"actionable, {numbers['wrong']} wrong**"
        + (f", **{numbers['pending']} pending**" if numbers["pending"] else "")
        + (
            f", {numbers['inconsistent']} marked in two columns at once"
            if numbers["inconsistent"]
            else ""
        )
        + "."
        + (
            f" {numbers['own_pull_requests']} pull requests of the owner's own repositories were "
            "reviewed in the same runs and are not in these counts."
            if numbers["own_pull_requests"]
            else ""
        )
    )
    page.append("")
    page.append(
        "Generated by `scripts/acceptance/receipts_page.py` from the §1 tables of the dated "
        "reports under `docs/acceptance/` -- every line verbatim as it was (or would have been) "
        "shown, its pull request, its level, its receipt or note id, and the verdict the owner "
        "wrote in the report's own three columns. Nothing here was typed into this page. A "
        "report that carries a §1b (the same lines under a later rule) contributes §1b's lines; "
        "a line §1b withdrew is listed at the end and counted nowhere. A verdict typed against "
        "a red line does not carry to the yellow line the same receipt became."
    )
    page.append("")
    page.append(
        "| # | pull request | level | the line | receipt / note | owner's verdict | report |"
    )
    page.append("|---|---|---|---|---|---|---|")
    for n, line in enumerate(shown, 1):
        repo, number = line.pull_request.split("#")
        url = f"https://github.com/{repo}/pull/{number}"
        text = _escape(line.text)
        level = LEVEL_WORDS.get(line.level, line.level)
        page.append(
            f"| {n} | [`{line.pull_request}`]({url}) | {level} | {text} | "
            f"`{line.evidence_id or '—'}` | **{line.verdict}** | "
            f"[{line.report}](acceptance/{line.report}) |"
        )
    withdrawn = [line for r in reports for line in r.lines if line.withdrawn]
    if withdrawn:
        page.append("")
        page.append("## Withdrawn under a later rule, counted nowhere")
        page.append("")
        page.append("| pull request | level | the line as it was | report |")
        page.append("|---|---|---|---|")
        for line in withdrawn:
            page.append(
                f"| `{line.pull_request}` | {LEVEL_WORDS.get(line.level, line.level)} | "
                f"{_escape(line.text)} | [{line.report}](acceptance/{line.report}) |"
            )
    page.append("")
    page.append("## Reports read")
    page.append("")
    for r in reports:
        counted = len([x for x in r.lines if not x.withdrawn])
        page.append(
            f"- [{r.path.name}](acceptance/{r.path.name}) — {len(r.pull_requests)} pull "
            f"requests, {counted} lines"
        )
    page.append("")
    readme_block = (
        f"{BEGIN}\n"
        f"On **{numbers['pull_requests']} merged pull requests** of "
        f"**{numbers['libraries']} open-source Python libraries**, attest said "
        f"**{numbers['lines']} lines** on {numbers['pull_requests_with_a_line']} of them; the "
        f"owner adjudicated each by hand: **{numbers['useful']} useful, "
        f"{numbers['true_but_not_actionable']} true but not actionable, {numbers['wrong']} wrong**"
        + (f", **{numbers['pending']} pending adjudication**" if numbers["pending"] else "")
        + ". Every line and its receipt: [`docs/receipts.md`](docs/receipts.md). "
        "*(These numbers are written by `scripts/acceptance/receipts_page.py` from the "
        "reports' own adjudication columns; nothing here is typed.)*\n"
        f"{END}"
    )
    return "\n".join(page) + "\n", readme_block, numbers


def splice_readme(text: str, block: str) -> str:
    start, end = text.find(BEGIN), text.find(END)
    if start < 0 or end < 0:
        raise SystemExit("README.md carries no receipts markers")
    return text[:start] + block + text[end + len(END):]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    paths = sorted(ACCEPTANCE.glob("*lines-on-real-prs*.md"))
    assert paths, "no lines-on-real-prs report under docs/acceptance: the input is empty"
    reports = [parse_report(p) for p in paths]
    assert any(r.lines for r in reports), "no line parsed from any report: the input is empty"
    page, block, numbers = build(reports)
    readme = splice_readme(README.read_text(encoding="utf-8"), block)
    if args.check:
        stale = []
        if RECEIPTS.read_text(encoding="utf-8") != page:
            stale.append(str(RECEIPTS))
        if README.read_text(encoding="utf-8") != readme:
            stale.append(str(README))
        print("stale: " + ", ".join(stale) if stale else "up to date")
        return 1 if stale else 0
    RECEIPTS.write_text(page, encoding="utf-8")
    README.write_text(readme, encoding="utf-8")
    print(numbers)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
